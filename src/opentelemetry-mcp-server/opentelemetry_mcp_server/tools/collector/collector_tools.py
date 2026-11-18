"""OpenTelemetryCollector CRD patch and custom resource deletion tools.

Provides ``otel_patch_collector`` (with pre-apply linting, unified diff,
GitOps guard, and secret redaction) and ``otel_delete_resource`` (with
MCP elicitation / confirmation gate).
"""

import difflib
from typing import Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from opentelemetry_mcp_server.models.findings import Finding, FindingSeverity
from opentelemetry_mcp_server.services.config_linter import lint_collector_config
from opentelemetry_mcp_server.tools.base import (
    BaseTool,
    confirm_destructive_action,
)
from opentelemetry_mcp_server.utils.gitops import (
    build_gitops_finding,
    detect_gitops_ownership,
)
from opentelemetry_mcp_server.utils.redaction import (
    redact_collector_config,
    sanitize_k8s_manifest,
)
from opentelemetry_mcp_server.utils.yaml_helpers import (
    config_to_yaml,
    safe_load_yaml,
)

_VALID_MODES = {"daemonset", "deployment", "statefulset", "sidecar"}


class CollectorTools(BaseTool):
    """OpenTelemetryCollector CRD patch and resource deletion tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("collector", is_write=True):
            return

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create or Patch OpenTelemetryCollector CRD",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_patch_collector(
            namespace: str = Field(
                ..., min_length=1, description="Target Kubernetes namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CR name"
            ),
            config_yaml: str = Field(
                ...,
                min_length=1,
                description=(
                    "Full OpenTelemetry Collector YAML config string containing "
                    "receivers, processors, exporters, connectors, and service.pipelines"
                ),
            ),
            workload_options: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Optional CRD workload spec options dict supporting keys: "
                    "'mode' ('daemonset'|'deployment'|'statefulset'|'sidecar'), "
                    "'replicas', 'image', 'service_account', 'labels', 'annotations', "
                    "'resources', 'env', 'volumes', 'volume_mounts', 'target_allocator'"
                ),
            ),
            overwrite: bool = Field(
                default=False,
                description="If True, replaces existing CR entirely; if False, patches",
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, lints config, computes unified diff, and returns preview "
                    "without applying. Set False after reviewing."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description=(
                    "Set True to confirm full overwrite or mutating a GitOps-managed CR "
                    "when dry_run=False"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Create or patch an OpenTelemetryCollector CRD with pre-apply validation.

            Runs the collector configuration linter before applying changes, blocks
            invalid configs (severity='error'), generates a unified diff against the
            existing configuration, detects Argo CD / Flux / Helm GitOps ownership,
            and redacts inline secrets in all outputs.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_patch_collector")

                w_opts = dict(workload_options or {})

                # Inspect existing collector if present
                existing_cr: Optional[Dict[str, Any]] = None
                existing_cfg_yaml = ""
                try:
                    existing_cr = await kubernetes_service.get_otel_collector(
                        namespace, name
                    )
                    try:
                        existing_cfg = (
                            collector_config_service.parse_collector_config(
                                existing_cr
                            )
                        )
                        existing_cfg_yaml = config_to_yaml(
                            redact_collector_config(existing_cfg)
                        )
                    except Exception:
                        existing_cfg_yaml = ""
                except OtelResourceNotFoundError:
                    existing_cr = None

                existing_spec = (existing_cr or {}).get("spec", {}) or {}
                mode_raw = (
                    w_opts.get("mode")
                    or existing_spec.get("mode")
                    or "deployment"
                )
                mode_lower = str(mode_raw).lower().strip()
                if mode_lower not in _VALID_MODES:
                    raise OtelValidationError(
                        f"Invalid mode: '{mode_raw}'. Supported: {sorted(_VALID_MODES)}"
                    )

                parsed_config = safe_load_yaml(config_yaml)
                if "service" not in parsed_config:
                    raise OtelValidationError(
                        "Collector config must contain a 'service' section "
                        "with at least one pipeline."
                    )
                pipelines = (
                    parsed_config.get("service", {}) or {}
                ).get("pipelines", {})
                if not pipelines:
                    raise OtelValidationError(
                        "Collector config must define at least one pipeline "
                        "under service.pipelines."
                    )

                replicas = w_opts.get(
                    "replicas", existing_spec.get("replicas")
                )
                image = w_opts.get("image")
                service_account = w_opts.get("service_account")
                labels = w_opts.get("labels")
                annotations = w_opts.get("annotations")
                resources = w_opts.get("resources")
                env = w_opts.get("env", existing_spec.get("env"))
                volumes = w_opts.get("volumes", existing_spec.get("volumes"))
                volume_mounts = w_opts.get(
                    "volume_mounts", existing_spec.get("volumeMounts")
                )
                target_allocator = w_opts.get("target_allocator")

                effective_cr_spec = dict(existing_spec)
                if target_allocator is not None:
                    effective_cr_spec["targetAllocator"] = target_allocator
                if env is not None:
                    effective_cr_spec["env"] = env
                if volumes is not None:
                    effective_cr_spec["volumes"] = volumes

                # Run config linter before apply
                findings: List[Finding] = lint_collector_config(
                    parsed_config,
                    mode=mode_lower,
                    replicas=int(replicas or 1),
                    cr_spec=effective_cr_spec,
                    env_vars=env,
                    volumes=volumes,
                )

                gitops_info = {"managed": False}
                if existing_cr:
                    gitops_info = detect_gitops_ownership(
                        existing_cr.get("metadata")
                    )
                    gitops_finding = build_gitops_finding(
                        name, namespace, gitops_info
                    )
                    if gitops_finding:
                        findings.append(gitops_finding)

                error_findings = [
                    f for f in findings if f.severity == FindingSeverity.ERROR
                ]
                is_valid = len(error_findings) == 0

                if not dry_run and not is_valid:
                    summary_codes = ", ".join(
                        f"{f.code.value}: {f.message}" for f in error_findings
                    )
                    raise OtelValidationError(
                        f"Collector configuration failed validation with {len(error_findings)} "
                        f"error(s): {summary_codes}"
                    )

                if not dry_run and (
                    overwrite or gitops_info.get("managed")
                ):
                    reason = (
                        f"Overwrite OpenTelemetryCollector '{namespace}/{name}'"
                        if overwrite
                        else f"Patch GitOps-managed OpenTelemetryCollector '{namespace}/{name}'"
                    )
                    confirmed = await confirm_destructive_action(
                        ctx, reason, confirm=confirm
                    )
                    if not confirmed:
                        return {
                            "action": "confirmation_required",
                            "dry_run": False,
                            "namespace": namespace,
                            "name": name,
                            "valid": is_valid,
                            "findings": [f.model_dump() for f in findings],
                            "message": (
                                f"Confirmation required to {reason.lower()}. "
                                "Pass confirm=True to proceed."
                            ),
                        }

                spec: Dict[str, Any] = {
                    "mode": mode_lower,
                    "config": parsed_config,
                }
                if image:
                    spec["image"] = image
                if replicas is not None:
                    spec["replicas"] = replicas
                if service_account:
                    spec["serviceAccount"] = service_account
                if resources:
                    spec["resources"] = resources
                if env:
                    spec["env"] = env
                if volumes:
                    spec["volumes"] = volumes
                if volume_mounts:
                    spec["volumeMounts"] = volume_mounts
                if target_allocator:
                    spec["targetAllocator"] = target_allocator

                redacted_cfg = redact_collector_config(parsed_config)
                new_cfg_yaml = config_to_yaml(redacted_cfg)
                diff_lines = list(
                    difflib.unified_diff(
                        existing_cfg_yaml.splitlines(keepends=True),
                        new_cfg_yaml.splitlines(keepends=True),
                        fromfile=f"{namespace}/{name} (current)",
                        tofile=f"{namespace}/{name} (proposed)",
                    )
                )
                config_diff = "".join(diff_lines)

                if dry_run:
                    crd_group = self.config.otel_operator.crd_group
                    crd_version = self.config.otel_operator.crd_api_version
                    preview_manifest = sanitize_k8s_manifest({
                        "apiVersion": f"{crd_group}/{crd_version}",
                        "kind": "OpenTelemetryCollector",
                        "metadata": {
                            "name": name,
                            "namespace": namespace,
                            **({"labels": labels} if labels else {}),
                            **({"annotations": annotations} if annotations else {}),
                        },
                        "spec": {**spec, "config": redacted_cfg},
                    })

                    pipeline_summary = {}
                    for pname, pcfg in pipelines.items():
                        if isinstance(pcfg, dict):
                            pipeline_summary[pname] = {
                                "receivers": pcfg.get("receivers", []),
                                "processors": pcfg.get("processors", []),
                                "exporters": pcfg.get("exporters", []),
                            }

                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "valid": is_valid,
                        "namespace": namespace,
                        "name": name,
                        "mode": mode_lower,
                        "spec": sanitize_k8s_manifest({**spec, "config": redacted_cfg}),
                        "spec_yaml": config_to_yaml(preview_manifest),
                        "config_diff": config_diff,
                        "pipeline_summary": pipeline_summary,
                        "findings": [f.model_dump() for f in findings],
                        "message": (
                            "Dry run — review spec_yaml, config_diff, and findings. "
                            "Set dry_run=False to apply."
                        ),
                    }

                result = await kubernetes_service.create_or_patch_collector(
                    namespace=namespace,
                    name=name,
                    spec=spec,
                    labels=labels,
                    annotations=annotations,
                    overwrite=overwrite,
                    dry_run=False,
                )

                return {
                    "action": "applied",
                    "dry_run": False,
                    "valid": is_valid,
                    "namespace": namespace,
                    "name": name,
                    "mode": mode_lower,
                    "overwrite": overwrite,
                    "config_diff": config_diff,
                    "findings": [f.model_dump() for f in findings],
                    "result": {
                        "name": result.get("metadata", {}).get("name"),
                        "namespace": result.get("metadata", {}).get("namespace"),
                        "uid": result.get("metadata", {}).get("uid"),
                        "resource_version": result.get("metadata", {}).get(
                            "resourceVersion"
                        ),
                    },
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_patch_collector",
                    namespace=namespace,
                    resource_name=name,
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete OpenTelemetry Custom Resource",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_delete_resource(
            kind: Literal[
                "OpenTelemetryCollector",
                "Instrumentation",
                "TargetAllocator",
                "OpAMPBridge",
            ] = Field(
                ...,
                description=(
                    "Custom Resource kind to delete: 'OpenTelemetryCollector', "
                    "'Instrumentation', 'TargetAllocator', or 'OpAMPBridge'"
                ),
            ),
            namespace: str = Field(
                ..., min_length=1, description="Target Kubernetes namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Custom Resource name"
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, verifies resource existence and previews deletion. "
                    "Set False with confirm=True to delete."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm permanent deletion when dry_run=False",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Delete an OpenTelemetry Custom Resource after confirmation.

            Supports deleting OpenTelemetryCollector, Instrumentation,
            TargetAllocator, and OpAMPBridge resources. Requires MCP elicitation
            or confirm=True when dry_run=False.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_delete_resource")

                preview = await kubernetes_service.delete_custom_resource(
                    kind=kind,
                    namespace=namespace,
                    name=name,
                    dry_run=True,
                )

                findings: List[Dict[str, Any]] = []
                gitops_info = detect_gitops_ownership(
                    preview.get("existing_metadata")
                )
                gitops_finding = build_gitops_finding(
                    name, namespace, gitops_info
                )
                if gitops_finding:
                    findings.append(gitops_finding.model_dump())

                if dry_run:
                    preview["findings"] = findings
                    preview["message"] = (
                        f"Dry run — would delete {kind} '{namespace}/{name}'. "
                        "Set dry_run=False and confirm=True to execute deletion."
                    )
                    return preview

                confirmed = await confirm_destructive_action(
                    ctx,
                    f"Delete {kind} '{namespace}/{name}'",
                    confirm=confirm,
                )
                if not confirmed:
                    return {
                        "action": "confirmation_required",
                        "kind": kind,
                        "namespace": namespace,
                        "name": name,
                        "dry_run": False,
                        "findings": findings,
                        "message": (
                            f"Deletion of {kind} '{namespace}/{name}' requires "
                            "confirmation. Pass confirm=True to proceed."
                        ),
                    }

                result = await kubernetes_service.delete_custom_resource(
                    kind=kind,
                    namespace=namespace,
                    name=name,
                    dry_run=False,
                )
                result["findings"] = findings
                result["message"] = (
                    f"Deleted {kind} '{namespace}/{name}'."
                )
                return result
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_delete_resource",
                    namespace=namespace,
                    resource_name=name,
                )
                raise
