"""Sampling configuration tool.

Provides ``otel_configure_sampling`` for configuring head, probabilistic,
tail, or disabled sampling with a trace-affinity architecture guard that
blocks tail_sampling on DaemonSet or multi-replica collectors lacking an
upstream loadbalancing exporter.
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
from opentelemetry_mcp_server.models.findings import (
    Finding,
    FindingCode,
    FindingSeverity,
)
from opentelemetry_mcp_server.tools.base import BaseTool
from opentelemetry_mcp_server.utils.config_merger import (
    collapse_presampling_connector_split,
    ensure_presampling_connector_split,
    merge_processor,
    remove_processor,
)
from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

_VALID_STRATEGIES = {"none", "head", "probabilistic", "tail"}


class SamplingTools(BaseTool):
    """Sampling configuration tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("pipeline", is_write=True):
            return

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Sampling Strategy",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_configure_sampling(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            strategy: Literal["none", "head", "probabilistic", "tail"] = Field(
                ...,
                description=(
                    "Target sampling strategy: 'none', 'head' (SDK-level on "
                    "Instrumentation CR), 'probabilistic' (collector processor), "
                    "or 'tail' (collector tail_sampling processor)"
                ),
            ),
            sampling_options: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "Optional sampling parameters dict supporting keys: "
                    "'sample_rate' (float 0.0-1.0 for head/probabilistic), "
                    "'decision_wait' (str, default '10s' for tail), "
                    "'num_traces' (int, default 50000 for tail), "
                    "'expected_new_traces_per_sec' (int), "
                    "'policies' (list of tail_sampling policy dicts), "
                    "'has_load_balancing_exporter' (bool, True if upstream tier "
                    "routes spans by traceID)"
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, validates topology and returns the sampling config "
                    "patch without applying. Set False after reviewing."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description=(
                    "Set True to confirm applying sampling changes when dry_run=False"
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Configure trace sampling strategy across collector and Instrumentation CRs.

            Supports 'head' (Instrumentation CR parentbased_traceidratio),
            'probabilistic' (collector probabilistic_sampler processor),
            'tail' (collector tail_sampling processor with trace-affinity guard),
            and 'none' (removes both head and tail sampling).
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_configure_sampling")

                if strategy not in _VALID_STRATEGIES:
                    raise OtelValidationError(
                        f"Invalid strategy: '{strategy}'. "
                        f"Supported: {sorted(_VALID_STRATEGIES)}"
                    )

                opts = dict(sampling_options or {})
                sample_rate = float(opts.get("sample_rate", 0.1))
                if not (0.0 <= sample_rate <= 1.0):
                    raise OtelValidationError(
                        f"sample_rate must be between 0.0 and 1.0 (got {sample_rate})."
                    )

                findings: List[Finding] = []

                if strategy == "head":
                    config_patch = (
                        f"# Apply to Instrumentation CRD in namespace '{namespace}':\n"
                        "spec:\n"
                        "  sampler:\n"
                        "    type: parentbased_traceidratio\n"
                        f'    argument: "{sample_rate}"\n'
                    )
                    if dry_run:
                        return {
                            "strategy": strategy,
                            "target_mode": strategy,
                            "collector": f"{namespace}/{collector_name}",
                            "config_patch": config_patch,
                            "dry_run": True,
                            "action": "dry_run",
                            "findings": [],
                            "message": (
                                "Dry run — review the head sampling patch above. "
                                "Set dry_run=False to apply to the namespace Instrumentation CR."
                            ),
                        }

                    existing_instr = (
                        await kubernetes_service.list_instrumentations(
                            namespace=namespace
                        )
                    )
                    items = existing_instr.get("items", [])
                    if not items:
                        raise OtelValidationError(
                            f"No Instrumentation CRD found in namespace '{namespace}'. "
                            "Create one first with otel_patch_instrumentation."
                        )
                    instr_name = items[0].get("metadata", {}).get("name", "")
                    existing_spec = dict(items[0].get("spec", {}) or {})
                    existing_spec["sampler"] = {
                        "type": "parentbased_traceidratio",
                        "argument": str(sample_rate),
                    }
                    await kubernetes_service.create_or_patch_instrumentation(
                        namespace=namespace,
                        name=instr_name,
                        spec=existing_spec,
                        overwrite=False,
                    )
                    return {
                        "strategy": strategy,
                        "target_mode": strategy,
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": False,
                        "action": "applied",
                        "instrumentation_cr": instr_name,
                        "sampler": existing_spec["sampler"],
                        "findings": [],
                        "message": (
                            f"Head sampling set to {sample_rate} on Instrumentation CR "
                            f"'{instr_name}'. Restart workloads to apply."
                        ),
                    }

                if strategy == "probabilistic":
                    pct = round(sample_rate * 100.0, 4)
                    proc_cfg = {"sampling_percentage": pct}
                    config_patch = config_to_yaml(
                        {"processors": {"probabilistic_sampler": proc_cfg}}
                    )
                    if dry_run:
                        return {
                            "strategy": strategy,
                            "target_mode": strategy,
                            "collector": f"{namespace}/{collector_name}",
                            "config_patch": config_patch,
                            "dry_run": True,
                            "action": "dry_run",
                            "findings": [],
                            "message": (
                                "Dry run — review the probabilistic_sampler config above. "
                                "Set dry_run=False to apply."
                            ),
                        }

                    raw = await kubernetes_service.get_otel_collector(
                        namespace, collector_name
                    )
                    current_cfg = (
                        collector_config_service.parse_collector_config(raw)
                    )
                    merged_cfg, changes = merge_processor(
                        current_cfg,
                        "probabilistic_sampler",
                        proc_cfg,
                        "traces",
                        before="batch",
                    )
                    merged_cfg, split_changes = ensure_presampling_connector_split(
                        merged_cfg
                    )
                    changes.extend(split_changes)
                    spec = dict(raw.get("spec", {}) or {})
                    spec["config"] = merged_cfg
                    await kubernetes_service.create_or_patch_collector(
                        namespace=namespace,
                        name=collector_name,
                        spec=spec,
                        dry_run=False,
                    )
                    return {
                        "strategy": strategy,
                        "target_mode": strategy,
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": False,
                        "action": "applied",
                        "changes": changes,
                        "sampling_percentage": pct,
                        "findings": [],
                        "message": (
                            f"Probabilistic sampling ({pct}%) applied to "
                            f"collector '{collector_name}'."
                        ),
                    }

                if strategy == "tail":
                    policies = opts.get("policies") or [
                        {
                            "name": "error-sampling",
                            "type": "status_code",
                            "status_code": {"status_codes": ["ERROR"]},
                        },
                        {
                            "name": "slow-traces",
                            "type": "latency",
                            "latency": {"threshold_ms": 5000},
                        },
                        {
                            "name": "probabilistic-fallback",
                            "type": "probabilistic",
                            "probabilistic": {
                                "sampling_percentage": round(
                                    sample_rate * 100.0, 2
                                )
                            },
                        },
                    ]
                    decision_wait = str(opts.get("decision_wait", "10s"))
                    num_traces = int(opts.get("num_traces", 50000))
                    has_lb = bool(opts.get("has_load_balancing_exporter", False))

                    processor_config: Dict[str, Any] = {
                        "decision_wait": decision_wait,
                        "num_traces": num_traces,
                        "policies": policies,
                    }
                    if opts.get("expected_new_traces_per_sec"):
                        processor_config["expected_new_traces_per_sec"] = int(
                            opts["expected_new_traces_per_sec"]
                        )

                    config_patch = config_to_yaml(
                        {"processors": {"tail_sampling": processor_config}}
                    )

                    # Inspect live collector to enforce trace-affinity guard
                    raw_collector = None
                    try:
                        raw_collector = (
                            await kubernetes_service.get_otel_collector(
                                namespace, collector_name
                            )
                        )
                    except OtelResourceNotFoundError:
                        raw_collector = None

                    if raw_collector:
                        c_spec = raw_collector.get("spec", {}) or {}
                        c_mode = str(
                            c_spec.get("mode", "deployment")
                        ).lower()
                        c_replicas = int(c_spec.get("replicas", 1) or 1)
                        if c_mode == "daemonset" or (
                            c_replicas > 1 and not has_lb
                        ):
                            findings.append(
                                Finding.create(
                                    FindingCode.CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY,
                                    message=(
                                        f"Collector '{collector_name}' runs in mode='{c_mode}' "
                                        f"(replicas={c_replicas}) without trace-ID-aware load "
                                        "balancing. Tail sampling requires all spans of a trace "
                                        "to reach the same collector instance."
                                    ),
                                    field_path="processors.tail_sampling",
                                    remediation=(
                                        "Deploy a dedicated tail-sampler StatefulSet/Deployment "
                                        "(or replica=1) fronted by a loadbalancing exporter with "
                                        "routing_key: traceID, or pass "
                                        "sampling_options={'has_load_balancing_exporter': True}."
                                    ),
                                )
                            )

                    # Check if head sampling is also active in namespace
                    try:
                        instrs = await kubernetes_service.list_instrumentations(
                            namespace=namespace
                        )
                        for item in instrs.get("items", []):
                            sampler_cfg = (
                                item.get("spec", {}) or {}
                            ).get("sampler", {})
                            if sampler_cfg.get("type") and sampler_cfg.get(
                                "type"
                            ) not in ("always_on", "parentbased_always_on"):
                                findings.append(
                                    Finding(
                                        code=FindingCode.CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY,
                                        severity=FindingSeverity.WARNING,
                                        message=(
                                            f"Instrumentation CR '{item.get('metadata', {}).get('name')}' "
                                            f"has head sampler '{sampler_cfg.get('type')}'. "
                                            "Head sampling drops spans at the SDK before tail_sampling "
                                            "can evaluate error/latency policies."
                                        ),
                                        field_path="spec.sampler",
                                        remediation=(
                                            "Set head sampler to 'parentbased_always_on' when "
                                            "using tail_sampling."
                                        ),
                                    )
                                )
                    except Exception:
                        pass

                    error_findings = [
                        f
                        for f in findings
                        if f.severity == FindingSeverity.ERROR
                    ]

                    if dry_run:
                        return {
                            "strategy": strategy,
                            "target_mode": strategy,
                            "collector": f"{namespace}/{collector_name}",
                            "config_patch": config_patch,
                            "dry_run": True,
                            "action": "dry_run",
                            "valid": len(error_findings) == 0,
                            "findings": [f.model_dump() for f in findings],
                            "message": (
                                "Dry run — review config_patch and findings above. "
                                "Set dry_run=False to apply."
                            ),
                        }

                    if error_findings:
                        raise OtelValidationError(
                            f"Cannot apply tail_sampling: {error_findings[0].message}"
                        )

                    if not raw_collector:
                        raw_collector = (
                            await kubernetes_service.get_otel_collector(
                                namespace, collector_name
                            )
                        )
                    current_cfg = (
                        collector_config_service.parse_collector_config(
                            raw_collector
                        )
                    )
                    target_trace_pipe = (
                        "traces/sampling"
                        if "traces/sampling"
                        in (current_cfg.get("service", {}) or {}).get(
                            "pipelines", {}
                        )
                        else "traces"
                    )
                    merged_cfg, changes = merge_processor(
                        current_cfg,
                        "tail_sampling",
                        processor_config,
                        target_trace_pipe,
                        before="batch",
                    )
                    merged_cfg, split_changes = ensure_presampling_connector_split(
                        merged_cfg
                    )
                    changes.extend(split_changes)
                    spec = dict(raw_collector.get("spec", {}) or {})
                    spec["config"] = merged_cfg

                    await kubernetes_service.create_or_patch_collector(
                        namespace=namespace,
                        name=collector_name,
                        spec=spec,
                        dry_run=False,
                    )

                    return {
                        "strategy": strategy,
                        "target_mode": strategy,
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": False,
                        "action": "applied",
                        "changes": changes,
                        "policies": [p.get("name", "") for p in policies],
                        "findings": [f.model_dump() for f in findings],
                        "message": (
                            f"Tail sampling applied to collector '{collector_name}'."
                        ),
                    }

                # strategy == "none"
                config_patch = (
                    "# Remove spec.sampler from Instrumentation CRD\n"
                    "# Remove tail_sampling and probabilistic_sampler from collector config\n"
                )
                if dry_run:
                    return {
                        "strategy": strategy,
                        "target_mode": strategy,
                        "collector": f"{namespace}/{collector_name}",
                        "config_patch": config_patch,
                        "dry_run": True,
                        "action": "dry_run",
                        "findings": [],
                        "message": (
                            "Dry run — would disable head, probabilistic, and tail sampling. "
                            "Set dry_run=False to apply."
                        ),
                    }

                all_changes: List[str] = []
                try:
                    raw = await kubernetes_service.get_otel_collector(
                        namespace, collector_name
                    )
                    current_cfg = (
                        collector_config_service.parse_collector_config(raw)
                    )
                    merged_cfg, changes1 = remove_processor(
                        current_cfg, "tail_sampling"
                    )
                    merged_cfg, changes2 = remove_processor(
                        merged_cfg, "probabilistic_sampler"
                    )
                    merged_cfg, changes3 = collapse_presampling_connector_split(
                        merged_cfg
                    )
                    changes = changes1 + changes2 + changes3
                    if changes:
                        spec = dict(raw.get("spec", {}) or {})
                        spec["config"] = merged_cfg
                        await kubernetes_service.create_or_patch_collector(
                            namespace=namespace,
                            name=collector_name,
                            spec=spec,
                            dry_run=False,
                        )
                        all_changes.extend(changes)
                except Exception:
                    all_changes.append("No collector changes needed")

                try:
                    instrs = await kubernetes_service.list_instrumentations(
                        namespace=namespace
                    )
                    for item in instrs.get("items", []):
                        instr_spec = dict(item.get("spec", {}) or {})
                        if "sampler" in instr_spec:
                            del instr_spec["sampler"]
                            instr_name = (
                                item.get("metadata", {}) or {}
                            ).get("name", "")
                            await kubernetes_service.create_or_patch_instrumentation(
                                namespace=namespace,
                                name=instr_name,
                                spec=instr_spec,
                                overwrite=False,
                            )
                            all_changes.append(
                                f"Removed sampler from Instrumentation CR '{instr_name}'"
                            )
                except Exception:
                    all_changes.append("No instrumentation changes needed")

                return {
                    "strategy": strategy,
                    "target_mode": strategy,
                    "collector": f"{namespace}/{collector_name}",
                    "dry_run": False,
                    "action": "applied",
                    "changes": all_changes,
                    "findings": [],
                    "message": "Sampling disabled.",
                }
            except (OtelValidationError, OtelOperationError):
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_configure_sampling",
                    namespace=namespace,
                    resource_name=collector_name,
                )
                raise
