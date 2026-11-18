"""Alertmanager domain core: matchers, routing, inhibition, time intervals, silence policy, redaction, and metrics."""

from alertmanager_mcp_server.domain.inhibition import (
    CompiledInhibitRule,
    InhibitionEvaluation,
    InhibitionMatchDetail,
    evaluate_inhibition,
    parse_inhibit_rules,
)
from alertmanager_mcp_server.domain.matchers import (
    CompiledMatcher,
    MatcherValidationError,
    escape_filter_value,
    format_filter_param,
    match_all,
    parse_matcher,
    parse_matcher_set,
    parse_route_matchers,
    split_matcher_expressions,
    validate_re2_regex,
)
from alertmanager_mcp_server.domain.metrics import (
    AlertmanagerMetricsSummary,
    IntegrationDeliveryStats,
    parse_prometheus_metrics,
)
from alertmanager_mcp_server.domain.redaction import (
    REDACTED_VALUE,
    is_secret_key,
    redact_config_data,
    redact_url_userinfo,
)
from alertmanager_mcp_server.domain.routing import (
    MatchedRouteDelivery,
    RouteNode,
    RouteStepTrace,
    RouteTree,
    RoutingEvaluation,
    build_route_node,
)
from alertmanager_mcp_server.domain.silence_policy import (
    PolicyViolation,
    SilencePolicy,
    SilencePolicyResult,
)
from alertmanager_mcp_server.domain.time_intervals import (
    TimeIntervalCatalog,
    matches_time_interval_entry,
)
from alertmanager_mcp_server.domain.timeparse import (
    TimeValidationError,
    format_rfc3339_utc,
    parse_rfc3339,
    resolve_silence_window,
    utc_now,
)

__all__ = [
    "AlertmanagerMetricsSummary",
    "CompiledInhibitRule",
    "CompiledMatcher",
    "InhibitionEvaluation",
    "InhibitionMatchDetail",
    "IntegrationDeliveryStats",
    "MatchedRouteDelivery",
    "MatcherValidationError",
    "PolicyViolation",
    "REDACTED_VALUE",
    "RouteNode",
    "RouteStepTrace",
    "RouteTree",
    "RoutingEvaluation",
    "SilencePolicy",
    "SilencePolicyResult",
    "TimeIntervalCatalog",
    "TimeValidationError",
    "build_route_node",
    "escape_filter_value",
    "evaluate_inhibition",
    "format_filter_param",
    "format_rfc3339_utc",
    "is_secret_key",
    "match_all",
    "matches_time_interval_entry",
    "parse_inhibit_rules",
    "parse_matcher",
    "parse_matcher_set",
    "parse_prometheus_metrics",
    "parse_rfc3339",
    "parse_route_matchers",
    "redact_config_data",
    "redact_url_userinfo",
    "resolve_silence_window",
    "split_matcher_expressions",
    "utc_now",
    "validate_re2_regex",
]
