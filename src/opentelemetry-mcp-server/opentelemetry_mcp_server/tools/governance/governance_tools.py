"""Observability security posture audit tool.

Provides ``otel_audit_security_posture`` for auditing collectors,
Instrumentation CRs, eBPF/OBI agents, and RBAC ClusterRoles against
security best practices (inline secrets, TLS settings, least-privilege
capabilities, read-only hostPath mounts, non-root containers, and RBAC
wildcards).
"""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.models.findings import (
    Finding,
    FindingCode,
    FindingSeverity,
)
from opentelemetry_mcp_server.services.config_linter import lint_collector_config
from opentelemetry_mcp_server.tools.base import BaseTool
from opentelemetry_mcp_server.utils.k8s_labels import EBPF_AGENT_LABELS
from opentelemetry_mcp_server.utils.redaction import detect_inline_secrets

_AUDIT_SCOPES = ("collectors", "instrumentation", "ebpf", "rbac")


class GovernanceTools(BaseTool):
    """Observability security posture and governance tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("governance", is_write=False):
            return

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Audit Observability Security Posture",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_audit_security_posture(
            namespace: Optional[str] = Field(
                default=None,
                description="Kubernetes namespace to scan (all namespaces if omitted)",
            ),
            scope: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Audit scopes to evaluate: 'collectors', 'instrumentation', "
                    "'ebpf', 'rbac' (all four if omitted)"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Audit the security posture of OpenTelemetry collectors, instrumentation, eBPF/OBI agents, and RBAC.

            Detects inline plaintext secrets, insecure exporters, TLS skip-verify,
            privileged eBPF pods, SYS_ADMIN capability usage, hostPID usage,
            writable /var/log hostPath mounts, root container execution, and
            wildcard RBAC rules.
            """
            try:
                active_scopes = set(scope or _AUDIT_SCOPES)
                findings: List[Finding] = []
                recommendations: List[str] = []

                collectors_audited = 0
                instrumentations_audited = 0
                rbac_roles_audited = 0
                pod_details: List[Dict[str, Any]] = []
                total_privileged = 0
                total_host_pid = 0
                all_capabilities = set()
                all_host_mounts = set()

                # 1. Collectors audit
                if "collectors" in active_scopes:
                    raw_collectors = (
                        await kubernetes_service.list_otel_collectors(
                            namespace=namespace
                        )
                    )
                    for item in raw_collectors.get("items", []):
                        collectors_audited += 1
                        meta = item.get("metadata", {}) or {}
                        c_name = meta.get("name", "unknown")
                        c_ns = meta.get("namespace", "default")
                        spec = item.get("spec", {}) or {}
                        mode = str(spec.get("mode", "deployment")).lower()

                        try:
                            cfg = (
                                collector_config_service.parse_collector_config(
                                    item
                                )
                            )
                            lint_findings = lint_collector_config(
                                cfg,
                                mode=mode,
                                env_vars=spec.get("env"),
                                volumes=spec.get("volumes"),
                            )
                            for lf in lint_findings:
                                if lf.code in (
                                    FindingCode.SEC_INLINE_SECRET,
                                    FindingCode.SEC_INSECURE_EXPORTER,
                                    FindingCode.SEC_TLS_SKIP_VERIFY,
                                    FindingCode.SEC_DEBUG_EXTENSION_EXPOSED,
                                ):
                                    findings.append(lf)
                        except Exception:
                            pass

                        # Check volumeMounts in collector CRD for writable /var/log
                        for vm in spec.get("volumeMounts", []) or []:
                            if not isinstance(vm, dict):
                                continue
                            mpath = str(
                                vm.get("mountPath")
                                or vm.get("mount_path")
                                or ""
                            )
                            ro = bool(
                                vm.get("readOnly")
                                or vm.get("read_only")
                                or False
                            )
                            if mpath.startswith("/var/log") and not ro:
                                findings.append(
                                    Finding.create(
                                        FindingCode.SEC_HOSTPATH_WRITABLE,
                                        message=(
                                            f"Collector '{c_ns}/{c_name}' mounts '{mpath}' "
                                            "without readOnly: true."
                                        ),
                                        field_path=f"collectors.{c_ns}.{c_name}.spec.volumeMounts",
                                        remediation="Set readOnly: true on /var/log hostPath mounts.",
                                    )
                                )

                    # Check collector pods for writable /var/log & runAsRoot
                    try:
                        all_pods = await kubernetes_service.list_pods(
                            namespace=namespace
                        )
                        for p in all_pods:
                            p_labels = p.get("labels", {}) or {}
                            if (
                                p_labels.get("app.kubernetes.io/component")
                                == "opentelemetry-collector"
                                or "collector" in p.get("name", "")
                            ):
                                p_name = p.get("name", "")
                                p_ns = p.get("namespace", "default")
                                psc = p.get("pod_security_context", {}) or {}
                                for c in p.get("containers", []) or []:
                                    sc = c.get("security_context", {}) or {}
                                    if (
                                        sc.get("run_as_user") == 0
                                        or psc.get("run_as_user") == 0
                                        or sc.get("run_as_non_root") is False
                                    ):
                                        findings.append(
                                            Finding.create(
                                                FindingCode.SEC_POD_RUN_AS_ROOT,
                                                message=(
                                                    f"Collector pod '{p_ns}/{p_name}' runs "
                                                    "as root (UID 0)."
                                                ),
                                                field_path=f"pods.{p_ns}.{p_name}.securityContext",
                                                remediation=(
                                                    "Configure securityContext.runAsNonRoot: true "
                                                    "unless reading root-owned host logs."
                                                ),
                                            )
                                        )
                                    for vm in c.get("volume_mounts", []) or []:
                                        mpath = str(vm.get("mount_path", ""))
                                        if mpath.startswith(
                                            "/var/log"
                                        ) and not vm.get("read_only", False):
                                            findings.append(
                                                Finding.create(
                                                    FindingCode.SEC_HOSTPATH_WRITABLE,
                                                    message=(
                                                        f"Pod '{p_ns}/{p_name}' mounts '{mpath}' "
                                                        "as writable."
                                                    ),
                                                    field_path=f"pods.{p_ns}.{p_name}.volumeMounts",
                                                    remediation="Mount /var/log as readOnly: true.",
                                                )
                                            )
                    except Exception:
                        pass

                # 2. Instrumentation CRs audit
                if "instrumentation" in active_scopes:
                    raw_instrs = (
                        await kubernetes_service.list_instrumentations(
                            namespace=namespace
                        )
                    )
                    for item in raw_instrs.get("items", []):
                        instrumentations_audited += 1
                        meta = item.get("metadata", {}) or {}
                        i_name = meta.get("name", "unknown")
                        i_ns = meta.get("namespace", "default")
                        spec = item.get("spec", {}) or {}
                        secret_hits = detect_inline_secrets(
                            spec, base_path=f"instrumentation.{i_ns}.{i_name}.spec"
                        )
                        for hit in secret_hits:
                            findings.append(
                                Finding.create(
                                    FindingCode.SEC_INLINE_SECRET,
                                    message=(
                                        f"Instrumentation CR '{i_ns}/{i_name}' contains "
                                        f"an inline secret at '{hit['field_path']}'."
                                    ),
                                    field_path=hit["field_path"],
                                    remediation=(
                                        "Use valueFrom.secretKeyRef instead of plaintext "
                                        "secret values in Instrumentation CRs."
                                    ),
                                )
                            )

                # 3. eBPF / OBI agents audit (D4: audit-only in MCP server)
                if "ebpf" in active_scopes:
                    all_ebpf_pods = []
                    for label in EBPF_AGENT_LABELS:
                        pods = await kubernetes_service.list_pods(
                            namespace=namespace, label_selector=label
                        )
                        all_ebpf_pods.extend(pods)

                    seen = set()
                    unique_pods = []
                    for p in all_ebpf_pods:
                        key = f"{p['namespace']}/{p['name']}"
                        if key not in seen:
                            seen.add(key)
                            unique_pods.append(p)

                    for pod in unique_pods[:50]:
                        is_privileged = False
                        pod_caps: List[str] = []
                        pod_mounts: List[str] = []
                        p_name = pod["name"]
                        p_ns = pod["namespace"]

                        for c in pod.get("containers", []):
                            sc = c.get("security_context", {}) or {}
                            if sc.get("privileged"):
                                is_privileged = True
                            caps = sc.get("capabilities", []) or []
                            pod_caps.extend(caps)
                            for vm in c.get("volume_mounts", []) or []:
                                mpath = vm.get("mount_path", "")
                                if "/sys" in mpath or "/proc" in mpath:
                                    pod_mounts.append(mpath)

                        for hv in pod.get("host_volumes", []) or []:
                            hpath = hv.get("host_path", "")
                            all_host_mounts.add(hpath)
                            pod_mounts.append(hpath)

                        if is_privileged:
                            total_privileged += 1
                            findings.append(
                                Finding.create(
                                    FindingCode.SEC_EBPF_PRIVILEGED,
                                    message=(
                                        f"eBPF agent pod '{p_ns}/{p_name}' runs with "
                                        "privileged: true."
                                    ),
                                    field_path=f"pods.{p_ns}.{p_name}.securityContext.privileged",
                                    remediation=(
                                        "Replace privileged: true with fine-grained Linux "
                                        "capabilities: [BPF, PERFMON, SYS_PTRACE, NET_RAW, "
                                        "DAC_READ_SEARCH, CHECKPOINT_RESTORE]."
                                    ),
                                )
                            )
                        if "SYS_ADMIN" in pod_caps:
                            findings.append(
                                Finding.create(
                                    FindingCode.SEC_EBPF_SYS_ADMIN,
                                    message=(
                                        f"eBPF agent pod '{p_ns}/{p_name}' grants "
                                        "broad SYS_ADMIN capability."
                                    ),
                                    field_path=f"pods.{p_ns}.{p_name}.securityContext.capabilities",
                                    remediation=(
                                        "Replace SYS_ADMIN with least-privilege capabilities "
                                        "(BPF, PERFMON, SYS_PTRACE) on Linux kernel >= 5.8."
                                    ),
                                )
                            )
                        if pod.get("host_pid"):
                            total_host_pid += 1
                            findings.append(
                                Finding.create(
                                    FindingCode.SEC_EBPF_HOST_PID,
                                    message=(
                                        f"eBPF agent pod '{p_ns}/{p_name}' enables "
                                        "hostPID: true."
                                    ),
                                    field_path=f"pods.{p_ns}.{p_name}.spec.hostPID",
                                    remediation=(
                                        "Verify hostPID is required for Go/process symbol "
                                        "resolution and restrict pod scheduling via PSP/PSA."
                                    ),
                                )
                            )

                        all_capabilities.update(pod_caps)
                        pod_details.append({
                            "pod_name": p_name,
                            "namespace": p_ns,
                            "node_name": pod.get("node_name"),
                            "privileged": is_privileged,
                            "host_pid": pod.get("host_pid", False),
                            "capabilities": pod_caps,
                            "volume_mounts": sorted(set(pod_mounts)),
                        })

                # 4. RBAC ClusterRoles audit
                if "rbac" in active_scopes:
                    roles = await kubernetes_service.list_otel_cluster_roles(
                        namespace=namespace
                    )
                    for role in roles:
                        rbac_roles_audited += 1
                        r_name = role.get("name", "unknown")
                        for idx, rule in enumerate(role.get("rules", []) or []):
                            res_list = rule.get("resources", []) or []
                            verb_list = rule.get("verbs", []) or []
                            write_verbs = sorted(
                                {"create", "update", "patch", "delete", "deletecollection"}
                                & {str(v).lower() for v in verb_list}
                            )
                            has_secrets = "secrets" in {str(r).lower() for r in res_list}
                            if "*" in res_list or "*" in verb_list or has_secrets or write_verbs:
                                findings.append(
                                    Finding.create(
                                        FindingCode.SEC_RBAC_WILDCARD,
                                        message=(
                                            f"ClusterRole '{r_name}' rule[{idx}] grants "
                                            f"excessive permissions (resources={res_list}, "
                                            f"verbs={verb_list})."
                                        ),
                                        field_path=f"clusterRoles.{r_name}.rules[{idx}]",
                                        remediation=(
                                            "Scope ClusterRole rules strictly to explicit non-secret "
                                            "resources and read-only verbs ['get', 'list', 'watch']."
                                        ),
                                    )
                                )

                # Compute overall risk level & recommendations
                risk_level = "low"
                has_critical = any(
                    f.code
                    in (
                        FindingCode.SEC_EBPF_SYS_ADMIN,
                        FindingCode.SEC_INLINE_SECRET,
                        FindingCode.SEC_RBAC_WILDCARD,
                    )
                    for f in findings
                )
                has_high = any(
                    f.severity == FindingSeverity.ERROR for f in findings
                )
                has_medium = any(
                    f.severity == FindingSeverity.WARNING for f in findings
                )

                if has_critical:
                    risk_level = "critical"
                elif has_high:
                    risk_level = "high"
                elif has_medium:
                    risk_level = "medium"

                for f in findings:
                    if f.remediation not in recommendations:
                        recommendations.append(f.remediation)
                if not recommendations:
                    recommendations.append("No security concerns detected")

                return {
                    "namespace": namespace or "all",
                    "scope": sorted(active_scopes),
                    "risk_level": risk_level,
                    "collectors_audited": collectors_audited,
                    "instrumentations_audited": instrumentations_audited,
                    "rbac_roles_audited": rbac_roles_audited,
                    "total_ebpf_pods": len(pod_details),
                    "total_privileged": total_privileged,
                    "total_host_pid": total_host_pid,
                    "unique_capabilities": sorted(all_capabilities),
                    "unique_host_mounts": sorted(all_host_mounts),
                    "pods": pod_details,
                    "ebpf_pods": pod_details,
                    "findings": [f.model_dump() for f in findings],
                    "recommendations": recommendations,
                }
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_audit_security_posture",
                    namespace=namespace or "default",
                )
                raise
