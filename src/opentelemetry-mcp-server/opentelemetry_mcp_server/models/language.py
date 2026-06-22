"""Pydantic models for language instrumentation capabilities.

Represents the per-language OTel instrumentation support matrix,
corresponding to the ``otel://lang/{language}`` resource.
Data is sourced from the embedded ``static/otel_lang_registry.json``.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from opentelemetry_mcp_server.models.common import StabilityLevel


class FrameworkSupport(BaseModel):
    """Auto-instrumentation support for a specific framework/library."""

    name: str = Field(description="Framework or library name (e.g., 'Spring Boot', 'Express')")
    min_version: Optional[str] = Field(
        default=None,
        description="Minimum supported framework version",
    )
    auto_instrumented: bool = Field(
        default=False,
        description="Whether zero-code auto-instrumentation is available",
    )
    manual_available: bool = Field(
        default=True,
        description="Whether manual SDK instrumentation is available",
    )
    stability: StabilityLevel = Field(
        default="stable",
        description="Instrumentation stability level",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes or caveats",
    )


class SignalSupport(BaseModel):
    """Per-signal stability and availability for a language."""

    traces: StabilityLevel = Field(default="stable", description="Traces signal stability")
    metrics: StabilityLevel = Field(default="stable", description="Metrics signal stability")
    logs: StabilityLevel = Field(default="stable", description="Logs signal stability")


class LanguageInstrumentationCapability(BaseModel):
    """Full instrumentation capability matrix for a programming language.

    Corresponds to the ``otel://lang/{language}`` resource.
    """

    language: str = Field(description="Language identifier (java, python, nodejs, dotnet, go, rust)")
    display_name: str = Field(description="Human-readable language name")

    # Signal support
    signal_support: SignalSupport = Field(
        default_factory=SignalSupport,
        description="Per-signal stability levels",
    )

    # Auto-instrumentation
    auto_instrumentation_available: bool = Field(
        default=False,
        description="Whether zero-code auto-instrumentation is supported",
    )
    auto_instrumentation_image: Optional[str] = Field(
        default=None,
        description="Default init-container image for K8s auto-instrumentation",
    )

    # eBPF support
    ebpf_supported: bool = Field(
        default=False,
        description="Whether eBPF-based instrumentation (OBI/Beyla) is supported",
    )

    # Framework matrix
    frameworks: List[FrameworkSupport] = Field(
        default_factory=list,
        description="Supported frameworks and libraries",
    )

    # Operator annotation key
    annotation_key: Optional[str] = Field(
        default=None,
        description="K8s annotation key for auto-instrumentation (e.g., 'instrumentation.opentelemetry.io/inject-java')",
    )

    # SDK package
    sdk_package: Optional[str] = Field(
        default=None,
        description="Primary SDK package name (e.g., 'opentelemetry-api' for Java)",
    )
