"""Prometheus data models package."""

from prometheus_mcp_server.models.common import BasePrometheusModel
from prometheus_mcp_server.models.backend import (
    BackendCapabilities,
    BackendInfo,
    BackendsSummary,
)
from prometheus_mcp_server.models.query import (
    DownsamplingMetadata,
    InstantQueryResult,
    InstantSample,
    LabelTopologyResult,
    RangeQueryResult,
    RangeSeries,
    ValidatePromQLResult,
)
from prometheus_mcp_server.models.target import (
    FailedTarget,
    FailedTargetsSummary,
    ServiceInfo,
    ServiceTopology,
    TargetInfo,
)
from prometheus_mcp_server.models.metadata import (
    CardinalityOverview,
    CardinalitySummary,
    MetricCatalog,
    MetricMetadata,
    RuntimeConfig,
    TopCardinalityMetric,
)
from prometheus_mcp_server.models.onboarding import (
    InstrumentationSnippet,
    InstrumentationStrategy,
    ScrapeEndpointTestResult,
)
from prometheus_mcp_server.models.exporter import (
    ExporterInfo,
    ExporterManifestResult,
    ExporterRecommendation,
    ExporterUninstallResult,
    ExporterVerificationResult,
)
from prometheus_mcp_server.models.rules import (
    AlertRule,
    RecordingRule,
    RuleGroup,
    RuleGroupList,
    RuleValidationResult,
    RuleTestResult,
    FiringSimulationResult,
    FiringHistoryAnalysis,
    DraftAlertRule,
)

__all__ = [
    'BasePrometheusModel',
    # Backend
    'BackendCapabilities', 'BackendInfo', 'BackendsSummary',
    # Query
    'DownsamplingMetadata', 'InstantQueryResult', 'InstantSample',
    'LabelTopologyResult', 'RangeQueryResult', 'RangeSeries', 'ValidatePromQLResult',
    # Target
    'FailedTarget', 'FailedTargetsSummary', 'ServiceInfo', 'ServiceTopology', 'TargetInfo',
    # Metadata
    'CardinalityOverview', 'CardinalitySummary', 'MetricCatalog', 'MetricMetadata',
    'RuntimeConfig', 'TopCardinalityMetric',
    # Onboarding
    'InstrumentationSnippet', 'InstrumentationStrategy', 'ScrapeEndpointTestResult',
    # Exporter
    'ExporterInfo', 'ExporterManifestResult', 'ExporterRecommendation',
    'ExporterUninstallResult', 'ExporterVerificationResult',
    # Rules
    'AlertRule', 'RecordingRule', 'RuleGroup', 'RuleGroupList',
    'RuleValidationResult', 'RuleTestResult',
    'FiringSimulationResult', 'FiringHistoryAnalysis', 'DraftAlertRule',
]

