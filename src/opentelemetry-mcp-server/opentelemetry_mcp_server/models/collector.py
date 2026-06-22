"""Pydantic models for OpenTelemetry Collector instances and pipelines.

These models represent the structured state of an OpenTelemetryCollector CRD
as parsed from the Kubernetes API and the embedded YAML configuration.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from opentelemetry_mcp_server.models.common import (
    CollectorMode,
    ComponentRef,
    SamplingMode,
    SignalType,
)


class ReceiverRef(ComponentRef):
    """Reference to a pipeline receiver."""

    protocols: List[str] = Field(
        default_factory=list,
        description="Protocols supported (e.g., ['grpc', 'http'])",
    )


class ProcessorRef(ComponentRef):
    """Reference to a pipeline processor."""

    pass


class ExporterRef(ComponentRef):
    """Reference to a pipeline exporter."""

    signals: List[SignalType] = Field(
        default_factory=list,
        description="Signals this exporter handles",
    )


class PipelineSpec(BaseModel):
    """A single telemetry pipeline within the collector config."""

    name: str = Field(description="Pipeline name (e.g., 'traces', 'metrics/prometheus')")
    signal: SignalType = Field(description="Primary signal type for this pipeline")
    receivers: List[ReceiverRef] = Field(
        default_factory=list, description="Ordered list of receivers"
    )
    processors: List[ProcessorRef] = Field(
        default_factory=list, description="Ordered list of processors"
    )
    exporters: List[ExporterRef] = Field(
        default_factory=list, description="Ordered list of exporters"
    )


class CollectorStatus(BaseModel):
    """Runtime status of the collector from the CRD status subresource."""

    replicas: int = Field(default=0, description="Desired replica count")
    ready_replicas: int = Field(default=0, description="Ready replica count")
    phase: str = Field(default="Unknown", description="CRD phase (e.g., 'Running')")
    message: Optional[str] = Field(
        default=None, description="Human-readable status message"
    )


class CollectorInstance(BaseModel):
    """Full representation of an OpenTelemetryCollector CRD.

    Corresponds to the ``otel://collector/{namespace}/{name}`` resource.
    """

    name: str = Field(description="CRD metadata.name")
    namespace: str = Field(description="CRD metadata.namespace")
    mode: CollectorMode = Field(description="Deployment mode from spec.mode")
    deployment_kind: str = Field(
        default="OpenTelemetryCollector",
        description="Kubernetes resource kind",
    )
    version: Optional[str] = Field(
        default=None,
        description="OTel Collector image version tag",
    )
    otel_distribution: Optional[str] = Field(
        default=None,
        description="Distribution name (e.g., 'contrib', 'core', 'custom')",
    )

    # Pipeline topology
    pipelines: List[PipelineSpec] = Field(
        default_factory=list, description="All configured pipelines"
    )

    # Feature flags
    spanmetrics_enabled: bool = Field(
        default=False, description="Whether spanmetrics connector is configured"
    )
    target_allocator_enabled: bool = Field(
        default=False, description="Whether Target Allocator is enabled"
    )
    sampling_mode: SamplingMode = Field(
        default="none", description="Detected sampling strategy"
    )

    # Status
    status: CollectorStatus = Field(
        default_factory=CollectorStatus, description="Runtime status"
    )

    # Summary for LLM token efficiency
    summary: str = Field(
        default="",
        description="One-line human-readable summary of the collector",
    )

    # Raw config (only included at detail_level=full)
    raw_config_yaml: Optional[str] = Field(
        default=None,
        description="Full raw YAML config (only when detail_level='full')",
    )

    labels: Dict[str, str] = Field(
        default_factory=dict, description="CRD metadata.labels"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="CRD metadata.annotations"
    )
