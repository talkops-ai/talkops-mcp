"""Unified OpenTelemetry Collector configuration and CRD linter.

Enforces structural, semantic, performance, and security invariants across
Collector YAML configs and OpenTelemetryCollector CR specs, emitting
canonical Finding objects (`CFG_*` and `SEC_*`).
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from opentelemetry_mcp_server.models.findings import (
    Finding,
    FindingCode,
    FindingSeverity,
)
from opentelemetry_mcp_server.utils.redaction import detect_inline_secrets

HIGH_CARDINALITY_ATTRIBUTE_KEYS = frozenset({
    "user.id",
    "user_id",
    "userid",
    "customer.id",
    "session.id",
    "session_id",
    "request.id",
    "request_id",
    "correlation_id",
    "trace_id",
    "span_id",
    "http.url",
    "url.full",
    "http.target",
    "url.path",
    "url.query",
    "client.address",
    "net.sock.peer.addr",
    "k8s.pod.uid",
    "k8s.pod.ip",
    "db.statement",
    "db.query.text",
})

DEPRECATED_COMPONENTS: Dict[str, str] = {
    "loki": "The 'loki' exporter is deprecated; use 'otlphttp/loki' targeting Loki's native '/otlp' endpoint.",
    "logging": "The 'logging' exporter has been removed in modern Collector releases; use the 'debug' exporter instead.",
    "jaeger": "The legacy 'jaeger' exporter has been removed; use 'otlp' or 'otlphttp' to export to Jaeger's native OTLP receiver.",
    "opencensus": "The 'opencensus' component is deprecated; migrate to 'otlp'.",
    "memory_ballast": "The 'memory_ballast' extension has been removed in Collector >= v0.111.0; use the GOMEMLIMIT environment variable (~80% of container memory limit) and memory_limiter processor instead.",
    "ballast": "The 'ballast' extension has been removed; use GOMEMLIMIT and memory_limiter instead.",
}

_REMOVED_IN_V0120 = frozenset({"logging", "jaeger", "memory_ballast", "ballast"})


def _parse_version_tuple(version_str: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse a 'v0.152.1' or '0.152.1' version tag into (major, minor)."""
    if not version_str:
        return None
    cleaned = version_str.strip().lstrip("vV")
    parts = cleaned.split(".")
    if len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def _is_external_endpoint(endpoint: str) -> bool:
    """Return True if an exporter endpoint appears external rather than cluster-local or loopback."""
    if not endpoint:
        return False
    ep = endpoint.strip().lower()
    if ep.startswith("https://"):
        host_part = ep[len("https://"):].split("/", 1)[0].split(":", 1)[0]
    elif ep.startswith("http://"):
        host_part = ep[len("http://"):].split("/", 1)[0].split(":", 1)[0]
    else:
        host_part = ep.split("/", 1)[0].split(":", 1)[0]

    if not host_part or host_part in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False
    if "." not in host_part:
        return False
    if (
        host_part.endswith(".svc")
        or ".svc." in host_part
        or host_part.endswith(".local")
        or host_part.endswith(".internal")
    ):
        return False
    if all(part.isdigit() for part in host_part.split(".")):
        return False
    return True


_HIGH_CARDINALITY_DIMENSIONS = HIGH_CARDINALITY_ATTRIBUTE_KEYS


def _base_component_type(name: str) -> str:
    """Return the component type prefix before '/' (e.g. 'otlphttp/loki' -> 'otlphttp')."""
    return name.split("/", 1)[0].strip().lower()


