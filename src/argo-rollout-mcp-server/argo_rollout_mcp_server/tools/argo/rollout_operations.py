"""Argo Rollouts lifecycle operations, AnalysisTemplate, Experiment, and Canary metrics comparison tools."""

import asyncio
from typing import Any, Dict, List, Literal, Optional
import requests
import yaml
from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from argo_rollout_mcp_server.models.schemas import (
    AnalysisThresholds,
    CanaryMetricsComparison,
    ExecutionResult,
)
from argo_rollout_mcp_server.tools.base import BaseTool, confirm_destructive_action

LIFECYCLE_ACTIONS = Literal[
    "promote",
    "promote_full",
    "pause",
    "resume",
    "abort",
    "retry",
    "skip_analysis",
]


class RolloutOperationTools(BaseTool):
    """Tools for rollout lifecycle actions, analysis templates, experiments, and canary metrics."""

    def register(self, mcp_instance) -> None:
        """Register rollout lifecycle and analysis tools with FastMCP."""
        if self.should_register("rollouts", is_write=True):
            self._register_lifecycle_tools(mcp_instance)

        if self.should_register("analysis", is_write=True):
            self._register_analysis_write_tools(mcp_instance)

        if self.should_register("analysis", is_write=False):
            self._register_analysis_read_tools(mcp_instance)

    def _register_lifecycle_tools(self, mcp_instance) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Rollout Lifecycle",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_manage_rollout_lifecycle(
            name: str = Field(..., min_length=1, description="Rollout name"),
            action: LIFECYCLE_ACTIONS = Field(
                ...,
                description=(
                    "Lifecycle action: promote (next step), promote_full (skip to 100%), "
                    "pause, resume, abort, retry, or skip_analysis"
                ),
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            confirm: bool = Field(
                default=False,
                description="Confirm high-impact action (abort, promote_full, skip_analysis)",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Execute a progressive delivery lifecycle action on an active Rollout."""
            self.check_write_access("argo_manage_rollout_lifecycle")

            valid_actions = (
                "promote",
                "promote_full",
                "pause",
                "resume",
                "abort",
                "retry",
                "skip_analysis",
            )
            if action not in valid_actions:
                self.handle_error(
                    ValueError(f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}"),
                    "argo_manage_rollout_lifecycle",
                    namespace=namespace,
                    resource_name=name,
                )

            if action in ("abort", "promote_full", "skip_analysis"):
                confirmed = await confirm_destructive_action(
                    ctx,
                    action_summary=f"Execute '{action}' on Rollout '{name}' in namespace '{namespace}'",
                    confirm=confirm,
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details={"rollout_name": name, "namespace": namespace, "action": action},
                )
                if not confirmed:
                    return ExecutionResult(
                        status="cancelled",
                        summary=(
                            f"Confirmation required to execute '{action}' on Rollout '{name}'. "
                            "Re-run with confirm=True after user approval."
                        ),
                        dry_run=False,
                        resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                        details={"name": name, "namespace": namespace, "action": action, "requires_confirmation": True},
                    )

            try:
                if action == "promote":
                    result = await self.argo_service.promote_rollout(name=name, namespace=namespace, full=False)
                elif action == "promote_full":
                    result = await self.argo_service.promote_rollout(name=name, namespace=namespace, full=True)
                elif action == "abort":
                    result = await self.argo_service.abort_rollout(name=name, namespace=namespace)
                elif action == "retry":
                    result = await self.argo_service.retry_rollout(name=name, namespace=namespace)
                elif action == "pause":
                    result = await self.argo_service.pause_rollout(name=name, namespace=namespace)
                elif action == "resume":
                    result = await self.argo_service.resume_rollout(name=name, namespace=namespace)
                else:  # skip_analysis
                    result = await self.argo_service.skip_analysis_promote(name=name, namespace=namespace)

                return ExecutionResult(
                    status="success",
                    summary=result.get("message", f"Executed '{action}' on Rollout '{name}'."),
                    dry_run=False,
                    resource_uri=f"argorollout://rollouts/{namespace}/{name}/detail",
                    details=result,
                )
            except Exception as e:
                self.handle_error(e, "argo_manage_rollout_lifecycle", namespace=namespace, resource_name=name)

    def _register_analysis_write_tools(self, mcp_instance) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Analysis Template",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_configure_analysis_template(
            rollout_name: str = Field(..., min_length=1, description="Rollout name to attach analysis to"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            template_name: Optional[str] = Field(
                default=None,
                description="AnalysisTemplate name (defaults to {service_name}-analysis)",
            ),
            metrics: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Custom AnalysisTemplate metric definitions (if omitted, uses thresholds)",
            ),
            thresholds: Optional[AnalysisThresholds] = Field(
                default=None,
                description="Error rate and P95/P99 latency thresholds for Prometheus analysis",
            ),
            scope: Literal["namespace", "cluster"] = Field(
                default="namespace",
                description="'namespace' for AnalysisTemplate or 'cluster' for ClusterAnalysisTemplate",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), return rendered AnalysisTemplate YAML without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create (or preview) an AnalysisTemplate/ClusterAnalysisTemplate and link it to a Rollout."""
            self.check_write_access("argo_configure_analysis_template")

            t_cfg = thresholds or AnalysisThresholds()
            svc_name = t_cfg.service_name or rollout_name
            tpl_name = template_name or f"{svc_name}-analysis"
            prom_url = (
                t_cfg.prometheus_url
                or (self.config.prometheus_url if self.config else None)
                or "http://prometheus:9090"
            )

            try:
                metrics_to_use = metrics or self.generator_service.get_analysis_metrics_from_thresholds(
                    service_name=svc_name,
                    prometheus_url=prom_url,
                    error_rate_threshold=t_cfg.error_rate_percent,
                    latency_p99_threshold=t_cfg.latency_p99_ms,
                    latency_p95_threshold=t_cfg.latency_p95_ms,
                )

                kind = "ClusterAnalysisTemplate" if scope == "cluster" else "AnalysisTemplate"
                meta: Dict[str, Any] = {"name": tpl_name}
                if scope == "namespace":
                    meta["namespace"] = namespace
                template_obj = {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": kind,
                    "metadata": meta,
                    "spec": {"metrics": metrics_to_use},
                }
                manifest_yaml = yaml.dump(template_obj, default_flow_style=False)

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed {kind} '{tpl_name}' for Rollout '{rollout_name}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=manifest_yaml,
                        resource_uri=f"argorollout://analysistemplates/{namespace}",
                        details={
                            "rollout_name": rollout_name,
                            "template_name": tpl_name,
                            "scope": scope,
                            "metrics_count": len(metrics_to_use),
                        },
                    )

                result = await self.argo_service.set_analysis_template(
                    rollout_name=rollout_name,
                    template_name=tpl_name,
                    namespace=namespace,
                    metrics=metrics_to_use,
                    scope=scope,
                    dry_run=False,
                )
                return ExecutionResult(
                    status="success",
                    summary=result.get(
                        "message",
                        f"Configured {kind} '{tpl_name}' and linked to Rollout '{rollout_name}'.",
                    ),
                    dry_run=False,
                    manifest=manifest_yaml,
                    resource_uri=f"argorollout://rollouts/{namespace}/{rollout_name}/detail",
                    details=result,
                )
            except Exception as e:
                self.handle_error(
                    e,
                    "argo_configure_analysis_template",
                    namespace=namespace,
                    resource_name=rollout_name,
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Analysis Template",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_delete_analysis_template(
            name: str = Field(..., min_length=1, description="AnalysisTemplate or ClusterAnalysisTemplate name"),
            namespace: str = Field(default="default", description="Kubernetes namespace (when scope='namespace')"),
            scope: Literal["namespace", "cluster"] = Field(
                default="namespace",
                description="'namespace' for AnalysisTemplate or 'cluster' for ClusterAnalysisTemplate",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm permanent deletion when interactive elicitation is unavailable",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Permanently delete an AnalysisTemplate or ClusterAnalysisTemplate."""
            self.check_write_access("argo_delete_analysis_template")

            confirmed = await confirm_destructive_action(
                ctx,
                action_summary=f"Delete {scope}-scoped AnalysisTemplate '{name}'",
                confirm=confirm,
                resource_uri=f"argorollout://analysistemplates/{namespace}",
                details={"name": name, "namespace": namespace, "scope": scope},
            )
            if not confirmed:
                return ExecutionResult(
                    status="cancelled",
                    summary=(
                        f"Confirmation required to delete AnalysisTemplate '{name}'. "
                        "Re-run with confirm=True after user approval."
                    ),
                    dry_run=False,
                    resource_uri=f"argorollout://analysistemplates/{namespace}",
                    details={"name": name, "namespace": namespace, "scope": scope, "requires_confirmation": True},
                )

            try:
                result = self.argo_service.delete_analysis_template(
                    name=name,
                    namespace=namespace,
                    scope=scope,
                )
                return ExecutionResult(
                    status="success",
                    summary=result.get("message", f"Deleted AnalysisTemplate '{name}'."),
                    dry_run=False,
                    details=result,
                )
            except Exception as e:
                self.handle_error(e, "argo_delete_analysis_template", namespace=namespace, resource_name=name)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create Argo Experiment",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_create_experiment(
            name: str = Field(..., min_length=1, description="Experiment name"),
            templates: List[Dict[str, Any]] = Field(
                ...,
                description=(
                    "Experiment template specs: [{name, replicas, specRef: 'stable'|'canary'}] "
                    "or [{name, replicas, template: {podTemplateSpec}}]"
                ),
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            duration: Optional[str] = Field(default=None, description="Experiment duration (e.g., '20m', '1h')"),
            analyses: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Optional AnalysisTemplate references to run during the experiment",
            ),
            rollout_name: Optional[str] = Field(
                default=None,
                description="Rollout name (required when templates use specRef: 'stable'|'canary')",
            ),
            progress_deadline_seconds: int = Field(
                default=300,
                ge=30,
                description="Seconds for Experiment ReplicaSets to become available",
            ),
            dry_run: bool = Field(
                default=False,
                description="If True, preview Experiment YAML without creating it in the cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create a standalone Argo Experiment for baseline vs. canary comparison."""
            self.check_write_access("argo_create_experiment")

            if dry_run:
                exp_preview = {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "Experiment",
                    "metadata": {"name": name, "namespace": namespace},
                    "spec": {
                        "templates": templates,
                        "progressDeadlineSeconds": progress_deadline_seconds,
                        **({"duration": duration} if duration else {}),
                        **({"analyses": analyses} if analyses else {}),
                    },
                }
                return ExecutionResult(
                    status="preview",
                    summary=f"Previewed Experiment '{name}' in namespace '{namespace}' (dry_run=True).",
                    dry_run=True,
                    manifest=yaml.dump(exp_preview, default_flow_style=False),
                    resource_uri=f"argorollout://experiments/{namespace}/{name}/status",
                    details={"experiment": name, "namespace": namespace, "templates": templates},
                )

            try:
                result = await self.argo_service.create_experiment(
                    name=name,
                    namespace=namespace,
                    templates=templates,
                    duration=duration,
                    analyses=analyses,
                    progress_deadline_seconds=progress_deadline_seconds,
                    rollout_name=rollout_name,
                    rollout_namespace=namespace,
                    dry_run=False,
                )
                warnings = [result["traefik_note"]] if result.get("traefik_note") else []
                return ExecutionResult(
                    status="success",
                    summary=result.get("message", f"Created Experiment '{name}' in namespace '{namespace}'."),
                    dry_run=False,
                    manifest=result.get("manifest"),
                    warnings=warnings,
                    resource_uri=f"argorollout://experiments/{namespace}/{name}/status",
                    details=result,
                )
            except Exception as e:
                self.handle_error(e, "argo_create_experiment", namespace=namespace, resource_name=name)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Argo Experiment",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def argo_delete_experiment(
            name: str = Field(..., min_length=1, description="Experiment name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            confirm: bool = Field(
                default=False,
                description="Confirm permanent deletion when interactive elicitation is unavailable",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Permanently delete an Argo Experiment and its ephemeral ReplicaSets."""
            self.check_write_access("argo_delete_experiment")

            confirmed = await confirm_destructive_action(
                ctx,
                action_summary=f"Delete Experiment '{name}' in namespace '{namespace}'",
                confirm=confirm,
                resource_uri=f"argorollout://experiments/{namespace}/{name}/status",
                details={"experiment": name, "namespace": namespace},
            )
            if not confirmed:
                return ExecutionResult(
                    status="cancelled",
                    summary=(
                        f"Confirmation required to delete Experiment '{name}'. "
                        "Re-run with confirm=True after user approval."
                    ),
                    dry_run=False,
                    resource_uri=f"argorollout://experiments/{namespace}/{name}/status",
                    details={"name": name, "namespace": namespace, "requires_confirmation": True},
                )

            try:
                result = await self.argo_service.delete_experiment(name=name, namespace=namespace)
                return ExecutionResult(
                    status="success",
                    summary=result.get("message", f"Deleted Experiment '{name}'."),
                    dry_run=False,
                    details=result,
                )
            except Exception as e:
                self.handle_error(e, "argo_delete_experiment", namespace=namespace, resource_name=name)

    def _register_analysis_read_tools(self, mcp_instance) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Compare Canary vs Stable Metrics",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_compare_canary_metrics(
            rollout_name: str = Field(..., min_length=1, description="Rollout name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            window: str = Field(default="5m", description="Prometheus rate window (e.g., '1m', '5m', '15m')"),
            ctx: Context = None,
        ) -> CanaryMetricsComparison:
            """Compare live Prometheus HTTP error rate, latency (P95/P99), and RPS between stable and canary Services."""
            prometheus_url = (
                (self.config.prometheus_url if self.config else None)
                or "http://prometheus:9090"
            ).rstrip("/")

            stable_svc = f"{rollout_name}-stable"
            canary_svc = f"{rollout_name}-canary"

            def _query_prom(promql: str) -> float:
                resp = requests.get(
                    f"{prometheus_url}/api/v1/query",
                    params={"query": promql},
                    timeout=5,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("data", {}).get("result", [])
                if results and results[0].get("value"):
                    val = float(results[0]["value"][1])
                    return 0.0 if val != val else round(val, 3)  # NaN guard
                return 0.0

            def _collect_variant(svc: str) -> Dict[str, float]:
                err_q = (
                    f'(sum(rate(http_requests_total{{job="{svc}",status=~"5.."}}[{window}])) / '
                    f'sum(rate(http_requests_total{{job="{svc}"}}[{window}]))) * 100'
                )
                p95_q = (
                    f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{job="{svc}"}}[{window}])) by (le)) * 1000'
                )
                p99_q = (
                    f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{job="{svc}"}}[{window}])) by (le)) * 1000'
                )
                rps_q = f'sum(rate(http_requests_total{{job="{svc}"}}[{window}]))'
                return {
                    "error_rate_pct": _query_prom(err_q),
                    "latency_p95_ms": _query_prom(p95_q),
                    "latency_p99_ms": _query_prom(p99_q),
                    "requests_per_sec": _query_prom(rps_q),
                }

            try:
                stable_metrics, canary_metrics = await asyncio.gather(
                    asyncio.to_thread(_collect_variant, stable_svc),
                    asyncio.to_thread(_collect_variant, canary_svc),
                )
            except Exception as e:
                raise ToolError(
                    f"Prometheus metrics comparison unavailable at '{prometheus_url}' for Rollout '{rollout_name}': {e}. "
                    "Check 'argorollout://metrics/prometheus/status' or configure --prometheus-url / PROMETHEUS_URL."
                )

            delta = {
                "error_rate_pct_diff": round(
                    canary_metrics["error_rate_pct"] - stable_metrics["error_rate_pct"], 3
                ),
                "latency_p95_ms_diff": round(
                    canary_metrics["latency_p95_ms"] - stable_metrics["latency_p95_ms"], 3
                ),
                "latency_p99_ms_diff": round(
                    canary_metrics["latency_p99_ms"] - stable_metrics["latency_p99_ms"], 3
                ),
            }

            if canary_metrics["error_rate_pct"] > 5.0 or delta["error_rate_pct_diff"] > 2.0:
                recommendation = "abort"
            elif canary_metrics["requests_per_sec"] == 0.0 and stable_metrics["requests_per_sec"] == 0.0:
                recommendation = "hold"
            else:
                recommendation = "promote"

            return CanaryMetricsComparison(
                rollout_name=rollout_name,
                namespace=namespace,
                window=window,
                prometheus_reachable=True,
                stable_service=stable_svc,
                canary_service=canary_svc,
                stable=stable_metrics,
                canary=canary_metrics,
                delta=delta,
                recommendation=recommendation,
            )
