"""Pydantic models for OTel Instrumentation CRDs and instrumented services.

Covers both Instrumentation CRD state (``otel://instrumentation/{ns}/{name}``)
and workload instrumentation status (``otel://service/{ns}/{name}``).
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from opentelemetry_mcp_server.models.common import SignalType, StabilityLevel


class InstrumentationEndpointConfig(BaseModel):
    """OTLP endpoint configuration from an Instrumentation CRD."""

    endpoint: str = Field(
        default="http://otel-collector:4317",
        description="OTLP endpoint the instrumented app sends telemetry to",
    )
    protocol: str = Field(
        default="grpc",
        description="OTLP protocol (grpc or http/protobuf)",
    )


class LanguageInstrumentationSpec(BaseModel):
    """Per-language auto-instrumentation configuration from an Instrumentation CRD."""

    language: str = Field(description="Language identifier (java, python, nodejs, dotnet, go)")
    image: Optional[str] = Field(
        default=None,
        description="Init-container image for the language auto-instrumentation agent",
    )
    env: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables injected into the application container",
    )
    volume_limit_size: Optional[str] = Field(
        default=None,
        description="Volume size limit for the init container (e.g., '200Mi')",
    )


class OtelInstrumentationProfile(BaseModel):
    """Full representation of an Instrumentation CRD.

    Corresponds to the ``otel://instrumentation/{namespace}/{name}`` resource.
    """

    name: str = Field(description="CRD metadata.name")
    namespace: str = Field(description="CRD metadata.namespace")

    # Exporter endpoint
    exporter: InstrumentationEndpointConfig = Field(
        default_factory=InstrumentationEndpointConfig,
        description="OTLP exporter configuration",
    )

    # Propagators
    propagators: List[str] = Field(
        default_factory=lambda: ["tracecontext", "baggage"],
        description="Context propagation formats",
    )

    # Sampler
    sampler_type: Optional[str] = Field(
        default=None,
        description="Sampler type (e.g., 'parentbased_traceidratio')",
    )
    sampler_argument: Optional[str] = Field(
        default=None,
        description="Sampler argument (e.g., '0.25' for 25% sampling)",
    )

    # Per-language specs
    languages: List[LanguageInstrumentationSpec] = Field(
        default_factory=list,
        description="Per-language instrumentation configurations",
    )

    # Resource attributes
    resource_attributes: Dict[str, str] = Field(
        default_factory=dict,
        description="Resource attributes injected into all telemetry",
    )

    labels: Dict[str, str] = Field(
        default_factory=dict, description="CRD metadata.labels"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="CRD metadata.annotations"
    )


class InstrumentedService(BaseModel):
    """Instrumentation status of a Kubernetes workload.

    Corresponds to the ``otel://service/{namespace}/{name}`` resource.
    Shows whether a Deployment/StatefulSet has OTel auto-instrumentation
    annotations and the resulting injection status.
    """

    name: str = Field(description="Workload name")
    namespace: str = Field(description="Workload namespace")
    kind: str = Field(
        default="Deployment",
        description="Workload kind (Deployment, StatefulSet, DaemonSet)",
    )

    # Annotation status
    instrumentation_annotation: Optional[str] = Field(
        default=None,
        description="Value of instrumentation.opentelemetry.io/inject-<lang> annotation",
    )
    language: Optional[str] = Field(
        default=None,
        description="Detected language from annotation (java, python, etc.)",
    )
    instrumentation_cr_name: Optional[str] = Field(
        default=None,
        description="Name of the Instrumentation CR being referenced",
    )

    # Injection status
    init_container_injected: bool = Field(
        default=False,
        description="Whether the OTel init container is present in the pod spec",
    )
    sdk_env_vars_present: bool = Field(
        default=False,
        description="Whether OTEL_* env vars are present in the container",
    )

    # Health indicators
    signals_detected: List[SignalType] = Field(
        default_factory=list,
        description="Signals the service is emitting based on env config",
    )
    endpoint_configured: Optional[str] = Field(
        default=None,
        description="OTLP endpoint the service is configured to send to",
    )

    # Readiness
    ready_replicas: int = Field(default=0, description="Ready pod count")
    total_replicas: int = Field(default=0, description="Desired pod count")

    warnings: List[str] = Field(
        default_factory=list,
        description="Instrumentation warnings (e.g., 'missing annotation', 'init container not found')",
    )
