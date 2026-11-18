"""T-U2: Unit tests for config_linter.py deterministic FindingCode rules."""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry_mcp_server.models.findings import FindingCode, FindingSeverity
from opentelemetry_mcp_server.services.collector_config_builder import (
    CollectorConfigBuilder,
)
from opentelemetry_mcp_server.services.config_linter import lint_collector_config


def _build_default_agent_config() -> dict:
    builder = CollectorConfigBuilder(MagicMock())
    return builder.build_config(
        signals=["traces", "metrics"],
        exporter_targets={"traces": "tempo:4317", "metrics": "mimir:9009"},
        mode="daemonset",
        role="agent",
    )


def test_valid_builder_config_has_zero_errors():
    cfg = _build_default_agent_config()
    findings = lint_collector_config(cfg, mode="daemonset", replicas=1)
    errors = [f for f in findings if f.severity == FindingSeverity.ERROR]
    assert len(errors) == 0


def test_detects_undeclared_component_and_invalid_processor_order():
    bad_cfg = {
        "receivers": {"otlp": {}},
        "processors": {"batch": {}, "memory_limiter": {}},
        "exporters": {"otlp": {}},
        "service": {
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["batch", "memory_limiter"],
                    "exporters": ["otlp", "missing_exporter"],
                }
            }
        },
    }
    findings = lint_collector_config(bad_cfg, mode="deployment", replicas=1)
    codes = {f.code for f in findings}
    assert FindingCode.CFG_UNDEFINED_COMPONENT_REF in codes
    assert FindingCode.CFG_MEMORY_LIMITER_NOT_FIRST in codes


def test_blocks_tail_sampling_on_daemonset_and_multi_replica_without_affinity():
    cfg = _build_default_agent_config()
    cfg["processors"]["tail_sampling"] = {"policies": []}
    cfg["service"]["pipelines"]["traces"]["processors"] = [
        "memory_limiter",
        "tail_sampling",
        "batch",
    ]
    findings = lint_collector_config(cfg, mode="daemonset", replicas=1)
    codes = {f.code for f in findings}
    assert FindingCode.CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY in codes


def test_detects_high_cardinality_connector_and_inline_secret():
    cfg = {
        "receivers": {"otlp": {}},
        "processors": {"memory_limiter": {}, "batch": {}},
        "exporters": {
            "otlp": {
                "endpoint": "https://api.vendor.io:4317",
                "headers": {"Authorization": "Bearer sk_live_supersecret123456"},
            }
        },
        "connectors": {
            "spanmetrics": {
                "dimensions": [{"name": "user.id"}, {"name": "http.request.method"}]
            }
        },
        "service": {
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp", "spanmetrics"],
                },
                "metrics": {
                    "receivers": ["spanmetrics"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp"],
                },
            }
        },
    }
    findings = lint_collector_config(cfg, mode="deployment", replicas=1)
    codes = {f.code for f in findings}
    assert FindingCode.CFG_SPANMETRICS_HIGH_CARD_DIMENSION in codes
    assert FindingCode.SEC_INLINE_SECRET in codes


def test_detects_connector_self_loop_and_signal_mismatch():
    cfg = {
        "receivers": {"otlp": {}},
        "processors": {"memory_limiter": {}, "batch": {}},
        "exporters": {"otlp/tempo": {"endpoint": "tempo:4317"}},
        "connectors": {"spanmetrics": {}},
        "service": {
            "pipelines": {
                "traces": {
                    "receivers": ["otlp", "spanmetrics"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["spanmetrics", "otlp/tempo"],
                }
            }
        },
    }
    findings = lint_collector_config(cfg, mode="deployment", replicas=1)
    loop_findings = [f for f in findings if f.code == FindingCode.CFG_CONNECTOR_LOOP]
    assert len(loop_findings) >= 1
    assert loop_findings[0].severity == FindingSeverity.ERROR


def test_removed_deprecations_are_errors_for_modern_target_version():
    cfg = {
        "receivers": {"otlp": {}},
        "processors": {"memory_limiter": {}, "batch": {}},
        "extensions": {"memory_ballast": {"size_mib": 256}},
        "exporters": {"logging": {"loglevel": "info"}},
        "service": {
            "extensions": ["memory_ballast"],
            "telemetry": {"metrics": {"address": "0.0.0.0:8888"}},
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["logging"],
                }
            },
        },
    }
    findings = lint_collector_config(
        cfg, mode="deployment", replicas=1, target_version="0.152.1"
    )
    err_codes = {
        f.code for f in findings if f.severity == FindingSeverity.ERROR
    }
    assert FindingCode.CFG_DEPRECATED_TELEMETRY_ADDRESS in err_codes
    assert FindingCode.CFG_DEPRECATED_COMPONENT in err_codes


