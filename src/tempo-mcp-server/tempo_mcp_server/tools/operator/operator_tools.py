"""Write-gated Tempo Operator CRD and per-tenant overrides mutation tools."""

import copy
from typing import Any, Dict, Optional, Union

import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field
from pydantic.fields import FieldInfo

from tempo_mcp_server.exceptions.custom import (
    TempoOperationError,
    TempoValidationError,
)
from tempo_mcp_server.tools.base import BaseTool, confirm_destructive_action
from tempo_mcp_server.utils.redaction import compute_unified_diff


def _rfc7386_merge(target: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply RFC 7386 JSON Merge Patch to a copy of target for preview diffing."""
    result = copy.deepcopy(target) if isinstance(target, dict) else {}
    for k, v in patch.items():
        if v is None:
            result.pop(k, None)
        elif isinstance(v, dict):
            result[k] = _rfc7386_merge(result.get(k, {}), v)
        else:
            result[k] = copy.deepcopy(v)
    return result


class OperatorTools(BaseTool):
    """Write-gated Tempo per-tenant overrides and Tempo Operator CRD apply tools."""

    def register(self, mcp_instance: Any) -> None:
        tempo_service = self.tempo_service
        kubernetes_service = self.kubernetes_service

        if self.should_register_tool("overrides", is_write=True):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Patch Tempo Tenant Overrides",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            async def tempo_patch_tenant_overrides(
                backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
                tenant: str = Field(..., min_length=1, description="Target tenant ID (X-Scope-OrgID)"),
                merge_patch: Dict[str, Any] = Field(
                    ...,
                    description="RFC 7386 JSON merge patch for /api/overrides",
                ),
                expected_etag: Optional[str] = Field(
                    default=None,
                    description="Optional If-Match ETag from tempo://overrides/{backend_id}/{tenant}",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Preview merged overrides and unified diff without mutating Tempo",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True to confirm mutation when client lacks interactive elicitation",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Preview or apply an RFC 7386 JSON merge patch to Tempo's /api/overrides endpoint for a tenant.

                Returns: {"action": str, "dry_run": bool, "tenant": str, "etag": str|null, "diff": str, "merged_preview": {...}}.
                When NOT to use: To read current overrides, read resource 'tempo://overrides/{backend_id}/{tenant}'.
                """
                self.require_write_access("tempo_patch_tenant_overrides")
                if isinstance(expected_etag, FieldInfo):
                    expected_etag = expected_etag.default
                if isinstance(dry_run, FieldInfo):
                    dry_run = dry_run.default
                if isinstance(confirm, FieldInfo):
                    confirm = confirm.default

                if not isinstance(merge_patch, dict) or not merge_patch:
                    raise TempoValidationError("merge_patch must be a non-empty dictionary.")

                try:
                    current_data = await tempo_service.get_tenant_overrides(
                        backend_id=backend_id,
                        tenant=tenant,
                        scope="api",
                    )
                    current_overrides = current_data.get("overrides") or {}
                    current_etag = expected_etag or current_data.get("etag")
                except Exception:
                    current_overrides = {}
                    current_etag = expected_etag

                merged_preview = _rfc7386_merge(current_overrides, merge_patch)
                diff_text = compute_unified_diff(
                    current_overrides,
                    merged_preview,
                    fromfile=f"overrides/{tenant} (current)",
                    tofile=f"overrides/{tenant} (desired)",
                )

                if dry_run:
                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "backend_id": backend_id,
                        "tenant": tenant,
                        "etag": current_etag,
                        "diff": diff_text,
                        "merged_preview": merged_preview,
                    }

                confirmed = await confirm_destructive_action(
                    ctx,
                    f"Patch Tempo overrides for tenant '{tenant}' on backend '{backend_id}'",
                    confirm=confirm,
                )
                if not confirmed:
                    return {
                        "action": "aborted",
                        "dry_run": False,
                        "backend_id": backend_id,
                        "tenant": tenant,
                        "diff": diff_text,
                        "message": "Operation cancelled or confirmation not granted. Re-run with dry_run=True or confirm=True.",
                    }

                try:
                    applied = await tempo_service.patch_tenant_overrides(
                        backend_id=backend_id,
                        tenant=tenant,
                        merge_patch=merge_patch,
                        expected_etag=current_etag,
                    )
                    return {
                        "action": "patched",
                        "dry_run": False,
                        "backend_id": backend_id,
                        "tenant": tenant,
                        "etag": applied.get("etag"),
                        "diff": diff_text,
                        "overrides": applied.get("overrides"),
                    }
                except Exception as e:
                    self.handle_error(e, "tempo_patch_tenant_overrides", backend_id=backend_id, resource_name=tenant)
                    raise

        if self.should_register_tool("operator", is_write=True):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Apply Tempo Operator CR Manifest",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            async def tempo_apply_operator_cr(
                manifest: Union[str, Dict[str, Any]] = Field(
                    ...,
                    description="Complete TempoStack or TempoMonolithic manifest as YAML string or dict",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Validate via Kubernetes API server dryRun=All and return unified diff without persisting",
                ),
                field_manager: str = Field(
                    default="talkops-tempo-mcp",
                    description="Kubernetes fieldManager label",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True to confirm cluster apply when client lacks interactive elicitation",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Validate and apply a TempoStack or TempoMonolithic custom resource manifest.

                Returns: {"action": str, "dry_run": bool, "name": str, "namespace": str, "kind": str, "diff": str, "manifest_yaml": str}.
                When NOT to use: To inspect existing CRs, read 'tempo://operator/crs/{namespace}' or 'tempo://operator/manifests/{kind}/{namespace}/{name}'.
                """
                self.require_write_access("tempo_apply_operator_cr")
                if isinstance(dry_run, FieldInfo):
                    dry_run = dry_run.default
                if isinstance(field_manager, FieldInfo):
                    field_manager = field_manager.default
                if isinstance(confirm, FieldInfo):
                    confirm = confirm.default

                if isinstance(manifest, str):
                    try:
                        parsed_manifest = yaml.safe_load(manifest)
                    except Exception as e:
                        raise TempoValidationError(f"Invalid YAML manifest: {e}") from e
                elif isinstance(manifest, dict):
                    parsed_manifest = manifest
                else:
                    raise TempoValidationError("manifest must be a YAML string or dict.")

                if not isinstance(parsed_manifest, dict):
                    raise TempoValidationError("manifest must parse to a mapping object.")

                kind = parsed_manifest.get("kind", "")
                meta = parsed_manifest.get("metadata") or {}
                name = meta.get("name", "<unknown>")
                namespace = meta.get("namespace", "default")

                try:
                    if dry_run:
                        if ctx:
                            await ctx.info(f"Running server-side dry-run for {kind} '{namespace}/{name}'...")
                        return await kubernetes_service.apply_tempo_cr_manifest(
                            manifest=parsed_manifest,
                            dry_run=True,
                            field_manager=field_manager,
                        )

                    confirmed = await confirm_destructive_action(
                        ctx,
                        f"Apply {kind} '{name}' in namespace '{namespace}'",
                        confirm=confirm,
                    )
                    if not confirmed:
                        preview = await kubernetes_service.apply_tempo_cr_manifest(
                            manifest=parsed_manifest,
                            dry_run=True,
                            field_manager=field_manager,
                        )
                        preview["action"] = "aborted"
                        preview["dry_run"] = False
                        preview["message"] = (
                            "Operation cancelled or confirmation not granted. "
                            "Review the diff and pass confirm=True after operator approval."
                        )
                        return preview

                    if ctx:
                        await ctx.info(f"Applying {kind} '{namespace}/{name}'...")
                    return await kubernetes_service.apply_tempo_cr_manifest(
                        manifest=parsed_manifest,
                        dry_run=False,
                        field_manager=field_manager,
                    )
                except (ValueError, TempoValidationError) as e:
                    raise TempoValidationError(str(e)) from e
                except TempoOperationError:
                    raise
                except Exception as e:
                    self.handle_error(
                        e,
                        "tempo_apply_operator_cr",
                        namespace=namespace,
                        resource_name=name,
                    )
                    raise
