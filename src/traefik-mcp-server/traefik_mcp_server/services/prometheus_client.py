"""Prometheus client and Traefik v3 metric label resolver."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests


def build_traefik_service_label_regex(namespace: str, service_name: str, port: Optional[Any] = None) -> str:
    """Build regex matching Traefik's Prometheus service label (`{ns}-{svc}-{port}@kubernetes` or `@kubernetescrd`)."""
    if "@" in service_name:
        return f"^{service_name}$"
    if port is not None:
        return f"^{namespace}-{service_name}-{port}(@kubernetes|@kubernetescrd)$"
    return f"^({namespace}-{service_name}(-[0-9a-zA-Z-]+)?(@kubernetes|@kubernetescrd)|.*{service_name}.*)$"


def build_traefik_router_label_regex(namespace: str, router_name: str) -> str:
    """Build regex matching Traefik's Prometheus router label (`{ns}-{router}@kubernetescrd`)."""
    if "@" in router_name:
        return f"^{router_name}$"
    return f"^({namespace}-{router_name}(-[0-9a-f]+)?(@kubernetescrd|@kubernetes|@kubernetesingressnginx)|.*{router_name}.*)$"


def build_traefik_label_regex(namespace: str, name: str, scope: str = "service") -> str:
    """Build regex matching Traefik's Prometheus service or router label."""
    if scope == "router":
        return build_traefik_router_label_regex(namespace, name)
    return build_traefik_service_label_regex(namespace, name)


