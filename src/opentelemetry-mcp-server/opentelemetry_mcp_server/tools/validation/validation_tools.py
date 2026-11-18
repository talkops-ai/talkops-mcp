"""Collector runtime diagnosis and configuration validation tools.

Provides:
- ``otel_diagnose_collector``: Single-call N->1 diagnosis correlating
  OpenTelemetryCollector CR status, pod container statuses (OOMKilled,
  CrashLoopBackOff), K8s Service endpoints, namespace events, redacted pod
  logs, internal Prometheus telemetry (:8888/metrics), and config linting.
- ``otel_validate_collector_config``: Deep static + live cluster validation
  of a live collector or raw YAML configuration.
"""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelValidationError,
)
from opentelemetry_mcp_server.models.findings import (
    Finding,
    FindingCode,
    FindingSeverity,
)
from opentelemetry_mcp_server.services.collector_metrics_service import (
    CollectorMetricsService,
)
from opentelemetry_mcp_server.services.config_linter import lint_collector_config
from opentelemetry_mcp_server.tools.base import BaseTool
from opentelemetry_mcp_server.utils.yaml_helpers import safe_load_yaml

_DIAGNOSE_SECTIONS = (
    "status",
    "pods",
    "service",
    "events",
    "logs",
    "metrics",
    "config_lint",
    "target_allocator",
)

_CHECK_CATEGORY_MAP = {
    "pipeline": {
        FindingCode.CFG_UNDECLARED_COMPONENT,
        FindingCode.CFG_UNUSED_COMPONENT,
        FindingCode.CFG_EXPORTER_NO_QUEUE_RETRY,
        FindingCode.CFG_GOMEMLIMIT_MISMATCH,
        FindingCode.CFG_CONNECTOR_LOOP,
    },
    "order": {
        FindingCode.CFG_MEMORY_LIMITER_NOT_FIRST,
        FindingCode.CFG_DOUBLE_BATCHING,
    },
    "filelog": {
        FindingCode.CFG_FILELOG_NO_SELF_EXCLUSION,
        FindingCode.CFG_FILELOG_EPHEMERAL_STORAGE,
    },
    "sampling": {
        FindingCode.CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY,
        FindingCode.CFG_CONNECTOR_LOOP,
    },
    "cardinality": {
        FindingCode.CFG_SPANMETRICS_HIGH_CARDINALITY,
        FindingCode.CFG_PROMETHEUS_NO_TARGET_ALLOCATOR,
    },
    "security": {
        FindingCode.SEC_INLINE_SECRET,
        FindingCode.SEC_INSECURE_EXPORTER,
        FindingCode.SEC_TLS_SKIP_VERIFY,
        FindingCode.SEC_MISSING_SECRET_KEY,
        FindingCode.SEC_DEBUG_EXTENSION_EXPOSED,
        FindingCode.SEC_PII_REDACTION_MISSING,
    },
    "deprecations": {
        FindingCode.CFG_DEPRECATED_TELEMETRY_ADDRESS,
        FindingCode.CFG_DEPRECATED_COMPONENT,
    },
    "rbac": {
        FindingCode.CFG_K8SATTR_MISSING_NODE_FILTER,
        FindingCode.CFG_K8SATTR_MISSING_RBAC,
    },
}


