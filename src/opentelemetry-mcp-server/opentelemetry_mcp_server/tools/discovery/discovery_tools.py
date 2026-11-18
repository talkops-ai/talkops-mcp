"""OpenTelemetry cluster survey, workload discovery, and A2UI tools.

Provides read-only tools for surveying cluster-wide OpenTelemetry topology,
listing workloads with instrumentation state across Deployments, StatefulSets,
and DaemonSets, and serving the TalkOps A2UI status datatable.
"""

import datetime
from typing import Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.models.findings import Finding, FindingCode
from opentelemetry_mcp_server.tools.base import BaseTool
from opentelemetry_mcp_server.utils.gitops import (
    build_gitops_finding,
    detect_gitops_ownership,
)
from opentelemetry_mcp_server.utils.k8s_labels import (
    EBPF_AGENT_LABELS,
    GO_TARGET_EXE_ANNOTATION,
    detect_language_from_annotations,
    detect_language_from_images,
    detect_language_from_name,
    detect_language_from_runtime_env,
    detect_signals_from_env,
    get_instrumentation_cr_from_annotations,
    has_otel_sdk_env,
)
from opentelemetry_mcp_server.utils.pagination import paginate

_SURVEY_SECTIONS = (
    "operator",
    "collectors",
    "instrumentations",
    "target_allocators",
    "opamp_bridges",
    "ebpf_agents",
    "backends",
)

_CONFLICT_ENV_VARS = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    "OTEL_COLLECTOR_NAME",
)


