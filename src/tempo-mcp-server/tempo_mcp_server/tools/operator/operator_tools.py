"""Tempo Operator CRD management tools.

Provides lifecycle management for TempoStack and TempoMonolithic custom
resources via the Tempo Operator (tempo.grafana.com/v1alpha1).
"""

from typing import Any, Dict, List, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions.custom import (
    TempoOperationError,
    TempoValidationError,
)
from tempo_mcp_server.tools.base import BaseTool

_VALID_KINDS = {"TempoStack", "TempoMonolithic"}
_VALID_STORAGE_TYPES = {"s3", "gcs", "azure", "pv"}


class OperatorTools(BaseTool):
    """Tempo Operator CRD lifecycle management tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Tempo Operator CRs",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_list_operator_crs(
            namespace: Optional[str] = Field(
                default=None,
                description=(
                    "Filter to a specific namespace. "
                    "If omitted, lists across all namespaces."
                ),
            ),
            kind: Optional[str] = Field(
                default=None,
                description=(
                    "Filter by CRD kind: 'TempoStack' or 'TempoMonolithic'. "
                    "If omitted, lists both kinds."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List Tempo Operator custom resources (TempoStack, TempoMonolithic).

            Scans the cluster for Tempo Operator CRDs and returns a summary
            of each instance. Read-only.

            Returns:
            - {"items": [{"name": str, "namespace": str, "kind": str, ...}], "total": int}

            When NOT to use: For Tempo HTTP API backends, use tempo_list_backends.

            Prerequisites: Tempo Operator must be installed and K8S_ENABLED=true.
            """
            try:
                if ctx:
                    await ctx.info("Listing Tempo Operator CRs...")
                if kind and kind not in _VALID_KINDS:
                    raise TempoValidationError(
                        f"Invalid kind: '{kind}'. Supported: {sorted(_VALID_KINDS)}"
                    )

                crs = await kubernetes_service.list_tempo_operator_crs(
                    namespace=namespace, kind=kind
                )

                items = []
                for cr in crs:
                    meta = cr.get("metadata", {})
                    spec = cr.get("spec", {})
                    status = cr.get("status", {})
                    conditions = status.get("conditions", [])

                    # Determine readiness from conditions
                    ready = None
                    status_phase = None
                    for cond in conditions:
                        if cond.get("type") == "Ready":
                            ready = cond.get("status") == "True"
                            status_phase = "Ready" if ready else "NotReady"
                            break

                    # Extract storage type
                    storage = spec.get("storage", {})
                    storage_type = (
                        storage.get("secret", {}).get("type")
                        or storage.get("tls", {}).get("type")
                        or None
                    )

                    # Extract retention
                    retention = spec.get("retention", {})
                    global_retention = retention.get("global", {}).get("traces")

                    items.append({
                        "name": meta.get("name", ""),
                        "namespace": meta.get("namespace", ""),
                        "kind": cr.get("_kind", cr.get("kind", "unknown")),
                        "storage_type": storage_type,
                        "retention": global_retention,
                        "status_phase": status_phase,
                        "ready": ready,
                    })

                return {"items": items, "total": len(items)}

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                raise TempoOperationError(
                    f"Failed to list Tempo Operator CRs: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Tempo Operator CR",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_operator_cr(
            namespace: str = Field(
                ..., min_length=1, description="Kubernetes namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="CR name"
            ),
            kind: str = Field(
                ...,
                description="CRD kind: 'TempoStack' or 'TempoMonolithic'",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get a Tempo Operator CR with full spec, status, and conditions.

            Returns the complete CRD including storage config, retention
            settings, resource sizing, and operator status. Read-only.

            Returns:
            - {"name": str, "namespace": str, "kind": str, "spec": {...},
               "status": {...}, "conditions": [...]}

            When NOT to use: For listing multiple CRs, use
            tempo_list_operator_crs.

            Common errors:
            - Not found: Verify namespace and name with tempo_list_operator_crs.
            """
            try:
                if ctx:
                    await ctx.info(
                        f"Fetching {kind} '{namespace}/{name}'..."
                    )
                if kind not in _VALID_KINDS:
                    raise TempoValidationError(
                        f"Invalid kind: '{kind}'. Supported: {sorted(_VALID_KINDS)}"
                    )

                cr = await kubernetes_service.get_tempo_operator_cr(
                    namespace=namespace, name=name, kind=kind
                )

                meta = cr.get("metadata", {})
                status = cr.get("status", {})

                return {
                    "name": meta.get("name", ""),
                    "namespace": meta.get("namespace", ""),
                    "kind": kind,
                    "api_version": cr.get("apiVersion", ""),
                    "labels": meta.get("labels", {}),
                    "spec": cr.get("spec", {}),
                    "status": status,
                    "conditions": status.get("conditions", []),
                }

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                raise TempoOperationError(
                    f"Failed to get Tempo Operator CR '{namespace}/{name}': {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create Tempo Operator CR",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_create_operator_cr(
            namespace: str = Field(
                ..., min_length=1, description="Target Kubernetes namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="CR name"
            ),
            kind: str = Field(
                ...,
                description="CRD kind: 'TempoStack' or 'TempoMonolithic'",
            ),
            storage_type: str = Field(
                ...,
                description="Storage backend: 's3', 'gcs', 'azure', or 'pv'",
            ),
            storage_secret: str = Field(
                ...,
                min_length=1,
                description=(
                    "Name of the K8s Secret containing storage credentials"
                ),
            ),
            retention: str = Field(
                default="48h",
                description="Global trace retention duration (e.g. '48h', '7d')",
            ),
            resources_total: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Total resource limits. Example: "
                    "{'limits': {'memory': '2Gi', 'cpu': '1000m'}}"
                ),
            ),
            multi_tenancy: bool = Field(
                default=False,
                description="Enable multi-tenancy mode",
            ),
            search_defaults: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Search configuration. Example: "
                    "{'defaultResultLimit': 20, 'maxResultLimit': 100}"
                ),
            ),
            jaeger_ui: bool = Field(
                default=True,
                description="Enable Jaeger query frontend UI",
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, returns the generated YAML without applying. "
                    "Set False only after reviewing the dry_run output."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Create a Tempo Operator CR (TempoStack or TempoMonolithic).

            Generates a complete CRD manifest with storage, retention,
            resources, and optional search/tenancy configuration.

            **WARNING: With dry_run=False, this creates a Kubernetes CRD
            that deploys Tempo pods in the target namespace.**

            Returns:
            - {"action": str, "dry_run": bool, "name": str,
               "manifest_yaml": str, "message": str}

            When NOT to use: For modifying an existing CR, use
            tempo_patch_operator_cr.

            Prerequisites: Tempo Operator must be installed.

            Common errors:
            - Secret not found: Ensure the storage secret exists in the namespace.
            - Invalid storage_type: Must be 's3', 'gcs', 'azure', or 'pv'.
            """
            try:
                if ctx:
                    await ctx.info(
                        f"{'Previewing' if dry_run else 'Creating'} {kind} "
                        f"'{name}' in namespace '{namespace}'..."
                    )
                if kind not in _VALID_KINDS:
                    raise TempoValidationError(
                        f"Invalid kind: '{kind}'. Supported: {sorted(_VALID_KINDS)}"
                    )
                if storage_type not in _VALID_STORAGE_TYPES:
                    raise TempoValidationError(
                        f"Invalid storage_type: '{storage_type}'. "
                        f"Supported: {sorted(_VALID_STORAGE_TYPES)}"
                    )

                # Build spec
                spec: Dict[str, Any] = {
                    "storage": {
                        "secret": {
                            "name": storage_secret,
                            "type": storage_type,
                        },
                    },
                    "retention": {
                        "global": {
                            "traces": retention,
                        },
                    },
                }

                if resources_total:
                    spec["resources"] = {"total": resources_total}

                if search_defaults:
                    spec["search"] = search_defaults

                if multi_tenancy:
                    spec["tenants"] = {"mode": "openshift"}

                if jaeger_ui:
                    spec["template"] = {
                        "queryFrontend": {
                            "jaegerQuery": {"enabled": True},
                        },
                    }

                labels = {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "app.kubernetes.io/part-of": "tempo",
                }

                # Build preview manifest
                op_cfg = self.config.tempo_operator
                preview = {
                    "apiVersion": f"{op_cfg.crd_group}/{op_cfg.crd_api_version}",
                    "kind": kind,
                    "metadata": {
                        "name": name,
                        "namespace": namespace,
                        "labels": labels,
                    },
                    "spec": spec,
                }
                manifest_yaml = yaml.dump(
                    preview, default_flow_style=False, sort_keys=False
                )

                if dry_run:
                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "name": name,
                        "namespace": namespace,
                        "kind": kind,
                        "manifest_yaml": manifest_yaml,
                        "message": (
                            "🔍 Review the generated manifest above. "
                            "Set dry_run=False to apply to the cluster."
                        ),
                    }

                # Apply to cluster
                result = await kubernetes_service.create_or_patch_tempo_cr(
                    namespace=namespace,
                    name=name,
                    kind=kind,
                    spec=spec,
                    labels=labels,
                    dry_run=False,
                )

                return {
                    "action": "created",
                    "dry_run": False,
                    "name": name,
                    "namespace": namespace,
                    "kind": kind,
                    "uid": result.get("metadata", {}).get("uid"),
                    "resource_version": result.get("metadata", {}).get(
                        "resourceVersion"
                    ),
                    "message": (
                        f"✅ {kind} '{name}' created in namespace "
                        f"'{namespace}'. The Tempo Operator will begin "
                        "reconciling shortly."
                    ),
                }

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                raise TempoOperationError(
                    f"Failed to create Tempo Operator CR: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Patch Tempo Operator CR",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_patch_operator_cr(
            namespace: str = Field(
                ..., min_length=1, description="Kubernetes namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="CR name"
            ),
            kind: str = Field(
                ...,
                description="CRD kind: 'TempoStack' or 'TempoMonolithic'",
            ),
            retention: Optional[str] = Field(
                default=None,
                description="New global trace retention (e.g. '48h', '7d')",
            ),
            resources_total: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "New total resource limits. Example: "
                    "{'limits': {'memory': '4Gi', 'cpu': '2000m'}}"
                ),
            ),
            search_defaults: Optional[Dict[str, Any]] = Field(
                default=None,
                description="New search configuration",
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, returns the patch without applying. "
                    "Set False only after review."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Patch specific fields of an existing Tempo Operator CR.

            Applies a strategic merge patch — only the fields you specify
            are updated; all other fields remain unchanged.

            **WARNING: With dry_run=False, this modifies a live Tempo CR
            which may trigger the operator to restart components.**

            Returns:
            - {"action": str, "dry_run": bool, "patch_spec": {...},
               "message": str}

            When NOT to use: For creating a new CR, use
            tempo_create_operator_cr.

            Common errors:
            - CR not found: Verify it exists with tempo_get_operator_cr.
            - No fields to patch: Provide at least one of retention,
              resources_total, or search_defaults.
            """
            try:
                if ctx:
                    await ctx.info(
                        f"{'Previewing patch for' if dry_run else 'Patching'} "
                        f"{kind} '{namespace}/{name}'..."
                    )
                if kind not in _VALID_KINDS:
                    raise TempoValidationError(
                        f"Invalid kind: '{kind}'. Supported: {sorted(_VALID_KINDS)}"
                    )

                # Build patch spec
                patch_spec: Dict[str, Any] = {}

                if retention is not None:
                    patch_spec["retention"] = {
                        "global": {"traces": retention}
                    }

                if resources_total is not None:
                    patch_spec["resources"] = {"total": resources_total}

                if search_defaults is not None:
                    patch_spec["search"] = search_defaults

                if not patch_spec:
                    raise TempoValidationError(
                        "No fields to patch. Provide at least one of: "
                        "retention, resources_total, search_defaults."
                    )

                if dry_run:
                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "name": name,
                        "namespace": namespace,
                        "kind": kind,
                        "patch_spec": patch_spec,
                        "message": (
                            "🔍 Review the patch above. "
                            "Set dry_run=False to apply."
                        ),
                    }

                result = await kubernetes_service.create_or_patch_tempo_cr(
                    namespace=namespace,
                    name=name,
                    kind=kind,
                    spec=patch_spec,
                    overwrite=False,
                    dry_run=False,
                )

                return {
                    "action": "patched",
                    "dry_run": False,
                    "name": name,
                    "namespace": namespace,
                    "kind": kind,
                    "patch_spec": patch_spec,
                    "resource_version": result.get("metadata", {}).get(
                        "resourceVersion"
                    ),
                    "message": (
                        f"✅ {kind} '{name}' patched. The Tempo Operator "
                        "will reconcile the changes."
                    ),
                }

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                raise TempoOperationError(
                    f"Failed to patch Tempo Operator CR: {e}"
                )
