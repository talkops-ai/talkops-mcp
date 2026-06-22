"""Pydantic models for Target Allocator state.

Represents the state of the OpenTelemetry Target Allocator (TA),
corresponding to the ``otel://target-allocator/{namespace}/{name}`` resource.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TargetAssignment(BaseModel):
    """A single scrape target assignment from the Target Allocator."""

    job_name: str = Field(description="Prometheus job name")
    target_url: str = Field(description="Scrape target URL (host:port)")
    labels: Dict[str, str] = Field(
        default_factory=dict,
        description="Target labels (namespace, pod, etc.)",
    )
    collector_name: str = Field(
        description="Name of the collector instance assigned to this target",
    )
    last_scrape: Optional[str] = Field(
        default=None,
        description="ISO timestamp of last successful scrape",
    )


class TargetAllocatorState(BaseModel):
    """Target Allocator state and assignment summary.

    Corresponds to the ``otel://target-allocator/{namespace}/{name}`` resource.
    """

    name: str = Field(description="Target Allocator name (derived from collector)")
    namespace: str = Field(description="Namespace")
    enabled: bool = Field(
        default=False,
        description="Whether Target Allocator is enabled for this collector",
    )

    # Allocation strategy
    allocation_strategy: str = Field(
        default="consistent-hashing",
        description="Target allocation strategy (consistent-hashing, least-weighted, per-node)",
    )
    filter_strategy: Optional[str] = Field(
        default=None,
        description="Filter strategy for target selection",
    )

    # Discovered targets
    total_targets: int = Field(
        default=0, description="Total number of discovered scrape targets"
    )
    total_collectors: int = Field(
        default=0, description="Number of collector instances participating"
    )
    assignments: List[TargetAssignment] = Field(
        default_factory=list,
        description="Detailed target-to-collector assignments (first 50)",
    )

    # ServiceMonitor/PodMonitor integration
    service_monitor_selector: Optional[Dict[str, str]] = Field(
        default=None,
        description="Label selector for ServiceMonitor CRDs",
    )
    pod_monitor_selector: Optional[Dict[str, str]] = Field(
        default=None,
        description="Label selector for PodMonitor CRDs",
    )
    service_monitors_matched: int = Field(
        default=0, description="Number of ServiceMonitors matched"
    )
    pod_monitors_matched: int = Field(
        default=0, description="Number of PodMonitors matched"
    )

    # Health
    replicas: int = Field(default=0, description="TA replica count")
    ready: bool = Field(default=False, description="Whether TA is healthy")

    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings (e.g., unbalanced allocation, unreachable TA)",
    )
