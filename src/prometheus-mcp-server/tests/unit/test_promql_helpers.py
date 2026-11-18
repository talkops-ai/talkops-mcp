"""Unit tests for PromQL semantic counter enforcement, PromQL 3.0 syntax, and series stats."""

from __future__ import annotations

from prometheus_mcp_server.utils.promql_helpers import (
    compute_auto_step,
    compute_series_stats,
    enforce_counter_rule_sync,
    parse_duration_seconds,
)

METADATA = {
    "http_requests_total": [{"type": "counter", "help": "Total HTTP requests"}],
    "my_http_requests_total": [{"type": "gauge", "help": "Custom gauge containing substring"}],
    "http.server.requests_total": [{"type": "counter", "help": "OTel UTF-8 counter"}],
    "node_memory_bytes": [{"type": "gauge", "help": "Memory gauge"}],
}


class TestPromQLHelpers:
    def test_enforce_counter_rule_rejects_raw_counter(self) -> None:
        err = enforce_counter_rule_sync(
            METADATA, 'sum by (job) (http_requests_total{job="api"})', allow_raw=False
        )
        assert err is not None
        assert "http_requests_total" in err

    def test_enforce_counter_rule_allows_wrapped_counter(self) -> None:
        err = enforce_counter_rule_sync(
            METADATA,
            'sum by (job) (rate(http_requests_total{job="api"}[5m]))',
            allow_raw=False,
        )
        assert err is None

    def test_enforce_counter_rule_no_substring_false_positive(self) -> None:
        # `my_http_requests_total` is a gauge in METADATA while `http_requests_total` is a counter.
        # Querying `my_http_requests_total` raw MUST NOT trigger a false-positive error for `http_requests_total`!
        err = enforce_counter_rule_sync(
            METADATA, 'my_http_requests_total{job="api"}', allow_raw=False
        )
        assert err is None

    def test_enforce_counter_rule_catches_second_unwrapped_counter_in_binary_expr(
        self,
    ) -> None:
        # Previously `q.startswith("rate(")` bypassed checking the second operand!
        err = enforce_counter_rule_sync(
            METADATA,
            "rate(http_requests_total[5m]) + http_requests_total",
            allow_raw=False,
        )
        assert err is not None

    def test_enforce_counter_rule_supports_promql_3_utf8_quoted_counter(self) -> None:
        raw_err = enforce_counter_rule_sync(
            METADATA, '{"http.server.requests_total", job="api"}', allow_raw=False
        )
        assert raw_err is not None

        wrapped_ok = enforce_counter_rule_sync(
            METADATA,
            'rate({"http.server.requests_total", job="api"}[5m])',
            allow_raw=False,
        )
        assert wrapped_ok is None

    def test_enforce_counter_rule_rejects_unbounded_name_regex(self) -> None:
        for pat in ('{__name__=~".+"}', '{__name__=~"..*", namespace="otel-demo"}', '{__name__=~"^.*$"}'):
            err = enforce_counter_rule_sync(METADATA, pat, allow_raw=False)
            assert err is not None
            assert "Unbounded metric selector" in err

    def test_exporter_secret_env_and_blackbox_configmap(self) -> None:
        from prometheus_mcp_server.utils.exporter_catalog import build_exporter_manifests
        from prometheus_mcp_server.utils.redaction import redact_sensitive_data

        pg_manifests = build_exporter_manifests(
            exporter_type="postgres_exporter",
            namespace="otel-demo",
            service_name="otel-demo-pg-exporter",
            config={
                "secret_env": {
                    "DATA_SOURCE_NAME": {"name": "otel-demo-pg-dsn", "key": "dsn"}
                }
            },
        )
        dep = next(m for m in pg_manifests if m["kind"] == "Deployment")
        env_list = dep["spec"]["template"]["spec"]["containers"][0]["env"]
        assert env_list == [
            {
                "name": "DATA_SOURCE_NAME",
                "valueFrom": {"secretKeyRef": {"name": "otel-demo-pg-dsn", "key": "dsn"}},
            }
        ]
        redacted = redact_sensitive_data(pg_manifests)
        r_dep = next(m for m in redacted if m["kind"] == "Deployment")
        assert r_dep["spec"]["template"]["spec"]["containers"][0]["env"][0]["valueFrom"]["secretKeyRef"]["name"] == "otel-demo-pg-dsn"

        bb_manifests = build_exporter_manifests(
            exporter_type="blackbox_exporter",
            namespace="observability",
            service_name="blackbox-exporter",
            config={},
        )
        bb_cm = next(m for m in bb_manifests if m["kind"] == "ConfigMap")
        assert "config.yml" in bb_cm["data"] and "blackbox.yml" in bb_cm["data"]
        bb_dep = next(m for m in bb_manifests if m["kind"] == "Deployment")
        assert "--config.file=/config/config.yml" in bb_dep["spec"]["template"]["spec"]["containers"][0]["args"]

    def test_parse_duration_and_series_stats(self) -> None:
        assert parse_duration_seconds("5m") == 300.0
        assert parse_duration_seconds("1h30m") == 5400.0
        assert compute_auto_step(1000.0, 4600.0, max_points=120) == "30s"

        stats = compute_series_stats([(1.0, 10.0), (2.0, 20.0), (3.0, 30.0)])
        assert stats["sample_count"] == 3
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["avg"] == 20.0
        assert stats["latest"] == 30.0
        assert stats["delta_pct"] == 200.0
