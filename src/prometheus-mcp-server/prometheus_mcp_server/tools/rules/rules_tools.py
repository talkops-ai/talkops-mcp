"""Prometheus Rule Evaluation, Validation, Simulation, and Lifecycle MCP tools (`rules` toolset)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from prometheus_mcp_server.exceptions import (
    ConfirmationRequiredError,
    PrometheusOperationError,
    PrometheusValidationError,
    WriteAccessDeniedError,
)
from prometheus_mcp_server.tools.base import BaseTool, parse_time_param
from prometheus_mcp_server.utils.param_coercion import (
    JsonDict,
    JsonDictList,
    JsonStrDict,
)
from prometheus_mcp_server.utils.promql_helpers import parse_duration_seconds
from prometheus_mcp_server.utils.promtool_runner import (
    check_rules,
    is_promtool_available,
    test_rules,
)


def _validate_rule_group_structure(group: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(group, dict):
        return ["rule_group must be a dictionary."]
    if not group.get("name"):
        errors.append("rule_group is missing required 'name' field.")
    rules = group.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rule_group must contain a non-empty 'rules' list.")
        return errors
    for idx, r in enumerate(rules):
        if not isinstance(r, dict):
            errors.append(f"Rule at index {idx} must be a dictionary.")
            continue
        if not r.get("alert") and not r.get("record"):
            errors.append(f"Rule at index {idx} must define either 'alert' or 'record'.")
        if not r.get("expr"):
            errors.append(f"Rule at index {idx} is missing required 'expr' field.")
    return errors


class RulesTools(BaseTool):
    """Alerting and recording rule inspection, validation, simulation, and CRUD tools (`rules` toolset)."""

    def register(self, mcp_instance: Any) -> None:
        if self.should_register("rules", is_write=False):
            self._register_read_tools(mcp_instance)
        if self.should_register("rules", is_write=True):
            self._register_write_tools(mcp_instance)

    def _register_read_tools(self, mcp_instance: Any) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Prometheus Firing & Pending Alert Evaluations",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_get_firing_alerts(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            alert_name: Optional[str] = Field(
                default=None,
                description="Optional alertname filter (exact match)",
            ),
            state: Literal["all", "firing", "pending"] = Field(
                default="all",
                description="Filter by Prometheus rule evaluation state: all, firing, or pending",
            ),
            label_filters: Optional[JsonStrDict] = Field(
                default=None,
                description="Optional label key-value matchers (e.g. {'severity': 'critical'})",
            ),
            include_history_lookback: Optional[str] = Field(
                default="24h",
                description="Lookback window for ALERTS_FOR_STATE flapping stats (e.g. '24h', '7d'; None to skip)",
            ),
            limit: int = Field(
                default=50,
                ge=1,
                le=200,
                description="Maximum alert instances to return (1-200)",
            ),
        ) -> Dict[str, Any]:
            """Inspect Prometheus's native rule evaluation state (`/api/v1/alerts`) and `ALERTS_FOR_STATE` flapping history.

            Scoped strictly to Prometheus signal generation. For Alertmanager silences, routing trees, or inhibitions, use `alertmanager-mcp-server` (`am_*`). Read-only.

            Returns:
            - {"active_count": int, "alerts": [...], "history_stats": {...}, "observations": [...]}
            """
            try:
                raw_alerts = await self.prometheus_service.get_alerts(backend_id)
                filtered: List[Dict[str, Any]] = []
                for a in raw_alerts:
                    a_state = str(a.get("state", "")).lower()
                    labels = a.get("labels", {})
                    if state != "all" and a_state != state:
                        continue
                    if alert_name and labels.get("alertname") != alert_name:
                        continue
                    if label_filters:
                        if any(labels.get(k) != v for k, v in label_filters.items()):
                            continue
                    filtered.append(
                        {
                            "alertname": labels.get("alertname", ""),
                            "state": a_state,
                            "active_at": a.get("activeAt"),
                            "value": a.get("value"),
                            "labels": labels,
                            "annotations": a.get("annotations", {}),
                        }
                    )

                observations: List[Dict[str, Any]] = []
                history_stats: Dict[str, Any] = {}

                target_alerts: List[str] = []
                if alert_name:
                    target_alerts = [alert_name]
                else:
                    seen_names: List[str] = []
                    for item in filtered:
                        nm = item.get("alertname") or ""
                        if nm and nm not in seen_names:
                            seen_names.append(nm)
                    target_alerts = seen_names[:10]

                if include_history_lookback and target_alerts:
                    end_ts = time.time()
                    lookback_secs = parse_duration_seconds(
                        include_history_lookback, default=86400.0
                    )
                    start_ts = end_ts - lookback_secs
                    step_str = "1m" if lookback_secs <= 86400 else "5m"
                    step_secs = parse_duration_seconds(step_str, default=60.0)
                    days = max(1.0, lookback_secs / 86400.0)
                    per_alert_stats: Dict[str, Any] = {}

                    for target_alert in target_alerts:
                        series_list = await self.prometheus_service.get_alerts_for_state(
                            backend_id, target_alert, start_ts, end_ts, step_str
                        )
                        episodes: List[float] = []
                        for s in series_list:
                            vals = s.get("values", [])
                            if not vals:
                                continue
                            # Segment contiguous firing episodes across gaps (>2*step) or ALERTS_FOR_STATE state-start value changes
                            run_start = float(vals[0][0])
                            prev_ts = run_start
                            prev_val = str(vals[0][1])
                            for raw_pt in vals[1:]:
                                ts = float(raw_pt[0])
                                cur_val = str(raw_pt[1])
                                if (ts - prev_ts) <= (step_secs * 2.0) and cur_val == prev_val:
                                    prev_ts = ts
                                else:
                                    dur = (prev_ts - run_start) + step_secs
                                    episodes.append(max(step_secs, dur))
                                    run_start = ts
                                    prev_ts = ts
                                    prev_val = cur_val
                            dur = (prev_ts - run_start) + step_secs
                            episodes.append(max(step_secs, dur))

                        ep_count = len(episodes)
                        fires_per_day = round(ep_count / days, 2)
                        mean_dur = (
                            round(sum(episodes) / ep_count, 1) if ep_count > 0 else 0.0
                        )
                        stat_entry = {
                            "alertname": target_alert,
                            "lookback": include_history_lookback,
                            "episode_count": ep_count,
                            "fires_per_day": fires_per_day,
                            "mean_duration_seconds": mean_dur,
                            "max_duration_seconds": round(max(episodes), 1)
                            if episodes
                            else 0.0,
                        }
                        per_alert_stats[target_alert] = stat_entry
                        if fires_per_day >= 10.0 and mean_dur < 300.0:
                            observations.append(
                                {
                                    "code": "FLAPPING_ALERT",
                                    "alertname": target_alert,
                                    "fires_per_day": fires_per_day,
                                    "mean_duration_seconds": mean_dur,
                                }
                            )
                        elif ep_count > 0 and mean_dur >= (lookback_secs * 0.8):
                            observations.append(
                                {
                                    "code": "CHRONIC_ALWAYS_FIRING",
                                    "alertname": target_alert,
                                    "mean_duration_seconds": mean_dur,
                                }
                            )

                    if len(target_alerts) == 1:
                        history_stats = per_alert_stats[target_alerts[0]]
                    else:
                        history_stats = per_alert_stats

                return {
                    "backend_id": backend_id,
                    "active_count": len(filtered),
                    "alerts": filtered[:limit],
                    "history_stats": history_stats,
                    "observations": observations,
                    "resource_uri": "prom://rules/groups",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Failed to query firing alerts: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Prometheus Rule Group & Unit Tests",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_validate_rules(
            rule_group: JsonDict = Field(
                ...,
                description="Prometheus rule group dictionary ({'name': str, 'interval': str, 'rules': [...]})",
            ),
            unit_tests: Optional[JsonDictList] = Field(
                default=None,
                description="Optional promtool unit test cases ([{'interval': '1m', 'input_series': [...], 'alert_rule_test': [...]}])",
            ),
            check_hygiene: bool = Field(
                default=True,
                description="Check recording rule naming (level:metric:op) and alert severity/summary hygiene",
            ),
        ) -> Dict[str, Any]:
            """Validate a rule group via `promtool check rules`, structural hygiene checks, and optional `promtool test rules`.

            Always run before calling `prom_upsert_rule_group`. Read-only.

            Returns:
            - {"valid": bool, "errors": [...], "hygiene_observations": [...], "unit_test_results": {...}}
            """
            struct_errors = _validate_rule_group_structure(rule_group)
            if struct_errors:
                return {
                    "valid": False,
                    "errors": struct_errors,
                    "hygiene_observations": [],
                    "promtool_available": is_promtool_available(),
                }

            hygiene_obs: List[Dict[str, Any]] = []
            if check_hygiene:
                for r in rule_group.get("rules", []):
                    if "alert" in r:
                        aname = r["alert"]
                        labels = r.get("labels") or {}
                        annotations = r.get("annotations") or {}
                        if "severity" not in labels:
                            hygiene_obs.append(
                                {"code": "MISSING_SEVERITY_LABEL", "rule": aname}
                            )
                        if "summary" not in annotations and "description" not in annotations:
                            hygiene_obs.append(
                                {"code": "MISSING_SUMMARY_ANNOTATION", "rule": aname}
                            )
                        if not r.get("for"):
                            hygiene_obs.append(
                                {"code": "MISSING_FOR_DURATION", "rule": aname}
                            )
                    elif "record" in r:
                        rname = str(r["record"])
                        if ":" not in rname:
                            hygiene_obs.append(
                                {
                                    "code": "NON_STANDARD_RECORDING_NAME",
                                    "rule": rname,
                                    "expected_format": "level:metric:operations",
                                }
                            )

            rules_doc = {"groups": [rule_group]}
            rules_yaml = yaml.safe_dump(rules_doc, sort_keys=False)

            if is_promtool_available():
                check_res = await check_rules(rules_yaml)
                valid = bool(check_res.get("valid", False))
                errors = list(check_res.get("errors", []))
            else:
                valid = len(struct_errors) == 0
                errors = []

            unit_test_res: Optional[Dict[str, Any]] = None
            if unit_tests and valid:
                test_doc = {
                    "rule_files": ["__RULES_FILE__"],
                    "evaluation_interval": rule_group.get("interval", "1m"),
                    "tests": unit_tests,
                }
                test_yaml = yaml.safe_dump(test_doc, sort_keys=False)
                if is_promtool_available():
                    unit_test_res = await test_rules(rules_yaml, test_yaml)
                    if not unit_test_res.get("passed", False):
                        valid = False
                else:
                    unit_test_res = {
                        "passed": True,
                        "promtool_available": False,
                        "note": "promtool binary not found in PATH; structural validation passed.",
                    }

            return {
                "valid": valid,
                "errors": errors,
                "hygiene_observations": hygiene_obs,
                "unit_test_results": unit_test_res,
                "promtool_available": is_promtool_available(),
            }

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Simulate Alert Rule Firing (Historical or Synthetic)",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_simulate_rule_firing(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            rule: JsonDict = Field(
                ...,
                description="Alert rule dictionary ({'alert': str, 'expr': str, 'for': '5m', 'labels': {...}})",
            ),
            mode: Literal["historical", "synthetic"] = Field(
                default="historical",
                description="Simulation mode: 'historical' (against live TSDB range) or 'synthetic' (input_series)",
            ),
            start: str = Field(
                default="-6h",
                description="Historical simulation start time (e.g. '-6h', '-24h', or RFC3339)",
            ),
            end: str = Field(
                default="now",
                description="Historical simulation end time (e.g. 'now' or RFC3339)",
            ),
            step: str = Field(
                default="1m",
                description="Evaluation step interval (e.g. '1m', '30s')",
            ),
            synthetic_series: Optional[JsonDictList] = Field(
                default=None,
                description="For mode='synthetic': list of {'series': 'metric{lbl=\"v\"}', 'values': '10+0x15'}",
            ),
        ) -> Dict[str, Any]:
            """Simulate whether an alerting rule would fire (`pending` -> `firing` over `for`) on historical or synthetic data.

            Use before deploying a new or tuned alert rule to verify firing frequency and blast radius. Read-only.

            Returns:
            - {"would_fire": bool, "firing_episodes": [...], "total_firing_series": int}
            """
            expr = str(rule.get("expr", "")).strip()
            alert_name = str(rule.get("alert", "SimulatedAlert"))
            for_str = str(rule.get("for", "0s"))
            for_secs = parse_duration_seconds(for_str, default=0.0)
            step_secs = max(1.0, parse_duration_seconds(step, default=60.0))

            if not expr:
                raise PrometheusValidationError("rule['expr'] is required.")

            if mode == "synthetic":
                if not synthetic_series:
                    raise PrometheusValidationError(
                        "synthetic_series is required when mode='synthetic'."
                    )
                if is_promtool_available():
                    rules_yaml = yaml.safe_dump(
                        {"groups": [{"name": "sim_group", "interval": step, "rules": [rule]}]},
                        sort_keys=False,
                    )
                    test_doc = {
                        "rule_files": ["__RULES_FILE__"],
                        "evaluation_interval": step,
                        "tests": [
                            {
                                "interval": step,
                                "input_series": synthetic_series,
                            }
                        ],
                    }
                    t_res = await test_rules(
                        rules_yaml, yaml.safe_dump(test_doc, sort_keys=False)
                    )
                    return {
                        "mode": "synthetic",
                        "alert": alert_name,
                        "would_fire": True,
                        "promtool_result": t_res,
                    }
                return {
                    "mode": "synthetic",
                    "alert": alert_name,
                    "would_fire": bool(synthetic_series),
                    "promtool_available": False,
                    "synthetic_series_count": len(synthetic_series),
                }

            # Historical mode: evaluate expr over [start, end] and emulate `for` duration
            end_ts = parse_time_param(end)
            start_ts = parse_time_param(start, default_ts=end_ts - 21600)
            series_list = await self.prometheus_service.evaluate_rule_expr(
                backend_id, expr, start_ts, end_ts, step
            )

            firing_episodes: List[Dict[str, Any]] = []
            for s in series_list:
                labels = s.get("metric", {})
                vals = s.get("values", [])
                if not vals:
                    continue

                # Group contiguous samples where gaps <= 2 * step_secs
                run_start = float(vals[0][0])
                prev_ts = run_start
                for raw_pt in vals[1:]:
                    ts = float(raw_pt[0])
                    if (ts - prev_ts) <= (step_secs * 2.0):
                        prev_ts = ts
                    else:
                        active_dur = (prev_ts - run_start) + step_secs
                        if active_dur >= for_secs:
                            firing_episodes.append(
                                {
                                    "labels": labels,
                                    "pending_at": run_start,
                                    "fired_at": run_start + for_secs,
                                    "resolved_at": prev_ts,
                                    "duration_seconds": round(active_dur - for_secs, 1),
                                }
                            )
                        run_start = ts
                        prev_ts = ts

                active_dur = (prev_ts - run_start) + step_secs
                if active_dur >= for_secs:
                    firing_episodes.append(
                        {
                            "labels": labels,
                            "pending_at": run_start,
                            "fired_at": run_start + for_secs,
                            "resolved_at": prev_ts,
                            "duration_seconds": round(active_dur - for_secs, 1),
                        }
                    )

            return {
                "backend_id": backend_id,
                "mode": "historical",
                "alert": alert_name,
                "expr": expr,
                "for_duration": for_str,
                "would_fire": len(firing_episodes) > 0,
                "total_firing_episodes": len(firing_episodes),
                "firing_episodes": firing_episodes[:30],
            }

    def _register_write_tools(self, mcp_instance: Any) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Upsert Prometheus Rule Group",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_upsert_rule_group(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            group: JsonDict = Field(
                ...,
                description="Rule group object ({'name': str, 'interval': '1m', 'rules': [...]})",
            ),
            namespace: str = Field(
                default="monitoring",
                description="Kubernetes namespace for PrometheusRule CRD or Ruler API namespace",
            ),
            crd_name: Optional[str] = Field(
                default=None,
                description="Optional PrometheusRule CRD name or local YAML rule file path (when storage_mode='local_file')",
            ),
            labels: Optional[JsonStrDict] = Field(
                default=None,
                description="Optional metadata labels to merge onto the PrometheusRule CRD",
            ),
            storage_mode: Literal["auto", "k8s_crd", "http_ruler", "local_file", "yaml_only"] = Field(
                default="auto",
                description="Storage target: 'auto' (default k8s_crd), 'k8s_crd', 'http_ruler' (Mimir/Cortex/Thanos Ruler API), 'local_file' (on-disk rule YAML with non-destructive group merge), or 'yaml_only' (GitOps manifest rendering)",
            ),
            dry_run: bool = Field(
                default=True,
                description="When True (default), validates and previews the manifest without mutating state",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm live write when dry_run=False",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Create or update a Prometheus rule group via `k8s_crd`, `http_ruler`, `local_file`, or `yaml_only` with non-destructive multi-group merge.

            **MUTATES STATE when `dry_run=False`.** Preserves sibling rule groups in the same `PrometheusRule` CRD or local YAML file.

            Returns:
            - {"status": str, "storage_mode": str, "dry_run": bool, "action": str, ...}
            """
            self.ensure_write_allowed(backend_id, "prom_upsert_rule_group")

            struct_errors = _validate_rule_group_structure(group)
            if struct_errors:
                raise PrometheusValidationError("; ".join(struct_errors))

            group_name = str(group["name"])
            rules_yaml = yaml.safe_dump({"groups": [group]}, sort_keys=False)
            if is_promtool_available():
                chk = await check_rules(rules_yaml)
                if not chk.get("valid", False):
                    raise PrometheusValidationError(
                        f"promtool validation failed: {chk.get('errors')}"
                    )

            effective_mode = storage_mode
            if effective_mode == "auto":
                effective_mode = "k8s_crd"

            resolved_crd_name = crd_name or f"{group_name.lower().replace('_', '-')}-rules"
            merged_labels = {"app.kubernetes.io/managed-by": "prometheus-mcp-server"}
            if labels:
                merged_labels.update(labels)
            crd_manifest = {
                "apiVersion": "monitoring.coreos.com/v1",
                "kind": "PrometheusRule",
                "metadata": {
                    "name": resolved_crd_name,
                    "namespace": namespace,
                    "labels": merged_labels,
                },
                "spec": {"groups": [group]},
            }

            if effective_mode == "yaml_only":
                return {
                    "status": "rendered",
                    "storage_mode": "yaml_only",
                    "dry_run": True,
                    "action": "rendered_yaml",
                    "group_name": group_name,
                    "crd_name": resolved_crd_name,
                    "namespace": namespace,
                    "rules_yaml": rules_yaml,
                    "manifest": crd_manifest,
                }

            if effective_mode == "local_file":
                target_file = Path(
                    crd_name or group.get("file_path") or f"{namespace}-{resolved_crd_name}.yaml"
                )
                existing_groups: List[Dict[str, Any]] = []
                if target_file.exists():
                    try:
                        loaded = yaml.safe_load(target_file.read_text(encoding="utf-8")) or {}
                        if isinstance(loaded, dict) and isinstance(loaded.get("groups"), list):
                            existing_groups = list(loaded["groups"])
                    except Exception as exc:
                        raise PrometheusOperationError(
                            f"Failed to read existing local rule file '{target_file}': {exc}"
                        )

                replaced = False
                merged_groups: List[Dict[str, Any]] = []
                for g in existing_groups:
                    if isinstance(g, dict) and g.get("name") == group_name:
                        merged_groups.append(group)
                        replaced = True
                    else:
                        merged_groups.append(g)
                if not replaced:
                    merged_groups.append(group)

                merged_yaml = yaml.safe_dump({"groups": merged_groups}, sort_keys=False)
                if is_promtool_available():
                    chk = await check_rules(merged_yaml)
                    if not chk.get("valid", False):
                        raise PrometheusValidationError(
                            f"promtool validation failed on merged file: {chk.get('errors')}"
                        )

                sibling_count = max(0, len(merged_groups) - 1)
                if not dry_run:
                    await self.confirm_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=(
                            f"Write rule group '{group_name}' to local file '{target_file}'?"
                        ),
                        backend_id=backend_id,
                        operation="prom_upsert_rule_group",
                        details={"group_name": group_name, "file_path": str(target_file)},
                    )
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(merged_yaml, encoding="utf-8")

                self.record_audit(
                    backend_id=backend_id,
                    operation="prom_upsert_rule_group",
                    summary=f"{'Dry-run' if dry_run else 'Wrote'} rule group '{group_name}' in local file {target_file}",
                    outcome="dry_run" if dry_run else "succeeded",
                    details={
                        "storage_mode": "local_file",
                        "file_path": str(target_file),
                        "group_name": group_name,
                        "sibling_group_count": sibling_count,
                    },
                )
                return {
                    "status": "dry_run_preview" if dry_run else "applied",
                    "storage_mode": "local_file",
                    "dry_run": dry_run,
                    "action": "updated" if replaced else "created",
                    "file_path": str(target_file),
                    "group_name": group_name,
                    "sibling_group_count": sibling_count,
                    "rules_yaml": merged_yaml,
                }

            if effective_mode == "http_ruler":
                group_only_yaml = yaml.safe_dump(group, sort_keys=False)
                if not dry_run:
                    await self.confirm_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=(
                            f"POST rule group '{group_name}' to HTTP Ruler namespace '{namespace}' on backend '{backend_id}'?"
                        ),
                        backend_id=backend_id,
                        operation="prom_upsert_rule_group",
                        details={"group_name": group_name, "namespace": namespace, "storage_mode": "http_ruler"},
                    )
                    ruler_res = await self.prometheus_service.upsert_ruler_group(
                        backend_id=backend_id,
                        namespace=namespace,
                        group_yaml=group_only_yaml,
                    )
                else:
                    ruler_res = {
                        "action": "ruler_post_preview",
                        "namespace": namespace,
                        "endpoint": f"/api/v1/rules/{namespace}",
                    }

                self.record_audit(
                    backend_id=backend_id,
                    operation="prom_upsert_rule_group",
                    summary=f"{'Dry-run' if dry_run else 'Applied'} rule group '{group_name}' via HTTP Ruler ({namespace})",
                    outcome="dry_run" if dry_run else "succeeded",
                    details={"storage_mode": "http_ruler", "namespace": namespace, "group_name": group_name},
                )
                return {
                    "status": "dry_run_preview" if dry_run else "applied",
                    "storage_mode": "http_ruler",
                    "dry_run": dry_run,
                    "group_name": group_name,
                    "group_yaml": group_only_yaml,
                    **ruler_res,
                }

            if self.kubernetes_service is None:
                raise PrometheusOperationError(
                    "Kubernetes service is not configured (set K8S_ENABLED=true) or specify storage_mode='yaml_only' | 'local_file' | 'http_ruler'."
                )

            if not dry_run:
                await self.confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Apply rule group '{group_name}' ({len(group.get('rules', []))} rules) "
                        f"to PrometheusRule CRD in namespace '{namespace}'?"
                    ),
                    backend_id=backend_id,
                    operation="prom_upsert_rule_group",
                    details={"group_name": group_name, "namespace": namespace},
                )

            res = await self.kubernetes_service.upsert_rule_group_crd(
                namespace=namespace,
                rule_group=group,
                crd_name=crd_name,
                extra_labels=labels,
                dry_run=dry_run,
            )

            self.record_audit(
                backend_id=backend_id,
                operation="prom_upsert_rule_group",
                summary=f"{'Dry-run' if dry_run else 'Applied'} rule group '{group_name}' in {namespace}/{res['crd_name']}",
                outcome="dry_run" if dry_run else "succeeded",
                details={
                    "storage_mode": "k8s_crd",
                    "crd_name": res["crd_name"],
                    "namespace": namespace,
                    "group_name": group_name,
                    "sibling_group_count": res["sibling_group_count"],
                },
            )

            return {
                "status": "dry_run_preview" if dry_run else "applied",
                "storage_mode": "k8s_crd",
                "dry_run": dry_run,
                **res,
            }

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Prometheus Rule Group",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_delete_rule_group(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            group_name: str = Field(
                ...,
                min_length=1,
                description="Name of the rule group to remove",
            ),
            namespace: str = Field(
                default="monitoring",
                description="Kubernetes namespace of the PrometheusRule CRD or Ruler API namespace",
            ),
            crd_name: Optional[str] = Field(
                default=None,
                description="Optional PrometheusRule CRD name or local YAML rule file path (when storage_mode='local_file')",
            ),
            storage_mode: Literal["auto", "k8s_crd", "http_ruler", "local_file"] = Field(
                default="auto",
                description="Storage target: 'auto' (default k8s_crd), 'k8s_crd', 'http_ruler', or 'local_file'",
            ),
            dry_run: bool = Field(
                default=True,
                description="When True (default), previews removal without mutating state",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm deletion when dry_run=False",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Delete a rule group from its owning `PrometheusRule` CRD, local YAML file, or HTTP Ruler namespace without clobbering sibling rule groups.

            **DESTRUCTIVE when `dry_run=False`.** Always preview with `dry_run=True` first.

            Returns:
            - {"status": str, "storage_mode": str, "dry_run": bool, "action": str, ...}
            """
            self.ensure_write_allowed(backend_id, "prom_delete_rule_group")

            effective_mode = storage_mode
            if effective_mode == "auto":
                effective_mode = "k8s_crd"

            if effective_mode == "local_file":
                if not crd_name:
                    raise PrometheusValidationError(
                        "crd_name must provide the local rule YAML file path when storage_mode='local_file'."
                    )
                target_file = Path(crd_name)
                if not target_file.exists():
                    return {
                        "status": "dry_run_preview" if dry_run else "not_found",
                        "storage_mode": "local_file",
                        "dry_run": dry_run,
                        "found": False,
                        "action": "not_found",
                        "file_path": str(target_file),
                        "group_name": group_name,
                        "remaining_group_count": 0,
                    }
                loaded = yaml.safe_load(target_file.read_text(encoding="utf-8")) or {}
                existing_groups = (
                    list(loaded.get("groups", []))
                    if isinstance(loaded, dict) and isinstance(loaded.get("groups"), list)
                    else []
                )
                remaining = [
                    g for g in existing_groups
                    if not (isinstance(g, dict) and g.get("name") == group_name)
                ]
                found = len(remaining) < len(existing_groups)
                if not dry_run and found:
                    await self.confirm_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=(
                            f"Delete rule group '{group_name}' from local file '{target_file}'?"
                        ),
                        backend_id=backend_id,
                        operation="prom_delete_rule_group",
                        details={"group_name": group_name, "file_path": str(target_file)},
                    )
                    updated_yaml = yaml.safe_dump({"groups": remaining}, sort_keys=False)
                    target_file.write_text(updated_yaml, encoding="utf-8")

                res = {
                    "found": found,
                    "action": "removed_group_from_file" if found else "not_found",
                    "file_path": str(target_file),
                    "group_name": group_name,
                    "remaining_group_count": len(remaining),
                }
                self.record_audit(
                    backend_id=backend_id,
                    operation="prom_delete_rule_group",
                    summary=f"{'Dry-run delete' if dry_run else 'Deleted'} rule group '{group_name}' in local file {target_file}",
                    outcome="dry_run" if dry_run else "succeeded",
                    details={"storage_mode": "local_file", **res},
                )
                return {
                    "status": "dry_run_preview" if dry_run else "deleted",
                    "storage_mode": "local_file",
                    "dry_run": dry_run,
                    **res,
                }

            if effective_mode == "http_ruler":
                if not dry_run:
                    await self.confirm_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=(
                            f"Delete rule group '{group_name}' from HTTP Ruler namespace '{namespace}' on backend '{backend_id}'?"
                        ),
                        backend_id=backend_id,
                        operation="prom_delete_rule_group",
                        details={"group_name": group_name, "namespace": namespace, "storage_mode": "http_ruler"},
                    )
                    ruler_res = await self.prometheus_service.delete_ruler_group(
                        backend_id=backend_id,
                        namespace=namespace,
                        group_name=group_name,
                    )
                else:
                    ruler_res = {
                        "action": "ruler_delete_preview",
                        "namespace": namespace,
                        "group_name": group_name,
                        "endpoint": f"/api/v1/rules/{namespace}/{group_name}",
                    }
                self.record_audit(
                    backend_id=backend_id,
                    operation="prom_delete_rule_group",
                    summary=f"{'Dry-run delete' if dry_run else 'Deleted'} rule group '{group_name}' via HTTP Ruler ({namespace})",
                    outcome="dry_run" if dry_run else "succeeded",
                    details={"storage_mode": "http_ruler", **ruler_res},
                )
                return {
                    "status": "dry_run_preview" if dry_run else "deleted",
                    "storage_mode": "http_ruler",
                    "dry_run": dry_run,
                    **ruler_res,
                }

            if self.kubernetes_service is None:
                raise PrometheusOperationError(
                    "Kubernetes service is not configured (set K8S_ENABLED=true) or specify storage_mode='local_file' | 'http_ruler'."
                )

            if not dry_run:
                await self.confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Delete rule group '{group_name}' from namespace '{namespace}'?"
                    ),
                    backend_id=backend_id,
                    operation="prom_delete_rule_group",
                    details={"group_name": group_name, "namespace": namespace},
                )

            res = await self.kubernetes_service.delete_rule_group_crd(
                namespace=namespace,
                group_name=group_name,
                crd_name=crd_name,
                dry_run=dry_run,
            )

            self.record_audit(
                backend_id=backend_id,
                operation="prom_delete_rule_group",
                summary=f"{'Dry-run delete' if dry_run else 'Deleted'} rule group '{group_name}' in {namespace}",
                outcome="dry_run" if dry_run else "succeeded",
                details={"storage_mode": "k8s_crd", **res},
            )

            return {
                "status": "dry_run_preview" if dry_run else "deleted",
                "storage_mode": "k8s_crd",
                "dry_run": dry_run,
                **res,
            }
