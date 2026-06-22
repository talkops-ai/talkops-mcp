"""Sampling configuration inspection and toggle tools."""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool


class SamplingTools(BaseTool):
    """Sampling inspection and configuration tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Inspect Sampling Configuration",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_inspect_sampling_configuration(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            instrumentation_cr_name: Optional[str] = Field(
                default=None,
                description="Instrumentation CR name to check head sampling config",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Inspect the complete sampling configuration for a collector.

            Cross-references head sampling (from Instrumentation CRDs) with
            tail sampling (from collector config) to detect conflicts and
            provide a holistic view. Read-only.

            Returns:
            - {"mode": str, "head_sampling": {...}|null, "tail_sampling": {...}|null, "warnings": [...]}

            When NOT to use: For modifying sampling, use
            otel_toggle_sampling_strategy.

            Common errors:
            - No sampling: Returns mode='none' with empty config.
            """
            try:
                raw = await kubernetes_service.get_otel_collector(
                    namespace, collector_name
                )
                cfg = collector_config_service.parse_collector_config(raw)

                instr_cr = None
                missing_cr_warning = None
                if instrumentation_cr_name:
                    try:
                        instr_cr = await kubernetes_service.get_instrumentation(
                            namespace, instrumentation_cr_name
                        )
                    except Exception:
                        instr_cr = None
                        missing_cr_warning = (
                            f"Instrumentation CR '{instrumentation_cr_name}' "
                            f"not found in namespace '{namespace}' — "
                            "head sampling data unavailable"
                        )

                sampling_config = collector_config_service.extract_sampling_config(
                    cfg, collector_name, namespace, instr_cr
                )

                result = sampling_config.model_dump()

                # Inject missing CR warning if applicable
                if missing_cr_warning:
                    warnings = result.get("warnings", [])
                    warnings.append(missing_cr_warning)
                    result["warnings"] = warnings

                return result
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to inspect sampling configuration: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Toggle Sampling Strategy",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_toggle_sampling_strategy(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            target_mode: str = Field(
                ...,
                description="Target sampling mode: 'head', 'tail', or 'none'",
            ),
            sample_rate: Optional[float] = Field(
                default=None,
                ge=0.0,
                le=1.0,
                description="Sample rate for head sampling (0.0-1.0)",
            ),
            tail_policies: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Tail sampling policies (list of policy dicts)",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True, generates the config patch without applying. Set False after review.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate sampling configuration changes.

            Generates the configuration patch needed to switch between
            head, tail, or no sampling. When dry_run=True, returns the
            YAML patch for review.

            **WARNING: With dry_run=False, this modifies collector or
            Instrumentation CRD configurations.**

            Returns:
            - {"target_mode": str, "config_patch": str, "dry_run": bool, "instructions": str}

            When NOT to use: For inspecting current sampling, use
            otel_inspect_sampling_configuration.

            Prerequisites: Verify current config with
            otel_inspect_sampling_configuration first.
            """
            try:
                from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

                if target_mode == "head":
                    rate = sample_rate or 1.0
                    config_patch = (
                        f"# Apply to Instrumentation CRD in namespace '{namespace}':\n"
                        f"spec:\n"
                        f"  sampler:\n"
                        f"    type: parentbased_traceidratio\n"
                        f"    argument: \"{rate}\"\n"
                    )
                    instructions = (
                        f"1. Update Instrumentation CR in {namespace}\n"
                        f"2. Set sampler.type to 'parentbased_traceidratio'\n"
                        f"3. Set sampler.argument to '{rate}'\n"
                        "4. Workloads will pick up the change on next restart"
                    )

                    if not dry_run:
                        # Apply head sampling to the Instrumentation CRD
                        try:
                            existing_instr = await kubernetes_service.list_instrumentations(
                                namespace=namespace
                            )
                            items = existing_instr.get("items", [])
                            if not items:
                                return {
                                    "error": (
                                        f"No Instrumentation CRD found in namespace '{namespace}'. "
                                        "Create one first with otel_patch_instrumentation."
                                    )
                                }
                            instr_name = items[0].get("metadata", {}).get("name", "")
                            existing_spec = items[0].get("spec", {})
                            existing_spec["sampler"] = {
                                "type": "parentbased_traceidratio",
                                "argument": str(rate),
                            }
                            result = await kubernetes_service.create_or_patch_instrumentation(
                                namespace=namespace,
                                name=instr_name,
                                spec=existing_spec,
                                overwrite=False,
                            )
                            return {
                                "target_mode": target_mode,
                                "collector": f"{namespace}/{collector_name}",
                                "dry_run": False,
                                "action": "applied",
                                "instrumentation_cr": instr_name,
                                "sampler": {"type": "parentbased_traceidratio", "argument": str(rate)},
                                "message": (
                                    f"Head sampling set to {rate} on Instrumentation CR "
                                    f"'{instr_name}'. Workloads pick up changes on next restart."
                                ),
                            }
                        except Exception as e:
                            raise OtelOperationError(
                                f"Failed to apply head sampling: {e}"
                            )

                elif target_mode == "tail":
                    policies = tail_policies or [
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
                            "probabilistic": {"sampling_percentage": 10},
                        },
                    ]

                    processor_config = {
                        "decision_wait": "10s",
                        "num_traces": 50000,
                        "policies": policies,
                    }
                    config_patch = collector_config_service.generate_tail_sampling_patch(
                        policies
                    )
                    instructions = (
                        f"1. Add the tail_sampling processor to collector '{collector_name}'\n"
                        "2. Add 'tail_sampling' to traces pipeline processors (before batch)\n"
                        "3. NOTE: Tail sampling requires all spans for a trace to arrive at\n"
                        "   the same collector instance. Use a load balancer with\n"
                        "   trace-ID-aware routing or a Gateway deployment."
                    )

                    if not dry_run:
                        # Fetch current config, merge, and apply
                        from opentelemetry_mcp_server.utils.config_merger import merge_processor

                        raw = await kubernetes_service.get_otel_collector(
                            namespace, collector_name
                        )
                        current_cfg = collector_config_service.parse_collector_config(raw)

                        merged_cfg, changes = merge_processor(
                            current_cfg,
                            "tail_sampling",
                            processor_config,
                            "traces",
                            before="batch",
                        )

                        spec = dict(raw.get("spec", {}))
                        spec["config"] = merged_cfg

                        result = await kubernetes_service.create_or_patch_collector(
                            namespace=namespace,
                            name=collector_name,
                            spec=spec,
                            dry_run=False,
                        )

                        return {
                            "target_mode": target_mode,
                            "collector": f"{namespace}/{collector_name}",
                            "dry_run": False,
                            "action": "applied",
                            "changes": changes,
                            "policies": [p.get("name", "") for p in policies],
                            "message": (
                                f"Tail sampling applied to collector '{collector_name}'. "
                                "NOTE: Tail sampling requires trace-ID-aware routing."
                            ),
                        }

                elif target_mode == "none":
                    config_patch = (
                        "# To disable head sampling:\n"
                        "# Remove spec.sampler from Instrumentation CRD\n\n"
                        "# To disable tail sampling:\n"
                        "# Remove tail_sampling processor from collector config\n"
                        "# Remove it from pipeline processors lists"
                    )
                    instructions = (
                        "1. Remove sampler config from Instrumentation CR\n"
                        "2. Remove tail_sampling processor from collector config\n"
                        "3. Remove tail_sampling from pipeline processor lists"
                    )

                    if not dry_run:
                        from opentelemetry_mcp_server.utils.config_merger import remove_processor

                        all_changes: List[str] = []

                        # Remove tail sampling from collector
                        try:
                            raw = await kubernetes_service.get_otel_collector(
                                namespace, collector_name
                            )
                            current_cfg = collector_config_service.parse_collector_config(raw)
                            merged_cfg, changes = remove_processor(
                                current_cfg, "tail_sampling"
                            )
                            if changes:
                                spec = dict(raw.get("spec", {}))
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

                        # Remove head sampling from Instrumentation CRD
                        try:
                            instrs = await kubernetes_service.list_instrumentations(
                                namespace=namespace
                            )
                            for item in instrs.get("items", []):
                                instr_spec = item.get("spec", {})
                                if "sampler" in instr_spec:
                                    del instr_spec["sampler"]
                                    instr_name = item.get("metadata", {}).get("name", "")
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
                            "target_mode": target_mode,
                            "collector": f"{namespace}/{collector_name}",
                            "dry_run": False,
                            "action": "applied",
                            "changes": all_changes,
                            "message": "Sampling disabled.",
                        }

                else:
                    return {
                        "error": f"Invalid target_mode: '{target_mode}'. Use 'head', 'tail', or 'none'."
                    }

                return {
                    "target_mode": target_mode,
                    "collector": f"{namespace}/{collector_name}",
                    "config_patch": config_patch,
                    "dry_run": dry_run,
                    "instructions": instructions,
                    "message": (
                        "Dry run — review the config_patch above. "
                        "Set dry_run=False to apply."
                    ),
                }
            except OtelOperationError:
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to generate/apply sampling config: {e}"
                )
