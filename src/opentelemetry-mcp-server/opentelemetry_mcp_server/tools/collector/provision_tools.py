"""Intent-driven collector provisioning tool.

Provides ``otel_provision_collector`` — role-aware, intent-driven creation
of OpenTelemetry Collector CRDs with automatic backend discovery, two-tier
Agent/Gateway/Tail-Sampler topology support, Secret reference validation,
GOMEMLIMIT sizing, K8S_NODE_NAME downward API injection, persistent filelog
checkpoint storage, and least-privilege RBAC generation.
"""

from typing import Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from opentelemetry_mcp_server.models.findings import Finding, FindingCode
from opentelemetry_mcp_server.services.collector_config_builder import (
    CollectorConfigBuilder,
)
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
from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

_VALID_SIGNALS = {"traces", "metrics", "logs"}
_VALID_ROLES = {"agent", "gateway", "tail-sampler", "all-in-one"}

_GOMEMLIMIT_BY_MEMORY = {
    "512Mi": "400MiB",
    "1Gi": "800MiB",
    "2Gi": "1600MiB",
}


class ProvisionTools(BaseTool):
    """Intent-driven collector provisioning tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("collector", is_write=True):
            return

        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Provision OpenTelemetry Collector",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_provision_collector(
            namespace: str = Field(
                ...,
                min_length=1,
                description="Target Kubernetes namespace where the collector will be deployed",
            ),
            signals: List[str] = Field(
                ...,
                min_length=1,
                description="Telemetry signals to collect: 'traces', 'metrics', 'logs'",
            ),
            role: Literal[
                "agent", "gateway", "tail-sampler", "all-in-one"
            ] = Field(
                default="all-in-one",
                description=(
                    "Collector architectural role: 'agent' (DaemonSet node collector), "
                    "'gateway' (Deployment aggregation tier), 'tail-sampler' "
                    "(StatefulSet trace-affinity tier), or 'all-in-one'"
                ),
            ),
            name: Optional[str] = Field(
                default=None,
                description=(
                    "Collector CR name (defaults to '{namespace}-collector' or "
                    "'{namespace}-{role}')"
                ),
            ),
            exporter_targets: Optional[Dict[str, str]] = Field(
                default=None,
                description=(
                    "Per-signal backend endpoints (e.g., {'traces': 'tempo:4317', "
                    "'metrics': 'http://prometheus:9090/api/v1/write'}). "
                    "Auto-discovered from cluster Services if omitted."
                ),
            ),
            pipeline_options: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Optional pipeline & workload tuning dict supporting keys: "
                    "'mode', 'replicas', 'node_count' (int target cluster nodes for sizing), "
                    "'cluster_size' ('small' | 'medium' | 'large'), 'resources' (dict), "
                    "'scan_namespaces', 'exporter_overrides', "
                    "'enable_spanmetrics', 'enable_servicegraph', 'enable_filelog', "
                    "'prometheus_scrape', 'infrastructure_receivers' "
                    "(['kubeletstats', 'hostmetrics', 'k8s_cluster', 'k8sobjects']), "
                    "'credentials_secret_refs' ([{'env_var': str, 'secret_name': str, 'key': str}]), "
                    "'collector_version'"
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, validates, lints, and returns the generated CRD and RBAC "
                    "manifests without applying. Set False after reviewing."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description=(
                    "Set True to confirm applying collector creation or overwrite "
                    "when dry_run=False"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Provision an OpenTelemetry Collector CRD and least-privilege RBAC from intent.

            Automatically discovers backend observability services, selects deployment
            mode by role/signals, configures pull-based internal telemetry (:8888),
            sending_queue + retry_on_failure, GOMEMLIMIT, K8S_NODE_NAME downward API,
            persistent hostPath file_storage for filelog, and validates the generated
            configuration against all collector linter invariants.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_provision_collector")

                invalid = set(signals) - _VALID_SIGNALS
                if invalid:
                    raise OtelValidationError(
                        f"Invalid signals: {invalid}. Supported: {sorted(_VALID_SIGNALS)}"
                    )

                if role not in _VALID_ROLES:
                    raise OtelValidationError(
                        f"Invalid role: '{role}'. Supported: {sorted(_VALID_ROLES)}"
                    )

                if exporter_targets:
                    invalid_targets = set(exporter_targets.keys()) - _VALID_SIGNALS
                    if invalid_targets:
                        raise OtelValidationError(
                            f"Invalid keys in exporter_targets: {invalid_targets}. "
                            f"Keys must be signals: {sorted(_VALID_SIGNALS)}"
                        )

                opts = dict(pipeline_options or {})
                mode_override = opts.get("mode")
                scan_namespaces = opts.get("scan_namespaces")
                exporter_overrides = opts.get("exporter_overrides")
                enable_spanmetrics = bool(opts.get("enable_spanmetrics", False))
                enable_servicegraph = bool(opts.get("enable_servicegraph", False))
                enable_filelog = bool(
                    opts.get(
                        "enable_filelog",
                        role == "agent" and "logs" in signals,
                    )
                )
                prometheus_scrape = bool(opts.get("prometheus_scrape", False))
                infra_receivers: List[str] = list(
                    opts.get("infrastructure_receivers") or []
                )
                secret_refs: List[Dict[str, str]] = list(
                    opts.get("credentials_secret_refs") or []
                )
                collector_version = str(
                    opts.get("collector_version")
                    or self.config.collector_version_default
                )

                builder = CollectorConfigBuilder(kubernetes_service)
                default_suffix = (
                    "collector" if role == "all-in-one" else f"{role}-collector"
                )
                collector_name = name or f"{namespace}-{default_suffix}"

                findings: List[Finding] = []

                # Check if collector already exists & whether it is GitOps-managed
                try:
                    existing_cr = await kubernetes_service.get_otel_collector(
                        namespace, collector_name
                    )
                    gitops_info = detect_gitops_ownership(
                        existing_cr.get("metadata")
                    )
                    gitops_finding = build_gitops_finding(
                        collector_name, namespace, gitops_info
                    )
                    if gitops_finding:
                        findings.append(gitops_finding)
                        if not dry_run:
                            confirmed = await confirm_destructive_action(
                                ctx,
                                f"Mutate GitOps-managed collector '{namespace}/{collector_name}' "
                                f"(managed by {gitops_info.get('manager')})",
                                confirm=confirm,
                            )
                            if not confirmed:
                                return {
                                    "action": "confirmation_required",
                                    "dry_run": False,
                                    "name": collector_name,
                                    "namespace": namespace,
                                    "findings": [f.model_dump() for f in findings],
                                    "message": (
                                        f"Collector '{namespace}/{collector_name}' is managed by "
                                        f"{gitops_info.get('manager')}. Pass confirm=True to override "
                                        "live state, or commit the generated spec_yaml to Git."
                                    ),
                                }
                except OtelResourceNotFoundError:
                    pass

                # Validate referenced K8s Secrets (metadata-only check)
                env_list: List[Dict[str, Any]] = []
                for ref in secret_refs:
                    env_var = ref.get("env_var", "")
                    sec_name = ref.get("secret_name", "")
                    sec_key = ref.get("key", "")
                    if not (env_var and sec_name and sec_key):
                        raise OtelValidationError(
                            "Each item in credentials_secret_refs must include "
                            "'env_var', 'secret_name', and 'key'."
                        )
                    sec_check = await kubernetes_service.check_secret_key_exists(
                        namespace=namespace,
                        secret_name=sec_name,
                        key=sec_key,
                    )
                    if not sec_check.get("exists") or not sec_check.get("key_exists"):
                        findings.append(
                            Finding.create(
                                FindingCode.SEC_MISSING_SECRET_KEY,
                                message=(
                                    f"Referenced Secret '{sec_name}' (key '{sec_key}') "
                                    f"for env var '{env_var}' was not found in namespace '{namespace}'."
                                ),
                                field_path=f"spec.env[{env_var}]",
                                remediation=(
                                    f"Create Secret '{sec_name}' with key '{sec_key}' in "
                                    f"namespace '{namespace}' before applying the collector."
                                ),
                            )
                        )
                    env_list.append({
                        "name": env_var,
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": sec_name,
                                "key": sec_key,
                            }
                        },
                    })

                if not dry_run and any(
                    f.code == FindingCode.SEC_MISSING_SECRET_KEY for f in findings
                ):
                    raise OtelValidationError(
                        "Cannot apply collector: one or more referenced Secrets or keys do not exist."
                    )

                # Step 1: Discover cluster size (allowing target scale override via pipeline_options)
                cluster_size, node_count = await builder.discover_cluster_size()
                target_nodes = opts.get("node_count")
                size_override = str(opts.get("cluster_size") or "").strip().lower()
                if size_override in ("small", "medium", "large"):
                    cluster_size = size_override
                    if isinstance(target_nodes, int) and target_nodes > 0:
                        node_count = target_nodes
                elif isinstance(target_nodes, int) and target_nodes > 0:
                    node_count = target_nodes
                    cluster_size = (
                        "large"
                        if target_nodes > 100
                        else "medium"
                        if target_nodes >= 20
                        else "small"
                    )
                try:
                    deployments = await kubernetes_service.list_deployments(
                        namespace=namespace
                    )
                    workload_count = len(deployments)
                except Exception:
                    workload_count = 0

                # Step 2: Discover exporter targets
                if exporter_targets:
                    discovered_targets = dict(exporter_targets)
                    discovery_meta: Dict[str, Any] = {
                        "scanned_namespaces": [],
                        "existing_collectors": [],
                        "discovered_services": [],
                        "fallbacks_used": [],
                        "user_provided": True,
                    }
                else:
                    discovered_targets, discovery_meta = (
                        await builder.discover_exporter_targets(
                            namespace=namespace,
                            signals=signals,
                            scan_namespaces=scan_namespaces,
                        )
                    )

                # Step 3: Select deployment mode
                if mode_override:
                    selected_mode = str(mode_override).lower().strip()
                    mode_rationale = f"Mode '{selected_mode}' specified in pipeline_options"
                else:
                    selected_mode, mode_rationale = builder.recommend_mode(
                        signals,
                        enable_filelog,
                        prometheus_scrape,
                        role=role,
                    )

                # Step 4: Size resources & GOMEMLIMIT
                custom_resources = opts.get("resources")
                resources = (
                    dict(custom_resources)
                    if isinstance(custom_resources, dict) and custom_resources
                    else builder.recommend_resources(cluster_size)
                )
                mem_limit = (
                    (resources.get("limits") or {}).get("memory", "512Mi")
                )
                gomemlimit = _GOMEMLIMIT_BY_MEMORY.get(mem_limit, "400MiB")
                env_list.append({"name": "GOMEMLIMIT", "value": gomemlimit})

                if selected_mode == "daemonset" or "kubeletstats" in infra_receivers:
                    env_list.append({
                        "name": "K8S_NODE_NAME",
                        "valueFrom": {
                            "fieldRef": {"fieldPath": "spec.nodeName"}
                        },
                    })

                # Step 5: Build collector config
                generated_config = builder.build_config(
                    signals=signals,
                    exporter_targets=discovered_targets,
                    namespace=namespace,
                    enable_spanmetrics=enable_spanmetrics,
                    enable_filelog=enable_filelog,
                    prometheus_scrape=prometheus_scrape,
                    collector_name=collector_name,
                    exporter_overrides=exporter_overrides,
                    role=role,
                    mode=selected_mode,
                    enable_servicegraph=enable_servicegraph,
                    extra_receivers=infra_receivers,
                )

                # Step 6: Build CRD spec
                crd_group = self.config.otel_operator.crd_group
                crd_version = self.config.otel_operator.crd_api_version

                spec: Dict[str, Any] = {
                    "mode": selected_mode,
                    "image": f"otel/opentelemetry-collector-contrib:{collector_version}",
                    "config": generated_config,
                    "resources": resources,
                    "env": env_list,
                }
                if selected_mode != "daemonset" and opts.get("replicas") is not None:
                    spec["replicas"] = int(opts["replicas"])

                labels = {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "app.kubernetes.io/part-of": "opentelemetry",
                    "app.kubernetes.io/component": role,
                    "talkops.ai/provisioned": "true",
                }

                if prometheus_scrape:
                    spec["targetAllocator"] = {
                        "enabled": True,
                        "allocationStrategy": "consistent-hashing",
                        "prometheusCR": {
                            "enabled": True,
                            "serviceMonitorSelector": {},
                            "podMonitorSelector": {},
                        },
                    }

                volumes: List[Dict[str, Any]] = []
                volume_mounts: List[Dict[str, Any]] = []
                if enable_filelog:
                    volumes.extend([
                        {
                            "name": "varlogpods",
                            "hostPath": {"path": "/var/log/pods"},
                        },
                        {
                            "name": "file-storage",
                            "hostPath": {
                                "path": "/var/lib/otelcol/file_storage",
                                "type": "DirectoryOrCreate",
                            },
                        },
                    ])
                    volume_mounts.extend([
                        {
                            "name": "varlogpods",
                            "mountPath": "/var/log/pods",
                            "readOnly": True,
                        },
                        {
                            "name": "file-storage",
                            "mountPath": "/var/lib/otelcol/file_storage",
                        },
                    ])
                if "hostmetrics" in infra_receivers:
                    volumes.append({
                        "name": "hostfs",
                        "hostPath": {"path": "/"},
                    })
                    volume_mounts.append({
                        "name": "hostfs",
                        "mountPath": "/hostfs",
                        "readOnly": True,
                    })

                if volumes:
                    spec["volumes"] = volumes
                    spec["volumeMounts"] = volume_mounts

                # Step 7: Lint generated config
                lint_findings = lint_collector_config(
                    generated_config,
                    mode=selected_mode,
                    replicas=spec.get("replicas", 1) or 1,
                    cr_spec=spec,
                    env_vars=env_list,
                    volumes=volumes,
                    rbac_bound=True,
                    has_load_balancing_exporter=(role == "tail-sampler"),
                )
                findings.extend(lint_findings)

                redacted_cfg = redact_collector_config(generated_config)
                config_yaml_str = config_to_yaml(redacted_cfg)

                preview_manifest = sanitize_k8s_manifest({
                    "apiVersion": f"{crd_group}/{crd_version}",
                    "kind": "OpenTelemetryCollector",
                    "metadata": {
                        "name": collector_name,
                        "namespace": namespace,
                        "labels": labels,
                    },
                    "spec": {**spec, "config": redacted_cfg},
                })

                pipeline_summary = {}
                pipelines = generated_config.get("service", {}).get(
                    "pipelines", {}
                )
                for pname, pcfg in pipelines.items():
                    if isinstance(pcfg, dict):
                        pipeline_summary[pname] = {
                            "receivers": pcfg.get("receivers", []),
                            "processors": pcfg.get("processors", []),
                            "exporters": pcfg.get("exporters", []),
                        }

                include_k8sattr = "k8sattributes" in (
                    generated_config.get("processors") or {}
                )
                rbac_manifests = kubernetes_service.build_receiver_rbac_manifests(
                    namespace=namespace,
                    collector_name=collector_name,
                    receivers=infra_receivers,
                    include_k8sattributes=include_k8sattr,
                    target_allocator_enabled=prometheus_scrape,
                )
                rbac_yaml = config_to_yaml([
                    rbac_manifests["cluster_role"],
                    rbac_manifests["cluster_role_binding"],
                ])

                warnings = []
                recommendations = []
                for signal, target in discovered_targets.items():
                    if target == "__debug__":
                        warnings.append(
                            f"No backend found for '{signal}' — using debug exporter "
                            "(stdout only). Specify exporter_targets to route to a backend."
                        )

                if "traces" in signals and not enable_spanmetrics:
                    recommendations.append(
                        "Consider pipeline_options={'enable_spanmetrics': True} to derive "
                        "RED metrics from traces."
                    )
                if "logs" in signals and not enable_filelog and role != "gateway":
                    recommendations.append(
                        "Consider pipeline_options={'enable_filelog': True} for container "
                        "log collection via DaemonSet filelog receiver."
                    )

                if dry_run:
                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "name": collector_name,
                        "namespace": namespace,
                        "role": role,
                        "mode": selected_mode,
                        "mode_rationale": mode_rationale,
                        "cluster_context": {
                            "cluster_size": cluster_size,
                            "node_count": node_count,
                            "workload_count": workload_count,
                        },
                        "auto_discovered": discovery_meta,
                        "exporter_targets": discovered_targets,
                        "generated_config_yaml": config_yaml_str,
                        "pipeline_summary": pipeline_summary,
                        "resource_sizing": resources,
                        "spec_yaml": config_to_yaml(preview_manifest),
                        "rbac_resources": {
                            "cluster_role": rbac_manifests["cluster_role"][
                                "metadata"
                            ]["name"],
                            "service_account": f"{collector_name}-collector",
                            "rbac_yaml": rbac_yaml,
                        },
                        "findings": [f.model_dump() for f in findings],
                        "warnings": warnings,
                        "recommendations": recommendations,
                        "message": (
                            "Review the generated config and spec above. "
                            "Set dry_run=False to apply to the cluster."
                        ),
                    }

                result = await kubernetes_service.create_or_patch_collector(
                    namespace=namespace,
                    name=collector_name,
                    spec=spec,
                    labels=labels,
                    overwrite=False,
                    dry_run=False,
                )

                rbac_result = await kubernetes_service.create_receiver_rbac(
                    namespace=namespace,
                    collector_name=collector_name,
                    receivers=infra_receivers,
                    include_k8sattributes=include_k8sattr,
                    target_allocator_enabled=prometheus_scrape,
                    dry_run=False,
                )

                return {
                    "action": "applied",
                    "dry_run": False,
                    "name": collector_name,
                    "namespace": namespace,
                    "role": role,
                    "mode": selected_mode,
                    "mode_rationale": mode_rationale,
                    "cluster_context": {
                        "cluster_size": cluster_size,
                        "node_count": node_count,
                        "workload_count": workload_count,
                    },
                    "auto_discovered": discovery_meta,
                    "exporter_targets": discovered_targets,
                    "pipeline_summary": pipeline_summary,
                    "resource_sizing": resources,
                    "result": {
                        "name": result.get("metadata", {}).get("name"),
                        "namespace": result.get("metadata", {}).get("namespace"),
                        "uid": result.get("metadata", {}).get("uid"),
                        "resource_version": result.get("metadata", {}).get(
                            "resourceVersion"
                        ),
                    },
                    "rbac_result": rbac_result,
                    "findings": [f.model_dump() for f in findings],
                    "warnings": warnings,
                    "recommendations": recommendations,
                    "message": (
                        f"Collector '{collector_name}' provisioned in namespace "
                        f"'{namespace}' with least-privilege RBAC."
                    ),
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_provision_collector",
                    namespace=namespace,
                    resource_name=name or f"{namespace}-collector",
                )
                raise
