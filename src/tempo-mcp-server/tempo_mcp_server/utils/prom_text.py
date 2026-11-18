"""Prometheus text exposition parser for Tempo /metrics operational facts.

Extracts factual telemetry counters and gauges from Tempo's /metrics endpoint:
- tempo_discarded_spans_total{reason="..."} (rate_limited, trace_too_large, live_traces_exceeded, etc.)
- tempo_ingest_group_partition_lag_seconds (Tempo 3.0 Kafka partition consumer lag)
- tempo_ring_members (ring member counts by state)
"""

import re
from typing import Any, Dict, List

_METRIC_LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{([^}]*)\})?"
    r"\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]?Inf)"
    r"(?:\s+\d+)?$"
)

_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"((?:\\.|[^"\\])*)"')


def parse_prometheus_text(text: str, metric_names: List[str] | None = None) -> List[Dict[str, Any]]:
    """Parse Prometheus exposition text into a list of {name, labels, value} samples."""
    if not text:
        return []

    target_set = set(metric_names) if metric_names else None
    samples: List[Dict[str, Any]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE_RE.match(line)
        if not match:
            continue
        name, raw_labels, raw_val = match.groups()
        if target_set is not None and name not in target_set:
            continue
        try:
            value = float(raw_val)
        except ValueError:
            continue

        labels: Dict[str, str] = {}
        if raw_labels:
            for lbl_match in _LABEL_RE.finditer(raw_labels):
                k, v = lbl_match.groups()
                labels[k] = v

        samples.append({
            "name": name,
            "labels": labels,
            "value": value,
        })

    return samples


def extract_tempo_metrics_facts(text: str) -> Dict[str, Any]:
    """Extract Tempo ingestion and Tempo 3.0 partition lag facts from /metrics output."""
    watched = [
        "tempo_discarded_spans_total",
        "tempo_ingest_group_partition_lag_seconds",
        "tempo_live_store_partition_owned",
        "tempo_block_builder_owned_partitions",
        "tempo_distributor_spans_received_total",
    ]
    samples = parse_prometheus_text(text, metric_names=watched)

    discarded_by_reason: Dict[str, float] = {}
    discarded_by_tenant: Dict[str, Dict[str, float]] = {}
    max_partition_lag_seconds: float = 0.0
    partition_lags: List[Dict[str, Any]] = []
    spans_received_total: float = 0.0

    for sample in samples:
        name = sample["name"]
        labels = sample["labels"]
        val = sample["value"]

        if name == "tempo_discarded_spans_total" and val > 0:
            reason = labels.get("reason", "unknown")
            tenant = labels.get("tenant")
            discarded_by_reason[reason] = discarded_by_reason.get(reason, 0.0) + val
            if tenant:
                t_map = discarded_by_tenant.setdefault(tenant, {})
                t_map[reason] = t_map.get(reason, 0.0) + val

        elif name == "tempo_ingest_group_partition_lag_seconds":
            if val > max_partition_lag_seconds:
                max_partition_lag_seconds = val
            partition_lags.append({
                "group": labels.get("group") or labels.get("component", "unknown"),
                "partition": labels.get("partition", "0"),
                "lag_seconds": val,
            })

        elif name == "tempo_distributor_spans_received_total":
            spans_received_total += val

    return {
        "discarded_spans_by_reason": discarded_by_reason,
        "discarded_spans_by_tenant": discarded_by_tenant if discarded_by_tenant else None,
        "total_discarded_spans": sum(discarded_by_reason.values()),
        "max_partition_lag_seconds": max_partition_lag_seconds if partition_lags else None,
        "partition_lags": partition_lags if partition_lags else None,
        "distributor_spans_received_total": spans_received_total if spans_received_total > 0 else None,
    }
