"""Test YAML parsing helpers."""

import pytest

from opentelemetry_mcp_server.exceptions import OtelConfigParseError
from opentelemetry_mcp_server.utils.yaml_helpers import (
    config_to_yaml,
    extract_connectors,
    extract_exporters,
    extract_pipelines,
    extract_processors,
    extract_receivers,
    find_connectors_of_type,
    find_processors_of_type,
    find_receivers_of_type,
    get_component_type,
    get_pipeline_signal,
    safe_load_yaml,
)


class TestYamlHelpers:
    """Test YAML parsing helpers."""

    def test_safe_load_valid(self) -> None:
        result = safe_load_yaml("key: value\nlist:\n  - a\n  - b")
        assert result["key"] == "value"
        assert result["list"] == ["a", "b"]

    def test_safe_load_empty(self) -> None:
        result = safe_load_yaml("")
        assert result == {}

    def test_safe_load_invalid(self) -> None:
        with pytest.raises(OtelConfigParseError):
            safe_load_yaml("- - invalid: {")

    def test_safe_load_non_mapping(self) -> None:
        with pytest.raises(OtelConfigParseError):
            safe_load_yaml("- a\n- b")

    def test_get_component_type(self) -> None:
        assert get_component_type("otlp") == "otlp"
        assert get_component_type("otlp/grpc") == "otlp"
        assert get_component_type("k8sattributes") == "k8sattributes"
        assert get_component_type("batch/large") == "batch"

    def test_get_pipeline_signal(self) -> None:
        assert get_pipeline_signal("traces") == "traces"
        assert get_pipeline_signal("metrics/prometheus") == "metrics"
        assert get_pipeline_signal("logs") == "logs"

    def test_config_to_yaml(self) -> None:
        cfg = {"receivers": {"otlp": {"protocols": {"grpc": {}}}}}
        yaml_str = config_to_yaml(cfg)
        assert "receivers:" in yaml_str
        assert "otlp:" in yaml_str

    def test_extract_sections(self) -> None:
        cfg = {
            "receivers": {"otlp": {}},
            "processors": {"batch": {}},
            "exporters": {"otlp": {}},
            "connectors": {"spanmetrics": {}},
            "service": {"pipelines": {"traces": {}}},
        }
        assert "otlp" in extract_receivers(cfg)
        assert "batch" in extract_processors(cfg)
        assert "otlp" in extract_exporters(cfg)
        assert "spanmetrics" in extract_connectors(cfg)
        assert "traces" in extract_pipelines(cfg)

    def test_find_processors_of_type(self) -> None:
        cfg = {
            "processors": {
                "batch": {},
                "batch/large": {},
                "memory_limiter": {},
            }
        }
        assert find_processors_of_type(cfg, "batch") == ["batch", "batch/large"]
        assert find_processors_of_type(cfg, "memory_limiter") == ["memory_limiter"]
        assert find_processors_of_type(cfg, "nonexistent") == []

    def test_find_connectors_of_type(self) -> None:
        cfg = {"connectors": {"spanmetrics": {}, "count": {}}}
        assert find_connectors_of_type(cfg, "spanmetrics") == ["spanmetrics"]

    def test_find_receivers_of_type(self) -> None:
        cfg = {"receivers": {"filelog": {}, "otlp": {}, "filelog/custom": {}}}
        assert find_receivers_of_type(cfg, "filelog") == ["filelog", "filelog/custom"]
