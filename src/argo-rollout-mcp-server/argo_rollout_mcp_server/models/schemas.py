"""Pydantic input and output models for Argo Rollout MCP Server tools."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrafficRoutingConfig(BaseModel):
    """Traffic routing configuration for Canary rollouts."""

    model_config = ConfigDict(extra="allow")

    traefik_service_name: Optional[str] = Field(
        default=None,
        description="TraefikService name for weighted routing (mutually exclusive with gateway_api_config).",
    )
    gateway_api_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Gateway API plugin config, e.g. {'httpRoute': 'my-route', 'namespace': 'default'}.",
    )
    gateway_api: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Alias for gateway_api_config.",
    )
    clear_routing: bool = Field(
        default=False,
        description="Set True to remove existing trafficRouting from the Rollout.",
    )


class CanaryServicesConfig(BaseModel):
    """Service names and port configuration for Rollout traffic splitting."""

    model_config = ConfigDict(extra="allow")

    stable_service: Optional[str] = Field(default=None, description="Stable service name (canary).")
    canary_service: Optional[str] = Field(default=None, description="Canary service name (canary).")
    active_service: Optional[str] = Field(default=None, description="Active service name (bluegreen).")
    preview_service: Optional[str] = Field(default=None, description="Preview service name (bluegreen).")
    auto_create: bool = Field(default=True, description="Automatically create prerequisite Services if missing.")
    port: int = Field(default=80, description="Service port.")
    target_port: Optional[int] = Field(default=None, description="Container targetPort (defaults to discovered port).")
    selector_labels: Optional[Dict[str, str]] = Field(default=None, description="Override pod selector labels.")


class StrategyOptions(BaseModel):
    """Strategy-specific options for Canary, Blue-Green, or Rolling Update rollouts."""

    model_config = ConfigDict(extra="allow")

    steps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Canary steps list (e.g. [{'setWeight': 20}, {'pause': {'duration': '5m'}}]).",
    )
    traffic_routing: Optional[TrafficRoutingConfig] = Field(
        default=None,
        description="Canary traffic router configuration (TraefikService or Gateway API HTTPRoute).",
    )
    scale_down_delay_seconds: Optional[int] = Field(
        default=None,
        description="Seconds to delay scaling down old ReplicaSet after promotion.",
    )
    max_surge: Optional[str] = Field(default="25%", description="Max surge for canary/rolling strategy.")
    max_unavailable: Optional[Any] = Field(default=0, description="Max unavailable for canary/rolling strategy.")
    # Blue-green options
    auto_promotion_enabled: bool = Field(
        default=False,
        description="Auto-promote blue-green rollout once preview ReplicaSet is ready.",
    )
    auto_promotion_seconds: Optional[int] = Field(
        default=None,
        description="Auto-promote blue-green rollout after N seconds.",
    )
    preview_replica_count: Optional[int] = Field(
        default=None,
        description="Number of preview replicas before promotion (blue-green).",
    )
    pre_promotion_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Pre-promotion Analysis descriptor for blue-green strategy.",
    )
    post_promotion_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Post-promotion Analysis descriptor for blue-green strategy.",
    )
    abort_scale_down_delay_seconds: Optional[int] = Field(
        default=None,
        description="Delay before scaling down preview ReplicaSet on abort (blue-green).",
    )
    anti_affinity: Optional[Dict[str, Any]] = Field(default=None, description="Anti-affinity rules.")
    active_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata added to active pods.")
    preview_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata added to preview pods.")
    scale_down: Literal["never", "onsuccess", "progressively"] = Field(
        default="onsuccess",
        description="workloadRef scaleDown mode when migrating with workload_ref.",
    )


class WorkloadOptions(BaseModel):
    """Pod template and replica sizing options when creating a Rollout."""

    model_config = ConfigDict(extra="allow")

    replicas: int = Field(default=3, ge=1, le=200, description="Desired pod replicas.")
    container_port: int = Field(default=80, description="Container listening port.")
    resource_requests: Optional[Dict[str, str]] = Field(
        default=None,
        description="Container resource requests (e.g. {'cpu': '100m', 'memory': '128Mi'}).",
    )
    resource_limits: Optional[Dict[str, str]] = Field(
        default=None,
        description="Container resource limits (e.g. {'cpu': '500m', 'memory': '256Mi'}).",
    )


class AnalysisThresholds(BaseModel):
    """Prometheus SLO thresholds for generating default AnalysisTemplate metrics."""

    model_config = ConfigDict(extra="allow")

    service_name: Optional[str] = Field(default=None, description="Service label for PromQL queries.")
    prometheus_url: Optional[str] = Field(default=None, description="Prometheus base URL override.")
    error_rate_percent: float = Field(default=5.0, ge=0.0, le=100.0, description="Max 5xx error rate percentage.")
    latency_p99_ms: float = Field(default=2000.0, gt=0.0, description="Max P99 latency in milliseconds.")
    latency_p95_ms: float = Field(default=1000.0, gt=0.0, description="Max P95 latency in milliseconds.")


class ExecutionResult(BaseModel):
    """Standard concise response returned by mutating and destructive MCP tools."""

    status: Literal["success", "preview", "confirmation_required", "cancelled", "aborted"] = Field(
        description="Execution outcome status."
    )
    summary: str = Field(description="Concise human- and model-readable outcome summary.")
    dry_run: bool = Field(default=False, description="True when returned as a dry-run preview without cluster mutation.")
    manifest: Optional[str] = Field(default=None, description="Rendered YAML manifest or patch preview.")
    resource_uri: Optional[str] = Field(
        default=None,
        description="MCP Resource URI to inspect the target resource without spending a tool turn.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational or safety warnings detected during execution.",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Compact operation-specific fields.",
    )


class ReadinessReport(BaseModel):
    """Concise readiness report returned by argo_validate_deployment_readiness."""

    ready: bool = Field(description="True when zero blocking issues prevent Rollout conversion.")
    score: int = Field(description="Readiness score from 0 to 100.")
    summary: str = Field(default="", description="Concise summary of readiness state and detected container port.")
    app_name: str = Field(default="", description="Deployment name.")
    namespace: str = Field(default="default", description="Kubernetes namespace.")
    replicas: int = Field(default=1, description="Configured replica count.")
    containers_count: int = Field(default=1, description="Number of containers in pod template.")
    detected_container_port: Optional[int] = Field(default=80, description="Auto-detected containerPort.")
    issues: List[str] = Field(
        default_factory=list,
        description="Blocking structural or Service selector issues that must be fixed before conversion.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-blocking Kubernetes best-practice warnings (probes, resources, replicas).",
    )
    recommendations: List[str] = Field(default_factory=list, description="Actionable improvement recommendations.")
    service_checks: Dict[str, Any] = Field(default_factory=dict, description="Service selector compatibility checks.")


class RolloutDiagnosisReport(BaseModel):
    """Correlated diagnostic summary returned by argo_diagnose_rollout (N-to-1 tool)."""

    name: str = Field(default="", description="Rollout name.")
    namespace: str = Field(default="default", description="Kubernetes namespace.")
    phase: str = Field(description="Current Rollout phase (Healthy, Progressing, Paused, Degraded, Unknown).")
    strategy: str = Field(default="canary", description="Rollout strategy (canary, bluegreen, unknown).")
    summary: str = Field(description="Concise root-cause and progression summary.")
    diagnosis_codes: List[str] = Field(
        default_factory=list,
        description="Standardized diagnostic codes mapping to troubleshooting-argo-rollouts error catalog.",
    )
    current_step: Optional[int] = Field(default=None, description="Current canary step index.")
    canary_weight: Optional[int] = Field(default=None, description="Current canary traffic weight percentage.")
    replicas: Dict[str, Any] = Field(default_factory=dict, description="Replica counts (desired, ready, available, updated).")
    conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Rollout status conditions.")
    failing_metrics: List[Dict[str, Any]] = Field(default_factory=list, description="Failing AnalysisRun metrics.")
    warning_events: List[Dict[str, Any]] = Field(default_factory=list, description="Recent Warning Kubernetes events.")
    pods: List[Dict[str, Any]] = Field(default_factory=list, description="Pod status snapshot when include_pods=True.")


class CanaryMetricsComparison(BaseModel):
    """Server-side Prometheus comparison between stable and canary services (N-to-1 tool)."""

    rollout_name: str = Field(description="Rollout name.")
    namespace: str = Field(default="default", description="Kubernetes namespace.")
    window: str = Field(default="5m", description="PromQL rate window.")
    prometheus_reachable: bool = Field(default=True, description="Whether Prometheus responded.")
    stable_service: str = Field(description="Stable Service name.")
    canary_service: str = Field(description="Canary Service name.")
    stable: Dict[str, float] = Field(default_factory=dict, description="Stable service metrics.")
    canary: Dict[str, float] = Field(default_factory=dict, description="Canary service metrics.")
    delta: Dict[str, float] = Field(default_factory=dict, description="Canary minus stable metric deltas.")
    recommendation: Literal["promote", "hold", "abort"] = Field(
        default="promote",
        description="Automated recommendation based on error rate and latency deltas.",
    )
