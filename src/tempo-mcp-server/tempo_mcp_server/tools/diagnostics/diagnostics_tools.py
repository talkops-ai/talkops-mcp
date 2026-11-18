"""Tempo diagnostics tool — version-aware (2.x & 3.x), facts-only observation codes."""

from typing import Annotated, Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field
from pydantic.fields import FieldInfo

from tempo_mcp_server.tools.base import BaseTool


class DiagnosticsTools(BaseTool):
    """Backend diagnostics and factual health observation tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("diagnostics", is_write=False):
            return

        tempo_service = self.tempo_service
        kubernetes_service = self.kubernetes_service
        server_config = self.config

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Tempo Diagnostics",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_diagnostics(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            tenant: Optional[str] = Field(default=None, description="Optional tenant ID"),
            include: Optional[List[str]] = Field(
                default=None,
                description="Optional sections to include: health, components, rings, ingestion, config, overrides, operator",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Collect factual health, version (2.x/3.x), ring, discarded-span, config, and Operator CR observations.

            Returns: {"ready": bool, "architecture_generation": str, "findings": [{"code": str, "component": str, "message": str, "evidence": {...}}], "observation_codes": [...]}.
            When NOT to use: For simple backend inventory, read 'tempo://system/backends'.
            """
            if isinstance(tenant, FieldInfo):
                tenant = tenant.default
            if isinstance(include, FieldInfo):
                include = include.default
            alias_map = {
                "ring": "rings",
                "component": "components",
                "override": "overrides",
            }
            if include:
                sections = {alias_map.get(s.strip().lower(), s.strip().lower()) for s in include if s}
                if "overrides" in sections:
                    sections.add("config")
            else:
                sections = {"health", "components", "rings", "ingestion", "config", "operator"}
            findings: List[Dict[str, Any]] = []
            observation_codes: List[str] = []

            def _add_finding(code: str, component: str, message: str, evidence: Optional[Dict[str, Any]] = None) -> None:
                findings.append({
                    "code": code,
                    "component": component,
                    "message": message,
                    "evidence": evidence or {},
                })
                if code not in observation_codes:
                    observation_codes.append(code)

            try:
                if ctx:
                    await ctx.info(f"Running diagnostics on backend '{backend_id}'...")

                # 1. Readiness check
                health = await tempo_service.check_health(backend_id)
                is_ready = bool(health.get("ready", False))
                if not is_ready:
                    _add_finding(
                        "BACKEND_UNREACHABLE",
                        "ready_endpoint",
                        f"Backend not ready: {health.get('error', 'unknown')}",
                        {"ready": False, "error": health.get("error")},
                    )

                # 2. Build info
                build_info = None
                try:
                    build_info = await tempo_service.get_build_info(backend_id)
                except Exception as e:
                    _add_finding(
                        "BUILD_INFO_UNAVAILABLE",
                        "buildinfo_endpoint",
                        f"Cannot retrieve build info: {e}",
                        {"error": str(e)},
                    )

                # 3. Component statuses
                services = None
                if "components" in sections:
                    try:
                        services = await tempo_service.get_status_services(backend_id)
                        if services:
                            for component, status in services.items():
                                if isinstance(status, str) and status.lower() not in ("running", "ready", "new", "disabled"):
                                    _add_finding(
                                        "COMPONENT_NOT_RUNNING",
                                        component,
                                        f"Component '{component}' status is '{status}'",
                                        {"component": component, "status": status},
                                    )
                    except Exception:
                        pass

                # 4. Safe runtime config facts
                config_facts: Dict[str, Any] = {}
                if "config" in sections:
                    config_facts = await tempo_service.get_safe_status_config(backend_id)
                    if config_facts:
                        procs = config_facts.get("metrics_generator_processors")
                        if tenant:
                            try:
                                ov_data = await tempo_service.get_tenant_overrides(
                                    backend_id=backend_id,
                                    tenant=tenant,
                                    scope="merged",
                                )
                                ov_procs = (ov_data.get("overrides") or {}).get("metrics_generator", {}).get("processors")
                                if isinstance(ov_procs, list):
                                    procs = [str(p).replace("_", "-") for p in ov_procs]
                            except Exception:
                                pass
                        if procs is not None:
                            expected_procs = {"service-graphs", "span-metrics", "local-blocks"}
                            norm_procs = {str(p).replace("_", "-") for p in procs}
                            missing_procs = sorted(expected_procs - norm_procs)
                            if not norm_procs or missing_procs:
                                _add_finding(
                                    "METRICS_GENERATOR_PROCESSOR_ABSENT",
                                    "metrics_generator",
                                    f"Missing metrics_generator processors: {missing_procs}" if missing_procs else "No metrics_generator processors enabled in runtime config.",
                                    {"processors": sorted(norm_procs), "missing_processors": missing_procs},
                                )
                        if config_facts.get("user_configurable_overrides_enabled") is False:
                            _add_finding(
                                "OVERRIDES_API_DISABLED",
                                "overrides",
                                "user_configurable_overrides is disabled in runtime config.",
                                {"user_configurable_overrides_enabled": False},
                            )

                # Detect Tempo 2.x vs 3.x generation
                major_version, arch_gen = tempo_service.detect_tempo_generation(
                    build_info, services, config_facts
                )

                # 5. Deployment mode + ring checks
                ring_checks = None
                detected_mode = "unknown"
                try:
                    backend = tempo_service._get_backend(backend_id)
                    detected_mode = backend.deployment_mode
                    if backend.multi_tenant and not (tenant or backend.default_tenant):
                        _add_finding(
                            "TENANT_HEADER_REQUIRED",
                            "multi_tenancy",
                            f"Backend '{backend_id}' has multi_tenant=true and no default_tenant configured.",
                            {"tenant_header": backend.tenant_header},
                        )
                except Exception:
                    pass

                if "rings" in sections:
                    if detected_mode == "unknown":
                        _add_finding(
                            "DEPLOYMENT_MODE_UNKNOWN",
                            "configuration",
                            "Deployment mode is 'unknown'; ring probes skipped.",
                            {"deployment_mode": "unknown"},
                        )
                    else:
                        try:
                            ring_checks = await tempo_service.check_rings(
                                backend_id,
                                deployment_mode_override=detected_mode,
                                architecture_generation=arch_gen if arch_gen != "unknown" else "2.x",
                            )
                            for ring_name, ring_status in ring_checks.items():
                                if not isinstance(ring_status, dict):
                                    continue
                                if ring_status.get("status") == "error":
                                    _add_finding(
                                        "RING_CHECK_FAILED",
                                        ring_name,
                                        f"Ring '{ring_name}' check failed: {ring_status.get('error', '')}",
                                        {"ring": ring_name, "error": ring_status.get("error")},
                                    )
                                elif (
                                    ring_status.get("leaving", 0) > 0
                                    or ring_status.get("pending", 0) > 0
                                    or ring_status.get("joining", 0) > 0
                                    or ring_status.get("inactive", 0) > 0
                                    or ring_status.get("unhealthy", 0) > 0
                                ):
                                    _add_finding(
                                        "RING_MEMBER_UNHEALTHY",
                                        ring_name,
                                        f"Ring '{ring_name}' has non-ACTIVE members.",
                                        {
                                            "ring": ring_name,
                                            "states": ring_status.get("states"),
                                        },
                                    )
                        except Exception:
                            pass

                # 6. Ingestion & Tempo 3.x partition lag facts from /metrics
                discarded_spans = None
                max_partition_lag = None
                if "ingestion" in sections:
                    metrics_facts = await tempo_service.get_prometheus_metrics_facts(backend_id)
                    if metrics_facts is None:
                        if is_ready:
                            _add_finding(
                                "INGESTION_METRICS_UNREACHABLE",
                                "metrics_endpoint",
                                "Tempo /metrics endpoint was not reachable from this client.",
                                {"endpoint": "/metrics"},
                            )
                    else:
                        discarded_spans = metrics_facts.get("discarded_spans_by_reason") or {}
                        if discarded_spans:
                            _add_finding(
                                "SPANS_DISCARDED",
                                "distributor",
                                f"Discarded spans observed across reasons: { sorted(discarded_spans.keys()) }",
                                {
                                    "discarded_spans_by_reason": discarded_spans,
                                    "total_discarded_spans": metrics_facts.get("total_discarded_spans", 0),
                                },
                            )
                        max_partition_lag = metrics_facts.get("max_partition_lag_seconds")
                        if max_partition_lag is not None and max_partition_lag > 0:
                            _add_finding(
                                "PARTITION_LAG_OBSERVED",
                                "live_store",
                                f"Observed Kafka partition lag of {max_partition_lag}s.",
                                {
                                    "max_partition_lag_seconds": max_partition_lag,
                                    "partition_lags": metrics_facts.get("partition_lags"),
                                },
                            )

                # 7. Kubernetes Tempo Operator CR status checks
                operator_crs: Optional[List[Dict[str, Any]]] = None
                if "operator" in sections and kubernetes_service and server_config.kubernetes.enabled:
                    try:
                        raw_crs = await kubernetes_service.list_tempo_operator_crs()
                        operator_crs = []
                        for cr in raw_crs:
                            meta = cr.get("metadata") or {}
                            cr_name = meta.get("name", "")
                            cr_ns = meta.get("namespace", "")
                            cr_kind = cr.get("_kind") or cr.get("kind", "TempoStack")
                            conditions = (cr.get("status") or {}).get("conditions") or []
                            ready_cond = next((c for c in conditions if c.get("type") == "Ready"), None)
                            is_cr_ready = (ready_cond.get("status") == "True") if isinstance(ready_cond, dict) else None
                            reason = ready_cond.get("reason") if isinstance(ready_cond, dict) else None
                            msg = ready_cond.get("message") if isinstance(ready_cond, dict) else None
                            operator_crs.append({
                                "kind": cr_kind,
                                "name": cr_name,
                                "namespace": cr_ns,
                                "ready": is_cr_ready,
                                "reason": reason,
                            })
                            if is_cr_ready is False:
                                _add_finding(
                                    "OPERATOR_CR_NOT_READY",
                                    f"{cr_kind}/{cr_ns}/{cr_name}",
                                    f"{cr_kind} '{cr_ns}/{cr_name}' has Ready=False ({reason or 'NotReady'}).",
                                    {
                                        "kind": cr_kind,
                                        "name": cr_name,
                                        "namespace": cr_ns,
                                        "reason": reason,
                                        "message": msg,
                                    },
                                )
                    except Exception:
                        pass

                payload_out: Dict[str, Any] = {
                    "ready": is_ready,
                    "tempo_major_version": major_version,
                    "architecture_generation": arch_gen,
                    "deployment_mode": detected_mode,
                    "build_info": build_info,
                    "services": services,
                    "ring_checks": ring_checks,
                    "discarded_spans": discarded_spans,
                    "max_partition_lag_seconds": max_partition_lag,
                    "config_facts": config_facts or None,
                    "findings": findings,
                    "observation_codes": observation_codes,
                }
                if operator_crs is not None:
                    payload_out["operator_crs"] = operator_crs
                return payload_out
            except Exception as e:
                self.handle_error(e, "tempo_get_diagnostics", backend_id=backend_id)
                raise
