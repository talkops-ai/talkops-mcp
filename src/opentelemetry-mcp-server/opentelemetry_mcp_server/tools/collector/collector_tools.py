"""OpenTelemetryCollector CRD create / patch tool.

Provides a write tool for creating or patching ``OpenTelemetryCollector``
Custom Resources, closing the lifecycle gap where read tools exist
(``otel_list_collectors``, ``otel_get_collector``) but no write tool was
available.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelValidationError,
)
from opentelemetry_mcp_server.tools.base import BaseTool

# Valid deployment modes per OTel Operator CRD spec
_VALID_MODES = {"daemonset", "deployment", "statefulset", "sidecar"}


class CollectorTools(BaseTool):
    """OpenTelemetryCollector CRD write tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

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
            mode: str = Field(
                ...,
                description=(
                    "Deployment mode: 'daemonset', 'deployment', "
                    "'statefulset', or 'sidecar'"
                ),
            ),
            config_yaml: str = Field(
                ...,
                min_length=1,
                description=(
                    "Full OTel Collector YAML config string containing "
                    "receivers, processors, exporters, connectors, "
                    "extensions, and service.pipelines sections"
                ),
            ),
            replicas: Optional[int] = Field(
                default=None,
                ge=1,
                description=(
                    "Number of collector replicas "
                    "(applies to deployment/statefulset modes)"
                ),
            ),
            image: Optional[str] = Field(
                default=None,
                description=(
                    "Collector container image "
                    "(e.g., 'otel/opentelemetry-collector-contrib:0.152.1'). "
                    "Omit to use the Operator's default image."
                ),
            ),
            service_account: Optional[str] = Field(
                default=None,
                description=(
                    "Kubernetes ServiceAccount name for the collector pods"
                ),
            ),
            labels: Optional[Dict[str, str]] = Field(
                default=None,
                description=(
                    "Metadata labels to apply to the CRD "
                    "(e.g., {'app.kubernetes.io/part-of': 'my-app'})"
                ),
            ),
            annotations: Optional[Dict[str, str]] = Field(
                default=None,
                description=(
                    "Metadata annotations to apply to the CRD"
                ),
            ),
            resources: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "K8s resource requests/limits for collector pods "
                    "(e.g., {'requests': {'cpu': '100m', 'memory': '256Mi'}, "
                    "'limits': {'cpu': '500m', 'memory': '512Mi'}})"
                ),
            ),
            env: Optional[List[Dict[str, str]]] = Field(
                default=None,
                description=(
                    "Environment variables for the collector container "
                    "(e.g., [{'name': 'K8S_NODE_NAME', 'valueFrom': "
                    "{'fieldRef': {'fieldPath': 'spec.nodeName'}}}])"
                ),
            ),
            volumes: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "K8s volume definitions to attach to collector pods"
                ),
            ),
            volume_mounts: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "K8s volumeMounts for the collector container"
                ),
            ),
            target_allocator: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Target Allocator configuration dict "
                    "(e.g., {'enabled': true, 'prometheusCR': "
                    "{'enabled': true, 'serviceMonitorSelector': {}}})"
                ),
            ),
            overwrite: bool = Field(
                default=False,
                description="If True, replaces existing CR entirely; if False, merges",
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, validates and returns the spec preview "
                    "without applying. Set False only after review."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Create or patch an OpenTelemetryCollector CRD.

            Use this to deploy or update an OTel Collector configuration
            via the OpenTelemetry Operator. The tool constructs a valid
            ``OpenTelemetryCollector`` custom resource from the provided
            parameters.

            **WARNING: With dry_run=False, this creates or modifies a
            Kubernetes CRD that controls collector pod deployments.
            A misconfigured collector config can break observability
            for the target namespace.**

            Returns:
            - dry_run=True: {"action": "dry_run", "spec": {...}, "spec_yaml": str, ...}
            - dry_run=False: {"action": "created"|"patched", "result": {...}}

            When NOT to use: For read-only inspection, use
            otel_get_collector or otel_list_collectors.

            Prerequisites: OTel Operator must be installed in the cluster
            with RBAC permissions for OpenTelemetryCollector CRDs.

            Common errors:
            - RBAC denied: Ensure service account has CRD write permissions.
            - Invalid config: Config YAML must be valid OTel Collector config.
            - Invalid mode: Must be 'daemonset', 'deployment', 'statefulset', or 'sidecar'.
            """
            try:
                # ── Validate mode ──
                mode_lower = mode.lower().strip()
                if mode_lower not in _VALID_MODES:
                    raise OtelValidationError(
                        f"Invalid mode: '{mode}'. "
                        f"Supported: {sorted(_VALID_MODES)}"
                    )

                # ── Validate and parse config YAML ──
                from opentelemetry_mcp_server.utils.yaml_helpers import (
                    safe_load_yaml,
                    config_to_yaml,
                )

                parsed_config = safe_load_yaml(config_yaml)

                # Validate that required sections exist
                if "service" not in parsed_config:
                    raise OtelValidationError(
                        "Collector config must contain a 'service' section "
                        "with at least one pipeline."
                    )
                pipelines = (
                    parsed_config.get("service", {}).get("pipelines", {})
                )
                if not pipelines:
                    raise OtelValidationError(
                        "Collector config must define at least one pipeline "
                        "under service.pipelines."
                    )

                # ── Build spec ──
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

                # ── Dry run: return preview ──
                if dry_run:
                    # Build a preview of the full CRD manifest
                    crd_group = self.config.otel_operator.crd_group
                    crd_version = self.config.otel_operator.crd_api_version

                    preview_manifest = {
                        "apiVersion": f"{crd_group}/{crd_version}",
                        "kind": "OpenTelemetryCollector",
                        "metadata": {
                            "name": name,
                            "namespace": namespace,
                            **({"labels": labels} if labels else {}),
                            **({"annotations": annotations} if annotations else {}),
                        },
                        "spec": spec,
                    }

                    # Summarize pipeline topology
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
                        "namespace": namespace,
                        "name": name,
                        "mode": mode_lower,
                        "spec": spec,
                        "spec_yaml": config_to_yaml(preview_manifest),
                        "pipeline_summary": pipeline_summary,
                        "message": (
                            "Dry run — review the spec_yaml above. "
                            "Set dry_run=False to apply."
                        ),
                    }

                # ── Apply ──
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
                    "namespace": namespace,
                    "name": name,
                    "mode": mode_lower,
                    "overwrite": overwrite,
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
                raise OtelOperationError(
                    f"Failed to create/patch collector: {e}"
                )
