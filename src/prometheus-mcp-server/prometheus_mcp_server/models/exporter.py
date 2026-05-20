"""Prometheus exporter models."""

from typing import Dict, List, Literal, Optional

from pydantic import Field

from prometheus_mcp_server.models.common import BasePrometheusModel
from prometheus_mcp_server.models.onboarding import ScrapeEndpointTestResult


class ExporterConfigField(BasePrometheusModel):
    """A single configuration input field for an exporter."""
    name: str
    type: str  # e.g., "string", "int", "bool"
    description: str
    example: str
    maps_to_flag: Optional[str] = None


class ExporterConfigModel(BasePrometheusModel):
    """Configuration model separating required and optional fields."""
    required: List[ExporterConfigField] = Field(default_factory=list)
    optional: List[ExporterConfigField] = Field(default_factory=list)


class K8sNuances(BasePrometheusModel):
    """Kubernetes-specific deployment nuances."""
    requires_rbac: bool = False
    requires_configmap: bool = False
    requires_secret: bool = False
    requires_udp_service: bool = False
    supports_sidecar: bool = False
    configmap_mount_path: Optional[str] = None
    secret_mount_path: Optional[str] = None


class ExporterDiscovery(BasePrometheusModel):
    """Auto-discovery labels for ServiceMonitor or scrape targets."""
    service_labels: Dict[str, str] = Field(default_factory=dict)
    servicemonitor_labels: Dict[str, str] = Field(default_factory=dict)


class ExporterInfo(BasePrometheusModel):
    """Information about a supported Prometheus exporter."""

    type: str
    description: str
    supported_environments: List[Literal["kubernetes", "vm"]] = Field(default_factory=list)
    default_scope: Optional[Literal["daemonset", "deployment", "sidecar"]] = None
    default_ports: Dict[str, int] = Field(default_factory=lambda: {"metrics": 9100})
    image: Optional[str] = None
    config_model: ExporterConfigModel = Field(default_factory=ExporterConfigModel)
    k8s_nuances: K8sNuances = Field(default_factory=K8sNuances)
    discovery: ExporterDiscovery = Field(default_factory=ExporterDiscovery)
    default_config_data: Optional[str] = None


class ExporterManifestResult(BasePrometheusModel):
    """Result of installing an exporter on Kubernetes."""

    applied_resources: List[str] = Field(default_factory=list)
    manifest_yaml: str = ""
    notes: str = ""


class ExporterUninstallResult(BasePrometheusModel):
    """Result of uninstalling an exporter from Kubernetes."""

    removed_resources: List[str] = Field(default_factory=list)


class ExporterRecommendation(BasePrometheusModel):
    """Exporter recommendation for a given service type."""

    exporters: List[ExporterInfo] = Field(default_factory=list)
    notes: str = ""


class ExporterVerificationResult(BasePrometheusModel):
    """Result of end-to-end exporter verification."""

    endpoint_check: ScrapeEndpointTestResult
    up_series_found: bool = False
    errors: List[str] = Field(default_factory=list)
