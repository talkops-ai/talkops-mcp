"""Unit tests for the config_merger utility.

Tests the config merger's ability to safely merge processors and
connectors into existing OTel Collector configurations, including
position-aware insertion, idempotent updates, and clean removal.
"""

import copy

import pytest

from opentelemetry_mcp_server.utils.config_merger import (
    merge_connector,
    merge_processor,
    remove_connector,
    remove_processor,
)


# ──────────────────────────────────────────────
# Sample Configs
# ──────────────────────────────────────────────

@pytest.fixture
def base_config():
    """Minimal OTel Collector config with standard pipelines."""
    return {
        "receivers": {
            "otlp": {
                "protocols": {
                    "grpc": {"endpoint": "0.0.0.0:4317"},
                    "http": {"endpoint": "0.0.0.0:4318"},
                },
            },
        },
        "processors": {
            "memory_limiter": {
                "check_interval": "1s",
                "limit_percentage": 80,
            },
            "batch": {
                "send_batch_size": 8192,
                "timeout": "5s",
            },
        },
        "exporters": {
            "otlp": {
                "endpoint": "tempo:4317",
                "tls": {"insecure": True},
            },
        },
        "service": {
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp"],
                },
                "metrics": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp"],
                },
            },
        },
    }


@pytest.fixture
def tail_sampling_config():
    """Standard tail_sampling processor config."""
    return {
        "decision_wait": "10s",
        "num_traces": 50000,
        "policies": [
            {
                "name": "error-sampling",
                "type": "status_code",
                "status_code": {"status_codes": ["ERROR"]},
            },
        ],
    }


@pytest.fixture
def spanmetrics_connector_config():
    """Standard spanmetrics connector config."""
    return {
        "histogram": {
            "explicit": {
                "buckets": [2, 4, 6, 8, 10, 50, 100, 200, 400, 800, 1000, 5000],
            },
        },
        "dimensions": [
            {"name": "http.method"},
            {"name": "http.status_code"},
        ],
        "metrics_flush_interval": "15s",
    }


# ──────────────────────────────────────────────
# merge_processor tests
# ──────────────────────────────────────────────

class TestMergeProcessor:
    """Tests for merge_processor()."""

    def test_adds_new_processor_before_batch(self, base_config, tail_sampling_config):
        """New processor is inserted before 'batch' by default."""
        merged, changes = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )

        # Processor definition added
        assert "tail_sampling" in merged["processors"]
        assert merged["processors"]["tail_sampling"] == tail_sampling_config

        # Inserted before batch in traces pipeline
        procs = merged["service"]["pipelines"]["traces"]["processors"]
        assert procs.index("tail_sampling") < procs.index("batch")
        assert "Inserted 'tail_sampling' before 'batch'" in changes[1]

    def test_does_not_mutate_original(self, base_config, tail_sampling_config):
        """Original config is not mutated."""
        original = copy.deepcopy(base_config)
        merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )
        assert base_config == original

    def test_insert_before_specific_processor(self, base_config, tail_sampling_config):
        """Insert before a specific processor name."""
        merged, changes = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
            before="memory_limiter",
        )

        procs = merged["service"]["pipelines"]["traces"]["processors"]
        assert procs.index("tail_sampling") == 0  # Before memory_limiter

    def test_insert_after_specific_processor(self, base_config, tail_sampling_config):
        """Insert after a specific processor name."""
        merged, changes = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
            after="memory_limiter",
        )

        procs = merged["service"]["pipelines"]["traces"]["processors"]
        assert procs.index("tail_sampling") == 1  # After memory_limiter

    def test_idempotent_if_already_in_pipeline(self, base_config, tail_sampling_config):
        """If processor already in pipeline, don't re-insert."""
        # First merge
        merged1, _ = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )
        # Second merge
        merged2, changes = merge_processor(
            merged1,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )

        procs = merged2["service"]["pipelines"]["traces"]["processors"]
        assert procs.count("tail_sampling") == 1
        assert any("already in" in c for c in changes)

    def test_updates_existing_processor_config(self, base_config, tail_sampling_config):
        """If processor definition exists, update it."""
        # Add it first
        merged1, _ = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )

        # Update with new config
        new_config = {"decision_wait": "30s", "num_traces": 100000, "policies": []}
        merged2, changes = merge_processor(
            merged1,
            "tail_sampling",
            new_config,
            "traces",
        )

        assert merged2["processors"]["tail_sampling"]["decision_wait"] == "30s"
        assert "Updated processor 'tail_sampling'" in changes[0]

    def test_creates_pipeline_if_missing(self, base_config, tail_sampling_config):
        """If target pipeline doesn't exist, create it."""
        merged, changes = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces/custom",
        )

        assert "traces/custom" in merged["service"]["pipelines"]
        procs = merged["service"]["pipelines"]["traces/custom"]["processors"]
        assert "tail_sampling" in procs

    def test_append_when_no_batch(self, tail_sampling_config):
        """If no 'batch' processor in pipeline, append at end."""
        cfg = {
            "processors": {},
            "service": {
                "pipelines": {
                    "traces": {
                        "receivers": ["otlp"],
                        "processors": ["memory_limiter"],
                        "exporters": ["otlp"],
                    },
                },
            },
        }

        merged, changes = merge_processor(
            cfg,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )

        procs = merged["service"]["pipelines"]["traces"]["processors"]
        assert procs[-1] == "tail_sampling"
        assert any("Appended" in c for c in changes)

    def test_preserves_other_pipelines(self, base_config, tail_sampling_config):
        """Other pipelines are not affected."""
        merged, _ = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )

        # metrics pipeline unchanged
        metrics_procs = merged["service"]["pipelines"]["metrics"]["processors"]
        assert "tail_sampling" not in metrics_procs
        assert metrics_procs == ["memory_limiter", "batch"]