class ValidationTools(BaseTool):
    """Collector runtime diagnosis and configuration validation tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("diagnostics", is_write=False):
            return

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Diagnose Collector Runtime & Pipeline Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_diagnose_collector(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            include: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Optional diagnostic sections to include: 'status', 'pods', "
                    "'service', 'events', 'logs', 'metrics', 'config_lint', "
                    "'target_allocator' (all included if omitted)"
                ),
            ),
            log_lines: int = Field(
                default=50,
                ge=10,
                le=500,
                description="Number of redacted pod log tail lines to analyze (default 50)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Perform a comprehensive single-call runtime and configuration diagnosis of a collector.

            Correlates OpenTelemetryCollector CR status, pod container states
            (OOMKilled, CrashLoopBackOff), Kubernetes Service endpoint readiness,
            namespace events, redacted pod logs (auth/TLS/DNS errors), internal
            Prometheus metrics (:8888/metrics), RBAC bindings, and configuration
            linter checks into prioritized Finding objects.
            """
            try:
                sections = set(include or _DIAGNOSE_SECTIONS)
                raw = await kubernetes_service.get_otel_collector(
                    namespace, name
                )
                spec = raw.get("spec", {}) or {}
                status_raw = raw.get("status", {}) or {}
                mode = str(spec.get("mode", "deployment")).lower()
                replicas = int(
                    status_raw.get("replicas", spec.get("replicas", 1)) or 1
                )

                cfg = collector_config_service.parse_collector_config(raw)
                instance = collector_config_service.build_collector_instance(
                    raw, cfg, detail_level="summary"
                )

                findings: List[Finding] = []
                result: Dict[str, Any] = {
                    "collector": f"{namespace}/{name}",
                    "name": name,
                    "namespace": namespace,
                    "mode": mode,
                }

                if "status" in sections:
                    result["status"] = instance.status.model_dump()
                    result["pipelines"] = [
                        p.model_dump() for p in instance.pipelines
                    ]

                # 1. Inspect collector pods for OOMKilled / CrashLoopBackOff
                if "pods" in sections:
                    all_pods = await kubernetes_service.list_pods(
                        namespace=namespace
                    )
                    collector_pods = [
                        p
                        for p in all_pods
                        if p.get("name", "").startswith(f"{name}-collector")
                        or p.get("name", "").startswith(name)
                        or (p.get("labels") or {}).get(
                            "app.kubernetes.io/instance"
                        )
                        == f"{namespace}.{name}"
                    ]
                    for p in collector_pods:
                        p_name = p.get("name", "")
                        for cs in p.get("container_statuses", []) or []:
                            reason = cs.get("reason") or ""
                            last_reason = (
                                cs.get("last_termination_reason") or ""
                            )
                            restarts = int(cs.get("restart_count", 0) or 0)
                            if (
                                reason == "OOMKilled"
                                or last_reason == "OOMKilled"
                            ):
                                findings.append(
                                    Finding.create(
                                        FindingCode.RT_POD_OOMKILLED,
                                        message=(
                                            f"Pod '{p_name}' container '{cs.get('name')}' "
                                            f"was OOMKilled (restarts={restarts})."
                                        ),
                                        remediation=(
                                            "Increase spec.resources.limits.memory, set "
                                            "GOMEMLIMIT to 80% of the memory limit, and "
                                            "ensure memory_limiter is the first processor."
                                        ),
                                    )
                                )
                            elif (
                                reason == "CrashLoopBackOff" or restarts >= 3
                            ):
                                findings.append(
                                    Finding.create(
                                        FindingCode.RT_POD_CRASHLOOP,
                                        message=(
                                            f"Pod '{p_name}' container '{cs.get('name')}' "
                                            f"is crashing (state={cs.get('state')}, "
                                            f"reason={reason}, restarts={restarts})."
                                        ),
                                        remediation=(
                                            "Inspect the logs section and config_lint findings "
                                            "for invalid config keys or missing volume mounts."
                                        ),
                                    )
                                )
                    result["pods"] = collector_pods

                # 2. Check Service & Endpoints
                if "service" in sections:
                    svc_health = (
                        await kubernetes_service.get_collector_service_health(
                            namespace=namespace, collector_name=name
                        )
                    )
                    result["service_health"] = svc_health
                    if (
                        mode != "sidecar"
                        and svc_health.get("ready_endpoints", 0) == 0
                    ):
                        findings.append(
                            Finding.create(
                                FindingCode.RT_NO_READY_ENDPOINTS,
                                message=(
                                    f"Service for collector '{name}' has 0 ready endpoints "
                                    f"(service_found={svc_health.get('service_found')})."
                                ),
                                remediation=(
                                    "Check collector pod readiness probes and container "
                                    "logs for startup errors."
                                ),
                            )
                        )

                # 3. Namespace events
                if "events" in sections:
                    result["events"] = (
                        await kubernetes_service.list_namespace_events(
                            namespace=namespace, involved_object_name=name
                        )
                    )

                # 4. Redacted pod logs & error classification
                if "logs" in sections:
                    log_info = await kubernetes_service.get_collector_pod_logs(
                        namespace=namespace,
                        collector_name=name,
                        tail_lines=log_lines,
                    )
                    result["logs"] = log_info
                    if log_info.get("auth_errors"):
                        first_auth = str(log_info["auth_errors"][0])
                        is_kubelet_rbac = (
                            "nodes/stats" in first_auth
                            or "kubeletstats" in first_auth.lower()
                        )
                        findings.append(
                            Finding.create(
                                FindingCode.RT_LOG_AUTH_ERROR,
                                message=(
                                    f"Collector '{name}' kubeletstats receiver failed with 403 Forbidden "
                                    f"(ClusterRole 'otel-k8sattr-{name}' is missing 'get' permissions on both "
                                    f"'nodes/stats' and 'nodes/proxy' subresources): {first_auth}"
                                    if is_kubelet_rbac
                                    else f"Collector logs contain authentication/authorization errors: {first_auth}"
                                ),
                                remediation=(
                                    f"Grant 'get', 'list', 'watch' on both 'nodes/stats' and 'nodes/proxy' "
                                    f"('nodes/metrics') in ClusterRole 'otel-k8sattr-{name}' via "
                                    f"otel_configure_receivers(namespace='{namespace}', collector_name='{name}', receivers=['kubeletstats'])."
                                    if is_kubelet_rbac
                                    else "Verify backend API token/credentials Secret and collector ServiceAccount RBAC permissions."
                                ),
                            )
                        )
                    if log_info.get("tls_errors"):
                        findings.append(
                            Finding.create(
                                FindingCode.RT_LOG_TLS_ERROR,
                                message=(
                                    f"Collector logs contain TLS certificate errors: "
                                    f"{log_info['tls_errors'][0]}"
                                ),
                                remediation=(
                                    "Verify the CA bundle mounted in exporter tls.ca_file "
                                    "and check certificate expiration."
                                ),
                            )
                        )
                    if log_info.get("dns_errors"):
                        findings.append(
                            Finding.create(
                                FindingCode.RT_LOG_DNS_ERROR,
                                message=(
                                    f"Collector logs contain DNS/network connectivity "
                                    f"errors: {log_info['dns_errors'][0]}"
                                ),
                                remediation=(
                                    "Verify the exporter endpoint hostname, port, and "
                                    "NetworkPolicies in the namespace."
                                ),
                            )
                        )

                # 5. Internal Prometheus metrics (:8888/metrics)
                if "metrics" in sections:
                    try:
                        metrics_service = CollectorMetricsService(
                            kubernetes_service
                        )
                        health_report = (
                            await metrics_service.fetch_pipeline_health(
                                namespace=namespace,
                                collector_name=name,
                            )
                        )
                        result["pipeline_health"] = health_report.to_dict()
                        findings.extend(health_report.findings)
                    except Exception as e:
                        result["pipeline_health"] = {
                            "healthy": False,
                            "error": str(e),
                        }

                # 6. Config linting + live RBAC correlation
                if "config_lint" in sections:
                    rbac_bound = (
                        await kubernetes_service.check_cluster_role_binding_exists(
                            collector_name=name, namespace=namespace
                        )
                    )
                    lint_findings = lint_collector_config(
                        cfg,
                        mode=mode,
                        replicas=replicas,
                        cr_spec=spec,
                        env_vars=spec.get("env"),
                        volumes=spec.get("volumes"),
                        rbac_bound=rbac_bound,
                    )
                    findings.extend(lint_findings)
                    result["config_lint"] = {
                        "rbac_bound": rbac_bound,
                        "finding_count": len(lint_findings),
                    }

                # 7. Target Allocator state & monitoring.coreos.com RBAC check
                if "target_allocator" in sections:
                    ta_spec = spec.get("targetAllocator", {}) or {}
                    ta_enabled = bool(ta_spec.get("enabled", False))
                    ta_pods_ready: List[Dict[str, Any]] = []
                    monitoring_rbac_resources: List[str] = []
                    if ta_enabled:
                        try:
                            ns_pods = await kubernetes_service.list_pods(
                                namespace=namespace
                            )
                            ta_pods_ready = [
                                {
                                    "name": p.get("name"),
                                    "phase": p.get("phase"),
                                    "ready": p.get("ready"),
                                }
                                for p in ns_pods
                                if "targetallocator" in str(p.get("name", "")).lower()
                                and str(p.get("name", "")).startswith(name)
                            ]
                        except Exception:
                            ta_pods_ready = []
                        try:
                            roles = await kubernetes_service.list_otel_cluster_roles(
                                namespace=namespace
                            )
                            seen_res = set()
                            for role in roles:
                                for rule in role.get("rules", []) or []:
                                    if "monitoring.coreos.com" in (
                                        rule.get("api_groups") or rule.get("apiGroups") or []
                                    ):
                                        for res_item in rule.get("resources", []) or []:
                                            seen_res.add(str(res_item))
                            monitoring_rbac_resources = sorted(seen_res)
                        except Exception:
                            monitoring_rbac_resources = []

                    prom_cr = ta_spec.get("prometheusCR") or {}
                    result["target_allocator"] = {
                        "enabled": ta_enabled,
                        "allocation_strategy": ta_spec.get(
                            "allocationStrategy", "consistent-hashing"
                        ),
                        "prometheus_cr": bool(prom_cr.get("enabled", False)),
                        "service_monitor_selector": prom_cr.get(
                            "serviceMonitorSelector", {}
                        ),
                        "pod_monitor_selector": prom_cr.get(
                            "podMonitorSelector", {}
                        ),
                        "pods": ta_pods_ready,
                        "monitoring_coreos_rbac_resources": monitoring_rbac_resources,
                    }

                error_findings = [
                    f for f in findings if f.severity == FindingSeverity.ERROR
                ]
                warning_findings = [
                    f
                    for f in findings
                    if f.severity == FindingSeverity.WARNING
                ]
                result["healthy"] = len(error_findings) == 0
                result["error_count"] = len(error_findings)
                result["warning_count"] = len(warning_findings)
                result["findings"] = [f.model_dump() for f in findings]
                return result
            except OtelOperationError:
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_diagnose_collector",
                    namespace=namespace,
                    resource_name=name,
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Collector Configuration",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_validate_collector_config(
            namespace: Optional[str] = Field(
                default=None,
                description="Collector namespace (when validating a live collector CR)",
            ),
            name: Optional[str] = Field(
                default=None,
                description="Collector CRD name (when validating a live collector CR)",
            ),
            config_yaml: Optional[str] = Field(
                default=None,
                description="Raw OTel Collector YAML string to validate (optional if namespace+name provided)",
            ),
            checks: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Optional subset of check categories to run: 'pipeline', "
                    "'order', 'filelog', 'sampling', 'cardinality', 'security', "
                    "'deprecations', 'rbac' (all run if omitted)"
                ),
            ),
            target_version: Optional[str] = Field(
                default=None,
                description="Target Collector version for deprecation checks (e.g., '0.152.1')",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Validate a live OpenTelemetryCollector CR or raw YAML configuration.

            Runs all static configuration linter checks (referential integrity,
            processor ordering, double batching, exporter queues, filelog safety,
            tail_sampling trace affinity, spanmetrics cardinality, v0.123+
            deprecations, GOMEMLIMIT, inline secrets) and correlates with live
            RBAC and Secret existence when a live collector is specified.
            """
            try:
                if not config_yaml and not (namespace and name):
                    raise OtelValidationError(
                        "Provide either (namespace and name) to validate a live "
                        "collector or config_yaml to validate raw YAML."
                    )

                mode = "deployment"
                replicas = 1
                cr_spec_for_lint: Optional[Dict[str, Any]] = None
                env_vars: Optional[List[Dict[str, Any]]] = None
                volumes: Optional[List[Dict[str, Any]]] = None
                rbac_bound: Optional[bool] = None
                extra_findings: List[Finding] = []

                if namespace and name:
                    raw = await kubernetes_service.get_otel_collector(
                        namespace, name
                    )
                    spec = raw.get("spec", {}) or {}
                    cr_spec_for_lint = spec
                    mode = str(spec.get("mode", "deployment")).lower()
                    replicas = int(spec.get("replicas", 1) or 1)
                    env_vars = spec.get("env")
                    volumes = spec.get("volumes")
                    rbac_bound = (
                        await kubernetes_service.check_cluster_role_binding_exists(
                            collector_name=name, namespace=namespace
                        )
                    )
                    # Check Secret references in spec.env
                    for env_entry in env_vars or []:
                        if not isinstance(env_entry, dict):
                            continue
                        vf = env_entry.get("valueFrom") or {}
                        sec_ref = vf.get("secretKeyRef") or {}
                        sec_name = sec_ref.get("name")
                        sec_key = sec_ref.get("key")
                        if sec_name:
                            check = (
                                await kubernetes_service.check_secret_key_exists(
                                    namespace=namespace,
                                    secret_name=sec_name,
                                    key=sec_key,
                                )
                            )
                            if not check.get("exists") or not check.get(
                                "key_exists"
                            ):
                                extra_findings.append(
                                    Finding.create(
                                        FindingCode.SEC_MISSING_SECRET_KEY,
                                        message=(
                                            f"Secret '{sec_name}' (key '{sec_key}') "
                                            f"referenced by env var '{env_entry.get('name')}' "
                                            f"does not exist in namespace '{namespace}'."
                                        ),
                                        field_path=f"spec.env[{env_entry.get('name')}]",
                                        remediation=(
                                            f"Create Secret '{sec_name}' with key '{sec_key}' "
                                            f"in namespace '{namespace}'."
                                        ),
                                    )
                                )
                    if not config_yaml:
                        cfg = collector_config_service.parse_collector_config(
                            raw
                        )
                    else:
                        cfg = safe_load_yaml(config_yaml)
                else:
                    cfg = safe_load_yaml(config_yaml or "")

                lint_findings = lint_collector_config(
                    cfg,
                    mode=mode,
                    replicas=replicas,
                    cr_spec=cr_spec_for_lint,
                    env_vars=env_vars,
                    volumes=volumes,
                    rbac_bound=rbac_bound,
                    target_version=target_version,
                )
                all_findings = lint_findings + extra_findings

                if checks:
                    allowed_codes = set()
                    for cat in checks:
                        allowed_codes.update(
                            _CHECK_CATEGORY_MAP.get(cat.lower(), set())
                        )
                    if allowed_codes:
                        all_findings = [
                            f for f in all_findings if f.code in allowed_codes
                        ]

                errors = [
                    f
                    for f in all_findings
                    if f.severity == FindingSeverity.ERROR
                ]
                warnings = [
                    f
                    for f in all_findings
                    if f.severity == FindingSeverity.WARNING
                ]

                return {
                    "collector": (
                        f"{namespace}/{name}"
                        if (namespace and name)
                        else "inline_yaml"
                    ),
                    "valid": len(errors) == 0,
                    "all_valid": len(errors) == 0,
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "checked_target_version": (
                        target_version or self.config.collector_version_default
                    ),
                    "mode": mode,
                    "findings": [f.model_dump() for f in all_findings],
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_validate_collector_config",
                    namespace=namespace or "default",
                    resource_name=name,
                )
                raise