class DiscoveryTools(BaseTool):
    """Cluster topology survey, workload discovery, and A2UI tools."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        if self.should_register_tool("discovery", is_write=False):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Survey Cluster OpenTelemetry Topology",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def otel_survey_cluster(
                namespaces: Optional[List[str]] = Field(
                    default=None,
                    description=(
                        "Optional list of Kubernetes namespaces to scope the survey "
                        "(surveys all namespaces if omitted)"
                    ),
                ),
                include: Optional[List[str]] = Field(
                    default=None,
                    description=(
                        "Optional sections to include: 'operator', 'collectors', "
                        "'instrumentations', 'target_allocators', 'opamp_bridges', "
                        "'ebpf_agents', 'backends' (all included if omitted)"
                    ),
                ),
                detail: Literal["summary", "full"] = Field(
                    default="summary",
                    description=(
                        "Detail level: 'summary' (compact metadata) or 'full' "
                        "(includes redacted collector YAML and service endpoint health)"
                    ),
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Survey the cluster's complete OpenTelemetry posture in a single call.

                Aggregates OpenTelemetry Operator health, OpenTelemetryCollector CRs,
                Instrumentation CRs, TargetAllocator CRs, OpAMPBridge CRs (read-only),
                eBPF/OBI agents, and backend observability services (Jaeger, Tempo,
                Prometheus, VictoriaMetrics, Mimir, Loki, OpenSearch), along with
                structured diagnostic findings.
                """
                try:
                    sections = set(include or _SURVEY_SECTIONS)
                    target_namespaces = namespaces or [None]  # type: ignore[list-item]
                    findings: List[Dict[str, Any]] = []
                    response: Dict[str, Any] = {
                        "detail": detail,
                        "namespaces_filter": namespaces,
                    }

                    # 1. Operator status
                    if "operator" in sections:
                        op_diag = await kubernetes_service.get_operator_diagnostics(
                            tail_lines=80
                        )
                        response["operator"] = op_diag
                        if not op_diag.get("operator_found"):
                            findings.append(
                                Finding.create(
                                    FindingCode.OP_NOT_INSTALLED,
                                    message=(
                                        "OpenTelemetry Operator pod was not found in "
                                        "standard operator namespaces."
                                    ),
                                    remediation=(
                                        "Install the OpenTelemetry Operator (and cert-manager "
                                        "for webhook certificates) before creating CRs."
                                    ),
                                ).model_dump()
                            )
                        for warn in op_diag.get("warnings", []):
                            w_low = warn.lower()
                            if "webhook" in w_low:
                                findings.append(
                                    Finding.create(
                                        FindingCode.OP_WEBHOOK_ERROR,
                                        message=warn,
                                        remediation=(
                                            "Verify cert-manager pods and mutating/validating "
                                            "webhook certificate secret in the operator namespace."
                                        ),
                                    ).model_dump()
                                )
                        for ns_name, cr_count in (
                            op_diag.get("instrumentation_cr_counts", {}) or {}
                        ).items():
                            if cr_count > 1:
                                findings.append(
                                    Finding.create(
                                        FindingCode.OP_MULTIPLE_INSTRUMENTATION_CRS,
                                        message=(
                                            f"Namespace '{ns_name}' has {cr_count} "
                                            "Instrumentation CRs. Auto-instrumentation "
                                            "requires a single default CR or explicit "
                                            "CR name in workload annotations."
                                        ),
                                        field_path=f"namespaces.{ns_name}.instrumentations",
                                        remediation=(
                                            "Delete duplicate Instrumentation CRs with "
                                            "otel_delete_resource or set the explicit CR name "
                                            "in the workload inject annotation."
                                        ),
                                    ).model_dump()
                                )

                    # 2. Collectors
                    if "collectors" in sections:
                        raw_collectors: List[Dict[str, Any]] = []
                        for ns in target_namespaces:
                            res = await kubernetes_service.list_otel_collectors(
                                namespace=ns
                            )
                            raw_collectors.extend(res.get("items", []))

                        collectors_out: List[Dict[str, Any]] = []
                        for item in raw_collectors:
                            meta = item.get("metadata", {}) or {}
                            c_name = meta.get("name", "unknown")
                            c_ns = meta.get("namespace", "default")
                            gitops_info = detect_gitops_ownership(meta)
                            gitops_finding = build_gitops_finding(
                                c_name, c_ns, gitops_info
                            )
                            if gitops_finding:
                                findings.append(gitops_finding.model_dump())

                            try:
                                cfg = collector_config_service.parse_collector_config(
                                    item
                                )
                                inst = collector_config_service.build_collector_instance(
                                    item, cfg, detail_level=detail
                                )
                                c_dict = (
                                    inst.model_dump()
                                    if detail == "full"
                                    else inst.model_dump(exclude={"raw_config_yaml"})
                                )
                                c_dict["gitops"] = gitops_info
                                if detail == "full":
                                    try:
                                        c_dict["service_health"] = (
                                            await kubernetes_service.get_collector_service_health(
                                                namespace=c_ns,
                                                collector_name=c_name,
                                            )
                                        )
                                    except Exception:
                                        c_dict["service_health"] = {
                                            "service_found": False
                                        }
                                collectors_out.append(c_dict)
                            except Exception as e:
                                collectors_out.append({
                                    "name": c_name,
                                    "namespace": c_ns,
                                    "gitops": gitops_info,
                                    "error": f"Failed to parse config: {e}",
                                })
                        response["collectors"] = collectors_out

                    # 3. Instrumentations
                    if "instrumentations" in sections:
                        raw_instrs: List[Dict[str, Any]] = []
                        for ns in target_namespaces:
                            res = await kubernetes_service.list_instrumentations(
                                namespace=ns
                            )
                            raw_instrs.extend(res.get("items", []))

                        instrs_out: List[Dict[str, Any]] = []
                        for item in raw_instrs:
                            meta = item.get("metadata", {}) or {}
                            spec = item.get("spec", {}) or {}
                            i_name = meta.get("name", "unknown")
                            i_ns = meta.get("namespace", "default")
                            gitops_info = detect_gitops_ownership(meta)
                            configured_langs = [
                                lang
                                for lang in (
                                    "java",
                                    "python",
                                    "nodejs",
                                    "dotnet",
                                    "go",
                                )
                                if lang in spec
                            ]
                            instrs_out.append({
                                "name": i_name,
                                "namespace": i_ns,
                                "endpoint": (
                                    spec.get("exporter", {}) or {}
                                ).get("endpoint"),
                                "propagators": spec.get("propagators", []),
                                "sampler": spec.get("sampler"),
                                "languages_configured": configured_langs,
                                "gitops": gitops_info,
                            })
                        response["instrumentations"] = instrs_out

                    # 4. TargetAllocators
                    if "target_allocators" in sections:
                        raw_tas: List[Dict[str, Any]] = []
                        for ns in target_namespaces:
                            res = await kubernetes_service.list_target_allocators(
                                namespace=ns
                            )
                            raw_tas.extend(res.get("items", []))
                        response["target_allocators"] = [
                            {
                                "name": (t.get("metadata", {}) or {}).get("name"),
                                "namespace": (t.get("metadata", {}) or {}).get(
                                    "namespace"
                                ),
                                "allocation_strategy": (
                                    t.get("spec", {}) or {}
                                ).get("allocationStrategy", "consistent-hashing"),
                                "prometheus_cr_enabled": bool(
                                    ((t.get("spec", {}) or {}).get("prometheusCR") or {}).get(
                                        "enabled", False
                                    )
                                ),
                            }
                            for t in raw_tas
                        ]

                    # 5. OpAMPBridges (read-only visibility per D6)
                    if "opamp_bridges" in sections:
                        raw_bridges: List[Dict[str, Any]] = []
                        for ns in target_namespaces:
                            res = await kubernetes_service.list_opamp_bridges(
                                namespace=ns
                            )
                            raw_bridges.extend(res.get("items", []))
                        response["opamp_bridges"] = [
                            {
                                "name": (b.get("metadata", {}) or {}).get("name"),
                                "namespace": (b.get("metadata", {}) or {}).get(
                                    "namespace"
                                ),
                                "endpoint": (b.get("spec", {}) or {}).get(
                                    "endpoint"
                                ),
                                "capabilities": (b.get("spec", {}) or {}).get(
                                    "capabilities", {}
                                ),
                            }
                            for b in raw_bridges
                        ]

                    # 6. eBPF / OBI agents
                    if "ebpf_agents" in sections:
                        ebpf_pods: List[Dict[str, Any]] = []
                        seen_pods = set()
                        for ns in target_namespaces:
                            for selector in EBPF_AGENT_LABELS:
                                try:
                                    pods = await kubernetes_service.list_pods(
                                        namespace=ns, label_selector=selector
                                    )
                                    for p in pods:
                                        key = f"{p.get('namespace')}/{p.get('name')}"
                                        if key not in seen_pods:
                                            seen_pods.add(key)
                                            ebpf_pods.append({
                                                "name": p.get("name"),
                                                "namespace": p.get("namespace"),
                                                "node_name": p.get("node_name"),
                                                "phase": p.get("phase"),
                                                "host_pid": p.get("host_pid", False),
                                            })
                                except Exception:
                                    continue
                        response["ebpf_agents"] = ebpf_pods

                    # 7. Backends discovery
                    if "backends" in sections:
                        from opentelemetry_mcp_server.services.collector_config_builder import (
                            CollectorConfigBuilder,
                        )

                        builder = CollectorConfigBuilder(kubernetes_service)
                        scan_ns = namespaces or ["default", "monitoring", "observability"]
                        _, discovery_meta = await builder.discover_exporter_targets(
                            namespace=scan_ns[0],
                            signals=["traces", "metrics", "logs"],
                            scan_namespaces=scan_ns,
                        )
                        response["backends"] = discovery_meta.get(
                            "discovered_services", []
                        )

                    response["findings"] = findings
                    response["summary"] = {
                        "operator_healthy": bool(
                            (response.get("operator") or {}).get("operator_found")
                        ),
                        "collector_count": len(response.get("collectors", [])),
                        "instrumentation_count": len(
                            response.get("instrumentations", [])
                        ),
                        "target_allocator_count": len(
                            response.get("target_allocators", [])
                        ),
                        "opamp_bridge_count": len(
                            response.get("opamp_bridges", [])
                        ),
                        "ebpf_agent_count": len(response.get("ebpf_agents", [])),
                        "finding_count": len(findings),
                    }
                    return response
                except Exception as e:
                    self.handle_error(
                        e,
                        tool_name="otel_survey_cluster",
                        namespace=(namespaces[0] if namespaces else "default"),
                    )
                    raise

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="List Workloads & Instrumentation Status",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def otel_list_workloads(
                namespace: str = Field(
                    default="default",
                    min_length=1,
                    description="Kubernetes namespace to scan",
                ),
                kinds: Optional[List[str]] = Field(
                    default=None,
                    description=(
                        "Workload kinds to scan: 'Deployment', 'StatefulSet', "
                        "'DaemonSet' (all three if omitted)"
                    ),
                ),
                state: Literal[
                    "any", "instrumented", "uninstrumented", "broken"
                ] = Field(
                    default="any",
                    description=(
                        "Filter workloads by instrumentation state: "
                        "'any', 'instrumented', 'uninstrumented', or 'broken'"
                    ),
                ),
                page_size: int = Field(
                    default=50,
                    ge=1,
                    le=200,
                    description="Items per page (default 50, max 200)",
                ),
                cursor: Optional[str] = Field(
                    default=None,
                    description="Pagination cursor from previous response",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """List Kubernetes workloads and their OpenTelemetry instrumentation state.

                Scans Deployments, StatefulSets, and DaemonSets in the target
                namespace, detects programming language, auto-instrumentation
                annotations, injected initContainers, conflicting OTEL_* env vars,
                and classifies each workload as 'instrumented', 'uninstrumented',
                or 'broken'.
                """
                try:
                    workloads = await kubernetes_service.list_workloads(
                        namespace=namespace, kinds=kinds
                    )

                    items_out: List[Dict[str, Any]] = []
                    counts_by_state = {
                        "instrumented": 0,
                        "uninstrumented": 0,
                        "broken": 0,
                    }

                    for wl in workloads:
                        w_name = wl["name"]
                        w_kind = wl.get("kind", "Deployment")
                        pod_annotations = wl.get("pod_annotations", {}) or {}
                        annotated_lang = detect_language_from_annotations(
                            pod_annotations
                        )
                        cr_name = get_instrumentation_cr_from_annotations(
                            pod_annotations
                        )
                        lang = annotated_lang

                        if lang is None:
                            container_images = [
                                c.get("image", "")
                                for c in wl.get("containers", [])
                                if not c.get("is_init_container")
                            ]
                            lang = detect_language_from_images(container_images)

                        if lang is None:
                            for c in wl.get("containers", []):
                                if not c.get("is_init_container"):
                                    lang = detect_language_from_name(
                                        c.get("name", "")
                                    )
                                    if lang:
                                        break
                            if lang is None:
                                lang = detect_language_from_name(w_name)

                        if lang is None:
                            for c in wl.get("containers", []):
                                if not c.get("is_init_container"):
                                    lang = detect_language_from_runtime_env(
                                        c.get("env", {})
                                    )
                                    if lang:
                                        break

                        init_injected = any(
                            c.get("is_init_container", False)
                            and "opentelemetry"
                            in (c.get("image", "") or "").lower()
                            for c in wl.get("containers", [])
                        )

                        otel_env = False
                        all_signals: List[str] = []
                        conflicting_env: List[str] = []
                        endpoint = None

                        for c in wl.get("containers", []):
                            if c.get("is_init_container"):
                                continue
                            env = c.get("env", {}) or {}
                            if has_otel_sdk_env(env):
                                otel_env = True
                            all_signals.extend(detect_signals_from_env(env))
                            endpoint = env.get(
                                "OTEL_EXPORTER_OTLP_ENDPOINT", endpoint
                            )
                            if annotated_lang:
                                for conflict_key in _CONFLICT_ENV_VARS:
                                    if conflict_key in env:
                                        conflicting_env.append(
                                            f"{c.get('name')}:{conflict_key}"
                                        )

                        wl_findings: List[Dict[str, Any]] = []
                        gitops_info = detect_gitops_ownership({
                            "labels": wl.get("labels", {}),
                            "annotations": wl.get("annotations", {}),
                        })
                        gitops_finding = build_gitops_finding(
                            w_name, namespace, gitops_info
                        )
                        if gitops_finding:
                            wl_findings.append(gitops_finding.model_dump())

                        if conflicting_env:
                            wl_findings.append(
                                Finding.create(
                                    FindingCode.INST_CONFLICTING_ENV_OVERRIDE,
                                    message=(
                                        f"{w_kind} '{w_name}' has hardcoded OTEL_* env vars "
                                        f"({', '.join(conflicting_env)}) that override "
                                        "OpenTelemetry Operator auto-instrumentation."
                                    ),
                                    field_path="spec.template.spec.containers[*].env",
                                    remediation=(
                                        "Call otel_manage_workload_instrumentation with "
                                        "injection_options={'strip_conflicting_env': True}."
                                    ),
                                ).model_dump()
                            )

                        go_missing_exe = (
                            annotated_lang == "go"
                            and not pod_annotations.get(GO_TARGET_EXE_ANNOTATION)
                        )
                        if go_missing_exe:
                            wl_findings.append(
                                Finding.create(
                                    FindingCode.INST_GO_MISSING_TARGET_EXE,
                                    message=(
                                        f"{w_kind} '{w_name}' has inject-go annotation "
                                        f"without '{GO_TARGET_EXE_ANNOTATION}'."
                                    ),
                                    field_path=f"spec.template.metadata.annotations.{GO_TARGET_EXE_ANNOTATION}",
                                    remediation=(
                                        "Provide injection_options={'go_target_exe': '/path/to/binary'} "
                                        "to otel_manage_workload_instrumentation."
                                    ),
                                ).model_dump()
                            )

                        # Classify instrumentation state
                        if annotated_lang:
                            if conflicting_env or go_missing_exe or not init_injected:
                                inst_state = "broken"
                            else:
                                inst_state = "instrumented"
                        elif init_injected or otel_env:
                            inst_state = "instrumented"
                        else:
                            inst_state = "uninstrumented"

                        counts_by_state[inst_state] += 1

                        entry = {
                            "name": w_name,
                            "namespace": wl["namespace"],
                            "kind": w_kind,
                            "language": lang,
                            "annotated_language": annotated_lang,
                            "instrumentation_cr_name": cr_name,
                            "instrumentation_state": inst_state,
                            "init_container_injected": init_injected,
                            "sdk_env_vars_present": otel_env,
                            "conflicting_env_vars": conflicting_env,
                            "signals_detected": sorted(set(all_signals)),
                            "endpoint_configured": endpoint,
                            "ready_replicas": wl.get("ready_replicas", 0),
                            "total_replicas": wl.get("replicas", 0),
                            "gitops": gitops_info,
                            "findings": wl_findings,
                        }

                        if state == "any" or inst_state == state:
                            items_out.append(entry)

                    page_items, next_cursor = paginate(
                        items_out, page_size, cursor
                    )

                    return {
                        "items": page_items,
                        "total_count": len(items_out),
                        "counts_by_state": counts_by_state,
                        "next_cursor": next_cursor,
                        "page_size": page_size,
                    }
                except Exception as e:
                    self.handle_error(
                        e,
                        tool_name="otel_list_workloads",
                        namespace=namespace,
                    )
                    raise

        if self.should_register_tool("ui", is_write=False):

            @mcp_instance.tool(
                name="otel_query_a2ui",
                annotations=ToolAnnotations(
                    title="OpenTelemetry A2UI Pipelines",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
            )
            async def otel_query_a2ui(
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Retrieve the status of all OpenTelemetry Collectors and their pipelines.

                This tool aggregates collector configurations and deep pipeline metrics
                across the cluster and formats the result precisely for the frontend
                A2UI Status Datatable schema.

                Returns:
                - Dict[str, Any]: A JSON object matching the A2UI `kind: "otel"` schema (title, columns, rows).

                When NOT to use:
                - Do not use for general collector discovery or programmatic state checks; use `otel_survey_cluster` instead.
                - Do not use to patch or modify collector state.

                Side effects:
                - None — read-only operation.

                Common errors:
                - Kubernetes API errors if cluster access is unavailable.
                """
                try:
                    from opentelemetry_mcp_server.services.collector_metrics_service import (
                        CollectorMetricsService,
                    )

                    # Fetch all collectors
                    raw = await kubernetes_service.list_otel_collectors()
                    items = raw.get("items", [])

                    rows = []
                    metrics_service = CollectorMetricsService(kubernetes_service)

                    now = datetime.datetime.now(datetime.timezone.utc)

                    overall_status_degraded = False

                    for item in items:
                        name = item.get("metadata", {}).get("name", "unknown")
                        namespace = item.get("metadata", {}).get(
                            "namespace", "unknown"
                        )

                        # Calculate Uptime from creationTimestamp
                        creation_str = item.get("metadata", {}).get(
                            "creationTimestamp"
                        )
                        uptime_str = "Unknown"
                        if creation_str:
                            try:
                                if creation_str.endswith("Z"):
                                    creation_str = creation_str[:-1] + "+00:00"
                                created_dt = datetime.datetime.fromisoformat(
                                    creation_str
                                )
                                diff = now - created_dt
                                days, remainder = divmod(
                                    diff.total_seconds(), 86400
                                )
                                hours, _ = divmod(remainder, 3600)
                                if days > 0:
                                    uptime_str = f"{int(days)}d"
                                else:
                                    uptime_str = f"{int(hours)}h"
                            except Exception:
                                pass

                        # Parse config to find pipelines
                        try:
                            cfg = collector_config_service.parse_collector_config(
                                item
                            )
                            instance = (
                                collector_config_service.build_collector_instance(
                                    item, cfg, detail_level="summary"
                                )
                            )
                            pipelines = ", ".join(
                                p.name for p in instance.pipelines
                            )
                            if not pipelines:
                                pipelines = "None"
                            phase = instance.status.phase
                        except Exception:
                            pipelines = "Unknown"
                            phase = "Error"

                        # Fetch deep pipeline health
                        status = phase
                        try:
                            report = await metrics_service.fetch_pipeline_health(
                                namespace=namespace,
                                collector_name=name,
                                metrics_port=8888,
                            )
                            if report.healthy:
                                status = "Healthy"
                            else:
                                status = "Degraded"
                                overall_status_degraded = True
                        except Exception:
                            pass

                        rows.append({
                            "name": name,
                            "status": status,
                            "pipeline": pipelines,
                            "uptime": uptime_str,
                        })

                    return {
                        "title": "OpenTelemetry Pipelines",
                        "overallSeverity": (
                            "warning" if overall_status_degraded else "success"
                        ),
                        "overallStatusLabel": "Health",
                        "overallStatusValue": (
                            "Degraded"
                            if overall_status_degraded
                            else "Healthy"
                        ),
                        "columns": [
                            {
                                "key": "name",
                                "label": "Collector Name",
                                "sortable": True,
                            },
                            {
                                "key": "status",
                                "label": "Status",
                                "sortable": True,
                            },
                            {
                                "key": "pipeline",
                                "label": "Pipeline Type",
                                "sortable": False,
                            },
                            {
                                "key": "uptime",
                                "label": "Uptime",
                                "sortable": True,
                            },
                        ],
                        "rows": rows,
                    }
                except Exception as e:
                    raise OtelOperationError(
                        f"Failed to query OpenTelemetry A2UI pipelines: {e}"
                    )
