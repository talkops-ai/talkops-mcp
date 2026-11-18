"""Sample Prometheus query fixtures for testing."""

import copy
from typing import Any, Dict


DEFAULT_PROMETHEUS_FIXTURE: Dict[str, Any] = {
    "metrics_by_window": {
        ("default", "payments-wrr", "5m"): {
            "rps": 140.0,
            "error_rate_4xx_pct": 1.2,
            "error_rate_5xx_pct": 0.2,
            "latency_p50_ms": 11.5,
            "latency_p95_ms": 42.0,
            "latency_p99_ms": 88.0,
            "open_connections": 18.0,
        },
        ("default", "payments-wrr", "1h"): {
            "rps": 135.0,
            "error_rate_4xx_pct": 1.1,
            "error_rate_5xx_pct": 0.1,
            "latency_p50_ms": 11.0,
            "latency_p95_ms": 40.0,
            "latency_p99_ms": 85.0,
            "open_connections": 16.0,
        },
        ("default", "payments-wrr", "15m"): {
            "rps": 142.0,
            "error_rate_4xx_pct": 1.3,
            "error_rate_5xx_pct": 0.2,
            "latency_p50_ms": 12.0,
            "latency_p95_ms": 43.0,
            "latency_p99_ms": 90.0,
            "open_connections": 19.0,
        },
        ("default", "payments-stable", "15m"): {
            "rps": 128.0,
            "error_rate_4xx_pct": 1.1,
            "error_rate_5xx_pct": 0.1,
            "latency_p50_ms": 11.2,
            "latency_p95_ms": 41.0,
            "latency_p99_ms": 86.0,
            "open_connections": 17.0,
        },
        ("default", "payments-canary", "15m"): {
            "rps": 14.0,
            "error_rate_4xx_pct": 1.5,
            "error_rate_5xx_pct": 0.3,
            "latency_p50_ms": 13.0,
            "latency_p95_ms": 45.0,
            "latency_p99_ms": 92.0,
            "open_connections": 2.0,
        },
    }
}


def get_prometheus_fixture() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_PROMETHEUS_FIXTURE)