def test_detects_external_insecure_exporter_and_exposed_debug_extension():
    cfg = {
        "receivers": {"otlp": {}},
        "processors": {"memory_limiter": {}, "batch": {}},
        "extensions": {"pprof": {"endpoint": "0.0.0.0:1777"}},
        "exporters": {
            "otlphttp/cloud": {
                "endpoint": "https://otlp-ingest.observability-cloud.io",
                "tls": {"insecure": True, "insecure_skip_verify": True},
            }
        },
        "service": {
            "extensions": ["pprof"],
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlphttp/cloud"],
                }
            },
        },
    }
    findings = lint_collector_config(cfg, mode="deployment", replicas=1)
    codes = {f.code for f in findings}
    assert FindingCode.SEC_INSECURE_EXPORTER in codes
    assert FindingCode.SEC_TLS_VERIFY_DISABLED in codes
    assert FindingCode.SEC_DEBUG_EXTENSION_EXPOSED in codes


def test_prometheusremotewrite_uses_remote_write_queue_and_rejects_sending_queue():
    from opentelemetry_mcp_server.services.collector_config_builder import (
        CollectorConfigBuilder,
    )

    exporters = CollectorConfigBuilder._build_exporters(
        {"metrics": "http://prometheus.observability.svc:9090/api/v1/write"}
    )
    prw = exporters["prometheusremotewrite/metrics"]
    assert "remote_write_queue" in prw
    assert "sending_queue" not in prw

    bad_cfg = {
        "receivers": {"otlp": {}},
        "processors": {"memory_limiter": {}, "batch": {}},
        "exporters": {
            "prometheusremotewrite/metrics": {
                "endpoint": "http://prometheus.observability.svc:9090/api/v1/write",
                "sending_queue": {"enabled": True, "queue_size": 1000},
                "retry_on_failure": {"enabled": True},
            }
        },
        "service": {
            "pipelines": {
                "metrics": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["prometheusremotewrite/metrics"],
                }
            }
        },
    }
    findings = lint_collector_config(bad_cfg, mode="deployment", replicas=1)
    assert any(
        f.code == FindingCode.CFG_DEPRECATED_COMPONENT
        and "remote_write_queue" in f.message
        for f in findings
    )


def test_receiver_builder_helpers_and_target_allocator_rbac():
    from opentelemetry_mcp_server.services.collector_config_builder import (
        CollectorConfigBuilder,
    )
    from opentelemetry_mcp_server.services.kubernetes_service import (
        KubernetesService,
    )

    assert "scrape_configs" in CollectorConfigBuilder._build_prometheus_receiver()["config"]
    assert CollectorConfigBuilder._build_filelog_receiver("otel-demo", "agent")["storage"] == "file_storage"
    assert "insecure_skip_verify" not in CollectorConfigBuilder._build_kubeletstats_receiver()
    assert CollectorConfigBuilder._build_hostmetrics_receiver()["root_path"] == "/hostfs"
    assert "Ready" in CollectorConfigBuilder._build_k8s_cluster_receiver()["node_conditions_to_report"]
    assert CollectorConfigBuilder._build_k8sobjects_receiver()["objects"][0]["name"] == "events"

    rbac = KubernetesService.build_receiver_rbac_manifests(
        namespace="otel-demo",
        collector_name="otel-ta-collector",
        receivers=["prometheus_ta"],
        target_allocator_enabled=True,
    )
    subjects = {s["name"] for s in rbac["cluster_role_binding"]["subjects"]}
    assert "otel-ta-collector-collector" in subjects
    assert "otel-ta-collector-targetallocator" in subjects
    resources = {
        res
        for rule in rbac["cluster_role"]["rules"]
        for res in rule.get("resources", [])
    }
    assert "endpointslices" in resources
    assert "servicemonitors" in resources
