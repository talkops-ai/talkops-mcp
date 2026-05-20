"""Alert firing simulation tools.

Provides granular tools for simulating alert firing behavior
using synthetic tests, historical data, and firing history analysis.
"""

import time
from typing import Any, Dict, List, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.promtool_runner import test_rules


def _parse_duration_to_seconds(duration: str) -> float:
    """Parse Prometheus duration string (e.g. '5m', '1h', '30s') to seconds."""
    duration = duration.strip()
    if not duration:
        return 0

    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    if duration[-1] in multipliers:
        try:
            return float(duration[:-1]) * multipliers[duration[-1]]
        except ValueError:
            pass
    try:
        return float(duration)
    except ValueError:
        return 0


class SimulationTools(BaseTool):
    """Alert firing simulation and analysis tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        prometheus_service = self.prometheus_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Simulate Alert Firing (Synthetic)",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_simulate_firing_synthetic(
            alert_name: str = Field(
                ..., description="Alert rule name for the test"
            ),
            expr: str = Field(
                ..., description="PromQL expression for the alert rule"
            ),
            input_series: List[Dict[str, Any]] = Field(
                ..., description="Test input series: [{\"series\": str, \"values\": str}]"
            ),
            for_duration: str = Field(
                default="5m", description="For duration before firing (e.g. '5m')"
            ),
            expected_alerts: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Expected alert evaluations: [{\"eval_time\": str, \"alertname\": str, \"exp_alerts\": [{\"exp_labels\": {...}}]}]"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Run synthetic alert firing test via promtool.

            Use this to verify that an alert rule fires correctly under
            controlled conditions with synthetic metric data. Read-only.

            Returns:
            - {\"passed\": bool, \"total_tests\": int, \"output\": str,
               \"errors\": [str], \"promtool_available\": bool}

            When NOT to use: For testing against real historical data, use
            prom_simulate_firing_historical instead.

            Prerequisites:
            - promtool binary must be in PATH (optional — graceful fallback).
            """
            try:
                # Build rules YAML
                rules_yaml = yaml.dump({
                    "groups": [{
                        "name": "test_group",
                        "rules": [{
                            "alert": alert_name,
                            "expr": expr,
                            "for": for_duration,
                            "labels": {"severity": "test"},
                        }],
                    }],
                }, default_flow_style=False)

                # Build test YAML
                alert_eval_list = expected_alerts or [{
                    "eval_time": for_duration,
                    "alertname": alert_name,
                }]

                test_spec = {
                    "rule_files": ["__RULES_FILE__"],
                    "evaluation_interval": "1m",
                    "tests": [{
                        "interval": "1m",
                        "input_series": input_series,
                        "alert_rule_test": alert_eval_list,
                    }],
                }
                test_yaml = yaml.dump(test_spec, default_flow_style=False)

                result = await test_rules(rules_yaml, test_yaml)
                return result
            except Exception as e:
                raise PrometheusOperationError(f"Synthetic simulation failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Simulate Alert Firing (Historical)",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_simulate_firing_historical(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            expr: str = Field(
                ..., description="PromQL alert expression to evaluate"
            ),
            for_duration: str = Field(
                default="5m", description="For duration before firing (e.g. '5m')"
            ),
            start: Optional[float] = Field(
                default=None, description="Start timestamp (defaults to now - 24h)"
            ),
            end: Optional[float] = Field(
                default=None, description="End timestamp (defaults to now)"
            ),
            step: str = Field(
                default="1m", description="Evaluation step (e.g. '1m', '30s')"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Evaluate alert expression against real historical data.

            Simulates the pending→firing state machine using a range query.
            Use this to answer "would this rule have fired in the last 24h?"
            Read-only.

            Returns:
            - {\"would_fire\": bool, \"firing_windows\": [{\"start\": float, \"end\": float}],
               \"pending_windows\": [...], \"total_firing_duration_seconds\": float,
               \"explanation\": str}

            When NOT to use: For synthetic/deterministic testing, use
            prom_simulate_firing_synthetic.
            """
            try:
                now = time.time()
                eval_start = start or (now - 86400)
                eval_end = end or now

                # Evaluate the expression over the time range
                series = await prometheus_service.evaluate_rule_expr(
                    backend_id, expr, eval_start, eval_end, step
                )

                for_seconds = _parse_duration_to_seconds(for_duration)

                # Simulate pending→firing state machine
                firing_windows: List[Dict[str, Any]] = []
                pending_windows: List[Dict[str, Any]] = []
                total_firing = 0.0

                for s in series:
                    values = s.get("values", [])
                    pending_start: Optional[float] = None
                    firing_start: Optional[float] = None

                    for ts, val in values:
                        ts = float(ts)
                        val_f = float(val) if isinstance(val, (int, float, str)) else 0

                        if val_f > 0:  # Expression is true
                            if pending_start is None:
                                pending_start = ts

                            elapsed = ts - pending_start
                            if elapsed >= for_seconds and firing_start is None:
                                firing_start = ts
                                pending_windows.append({
                                    "start": pending_start,
                                    "end": ts,
                                    "duration_seconds": elapsed,
                                })
                        else:
                            # Expression became false
                            if firing_start is not None:
                                firing_dur = ts - firing_start
                                firing_windows.append({
                                    "start": firing_start,
                                    "end": ts,
                                    "duration_seconds": firing_dur,
                                })
                                total_firing += firing_dur
                                firing_start = None
                            pending_start = None

                    # Handle case where still firing at end of range
                    if firing_start is not None:
                        firing_dur = eval_end - firing_start
                        firing_windows.append({
                            "start": firing_start,
                            "end": eval_end,
                            "duration_seconds": firing_dur,
                        })
                        total_firing += firing_dur

                would_fire = len(firing_windows) > 0
                explanation = (
                    f"Alert would have fired {len(firing_windows)} time(s) "
                    f"for a total of {total_firing:.0f} seconds "
                    f"in the evaluated time range."
                    if would_fire else
                    "Alert would NOT have fired in the evaluated time range."
                )

                return {
                    "would_fire": would_fire,
                    "firing_windows": firing_windows,
                    "pending_windows": pending_windows,
                    "total_firing_duration_seconds": total_firing,
                    "series_evaluated": len(series),
                    "explanation": explanation,
                }
            except Exception as e:
                raise PrometheusOperationError(f"Historical simulation failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Analyze Alert Firing History",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_analyze_firing_history(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            alert_name: str = Field(
                ..., description="Alert name to analyze"
            ),
            lookback_hours: int = Field(
                default=24, description="Hours to look back (default: 24)"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Analyze alert firing frequency and duration for tuning.

            Uses ALERTS_FOR_STATE metric to compute firing statistics.
            Use this to identify noisy alerts or tune thresholds. Read-only.

            Returns:
            - {\"alert_name\": str, \"total_firings\": int,
               \"avg_firing_duration_seconds\": float,
               \"max_firing_duration_seconds\": float,
               \"firing_frequency_per_day\": float,
               \"recommendation\": str}

            When NOT to use: For simulating rule changes, use
            prom_simulate_firing_historical.
            """
            try:
                now = time.time()
                start = now - (lookback_hours * 3600)
                step = "5m"

                series = await prometheus_service.get_alerts_for_state(
                    backend_id, alert_name, start, now, step
                )

                # Analyze firing windows
                firing_durations: List[float] = []

                for s in series:
                    values = s.get("values", [])
                    fire_start: Optional[float] = None

                    for ts, val in values:
                        ts_f = float(ts)
                        val_f = float(val) if isinstance(val, (int, float, str)) else 0

                        if val_f > 0 and fire_start is None:
                            fire_start = ts_f
                        elif val_f == 0 and fire_start is not None:
                            firing_durations.append(ts_f - fire_start)
                            fire_start = None

                    if fire_start is not None:
                        firing_durations.append(now - fire_start)

                total_firings = len(firing_durations)
                avg_duration = (
                    sum(firing_durations) / total_firings
                    if total_firings > 0 else 0
                )
                max_duration = max(firing_durations) if firing_durations else 0
                frequency_per_day = (
                    total_firings / (lookback_hours / 24)
                    if lookback_hours > 0 else 0
                )

                # Generate recommendation
                recommendation = ""
                if total_firings == 0:
                    recommendation = "No firings detected. Alert may need lower thresholds or the issue hasn't occurred."
                elif frequency_per_day > 10:
                    recommendation = (
                        f"Alert is noisy ({frequency_per_day:.1f} firings/day). "
                        "Consider increasing 'for' duration or adjusting thresholds."
                    )
                elif avg_duration < 60:
                    recommendation = (
                        f"Average firing duration is very short ({avg_duration:.0f}s). "
                        "Consider increasing 'for' duration to reduce flapping."
                    )
                else:
                    recommendation = "Alert firing pattern looks healthy."

                return {
                    "alert_name": alert_name,
                    "lookback_hours": lookback_hours,
                    "total_firings": total_firings,
                    "avg_firing_duration_seconds": round(avg_duration, 2),
                    "max_firing_duration_seconds": round(max_duration, 2),
                    "firing_frequency_per_day": round(frequency_per_day, 2),
                    "recommendation": recommendation,
                }
            except Exception as e:
                raise PrometheusOperationError(f"Firing history analysis failed: {e}")
