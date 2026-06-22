"""Pydantic models for sampling configuration."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from opentelemetry_mcp_server.models.common import SamplingMode


class TailSamplingPolicy(BaseModel):
    """A single tail-sampling policy definition."""

    name: str = Field(description="Policy name")
    type: str = Field(
        description="Policy type (e.g., 'status_code', 'string_attribute', 'latency', 'probabilistic')"
    )
    config: Dict[str, object] = Field(
        default_factory=dict,
        description="Policy-specific configuration parameters",
    )


class SamplingConfig(BaseModel):
    """Sampling configuration extracted from collector and Instrumentation CRDs.

    Used by ``otel_inspect_sampling_configuration`` tool.
    """

    collector_name: str = Field(description="Collector CRD name")
    collector_namespace: str = Field(description="Collector namespace")

    mode: SamplingMode = Field(
        default="none",
        description="Detected sampling mode (head, tail, none)",
    )

    # Head sampling (from Instrumentation CRD)
    head_sampler_type: Optional[str] = Field(
        default=None,
        description="Head sampler type from Instrumentation CRD (e.g., 'parentbased_traceidratio')",
    )
    head_sample_rate: Optional[float] = Field(
        default=None,
        description="Head sampling rate (0.0 - 1.0)",
    )
    head_source: Optional[str] = Field(
        default=None,
        description="Source of head sampling config (Instrumentation CR name)",
    )

    # Tail sampling (from collector config)
    tail_sampling_processor: Optional[str] = Field(
        default=None,
        description="Name of the tail_sampling processor in collector config",
    )
    tail_policies: List[TailSamplingPolicy] = Field(
        default_factory=list,
        description="Tail sampling policies",
    )
    tail_decision_wait: Optional[str] = Field(
        default=None,
        description="Decision wait time (e.g., '10s')",
    )
    tail_num_traces: Optional[int] = Field(
        default=None,
        description="Number of traces kept in memory for tail sampling",
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Sampling warnings (e.g., 'head + tail conflict', 'high memory risk')",
    )