class PrometheusClient:
    """HTTP client for querying Traefik v3 Prometheus metrics."""

    def __init__(
        self,
        prometheus_url: Optional[str] = "http://prometheus:9090",
        base_url: Optional[str] = "__UNSET__",
        timeout: float = 3.0,
        fixture_data: Optional[Dict[str, Any]] = None,
    ):
        url = prometheus_url if base_url == "__UNSET__" else base_url
        self.prometheus_url = (url or "").rstrip("/") if url else None
        self.timeout = timeout
        self.fixture_data = fixture_data

    def is_reachable(self) -> bool:
        if not self.prometheus_url:
            return False
        if self.fixture_data is not None:
            return True
        return bool(self.get_status().get("reachable"))

    def _query_scalar(self, promql: str) -> Optional[float]:
        if not self.prometheus_url:
            return None
        try:
            resp = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": promql},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
            if payload.get("status") != "success":
                return None
            results = payload.get("data", {}).get("result", [])
            if not results:
                return 0.0
            val = float(results[0]["value"][1])
            if val != val:  # NaN check
                return 0.0
            return round(val, 4)
        except Exception:
            return None

    def get_status(self) -> Dict[str, Any]:
        """Check Prometheus reachability and whether Traefik router labels are enabled."""
        if not self.prometheus_url:
            return {
                "status": "unconfigured",
                "reachable": False,
                "prometheus_url": None,
                "add_routers_labels": False,
                "message": "PROMETHEUS_URL is not configured.",
            }
        if self.fixture_data is not None:
            return {
                "status": "healthy",
                "reachable": True,
                "prometheus_url": self.prometheus_url,
                "http_status": 200,
                "add_routers_labels": True,
            }
        try:
            resp = requests.get(f"{self.prometheus_url}/-/healthy", timeout=self.timeout)
            reachable = resp.status_code == 200
            router_Check = self._query_scalar("count(traefik_router_requests_total)") if reachable else None
            return {
                "status": "healthy" if reachable else "degraded",
                "reachable": reachable,
                "prometheus_url": self.prometheus_url,
                "http_status": resp.status_code,
                "add_routers_labels": bool(router_Check and router_Check > 0),
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "reachable": False,
                "prometheus_url": self.prometheus_url,
                "add_routers_labels": False,
                "message": f"Prometheus is unreachable at {self.prometheus_url}: {exc}",
            }

    def get_service_summary(
        self,
        namespace: str,
        service: str,
        window: str = "5m",
        configured_backends: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Query RPS, 4xx/5xx error rate, p95 latency, and server_up for a service."""
        if not self.prometheus_url:
            return {
                "status": "unavailable",
                "service": service,
                "namespace": namespace,
                "prometheus_url": None,
                "message": "PROMETHEUS_URL is not configured.",
            }
        if self.fixture_data is not None:
            m_map = self.fixture_data.get("metrics_by_window") or {}
            fx = m_map.get((namespace, service, window)) or m_map.get((namespace, service, "5m"))
            if fx:
                return {
                    "status": "available",
                    "service": service,
                    "namespace": namespace,
                    "window": window,
                    "prometheus_url": self.prometheus_url,
                    "metrics": {
                        "request_rate_rps": fx.get("rps", 0.0),
                        "error_rate_4xx_pct": fx.get("error_rate_4xx_pct", 0.0),
                        "error_rate_5xx_pct": fx.get("error_rate_5xx_pct", 0.0),
                        "latency_p95_ms": fx.get("latency_p95_ms", fx.get("p95_ms", 0.0)),
                        "server_up_ratio": 1.0,
                    },
                }
        re_parts = [build_traefik_service_label_regex(namespace, service)]
        for b in configured_backends or []:
            if b.get("name"):
                re_parts.append(build_traefik_service_label_regex(namespace, str(b["name"]), b.get("port")))
        label_re = "|".join(f"(?:{p})" for p in re_parts) if len(re_parts) > 1 else re_parts[0]
        rps = self._query_scalar(
            f'sum(rate(traefik_service_requests_total{{service=~"{label_re}"}}[{window}]))'
        )
        if rps is None:
            return {
                "status": "unavailable",
                "service": service,
                "namespace": namespace,
                "prometheus_url": self.prometheus_url,
                "message": f"Unable to reach Prometheus at '{self.prometheus_url}'.",
            }
        err_5xx = self._query_scalar(
            f'sum(rate(traefik_service_requests_total{{service=~"{label_re}",code=~"5.."}}[{window}]))'
        ) or 0.0
        err_4xx = self._query_scalar(
            f'sum(rate(traefik_service_requests_total{{service=~"{label_re}",code=~"4.."}}[{window}]))'
        ) or 0.0
        p95_sec = self._query_scalar(
            f'histogram_quantile(0.95, sum(rate(traefik_service_request_duration_seconds_bucket{{service=~"{label_re}"}}[{window}])) by (le))'
        ) or 0.0
        server_up = self._query_scalar(
            f'avg(traefik_service_server_up{{service=~"{label_re}"}})'
        )
        err_5xx_pct = round((err_5xx / rps) * 100.0, 2) if rps > 0 else 0.0
        err_4xx_pct = round((err_4xx / rps) * 100.0, 2) if rps > 0 else 0.0
        return {
            "status": "available",
            "service": service,
            "namespace": namespace,
            "window": window,
            "prometheus_url": self.prometheus_url,
            "metrics": {
                "request_rate_rps": rps,
                "error_rate_4xx_pct": err_4xx_pct,
                "error_rate_5xx_pct": err_5xx_pct,
                "latency_p95_ms": round(p95_sec * 1000.0, 2),
                "server_up_ratio": server_up,
            },
        }

    def _window_metrics_for_selector(
        self,
        metric_prefix: str,
        selector: str,
        window: str,
    ) -> Optional[Dict[str, float]]:
        rps = self._query_scalar(
            f"sum(rate({metric_prefix}_requests_total{{{selector}}}[{window}]))"
        )
        if rps is None:
            return None
        err_5xx = self._query_scalar(
            f'sum(rate({metric_prefix}_requests_total{{{selector},code=~"5.."}}[{window}]))'
        ) or 0.0
        err_4xx = self._query_scalar(
            f'sum(rate({metric_prefix}_requests_total{{{selector},code=~"4.."}}[{window}]))'
        ) or 0.0
        p50 = (
            self._query_scalar(
                f"histogram_quantile(0.50, sum(rate({metric_prefix}_request_duration_seconds_bucket{{{selector}}}[{window}])) by (le))"
            )
            or 0.0
        ) * 1000.0
        p95 = (
            self._query_scalar(
                f"histogram_quantile(0.95, sum(rate({metric_prefix}_request_duration_seconds_bucket{{{selector}}}[{window}])) by (le))"
            )
            or 0.0
        ) * 1000.0
        p99 = (
            self._query_scalar(
                f"histogram_quantile(0.99, sum(rate({metric_prefix}_request_duration_seconds_bucket{{{selector}}}[{window}])) by (le))"
            )
            or 0.0
        ) * 1000.0
        return {
            "rps": round(rps, 4),
            "error_rate_4xx_pct": round((err_4xx / rps) * 100.0, 2) if rps > 0 else 0.0,
            "error_rate_5xx_pct": round((err_5xx / rps) * 100.0, 2) if rps > 0 else 0.0,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
        }

    def compare_windows(
        self,
        scope: str,
        name: str,
        namespace: str = "default",
        baseline_window: str = "1h",
        comparison_window: str = "15m",
        configured_backends: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Compare baseline and comparison windows across service, router, or entrypoint scope."""
        scope_l = scope.strip().lower()
        if scope_l == "router":
            metric_prefix = "traefik_router"
            label_re = build_traefik_router_label_regex(namespace, name)
            selector = f'router=~"{label_re}"'
        elif scope_l == "entrypoint":
            metric_prefix = "traefik_entrypoint"
            selector = f'entrypoint="{name}"'
        else:
            metric_prefix = "traefik_service"
            re_parts = [build_traefik_service_label_regex(namespace, name)]
            for b in configured_backends or []:
                if b.get("name"):
                    re_parts.append(build_traefik_service_label_regex(namespace, str(b["name"]), b.get("port")))
            label_re = "|".join(f"(?:{p})" for p in re_parts) if len(re_parts) > 1 else re_parts[0]
            selector = f'service=~"{label_re}"'

        if self.fixture_data is not None:
            m_map = self.fixture_data.get("metrics_by_window") or {}
            fx_base = m_map.get((namespace, name, baseline_window))
            fx_comp = m_map.get((namespace, name, comparison_window))
            if fx_base and fx_comp:
                base = {
                    "rps": fx_base.get("rps", 0.0),
                    "error_rate_4xx_pct": fx_base.get("error_rate_4xx_pct", 0.0),
                    "error_rate_5xx_pct": fx_base.get("error_rate_5xx_pct", 0.0),
                    "p50_ms": fx_base.get("latency_p50_ms", fx_base.get("p50_ms", 0.0)),
                    "p95_ms": fx_base.get("latency_p95_ms", fx_base.get("p95_ms", 0.0)),
                    "p99_ms": fx_base.get("latency_p99_ms", fx_base.get("p99_ms", 0.0)),
                }
                comp = {
                    "rps": fx_comp.get("rps", 0.0),
                    "error_rate_4xx_pct": fx_comp.get("error_rate_4xx_pct", 0.0),
                    "error_rate_5xx_pct": fx_comp.get("error_rate_5xx_pct", 0.0),
                    "p50_ms": fx_comp.get("latency_p50_ms", fx_comp.get("p50_ms", 0.0)),
                    "p95_ms": fx_comp.get("latency_p95_ms", fx_comp.get("p95_ms", 0.0)),
                    "p99_ms": fx_comp.get("latency_p99_ms", fx_comp.get("p99_ms", 0.0)),
                }
            else:
                base = self._window_metrics_for_selector(metric_prefix, selector, baseline_window)
                comp = self._window_metrics_for_selector(metric_prefix, selector, comparison_window)
        else:
            base = self._window_metrics_for_selector(metric_prefix, selector, baseline_window)
            comp = self._window_metrics_for_selector(metric_prefix, selector, comparison_window)

        if base is None or comp is None:
            return {
                "scope": scope_l,
                "name": name,
                "namespace": namespace,
                "baseline_window": baseline_window,
                "comparison_window": comparison_window,
                "prometheus_available": False,
                "verdict": "insufficient_data",
                "summary": (
                    f"Prometheus metrics unavailable for {scope_l} '{name}' at {self.prometheus_url}. "
                    + (
                        "Ensure --metrics.prometheus.addRoutersLabels=true is enabled in Traefik static config."
                        if scope_l == "router"
                        else "Read 'traefik://server/capabilities' to check Prometheus connectivity."
                    )
                ),
                "baseline": {},
                "comparison": {},
                "deltas": {},
                "backend_split": [],
            }

        deltas = {
            "rps_delta": round(comp["rps"] - base["rps"], 4),
            "error_rate_5xx_delta_pct": round(comp["error_rate_5xx_pct"] - base["error_rate_5xx_pct"], 2),
            "error_rate_4xx_delta_pct": round(comp["error_rate_4xx_pct"] - base["error_rate_4xx_pct"], 2),
            "p95_delta_ms": round(comp["p95_ms"] - base["p95_ms"], 2),
            "p99_delta_ms": round(comp["p99_ms"] - base["p99_ms"], 2),
        }

        if base["rps"] == 0 and comp["rps"] == 0:
            verdict = "insufficient_data"
        elif comp["error_rate_5xx_pct"] >= 5.0 or deltas["error_rate_5xx_delta_pct"] >= 2.0 or (
            base["p99_ms"] > 0 and comp["p99_ms"] > base["p99_ms"] * 1.5 and deltas["p99_delta_ms"] > 50.0
        ):
            verdict = "regression"
        elif deltas["error_rate_5xx_delta_pct"] < -0.5 or (
            base["p99_ms"] > 0 and comp["p99_ms"] < base["p99_ms"] * 0.8
        ):
            verdict = "improved"
        else:
            verdict = "stable"

        # Compute observed vs configured backend split when configured_backends provided
        backend_split: List[Dict[str, Any]] = []
        if configured_backends:
            total_cfg_weight = sum(int(b.get("weight") or 0) for b in configured_backends) or 100
            obs_rates: List[float] = []
            for b in configured_backends:
                b_name = b.get("name", "")
                if self.fixture_data is not None:
                    fx_b = (self.fixture_data.get("metrics_by_window") or {}).get((namespace, b_name, comparison_window))
                    r = float(fx_b.get("rps", 0.0)) if fx_b else 0.0
                else:
                    b_re = build_traefik_service_label_regex(namespace, b_name, b.get("port"))
                    r = self._query_scalar(
                        f'sum(rate(traefik_service_requests_total{{service=~"{b_re}"}}[{comparison_window}]))'
                    ) or 0.0
                obs_rates.append(r)
            total_obs = sum(obs_rates)
            for b, obs_r in zip(configured_backends, obs_rates):
                w = int(b.get("weight") or 0)
                cfg_pct = round((w / total_cfg_weight) * 100.0, 1)
                obs_pct = round((obs_r / total_obs) * 100.0, 1) if total_obs > 0 else cfg_pct
                backend_split.append({
                    "name": b.get("name"),
                    "port": b.get("port", 80),
                    "configured_weight": w,
                    "configured_percent": cfg_pct,
                    "observed_rps": obs_r,
                    "observed_percent": obs_pct,
                })

        summary = (
            f"[{verdict.upper()}] {scope_l} '{name}' ({comparison_window} vs {baseline_window}): "
            f"RPS={comp['rps']} (delta {deltas['rps_delta']:+}), "
            f"5xx={comp['error_rate_5xx_pct']}% (delta {deltas['error_rate_5xx_delta_pct']:+}%), "
            f"p99={comp['p99_ms']}ms (delta {deltas['p99_delta_ms']:+}ms)."
        )

        return {
            "scope": scope_l,
            "name": name,
            "namespace": namespace,
            "baseline_window": baseline_window,
            "comparison_window": comparison_window,
            "prometheus_available": True,
            "verdict": verdict,
            "summary": summary,
            "baseline": base,
            "comparison": comp,
            "deltas": deltas,
            "backend_split": backend_split,
        }
