"""Pipeline receiver and OTTL processing configuration tools.

Provides:
- ``otel_configure_receivers``: Configure infrastructure and log receivers
  (kubeletstats, hostmetrics, k8s_cluster, k8s_events/k8sobjects, filelog,
  prometheus_ta) with hostPath mounts and least-privilege RBAC.
- ``otel_configure_processing``: Configure OTTL transform and filter
  processors for JSON log parsing, PII masking, high-cardinality attribute
  dropping, and health-check noise filtering.
"""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelValidationError,
)
from opentelemetry_mcp_server.services.collector_config_builder import (
    CollectorConfigBuilder,
)
from opentelemetry_mcp_server.services.config_linter import lint_collector_config
from opentelemetry_mcp_server.tools.base import (
    BaseTool,
    confirm_destructive_action,
)
from opentelemetry_mcp_server.utils.config_merger import merge_processor
from opentelemetry_mcp_server.utils.gitops import (
    build_gitops_finding,
    detect_gitops_ownership,
)
from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

_VALID_RECEIVERS = {
    "kubeletstats",
    "hostmetrics",
    "k8s_cluster",
    "k8s_events",
    "k8sobjects",
    "filelog",
    "prometheus_ta",
}

# Curated PII regex pattern registry (used by generate_log_transform_config)
_PII_PATTERNS: Dict[str, Dict[str, str]] = {
    "ssn": {
        "description": "US Social Security Number (XXX-XX-XXXX)",
        "regex": r"\\d{3}-\\d{2}-\\d{4}",
        "replacement": "***-**-****",
    },
    "credit_card": {
        "description": "Credit card number (16 digits with optional separators)",
        "regex": r"\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}",
        "replacement": "****-****-****-****",
    },
    "email": {
        "description": "Email address",
        "regex": r"[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}",
        "replacement": "[REDACTED_EMAIL]",
    },
    "ipv4": {
        "description": "IPv4 address",
        "regex": r"\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}",
        "replacement": "[REDACTED_IP]",
    },
    "phone_us": {
        "description": "US phone number (+1-XXX-XXX-XXXX or similar)",
        "regex": r"\\+?1?[\\s.-]?\\(?\\d{3}\\)?[\\s.-]?\\d{3}[\\s.-]?\\d{4}",
        "replacement": "[REDACTED_PHONE]",
    },
    "jwt": {
        "description": "JSON Web Token (eyJ... pattern)",
        "regex": r"eyJ[A-Za-z0-9_-]+\\.eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+",
        "replacement": "[REDACTED_JWT]",
    },
    "bearer_token": {
        "description": "Bearer auth token in headers",
        "regex": r"Bearer\\s+[A-Za-z0-9._~+/=-]+",
        "replacement": "Bearer [REDACTED]",
    },
    "url_query_secrets": {
        "description": "OAuth/API secrets in URL query parameters (api_key, access_token, code, secret, password, token)",
        "regex": r"(?i)([?&](?:api_key|access_token|code|secret|password|token)=)[^&\\s\"']+",
        "replacement": "${1}[REDACTED]",
    },
}


