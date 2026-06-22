"""Pydantic models for eBPF instrumentation footprint analysis."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EbpfPodDetail(BaseModel):
    """eBPF instrumentation detail for a single pod."""

    pod_name: str = Field(description="Pod name")
    namespace: str = Field(description="Pod namespace")
    node_name: str = Field(description="Node the pod is scheduled on")
    privileged: bool = Field(
        default=False,
        description="Whether the eBPF container runs in privileged mode",
    )
    host_pid: bool = Field(
        default=False,
        description="Whether hostPID is enabled",
    )
    capabilities: List[str] = Field(
        default_factory=list,
        description="Linux capabilities granted (e.g., 'SYS_ADMIN', 'BPF', 'PERFMON')",
    )
    volume_mounts: List[str] = Field(
        default_factory=list,
        description="Host paths mounted (e.g., '/sys/kernel/debug', '/proc')",
    )


class EbpfFootprint(BaseModel):
    """eBPF instrumentation footprint analysis.

    Used by ``otel_analyze_ebpf_footprint`` tool to audit
    security posture and resource usage of eBPF-based observability agents
    like OpenTelemetry eBPF Instrumentation (OBI) or Grafana Beyla.
    """

    namespace: str = Field(description="Namespace being audited")
    total_ebpf_pods: int = Field(
        default=0,
        description="Total pods with eBPF instrumentation detected",
    )

    pods: List[EbpfPodDetail] = Field(
        default_factory=list,
        description="Detailed eBPF pod analysis (first 50)",
    )

    # Aggregate security posture
    total_privileged: int = Field(
        default=0,
        description="Count of pods running in privileged mode",
    )
    total_host_pid: int = Field(
        default=0,
        description="Count of pods with hostPID enabled",
    )
    unique_capabilities: List[str] = Field(
        default_factory=list,
        description="Deduplicated list of all Linux capabilities granted",
    )
    unique_host_mounts: List[str] = Field(
        default_factory=list,
        description="Deduplicated list of all host paths mounted",
    )

    # Resource usage
    total_cpu_request: Optional[str] = Field(
        default=None,
        description="Aggregate CPU request across all eBPF pods",
    )
    total_memory_request: Optional[str] = Field(
        default=None,
        description="Aggregate memory request across all eBPF pods",
    )

    # Risk assessment
    risk_level: str = Field(
        default="low",
        description="Overall risk level: low, medium, high, critical",
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Security recommendations based on the audit",
    )