def lint_collector_config(
    config: Dict[str, Any],
    *,
    mode: Optional[str] = None,
    replicas: Optional[int] = None,
    cr_spec: Optional[Dict[str, Any]] = None,
    env_vars: Optional[List[Dict[str, Any]]] = None,
    volumes: Optional[List[Dict[str, Any]]] = None,
    rbac_bound: Optional[bool] = None,
    has_trace_affinity: bool = False,
    has_load_balancing_exporter: bool = False,
    target_version: Optional[str] = None,
    checks: Optional[List[str]] = None,
    custom_high_card_keys: Optional[List[str]] = None,
) -> List[Finding]:
    """Run deterministic lint checks against a parsed Collector config and optional CR spec."""
    active_checks = set(c.lower() for c in (checks or ["all"]))
    run_all = "all" in active_checks

    findings: List[Finding] = []
    if not isinstance(config, dict):
        return findings

    if cr_spec is None and (env_vars is not None or volumes is not None):
        cr_spec = {}
        if env_vars is not None:
            cr_spec["env"] = env_vars
        if volumes is not None:
            cr_spec["volumes"] = volumes
    has_trace_affinity = bool(has_trace_affinity or has_load_balancing_exporter)

    resolved_mode = (
        mode
        or (cr_spec.get("mode") if isinstance(cr_spec, dict) else None)
        or "deployment"
    ).lower()
    resolved_replicas = replicas
    if resolved_replicas is None and isinstance(cr_spec, dict):
        resolved_replicas = cr_spec.get("replicas")

    receivers: Dict[str, Any] = config.get("receivers") or {}
    processors: Dict[str, Any] = config.get("processors") or {}
    exporters: Dict[str, Any] = config.get("exporters") or {}
    connectors: Dict[str, Any] = config.get("connectors") or {}
    extensions: Dict[str, Any] = config.get("extensions") or {}
    service: Dict[str, Any] = config.get("service") or {}
    pipelines: Dict[str, Any] = service.get("pipelines") or {}
    service_extensions: List[str] = service.get("extensions") or []

    # ── 1. Referential Integrity & Unused Components ──
    if run_all or "referential" in active_checks:
        used_receivers: Set[str] = set()
        used_processors: Set[str] = set()
        used_exporters: Set[str] = set()
        used_extensions: Set[str] = set(service_extensions)

        for ext_name in service_extensions:
            if ext_name not in extensions:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_UNDEFINED_COMPONENT_REF,
                        f"service.extensions references undefined extension '{ext_name}'.",
                        component=f"service.extensions.{ext_name}",
                        evidence={"missing_extension": ext_name, "defined": list(extensions.keys())},
                        next_tool_hint="Add the extension under 'extensions:' or remove it from 'service.extensions'.",
                    )
                )

        for pname, pcfg in pipelines.items():
            if not isinstance(pcfg, dict):
                continue
            p_receivers = pcfg.get("receivers") or []
            p_processors = pcfg.get("processors") or []
            p_exporters = pcfg.get("exporters") or []

            for r in p_receivers:
                used_receivers.add(r)
                if r not in receivers and r not in connectors:
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_UNDEFINED_COMPONENT_REF,
                            f"Pipeline '{pname}' references undefined receiver/connector '{r}'.",
                            component=f"service.pipelines.{pname}.receivers",
                            evidence={
                                "pipeline": pname,
                                "missing_receiver": r,
                                "defined_receivers": list(receivers.keys()),
                                "defined_connectors": list(connectors.keys()),
                            },
                            next_tool_hint="Define the receiver in 'receivers:' or 'connectors:' before applying.",
                        )
                    )

            for proc in p_processors:
                used_processors.add(proc)
                if proc not in processors:
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_UNDEFINED_COMPONENT_REF,
                            f"Pipeline '{pname}' references undefined processor '{proc}'.",
                            component=f"service.pipelines.{pname}.processors",
                            evidence={
                                "pipeline": pname,
                                "missing_processor": proc,
                                "defined_processors": list(processors.keys()),
                            },
                            next_tool_hint="Define the processor in 'processors:' before applying.",
                        )
                    )

            for exp in p_exporters:
                used_exporters.add(exp)
                if exp not in exporters and exp not in connectors:
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_UNDEFINED_COMPONENT_REF,
                            f"Pipeline '{pname}' references undefined exporter/connector '{exp}'.",
                            component=f"service.pipelines.{pname}.exporters",
                            evidence={
                                "pipeline": pname,
                                "missing_exporter": exp,
                                "defined_exporters": list(exporters.keys()),
                                "defined_connectors": list(connectors.keys()),
                            },
                            next_tool_hint="Ensure exporter names in 'service.pipelines' match keys in 'exporters:' or 'connectors:'.",
                        )
                    )

            # Check connector loops & signal-type mismatches in the pipeline
            pipe_signal = pname.split("/", 1)[0].strip().lower()
            overlap_conns = set(p_receivers) & set(p_exporters) & set(connectors.keys())
            for loop_conn in sorted(overlap_conns):
                findings.append(
                    Finding.create(
                        FindingCode.CFG_CONNECTOR_LOOP,
                        f"Connector '{loop_conn}' is wired as both a receiver and an exporter in the same pipeline '{pname}', creating a feedback loop.",
                        component=f"service.pipelines.{pname}",
                        evidence={"pipeline": pname, "connector": loop_conn},
                        next_tool_hint=(
                            f"Wire '{loop_conn}' as an exporter in the source pipeline and as a receiver in a separate target pipeline."
                        ),
                    )
                )

            for r in p_receivers:
                if r in connectors and r not in overlap_conns:
                    c_base = _base_component_type(r)
                    if c_base in ("spanmetrics", "servicegraph") and pipe_signal != "metrics":
                        findings.append(
                            Finding.create(
                                FindingCode.CFG_CONNECTOR_LOOP,
                                f"Connector '{r}' ({c_base}) is a traces -> metrics connector and cannot be wired as a receiver in '{pname}' ({pipe_signal}).",
                                component=f"service.pipelines.{pname}.receivers",
                                evidence={"pipeline": pname, "connector": r, "expected_receiver_signal": "metrics"},
                                next_tool_hint=f"Move '{r}' to 'receivers:' of a 'metrics/{c_base}' pipeline.",
                            )
                        )
            for exp in p_exporters:
                if exp in connectors and exp not in overlap_conns:
                    c_base = _base_component_type(exp)
                    if c_base in ("spanmetrics", "servicegraph") and pipe_signal != "traces":
                        findings.append(
                            Finding.create(
                                FindingCode.CFG_CONNECTOR_LOOP,
                                f"Connector '{exp}' ({c_base}) is a traces -> metrics connector and cannot be wired as an exporter in '{pname}' ({pipe_signal}).",
                                component=f"service.pipelines.{pname}.exporters",
                                evidence={"pipeline": pname, "connector": exp, "expected_exporter_signal": "traces"},
                                next_tool_hint=f"Wire '{exp}' as an exporter only on a 'traces' pipeline.",
                            )
                        )

        # Check unused defined components
        for r in receivers:
            if r not in used_receivers:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_UNUSED_COMPONENT,
                        f"Receiver '{r}' is defined in 'receivers:' but not wired into any pipeline.",
                        component=f"receivers.{r}",
                        evidence={"component_type": "receiver", "name": r},
                    )
                )
        for proc in processors:
            if proc not in used_processors:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_UNUSED_COMPONENT,
                        f"Processor '{proc}' is defined in 'processors:' but not wired into any pipeline.",
                        component=f"processors.{proc}",
                        evidence={"component_type": "processor", "name": proc},
                    )
                )
        for exp in exporters:
            if exp not in used_exporters:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_UNUSED_COMPONENT,
                        f"Exporter '{exp}' is defined in 'exporters:' but not wired into any pipeline.",
                        component=f"exporters.{exp}",
                        evidence={"component_type": "exporter", "name": exp},
                    )
                )
        for conn in connectors:
            if conn not in used_receivers or conn not in used_exporters:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_UNUSED_COMPONENT,
                        f"Connector '{conn}' must be wired as both an exporter in a source pipeline and a receiver in a target pipeline.",
                        component=f"connectors.{conn}",
                        evidence={
                            "connector": conn,
                            "used_as_exporter": conn in used_exporters,
                            "used_as_receiver": conn in used_receivers,
                        },
                    )
                )
        for ext in extensions:
            if ext not in used_extensions:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_UNUSED_COMPONENT,
                        f"Extension '{ext}' is defined in 'extensions:' but not enabled in 'service.extensions'.",
                        component=f"extensions.{ext}",
                        evidence={"component_type": "extension", "name": ext},
                    )
                )

    # ── 2. Processor Order & Batching Invariants ──
    if run_all or "processor_order" in active_checks or "resiliency" in active_checks:
        for pname, pcfg in pipelines.items():
            if not isinstance(pcfg, dict):
                continue
            p_processors = pcfg.get("processors") or []
            p_exporters = pcfg.get("exporters") or []

            has_mem_limiter_first = bool(
                p_processors and _base_component_type(p_processors[0]) == "memory_limiter"
            )
            if not has_mem_limiter_first:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_MEMORY_LIMITER_NOT_FIRST,
                        f"Pipeline '{pname}' does not place 'memory_limiter' as the first processor (found: {p_processors}).",
                        component=f"service.pipelines.{pname}.processors",
                        evidence={"pipeline": pname, "processors": p_processors},
                        next_tool_hint="Place 'memory_limiter' at index 0 of every pipeline's processor chain to prevent OOM crashes.",
                    )
                )

            has_batch_proc = any(
                _base_component_type(proc) == "batch" for proc in p_processors
            )
            if has_batch_proc:
                for exp in p_exporters:
                    exp_cfg = exporters.get(exp)
                    if isinstance(exp_cfg, dict):
                        sq = exp_cfg.get("sending_queue")
                        if isinstance(sq, dict) and "batch" in sq:
                            findings.append(
                                Finding.create(
                                    FindingCode.CFG_DOUBLE_BATCHING,
                                    f"Pipeline '{pname}' uses both the 'batch' processor and exporter '{exp}' sending_queue.batch.",
                                    component=f"service.pipelines.{pname}",
                                    evidence={"pipeline": pname, "exporter": exp},
                                    next_tool_hint="Remove the 'batch' processor when using exporter-level sending_queue.batch.",
                                )
                            )

            # Check if pipeline only exports to debug/nop
            real_exporters = [
                e for e in p_exporters
                if _base_component_type(e) not in ("debug", "logging", "nop")
            ]
            if p_exporters and not real_exporters:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_DEBUG_EXPORTER_ONLY,
                        f"Pipeline '{pname}' exports only to debug/nop ({p_exporters}); telemetry is not persisted to a backend.",
                        component=f"service.pipelines.{pname}.exporters",
                        evidence={"pipeline": pname, "exporters": p_exporters},
                    )
                )

    # ── 3. Exporter Resiliency (sending_queue / remote_write_queue & retry_on_failure) ──
    if run_all or "resiliency" in active_checks:
        for exp_name, exp_cfg in exporters.items():
            base_type = _base_component_type(exp_name)
            if base_type in ("debug", "logging", "nop", "prometheus", "loadbalancing"):
                continue
            if not isinstance(exp_cfg, dict):
                exp_cfg = {}
            if base_type == "prometheusremotewrite":
                rwq = exp_cfg.get("remote_write_queue")
                sq = exp_cfg.get("sending_queue")
                if isinstance(sq, dict):
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_DEPRECATED_COMPONENT,
                            f"Exporter '{exp_name}' sets invalid key 'sending_queue'; prometheusremotewrite uses 'remote_write_queue'.",
                            component=f"exporters.{exp_name}.sending_queue",
                            severity=FindingSeverity.ERROR,
                            evidence={"exporter": exp_name, "invalid_key": "sending_queue"},
                            next_tool_hint="Replace 'sending_queue' with 'remote_write_queue: {enabled: true, queue_size: 1000, num_consumers: 4}'.",
                        )
                    )
                elif not isinstance(rwq, dict) or rwq.get("enabled") is False:
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_NO_SENDING_QUEUE,
                            f"Exporter '{exp_name}' does not configure an enabled 'remote_write_queue'.",
                            component=f"exporters.{exp_name}",
                            evidence={"exporter": exp_name},
                            next_tool_hint="Configure 'remote_write_queue: {enabled: true, queue_size: 1000, num_consumers: 4}' on prometheusremotewrite exporters.",
                        )
                    )
            else:
                sq = exp_cfg.get("sending_queue")
                if not isinstance(sq, dict) or sq.get("enabled") is False:
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_NO_SENDING_QUEUE,
                            f"Exporter '{exp_name}' does not configure an enabled 'sending_queue'.",
                            component=f"exporters.{exp_name}",
                            evidence={"exporter": exp_name},
                            next_tool_hint="Configure 'sending_queue: {enabled: true, queue_size: 1000}' on production exporters.",
                        )
                    )
            retry = exp_cfg.get("retry_on_failure")
            if not isinstance(retry, dict) or retry.get("enabled") is False:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_NO_RETRY,
                        f"Exporter '{exp_name}' does not configure 'retry_on_failure'.",
                        component=f"exporters.{exp_name}",
                        evidence={"exporter": exp_name},
                        next_tool_hint="Configure 'retry_on_failure: {enabled: true}' on production exporters.",
                    )
                )

    # ── 4. Deprecations (telemetry.metrics.address & deprecated components) ──
    if run_all or "deprecations" in active_checks:
        ver_tuple = _parse_version_tuple(target_version)
        strict_modern = ver_tuple is not None and ver_tuple >= (0, 120)
        telemetry = service.get("telemetry") or {}
        metrics_tel = telemetry.get("metrics") if isinstance(telemetry, dict) else None
        if isinstance(metrics_tel, dict) and "address" in metrics_tel:
            findings.append(
                Finding.create(
                    FindingCode.CFG_DEPRECATED_TELEMETRY_ADDRESS,
                    "service.telemetry.metrics.address is deprecated and rejected in Collector >= v0.120.0; use service.telemetry.metrics.readers.",
                    component="service.telemetry.metrics.address",
                    severity=FindingSeverity.ERROR if strict_modern else FindingSeverity.WARNING,
                    evidence={
                        "address": metrics_tel.get("address"),
                        "target_version": target_version,
                    },
                    next_tool_hint="Replace 'service.telemetry.metrics.address' with 'service.telemetry.metrics.readers' pull prometheus config.",
                )
            )

        for section_name, section_dict in (
            ("receivers", receivers),
            ("processors", processors),
            ("exporters", exporters),
            ("extensions", extensions),
        ):
            for comp_name in section_dict:
                base_type = _base_component_type(comp_name)
                if base_type in DEPRECATED_COMPONENTS:
                    dep_sev = (
                        FindingSeverity.ERROR
                        if (strict_modern and base_type in _REMOVED_IN_V0120)
                        else FindingSeverity.WARNING
                    )
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_DEPRECATED_COMPONENT,
                            f"{section_name}.{comp_name}: {DEPRECATED_COMPONENTS[base_type]}",
                            component=f"{section_name}.{comp_name}",
                            severity=dep_sev,
                            evidence={"component": comp_name, "type": base_type, "target_version": target_version},
                        )
                    )

    # ── 5. k8sattributes Enrichment & RBAC ──
    if run_all or "enrichment" in active_checks:
        for proc_name, proc_cfg in processors.items():
            if _base_component_type(proc_name) != "k8sattributes":
                continue
            if not isinstance(proc_cfg, dict):
                proc_cfg = {}
            if resolved_mode == "daemonset":
                filt = proc_cfg.get("filter") or {}
                if not isinstance(filt, dict) or not filt.get("node_from_env_var"):
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_K8SATTR_NO_NODE_FILTER,
                            f"DaemonSet collector uses '{proc_name}' without 'filter.node_from_env_var: K8S_NODE_NAME', causing every agent pod to watch all cluster pods.",
                            component=f"processors.{proc_name}.filter",
                            evidence={"mode": resolved_mode, "processor": proc_name},
                            next_tool_hint="Set 'filter.node_from_env_var: K8S_NODE_NAME' and inject K8S_NODE_NAME from spec.nodeName.",
                        )
                    )
            if rbac_bound is False:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_K8SATTR_RBAC_MISSING,
                        f"Processor '{proc_name}' is enabled, but the ClusterRoleBinding for k8sattributes was not found.",
                        component=f"processors.{proc_name}",
                        evidence={"processor": proc_name, "rbac_bound": False},
                        next_tool_hint="Call otel_provision_collector or otel_configure_receivers to provision least-privilege RBAC.",
                    )
                )

    # ── 6. Filelog Safety (Self-Exclusion & Persistent Checkpoints) ──
    if run_all or "filelog" in active_checks:
        for rec_name, rec_cfg in receivers.items():
            if _base_component_type(rec_name) != "filelog":
                continue
            if not isinstance(rec_cfg, dict):
                rec_cfg = {}
            includes = rec_cfg.get("include") or []
            excludes = rec_cfg.get("exclude") or []
            if any("/var/log/pods" in str(inc) or "/var/log/containers" in str(inc) for inc in includes):
                if not excludes:
                    findings.append(
                        Finding.create(
                            FindingCode.CFG_FILELOG_NO_SELF_EXCLUDE,
                            f"Receiver '{rec_name}' tails container logs without an 'exclude' pattern for the collector's own pod logs (infinite log loop).",
                            component=f"receivers.{rec_name}.exclude",
                            evidence={"include": includes, "exclude": excludes},
                            next_tool_hint="Add an 'exclude' glob matching the collector's own pod logs under /var/log/pods.",
                        )
                    )

            storage_ext = rec_cfg.get("storage")
            ephemeral_volume = False
            if isinstance(cr_spec, dict):
                for vol in cr_spec.get("volumes") or []:
                    if isinstance(vol, dict) and vol.get("name") in ("file-storage", "varlibotelcol") and "emptyDir" in vol:
                        ephemeral_volume = True
            if not storage_ext or storage_ext not in extensions or ephemeral_volume:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_FILELOG_EPHEMERAL_CHECKPOINT,
                        f"Receiver '{rec_name}' uses missing or ephemeral checkpoint storage (storage={storage_ext!r}, emptyDir={ephemeral_volume}). Pod restarts will re-ingest or drop logs.",
                        component=f"receivers.{rec_name}.storage",
                        evidence={"storage": storage_ext, "ephemeral_volume": ephemeral_volume},
                        next_tool_hint="Configure 'storage: file_storage' backed by a hostPath DirectoryOrCreate volume on DaemonSet nodes.",
                    )
                )

    # ── 7. Tail Sampling Trace Affinity ──
    if run_all or "sampling" in active_checks:
        has_tail_sampling = any(
            _base_component_type(p) == "tail_sampling" for p in processors
        )
        has_lb_exporter = any(
            _base_component_type(e) == "loadbalancing" for e in exporters
        )
        if has_tail_sampling and not has_trace_affinity and not has_lb_exporter:
            if resolved_mode == "daemonset" or (resolved_replicas is not None and resolved_replicas > 1):
                findings.append(
                    Finding.create(
                        FindingCode.CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY,
                        f"tail_sampling is configured on mode='{resolved_mode}' (replicas={resolved_replicas}) without traceID-aware load-balancing.",
                        component="processors.tail_sampling",
                        evidence={
                            "mode": resolved_mode,
                            "replicas": resolved_replicas,
                            "has_trace_affinity": has_trace_affinity,
                        },
                        next_tool_hint=(
                            "Deploy a StatefulSet tail-sampler tier with a headless Service and route spans to it "
                            "via a 'loadbalancing' exporter (routing_key: traceID), or set replicas=1."
                        ),
                    )
                )

    # ── 8. Cardinality & Prometheus Scrape Duplication ──
    if run_all or "cardinality" in active_checks:
        high_card_set = set(HIGH_CARDINALITY_ATTRIBUTE_KEYS)
        if custom_high_card_keys:
            high_card_set.update(k.lower().strip() for k in custom_high_card_keys)

        for conn_name, conn_cfg in connectors.items():
            base_type = _base_component_type(conn_name)
            if base_type not in ("spanmetrics", "servicegraph"):
                continue
            if not isinstance(conn_cfg, dict):
                continue
            dims = conn_cfg.get("dimensions") or []
            bad_dims: List[str] = []
            for d in dims:
                d_name = d.get("name", "") if isinstance(d, dict) else str(d)
                if d_name.lower().strip() in high_card_set:
                    bad_dims.append(d_name)
            if bad_dims:
                findings.append(
                    Finding.create(
                        FindingCode.CFG_SPANMETRICS_HIGH_CARD_DIMENSION,
                        f"Connector '{conn_name}' includes high-cardinality dimension(s): {bad_dims}.",
                        component=f"connectors.{conn_name}.dimensions",
                        evidence={"connector": conn_name, "high_cardinality_dimensions": bad_dims},
                        next_tool_hint="Remove unbounded dimensions from connector configuration using otel_configure_connectors.",
                    )
                )

        has_prom_receiver = any(
            _base_component_type(r) == "prometheus" for r in receivers
        )
        if has_prom_receiver:
            ta_cfg = (cr_spec or {}).get("targetAllocator") if isinstance(cr_spec, dict) else None
            ta_enabled = bool(isinstance(ta_cfg, dict) and ta_cfg.get("enabled"))
            ta_strategy = ta_cfg.get("allocationStrategy") if isinstance(ta_cfg, dict) else None
            if (resolved_mode == "daemonset" and (not ta_enabled or ta_strategy != "per-node")) or (
                (resolved_replicas or 1) > 1 and not ta_enabled
            ):
                findings.append(
                    Finding.create(
                        FindingCode.CFG_PROM_SCRAPE_DUPLICATION,
                        f"Prometheus receiver is active on mode='{resolved_mode}' (replicas={resolved_replicas}) without Target Allocator sharding (enabled={ta_enabled}, strategy={ta_strategy}).",
                        component="receivers.prometheus",
                        evidence={
                            "mode": resolved_mode,
                            "replicas": resolved_replicas,
                            "target_allocator_enabled": ta_enabled,
                            "allocation_strategy": ta_strategy,
                        },
                        next_tool_hint="Enable Target Allocator ('consistent-hashing' for StatefulSet or 'per-node' for DaemonSet) via otel_configure_receivers.",
                    )
                )

    # ── 9. GOMEMLIMIT & Security Checks (Inline Secrets, TLS Verify) ──
    if run_all or "security" in active_checks:
        inline_secrets = detect_inline_secrets(config, path="config")
        if isinstance(cr_spec, dict):
            # Also check spec.env for literal secrets
            for idx, env_item in enumerate(cr_spec.get("env") or []):
                inline_secrets.extend(detect_inline_secrets(env_item, path=f"spec.env[{idx}]"))

        if inline_secrets:
            findings.append(
                Finding.create(
                    FindingCode.SEC_INLINE_SECRET,
                    f"Detected {len(inline_secrets)} hardcoded credential/secret value(s) in configuration.",
                    component=inline_secrets[0]["path"],
                    evidence={"secrets": inline_secrets},
                    next_tool_hint="Replace plaintext credentials with '${env:VAR_NAME}' and inject via Kubernetes Secret secretKeyRef.",
                )
            )

        for section_name, section_dict in (("exporters", exporters), ("receivers", receivers)):
            for comp_name, comp_cfg in section_dict.items():
                if not isinstance(comp_cfg, dict):
                    continue
                tls_blocks: List[Tuple[str, Dict[str, Any]]] = []
                if isinstance(comp_cfg.get("tls"), dict):
                    tls_blocks.append((f"{section_name}.{comp_name}.tls", comp_cfg["tls"]))
                for proto in ("http", "grpc"):
                    sub = comp_cfg.get(proto)
                    if isinstance(sub, dict) and isinstance(sub.get("tls"), dict):
                        tls_blocks.append((f"{section_name}.{comp_name}.{proto}.tls", sub["tls"]))
                for tls_path, tls_cfg in tls_blocks:
                    if tls_cfg.get("insecure_skip_verify") is True:
                        findings.append(
                            Finding.create(
                                FindingCode.SEC_TLS_VERIFY_DISABLED,
                                f"TLS certificate verification is disabled ('insecure_skip_verify: true') at '{tls_path}'.",
                                component=tls_path,
                                evidence={"path": tls_path, "insecure_skip_verify": True},
                                next_tool_hint="Remove 'insecure_skip_verify: true' and configure 'ca_file' or trusted system certificates.",
                            )
                        )
                    if section_name == "exporters" and tls_cfg.get("insecure") is True:
                        raw_ep = str(
                            comp_cfg.get("endpoint")
                            or (comp_cfg.get("http") or {}).get("endpoint")
                            or ""
                        )
                        if _is_external_endpoint(raw_ep):
                            findings.append(
                                Finding.create(
                                    FindingCode.SEC_INSECURE_EXPORTER,
                                    f"External exporter '{comp_name}' ('{raw_ep}') disables TLS transport security ('tls.insecure: true').",
                                    component=tls_path,
                                    evidence={"exporter": comp_name, "endpoint": raw_ep, "insecure": True},
                                    next_tool_hint="Set 'tls.insecure: false' on external endpoints so OTLP payloads are encrypted in transit.",
                                )
                            )

        for ext_name, ext_cfg in extensions.items():
            if _base_component_type(ext_name) not in ("pprof", "zpages"):
                continue
            if not isinstance(ext_cfg, dict):
                continue
            ext_ep = str(ext_cfg.get("endpoint", "")).strip()
            if ext_ep.startswith("0.0.0.0:") or ext_ep.startswith(":"):
                findings.append(
                    Finding.create(
                        FindingCode.SEC_DEBUG_EXTENSION_EXPOSED,
                        f"Diagnostic extension '{ext_name}' binds to all interfaces ('{ext_ep}') instead of loopback '127.0.0.1'.",
                        component=f"extensions.{ext_name}.endpoint",
                        evidence={"extension": ext_name, "endpoint": ext_ep},
                        next_tool_hint="Bind pprof and zpages extensions strictly to '127.0.0.1' or disable them in production.",
                    )
                )

    if (run_all or "resiliency" in active_checks) and isinstance(cr_spec, dict):
        env_list = cr_spec.get("env") or []
        has_gomemlimit = any(
            isinstance(e, dict) and e.get("name") == "GOMEMLIMIT"
            for e in env_list
        )
        if not has_gomemlimit:
            findings.append(
                Finding.create(
                    FindingCode.CFG_NO_GOMEMLIMIT,
                    "Collector spec.env does not set GOMEMLIMIT (~80% of container memory limit).",
                    component="spec.env",
                    evidence={"env_names": [e.get("name") for e in env_list if isinstance(e, dict)]},
                    next_tool_hint="Add GOMEMLIMIT to collector env (e.g. '400MiB' for a 512Mi memory limit) to prevent Go runtime OOMs.",
                )
            )

    return findings