def generate_log_transform_config(
    mask_patterns: Optional[List[str]] = None,
    parse_json: bool = True,
    extract_fields: Optional[List[str]] = None,
    custom_mask_rules: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Generate a transform processor config for log processing."""
    statements: List[str] = []

    if parse_json:
        statements.append(
            'merge_maps(cache, ParseJSON(body), "upsert") '
            'where IsMatch(body, "^\\\\{")'
        )
        if extract_fields:
            for field_name in extract_fields:
                safe_attr = field_name.replace(".", "_")
                statements.append(
                    f'set(attributes["{safe_attr}"], cache["{field_name}"]) '
                    f'where cache["{field_name}"] != nil'
                )
        statements.append("set(body, cache) where cache != nil")

    if mask_patterns:
        for pattern_name in mask_patterns:
            pattern = _PII_PATTERNS.get(pattern_name)
            if not pattern:
                continue
            statements.append(
                f'replace_pattern(body, "{pattern["regex"]}", '
                f'"{pattern["replacement"]}") '
                "where IsString(body)"
            )

    if custom_mask_rules:
        for rule in custom_mask_rules:
            target = rule.get("field", "body")
            regex = rule.get("regex", "")
            replacement = rule.get("replacement", "[REDACTED]")
            if not regex:
                continue
            if target == "body":
                statements.append(
                    f'replace_pattern(body, "{regex}", "{replacement}") '
                    "where IsString(body)"
                )
            else:
                statements.append(
                    f'replace_pattern(attributes["{target}"], '
                    f'"{regex}", "{replacement}") '
                    f'where attributes["{target}"] != nil'
                )

    if not statements:
        return {}

    return {
        "processors": {
            "transform/log_processing": {
                "error_mode": "ignore",
                "log_statements": [
                    {
                        "context": "log",
                        "statements": statements,
                    }
                ],
            }
        }
    }


class LogTransformTools(BaseTool):
    """Pipeline receiver and OTTL processing tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("pipeline", is_write=True):
            return

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Collector Receivers & RBAC",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_configure_receivers(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            receivers: List[str] = Field(
                ...,
                min_length=1,
                description=(
                    "Receivers to enable: 'kubeletstats', 'hostmetrics', "
                    "'k8s_cluster', 'k8s_events' (or 'k8sobjects'), 'filelog', "
                    "'prometheus_ta'"
                ),
            ),
            receiver_options: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Optional receiver settings dict supporting keys: "
                    "'collection_interval' (str), 'service_monitor_selector' (dict), "
                    "'pod_monitor_selector' (dict), 'replicas' (int)"
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, previews the receiver config, volume mounts, and RBAC "
                    "without applying. Set False after reviewing."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description=(
                    "Set True to confirm applying receiver and RBAC changes "
                    "when dry_run=False"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Configure Kubernetes infrastructure, log, and Prometheus TA receivers.

            Wires kubeletstats, hostmetrics, k8s_cluster, k8sobjects (events),
            filelog (with persistent hostPath file_storage), and Prometheus Target
            Allocator into an existing OpenTelemetryCollector CRD and generates
            the required least-privilege ClusterRole / ClusterRoleBinding.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_configure_receivers")

                invalid = set(receivers) - _VALID_RECEIVERS
                if invalid:
                    raise OtelValidationError(
                        f"Unsupported receivers: {invalid}. "
                        f"Supported: {sorted(_VALID_RECEIVERS)}"
                    )

                opts = dict(receiver_options or {})
                raw = await kubernetes_service.get_otel_collector(
                    namespace, collector_name
                )
                current_cfg = collector_config_service.parse_collector_config(
                    raw
                )
                spec = dict(raw.get("spec", {}) or {})
                mode = str(spec.get("mode", "deployment")).lower()

                gitops_info = detect_gitops_ownership(raw.get("metadata"))
                gitops_finding = build_gitops_finding(
                    collector_name, namespace, gitops_info
                )

                receivers_cfg = dict(current_cfg.get("receivers", {}) or {})
                extensions_cfg = dict(current_cfg.get("extensions", {}) or {})
                service_cfg = dict(current_cfg.get("service", {}) or {})
                pipelines_cfg = dict(service_cfg.get("pipelines", {}) or {})
                service_exts = list(service_cfg.get("extensions", []) or [])

                volumes = list(spec.get("volumes", []) or [])
                volume_mounts = list(spec.get("volumeMounts", []) or [])
                env_list = list(spec.get("env", []) or [])

                def _ensure_pipeline_receiver(
                    signal_prefix: str, rec_name: str
                ) -> None:
                    matched_pipe = None
                    for pname, pcfg in pipelines_cfg.items():
                        if pname == signal_prefix or pname.startswith(
                            f"{signal_prefix}/"
                        ):
                            matched_pipe = pname
                            break
                    if not matched_pipe:
                        default_procs = [
                            p
                            for p in ["memory_limiter", "k8sattributes", "batch"]
                            if p in (current_cfg.get("processors") or {})
                        ]
                        default_exps = list(
                            (current_cfg.get("exporters") or {}).keys()
                        )[:1] or ["debug"]
                        pipelines_cfg[signal_prefix] = {
                            "receivers": [rec_name],
                            "processors": default_procs,
                            "exporters": default_exps,
                        }
                    else:
                        recs = list(
                            pipelines_cfg[matched_pipe].get("receivers", [])
                        )
                        if rec_name not in recs:
                            recs.append(rec_name)
                            pipelines_cfg[matched_pipe]["receivers"] = recs

                collection_interval = opts.get("collection_interval")

                for rec in receivers:
                    if rec == "kubeletstats":
                        cfg_block = (
                            CollectorConfigBuilder._build_kubeletstats_receiver()
                        )
                        if collection_interval:
                            cfg_block["collection_interval"] = str(
                                collection_interval
                            )
                        receivers_cfg["kubeletstats"] = cfg_block
                        _ensure_pipeline_receiver("metrics", "kubeletstats")
                        if not any(
                            e.get("name") == "K8S_NODE_NAME"
                            for e in env_list
                            if isinstance(e, dict)
                        ):
                            env_list.append({
                                "name": "K8S_NODE_NAME",
                                "valueFrom": {
                                    "fieldRef": {"fieldPath": "spec.nodeName"}
                                },
                            })
                    elif rec == "hostmetrics":
                        cfg_block = (
                            CollectorConfigBuilder._build_hostmetrics_receiver()
                        )
                        if collection_interval:
                            cfg_block["collection_interval"] = str(
                                collection_interval
                            )
                        receivers_cfg["hostmetrics"] = cfg_block
                        _ensure_pipeline_receiver("metrics", "hostmetrics")
                        if not any(
                            v.get("name") == "hostfs"
                            for v in volumes
                            if isinstance(v, dict)
                        ):
                            volumes.append({
                                "name": "hostfs",
                                "hostPath": {"path": "/"},
                            })
                            volume_mounts.append({
                                "name": "hostfs",
                                "mountPath": "/hostfs",
                                "readOnly": True,
                            })
                    elif rec == "k8s_cluster":
                        cfg_block = (
                            CollectorConfigBuilder._build_k8s_cluster_receiver()
                        )
                        if collection_interval:
                            cfg_block["collection_interval"] = str(
                                collection_interval
                            )
                        receivers_cfg["k8s_cluster"] = cfg_block
                        _ensure_pipeline_receiver("metrics", "k8s_cluster")
                    elif rec in ("k8s_events", "k8sobjects"):
                        receivers_cfg["k8sobjects"] = (
                            CollectorConfigBuilder._build_k8sobjects_receiver()
                        )
                        _ensure_pipeline_receiver("logs", "k8sobjects")
                    elif rec == "filelog":
                        receivers_cfg["filelog"] = (
                            CollectorConfigBuilder._build_filelog_receiver(
                                namespace, collector_name
                            )
                        )
                        extensions_cfg["file_storage"] = {
                            "directory": "/var/lib/otelcol/file_storage",
                            "timeout": "10s",
                        }
                        if "file_storage" not in service_exts:
                            service_exts.append("file_storage")
                        _ensure_pipeline_receiver("logs", "filelog")
                        if not any(
                            v.get("name") == "varlogpods"
                            for v in volumes
                            if isinstance(v, dict)
                        ):
                            volumes.append({
                                "name": "varlogpods",
                                "hostPath": {"path": "/var/log/pods"},
                            })
                            volume_mounts.append({
                                "name": "varlogpods",
                                "mountPath": "/var/log/pods",
                                "readOnly": True,
                            })
                        # Ensure persistent hostPath for file-storage (fixes B4)
                        volumes = [
                            v
                            for v in volumes
                            if isinstance(v, dict)
                            and v.get("name") != "file-storage"
                        ]
                        volumes.append({
                            "name": "file-storage",
                            "hostPath": {
                                "path": "/var/lib/otelcol/file_storage",
                                "type": "DirectoryOrCreate",
                            },
                        })
                        if not any(
                            vm.get("name") == "file-storage"
                            for vm in volume_mounts
                            if isinstance(vm, dict)
                        ):
                            volume_mounts.append({
                                "name": "file-storage",
                                "mountPath": "/var/lib/otelcol/file_storage",
                            })
                    elif rec == "prometheus_ta":
                        receivers_cfg["prometheus"] = (
                            CollectorConfigBuilder._build_prometheus_receiver()
                        )
                        _ensure_pipeline_receiver("metrics", "prometheus")
                        if mode != "statefulset":
                            mode = "statefulset"
                            spec["mode"] = "statefulset"
                        if opts.get("replicas") is not None:
                            spec["replicas"] = int(opts["replicas"])
                        spec["targetAllocator"] = {
                            "enabled": True,
                            "allocationStrategy": "consistent-hashing",
                            "prometheusCR": {
                                "enabled": True,
                                "serviceMonitorSelector": opts.get(
                                    "service_monitor_selector", {}
                                ),
                                "podMonitorSelector": opts.get(
                                    "pod_monitor_selector", {}
                                ),
                            },
                        }

                updated_cfg = dict(current_cfg)
                updated_cfg["receivers"] = receivers_cfg
                if extensions_cfg:
                    updated_cfg["extensions"] = extensions_cfg
                service_cfg["pipelines"] = pipelines_cfg
                if service_exts:
                    service_cfg["extensions"] = service_exts
                updated_cfg["service"] = service_cfg

                spec["config"] = updated_cfg
                if volumes:
                    spec["volumes"] = volumes
                if volume_mounts:
                    spec["volumeMounts"] = volume_mounts
                if env_list:
                    spec["env"] = env_list

                findings = lint_collector_config(
                    updated_cfg,
                    mode=mode,
                    replicas=int(spec.get("replicas", 1) or 1),
                    cr_spec=spec,
                    env_vars=env_list,
                    volumes=volumes,
                    rbac_bound=True,
                )
                if gitops_finding:
                    findings.append(gitops_finding)

                include_k8sattr = "k8sattributes" in (
                    updated_cfg.get("processors") or {}
                )
                ta_enabled = bool(
                    (spec.get("targetAllocator") or {}).get("enabled", False)
                )
                rbac_manifests = (
                    kubernetes_service.build_receiver_rbac_manifests(
                        namespace=namespace,
                        collector_name=collector_name,
                        receivers=receivers,
                        include_k8sattributes=include_k8sattr,
                        target_allocator_enabled=ta_enabled,
                    )
                )
                rbac_yaml = config_to_yaml([
                    rbac_manifests["cluster_role"],
                    rbac_manifests["cluster_role_binding"],
                ])

                if dry_run:
                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": True,
                        "action": "dry_run",
                        "mode": mode,
                        "replicas": spec.get("replicas", 1),
                        "target_allocator": spec.get("targetAllocator"),
                        "receivers_configured": receivers,
                        "config_snippet": config_to_yaml(
                            {"receivers": {r: receivers_cfg[r] for r in receivers_cfg if r in receivers or (r == "k8sobjects" and "k8s_events" in receivers) or (r == "prometheus" and "prometheus_ta" in receivers)}}
                        ),
                        "rbac_yaml": rbac_yaml,
                        "findings": [f.model_dump() for f in findings],
                        "message": (
                            "Review receiver config, targetAllocator spec, and RBAC above. "
                            "Call otel_configure_receivers with dry_run=False, confirm=True to apply."
                        ),
                    }

                if gitops_info.get("managed"):
                    confirmed = await confirm_destructive_action(
                        ctx,
                        f"Configure receivers on GitOps-managed collector "
                        f"'{namespace}/{collector_name}'",
                        confirm=confirm,
                    )
                    if not confirmed:
                        return {
                            "collector": f"{namespace}/{collector_name}",
                            "dry_run": False,
                            "action": "confirmation_required",
                            "findings": [f.model_dump() for f in findings],
                            "message": (
                                f"Collector '{namespace}/{collector_name}' is managed by "
                                f"{gitops_info.get('manager')}. Pass confirm=True to apply."
                            ),
                        }

                await kubernetes_service.create_or_patch_collector(
                    namespace=namespace,
                    name=collector_name,
                    spec=spec,
                    dry_run=False,
                )
                rbac_result = await kubernetes_service.create_receiver_rbac(
                    namespace=namespace,
                    collector_name=collector_name,
                    receivers=receivers,
                    include_k8sattributes=include_k8sattr,
                    target_allocator_enabled=ta_enabled,
                    dry_run=False,
                )

                return {
                    "collector": f"{namespace}/{collector_name}",
                    "dry_run": False,
                    "action": "applied",
                    "receivers_configured": receivers,
                    "rbac_result": rbac_result,
                    "findings": [f.model_dump() for f in findings],
                    "message": (
                        f"Configured receivers {receivers} and updated RBAC "
                        f"for collector '{collector_name}'."
                    ),
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_configure_receivers",
                    namespace=namespace,
                    resource_name=collector_name,
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure OTTL Processing & Noise Filtering",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_configure_processing(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            signals: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Signals to apply processing rules to: 'logs', 'metrics', "
                    "'traces' (defaults based on rule types)"
                ),
            ),
            rules: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Processing rules dict supporting keys: "
                    "'parse_json' (bool), 'extract_fields' (list of JSON keys), "
                    "'mask_pii' (list from ['ssn', 'credit_card', 'email', 'ipv4', "
                    "'phone_us', 'jwt', 'bearer_token', 'url_query_secrets']), "
                    "'custom_mask_rules' (list of {'field', 'regex', 'replacement'}), "
                    "'drop_attributes' (list of attribute keys to delete), "
                    "'drop_noise_paths' (list of URL paths like ['/healthz', '/readyz', '/metrics']), "
                    "'preserve_errors' (bool, default True — keeps 4xx/5xx/STATUS_CODE_ERROR probe spans when dropping noise paths), "
                    "'filter_conditions' (dict of custom OTTL filter expressions by signal: {'traces': [...], 'logs': [...], 'metrics': [...]}), "
                    "'ottl_statements' (list of raw OTTL statements)"
                ),
            ),
            target_pipelines: Optional[List[str]] = Field(
                default=None,
                description="Explicit pipeline names to wire processors into (auto-selected if omitted)",
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, returns the generated OTTL processor snippet without applying. "
                    "Set False to merge into the collector."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description=(
                    "Set True to confirm applying OTTL processing changes when dry_run=False"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Configure OTTL transform and filter processors for PII masking, JSON parsing, attribute dropping, and noise reduction.

            Generates and optionally merges ``transform/*`` and ``filter/*``
            processors into the collector's pipelines before the ``batch``
            processor.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_configure_processing")

                rules_dict = dict(rules or {})
                parse_json = bool(rules_dict.get("parse_json", False))
                extract_fields = rules_dict.get("extract_fields")
                mask_patterns = rules_dict.get("mask_pii") or rules_dict.get(
                    "mask_patterns"
                )
                if mask_patterns is True:
                    mask_patterns = ["email", "credit_card", "ssn", "ipv4"]
                elif isinstance(mask_patterns, str):
                    mask_patterns = [mask_patterns]
                custom_mask_rules = rules_dict.get("custom_mask_rules")
                drop_attributes: List[str] = list(
                    rules_dict.get("drop_attributes") or []
                )
                drop_noise_paths: List[str] = list(
                    rules_dict.get("drop_noise_paths") or []
                )
                preserve_errors: bool = bool(
                    rules_dict.get("preserve_errors", True)
                )
                custom_filter_conds: Dict[str, List[str]] = dict(
                    rules_dict.get("filter_conditions") or {}
                )
                custom_ottl: List[str] = list(
                    rules_dict.get("ottl_statements") or []
                )

                if mask_patterns:
                    unknown = [
                        p for p in mask_patterns if p not in _PII_PATTERNS
                    ]
                    if unknown:
                        raise OtelValidationError(
                            f"Unknown PII patterns: {unknown}. "
                            f"Available: {list(_PII_PATTERNS.keys())}"
                        )

                processors_to_merge: Dict[str, Dict[str, Any]] = {}
                processor_target_signals: Dict[str, List[str]] = {}
                statements_count = 0

                # 1. Log transform (JSON parsing + PII masking)
                if (
                    parse_json
                    or mask_patterns
                    or extract_fields
                    or custom_mask_rules
                ):
                    log_cfg = generate_log_transform_config(
                        mask_patterns=mask_patterns,
                        parse_json=parse_json,
                        extract_fields=extract_fields,
                        custom_mask_rules=custom_mask_rules,
                    )
                    if log_cfg:
                        proc_body = log_cfg["processors"][
                            "transform/log_processing"
                        ]
                        processors_to_merge["transform/log_processing"] = (
                            proc_body
                        )
                        processor_target_signals[
                            "transform/log_processing"
                        ] = ["logs"]
                        statements_count += len(
                            proc_body["log_statements"][0]["statements"]
                        )

                # 1b. Trace PII masking when 'traces' is included in signals
                if (mask_patterns or custom_mask_rules) and (
                    signals and "traces" in signals
                ):
                    trace_mask_stmts: List[str] = []
                    for pat_name in mask_patterns or []:
                        if pat_name in _PII_PATTERNS:
                            rx = _PII_PATTERNS[pat_name]["regex"]
                            rep = _PII_PATTERNS[pat_name]["replacement"]
                            trace_mask_stmts.append(
                                f'replace_all_patterns(attributes, "value", "{rx}", "{rep}")'
                            )
                    for crule in custom_mask_rules or []:
                        if isinstance(crule, dict) and crule.get("regex"):
                            rx = crule["regex"]
                            rep = crule.get("replacement", "[REDACTED]")
                            fld = crule.get("field")
                            if fld and fld not in ("body", "body.string"):
                                trace_mask_stmts.append(
                                    f'replace_pattern(attributes["{fld}"], "{rx}", "{rep}") where attributes["{fld}"] != nil'
                                )
                            else:
                                trace_mask_stmts.append(
                                    f'replace_all_patterns(attributes, "value", "{rx}", "{rep}")'
                                )
                    if trace_mask_stmts:
                        processors_to_merge["transform/mask_traces_pii"] = {
                            "error_mode": "ignore",
                            "trace_statements": [
                                {
                                    "context": "span",
                                    "statements": trace_mask_stmts,
                                }
                            ],
                        }
                        processor_target_signals[
                            "transform/mask_traces_pii"
                        ] = ["traces"]
                        statements_count += len(trace_mask_stmts)

                # 2. Drop attributes across requested signals
                if drop_attributes or custom_ottl:
                    target_sigs = signals or ["metrics"]
                    context_map = {
                        "metrics": ("metric_statements", "datapoint"),
                        "traces": ("trace_statements", "span"),
                        "logs": ("log_statements", "log"),
                    }
                    for sig in target_sigs:
                        if sig not in context_map:
                            continue
                        stmt_key, ctx_name = context_map[sig]
                        stmts = [
                            f'delete_key(attributes, "{attr}")'
                            for attr in drop_attributes
                        ] + list(custom_ottl)
                        if not stmts:
                            continue
                        proc_name = f"transform/drop_{sig}_attributes"
                        processors_to_merge[proc_name] = {
                            "error_mode": "ignore",
                            stmt_key: [
                                {
                                    "context": ctx_name,
                                    "statements": stmts,
                                }
                            ],
                        }
                        processor_target_signals[proc_name] = [sig]
                        statements_count += len(stmts)

                # 3. Drop healthcheck / synthetic noise via filter processor
                if drop_noise_paths or custom_filter_conds:
                    filter_sigs = list(signals or [])
                    if not filter_sigs:
                        filter_sigs = (
                            list(custom_filter_conds.keys())
                            if custom_filter_conds and not drop_noise_paths
                            else ["traces", "logs"]
                        )
                    filter_body: Dict[str, Any] = {"error_mode": "ignore"}
                    escaped_paths = (
                        "|".join(p.replace("/", "\\/") for p in drop_noise_paths)
                        if drop_noise_paths
                        else ""
                    )
                    err_guard = (
                        ' and status.code != STATUS_CODE_ERROR'
                        ' and (attributes["http.response.status_code"] == nil or attributes["http.response.status_code"] < 400)'
                        ' and (attributes["http.status_code"] == nil or attributes["http.status_code"] < 400)'
                        if preserve_errors
                        else ""
                    )
                    span_exprs: List[str] = []
                    if drop_noise_paths and "traces" in filter_sigs:
                        span_exprs.extend([
                            f'IsMatch(attributes["url.path"], "^({escaped_paths})$"){err_guard}',
                            f'IsMatch(attributes["http.target"], "^({escaped_paths})(\\\\?.*)?$"){err_guard}',
                        ])
                    if custom_filter_conds.get("traces"):
                        span_exprs.extend(list(custom_filter_conds["traces"]))
                    if span_exprs:
                        filter_body["traces"] = {"span": span_exprs}
                        statements_count += len(span_exprs)

                    log_exprs: List[str] = []
                    if drop_noise_paths and "logs" in filter_sigs:
                        log_err_guard = (
                            " and severity_number < SEVERITY_NUMBER_ERROR"
                            if preserve_errors
                            else ""
                        )
                        log_exprs.append(
                            f'IsMatch(body.string, "({escaped_paths})"){log_err_guard} where body.string != nil'
                        )
                    if custom_filter_conds.get("logs"):
                        log_exprs.extend(list(custom_filter_conds["logs"]))
                    if log_exprs:
                        filter_body["logs"] = {"log_record": log_exprs}
                        statements_count += len(log_exprs)

                    metric_exprs = list(custom_filter_conds.get("metrics") or [])
                    if metric_exprs:
                        filter_body["metrics"] = {"metric": metric_exprs}
                        statements_count += len(metric_exprs)
                        if "metrics" not in filter_sigs:
                            filter_sigs.append("metrics")

                    processors_to_merge["filter/drop_noise"] = filter_body
                    processor_target_signals["filter/drop_noise"] = filter_sigs

                if not processors_to_merge:
                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": dry_run,
                        "action": "no_change",
                        "message": (
                            "No processing rules specified. Provide rules with "
                            "parse_json, mask_pii, drop_attributes, or drop_noise_paths."
                        ),
                    }

                config_snippet = config_to_yaml(
                    {"processors": processors_to_merge}
                )
                patterns_applied = [
                    {
                        "name": p,
                        "description": _PII_PATTERNS[p]["description"],
                        "replacement": _PII_PATTERNS[p]["replacement"],
                    }
                    for p in (mask_patterns or [])
                    if p in _PII_PATTERNS
                ]

                if dry_run:
                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": True,
                        "action": "dry_run",
                        "config_snippet": config_snippet,
                        "yaml_snippet": config_snippet,
                        "processors_generated": list(
                            processors_to_merge.keys()
                        ),
                        "patterns_applied": patterns_applied,
                        "attributes_to_drop": drop_attributes,
                        "drop_noise_paths": drop_noise_paths,
                        "statements_count": statements_count,
                        "message": (
                            "Review the OTTL processor configuration above. "
                            "Set dry_run=False to apply to the collector."
                        ),
                    }

                raw = await kubernetes_service.get_otel_collector(
                    namespace, collector_name
                )
                current_cfg = collector_config_service.parse_collector_config(
                    raw
                )
                merged_cfg = dict(current_cfg)
                all_changes: List[str] = []

                for proc_name, proc_cfg in processors_to_merge.items():
                    pipes = target_pipelines or processor_target_signals.get(
                        proc_name, ["logs"]
                    )
                    for pipe in pipes:
                        merged_cfg, changes = merge_processor(
                            merged_cfg,
                            proc_name,
                            proc_cfg,
                            pipe,
                            before="batch",
                        )
                        all_changes.extend(changes)

                spec = dict(raw.get("spec", {}) or {})
                spec["config"] = merged_cfg
                findings = lint_collector_config(
                    merged_cfg,
                    mode=str(spec.get("mode", "deployment")).lower(),
                )

                await kubernetes_service.create_or_patch_collector(
                    namespace=namespace,
                    name=collector_name,
                    spec=spec,
                    dry_run=False,
                )

                return {
                    "collector": f"{namespace}/{collector_name}",
                    "dry_run": False,
                    "action": "applied",
                    "changes": all_changes,
                    "processors_applied": list(processors_to_merge.keys()),
                    "patterns_applied": patterns_applied,
                    "attributes_to_drop": drop_attributes,
                    "statements_count": statements_count,
                    "findings": [f.model_dump() for f in findings],
                    "message": (
                        "OTTL processing rules applied to collector "
                        f"'{collector_name}'."
                    ),
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_configure_processing",
                    namespace=namespace,
                    resource_name=collector_name,
                )
                raise
