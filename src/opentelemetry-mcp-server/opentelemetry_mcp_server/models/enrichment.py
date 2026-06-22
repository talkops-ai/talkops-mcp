"""Pydantic models for Kubernetes attribute enrichment profiles.

Represents the ``k8sattributes`` processor configuration extracted
from an OpenTelemetryCollector config, corresponding to the
``otel://k8s-enrichment/{namespace}/{collector}`` resource.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class K8sEnrichmentProfile(BaseModel):
    """Kubernetes attribute enrichment configuration.

    Shows which resource attributes are being extracted from the K8s API
    and injected into telemetry data via the ``k8sattributes`` processor.
    """

    collector_name: str = Field(description="Parent collector CRD name")
    collector_namespace: str = Field(description="Parent collector namespace")
    enabled: bool = Field(
        default=False,
        description="Whether k8sattributes processor is present in any pipeline",
    )

    # Extracted metadata keys
    extract_metadata: List[str] = Field(
        default_factory=list,
        description="Metadata fields being extracted (e.g., 'k8s.pod.name', 'k8s.namespace.name')",
    )
    extract_labels: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Pod/namespace labels being extracted as resource attributes",
    )
    extract_annotations: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Pod/namespace annotations being extracted",
    )

    # Filter configuration
    filter_namespace: Optional[str] = Field(
        default=None,
        description="Namespace filter applied to k8sattributes processor",
    )
    filter_node: Optional[str] = Field(
        default=None,
        description="Node filter (from OTEL_RESOURCE_ATTRIBUTES env injection)",
    )

    # RBAC
    pod_association: List[str] = Field(
        default_factory=list,
        description="Pod association sources (e.g., 'resource_attribute', 'connection')",
    )
    requires_cluster_role: bool = Field(
        default=True,
        description="Whether the processor requires cluster-wide RBAC",
    )

    # Processor position in pipeline
    pipeline_positions: List[str] = Field(
        default_factory=list,
        description="Pipelines containing this processor and its position index",
    )
