"""Safe YAML parsing and OTel Collector config extraction utilities."""

from typing import Any, Dict, List, Optional, cast

import yaml

from opentelemetry_mcp_server.exceptions import OtelConfigParseError
from opentelemetry_mcp_server.models.common import SignalType


def safe_load_yaml(raw: str) -> Dict[str, Any]:
    """Safely parse YAML string into a dictionary.

    Args:
        raw: Raw YAML string to parse.

    Returns:
        Parsed dictionary.

    Raises:
        OtelConfigParseError: If YAML is malformed or not a mapping.
    """
    try:
        result = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise OtelConfigParseError(f"Failed to parse YAML: {e}")

    if result is None:
        return {}
    if not isinstance(result, dict):
        raise OtelConfigParseError(
            f"Expected YAML mapping, got {type(result).__name__}"
        )
    return result


def extract_service_section(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the ``service`` section from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        The ``service`` section, or empty dict if missing.
    """
    return cfg.get("service", {})


def extract_pipelines(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ``service.pipelines`` from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        Dictionary of pipeline name -> pipeline config.
    """
    service = extract_service_section(cfg)
    return service.get("pipelines", {})


def extract_receivers(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the ``receivers`` section from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        Dictionary of receiver name -> receiver config.
    """
    return cfg.get("receivers", {})


def extract_processors(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the ``processors`` section from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        Dictionary of processor name -> processor config.
    """
    return cfg.get("processors", {})


def extract_exporters(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the ``exporters`` section from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        Dictionary of exporter name -> exporter config.
    """
    return cfg.get("exporters", {})


def extract_connectors(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the ``connectors`` section from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        Dictionary of connector name -> connector config.
    """
    return cfg.get("connectors", {})


def extract_extensions(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the ``extensions`` section from a collector config.

    Args:
        cfg: Parsed collector config dictionary.

    Returns:
        Dictionary of extension name -> extension config.
    """
    return cfg.get("extensions", {})


def get_component_type(name: str) -> str:
    """Extract the base type from a component instance name.

    OTel Collector component names follow the pattern ``type/instance``
    (e.g., ``otlp/grpc``, ``batch``, ``k8sattributes``).

    Args:
        name: Component instance name from config.

    Returns:
        Base component type.
    """
    return name.split("/")[0]


def get_pipeline_signal(pipeline_name: str) -> SignalType:
    """Extract the signal type from a pipeline name.

    Pipeline names follow the pattern ``signal[/qualifier]``
    (e.g., ``traces``, ``metrics/prometheus``, ``logs``).

    Args:
        pipeline_name: Pipeline name from config.

    Returns:
        Signal type string (one of 'traces', 'metrics', 'logs').
    """
    return cast(SignalType, pipeline_name.split("/")[0])


def config_to_yaml(cfg: Any) -> str:
    """Serialize a config dictionary (or list) back to YAML.

    Args:
        cfg: Configuration dictionary or list.

    Returns:
        YAML string representation.
    """
    return yaml.dump(cfg, default_flow_style=False, sort_keys=False)


def find_processors_of_type(
    cfg: Dict[str, Any], processor_type: str
) -> List[str]:
    """Find all processor instance names of a given type.

    Args:
        cfg: Parsed collector config dictionary.
        processor_type: Base processor type to search for.

    Returns:
        List of processor instance names matching the type.
    """
    processors = extract_processors(cfg)
    return [
        name
        for name in processors
        if get_component_type(name) == processor_type
    ]


def find_connectors_of_type(
    cfg: Dict[str, Any], connector_type: str
) -> List[str]:
    """Find all connector instance names of a given type.

    Args:
        cfg: Parsed collector config dictionary.
        connector_type: Base connector type to search for.

    Returns:
        List of connector instance names matching the type.
    """
    connectors = extract_connectors(cfg)
    return [
        name
        for name in connectors
        if get_component_type(name) == connector_type
    ]


def find_receivers_of_type(
    cfg: Dict[str, Any], receiver_type: str
) -> List[str]:
    """Find all receiver instance names of a given type.

    Args:
        cfg: Parsed collector config dictionary.
        receiver_type: Base receiver type to search for.

    Returns:
        List of receiver instance names matching the type.
    """
    receivers = extract_receivers(cfg)
    return [
        name
        for name in receivers
        if get_component_type(name) == receiver_type
    ]