# ──────────────────────────────────────────────
# remove_processor tests
# ──────────────────────────────────────────────

class TestRemoveProcessor:
    """Tests for remove_processor()."""

    def test_removes_processor_definition_and_pipeline_refs(
        self, base_config, tail_sampling_config
    ):
        """Processor is removed from definition and all pipelines."""
        # Add it first
        merged, _ = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )
        assert "tail_sampling" in merged["processors"]

        # Remove it
        cleaned, changes = remove_processor(merged, "tail_sampling")

        assert "tail_sampling" not in cleaned["processors"]
        assert "tail_sampling" not in cleaned["service"]["pipelines"]["traces"]["processors"]
        assert len(changes) >= 2  # definition + pipeline ref

    def test_does_not_mutate_original(self, base_config, tail_sampling_config):
        """Original is not mutated."""
        merged, _ = merge_processor(
            base_config,
            "tail_sampling",
            tail_sampling_config,
            "traces",
        )
        original = copy.deepcopy(merged)
        remove_processor(merged, "tail_sampling")
        assert merged == original

    def test_noop_if_not_present(self, base_config):
        """No error if processor doesn't exist."""
        cleaned, changes = remove_processor(base_config, "nonexistent")
        assert len(changes) == 0


# ──────────────────────────────────────────────
# merge_connector tests
# ──────────────────────────────────────────────

class TestMergeConnector:
    """Tests for merge_connector()."""

    def test_adds_connector_and_wires_pipelines(
        self, base_config, spanmetrics_connector_config
    ):
        """Connector is added and wired as exporter→receiver."""
        merged, changes = merge_connector(
            base_config,
            "spanmetrics",
            spanmetrics_connector_config,
            source_pipeline="traces",
            target_pipeline="metrics/spanmetrics",
            target_pipeline_exporters=["otlp"],
            target_pipeline_processors=["batch"],
        )

        # Connector definition
        assert "spanmetrics" in merged["connectors"]

        # Source pipeline: spanmetrics as exporter
        traces_exporters = merged["service"]["pipelines"]["traces"]["exporters"]
        assert "spanmetrics" in traces_exporters

        # Target pipeline: spanmetrics as receiver
        sm_pipe = merged["service"]["pipelines"]["metrics/spanmetrics"]
        assert "spanmetrics" in sm_pipe["receivers"]
        assert "otlp" in sm_pipe["exporters"]
        assert "batch" in sm_pipe["processors"]

    def test_does_not_mutate_original(self, base_config, spanmetrics_connector_config):
        """Original config is not mutated."""
        original = copy.deepcopy(base_config)
        merge_connector(
            base_config,
            "spanmetrics",
            spanmetrics_connector_config,
            "traces",
            "metrics/spanmetrics",
        )
        assert base_config == original

    def test_idempotent_connector(self, base_config, spanmetrics_connector_config):
        """Second merge doesn't duplicate wiring."""
        merged1, _ = merge_connector(
            base_config,
            "spanmetrics",
            spanmetrics_connector_config,
            "traces",
            "metrics/spanmetrics",
            target_pipeline_exporters=["otlp"],
        )
        merged2, _ = merge_connector(
            merged1,
            "spanmetrics",
            spanmetrics_connector_config,
            "traces",
            "metrics/spanmetrics",
            target_pipeline_exporters=["otlp"],
        )

        traces_exporters = merged2["service"]["pipelines"]["traces"]["exporters"]
        assert traces_exporters.count("spanmetrics") == 1

    def test_inherits_exporter_from_source(self, base_config, spanmetrics_connector_config):
        """If no target_pipeline_exporters, inherit from source pipeline."""
        merged, changes = merge_connector(
            base_config,
            "spanmetrics",
            spanmetrics_connector_config,
            "traces",
            "metrics/spanmetrics",
        )

        sm_pipe = merged["service"]["pipelines"]["metrics/spanmetrics"]
        assert "otlp" in sm_pipe["exporters"]
        assert any("Inherited" in c for c in changes)


# ──────────────────────────────────────────────
# remove_connector tests
# ──────────────────────────────────────────────

class TestRemoveConnector:
    """Tests for remove_connector()."""

    def test_removes_connector_and_cleans_pipelines(
        self, base_config, spanmetrics_connector_config
    ):
        """Connector, wiring, and empty target pipeline are removed."""
        merged, _ = merge_connector(
            base_config,
            "spanmetrics",
            spanmetrics_connector_config,
            "traces",
            "metrics/spanmetrics",
            target_pipeline_exporters=["otlp"],
        )

        cleaned, changes = remove_connector(merged, "spanmetrics")

        assert "spanmetrics" not in cleaned.get("connectors", {})
        assert "spanmetrics" not in cleaned["service"]["pipelines"]["traces"]["exporters"]
        # Target pipeline should be removed because it has no receivers
        assert "metrics/spanmetrics" not in cleaned["service"]["pipelines"]
        assert any("Removed empty pipeline" in c for c in changes)

    def test_noop_if_not_present(self, base_config):
        """No error if connector doesn't exist."""
        cleaned, changes = remove_connector(base_config, "nonexistent")
        assert len(changes) == 0
