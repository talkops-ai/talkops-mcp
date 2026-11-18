"""Kubernetes label constants and selector utilities for OpenTelemetry."""

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

# ──────────────────────────────────────────────
# OTel Operator label constants
# ──────────────────────────────────────────────

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "opentelemetry-operator"

OTEL_COMPONENT_LABEL = "app.kubernetes.io/component"
OTEL_INSTANCE_LABEL = "app.kubernetes.io/instance"
OTEL_NAME_LABEL = "app.kubernetes.io/name"
OTEL_PART_OF_LABEL = "app.kubernetes.io/part-of"

# ──────────────────────────────────────────────
# Auto-instrumentation annotation keys
# ──────────────────────────────────────────────

INSTRUMENTATION_ANNOTATION_PREFIX = "instrumentation.opentelemetry.io/inject-"

LANGUAGE_ANNOTATION_KEYS = {
    "java": f"{INSTRUMENTATION_ANNOTATION_PREFIX}java",
    "python": f"{INSTRUMENTATION_ANNOTATION_PREFIX}python",
    "nodejs": f"{INSTRUMENTATION_ANNOTATION_PREFIX}nodejs",
    "dotnet": f"{INSTRUMENTATION_ANNOTATION_PREFIX}dotnet",
    "go": f"{INSTRUMENTATION_ANNOTATION_PREFIX}go",
    "apache-httpd": f"{INSTRUMENTATION_ANNOTATION_PREFIX}apache-httpd",
    "nginx": f"{INSTRUMENTATION_ANNOTATION_PREFIX}nginx",
    "sdk": f"{INSTRUMENTATION_ANNOTATION_PREFIX}sdk",
}

CONTAINER_NAMES_ANNOTATION = "instrumentation.opentelemetry.io/container-names"
DOTNET_RUNTIME_ANNOTATION = "instrumentation.opentelemetry.io/otel-dotnet-auto-runtime"
GO_TARGET_EXE_ANNOTATION = "instrumentation.opentelemetry.io/otel-go-auto-target-exe"
RESOURCE_ATTR_ANNOTATION_PREFIX = "resource.opentelemetry.io/"

# All known annotation keys for scanning
ALL_INSTRUMENTATION_ANNOTATIONS = list(LANGUAGE_ANNOTATION_KEYS.values())

# ──────────────────────────────────────────────
# Per-language OTLP protocol and port defaults (B7 invariant)
# ──────────────────────────────────────────────
# Maps language -> (default_otlp_protocol, default_port)
LANGUAGE_DEFAULT_OTLP: Dict[str, Tuple[str, int]] = {
    "java": ("grpc", 4317),
    "nodejs": ("grpc", 4317),
    "python": ("http/protobuf", 4318),
    "dotnet": ("http/protobuf", 4318),
    "go": ("http/protobuf", 4318),
    "apache-httpd": ("http/protobuf", 4318),
    "nginx": ("grpc", 4317),
    "sdk": ("http/protobuf", 4318),
}


def derive_language_otlp_env(
    collector_endpoint: str, language: str
) -> Dict[str, str]:
    """Derive language-specific OTEL_EXPORTER_OTLP_ENDPOINT and PROTOCOL env vars.

    Different OTel auto-instrumentation agents default to different OTLP
    protocols (e.g., Java/Node.js often use gRPC on 4317, whereas Python,
    .NET, and Go use HTTP/protobuf on 4318). Given a base collector service
    endpoint, this helper derives the matching port and explicit protocol
    for the target language so mixed-language namespaces never fail.
    """
    lang_key = language.lower().strip()
    protocol, target_port = LANGUAGE_DEFAULT_OTLP.get(
        lang_key, ("http/protobuf", 4318)
    )

    raw = collector_endpoint.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "otel-collector"
    port = parsed.port

    # Replace standard OTLP ports (4317/4318) with the language's native port
    if port in (None, 4317, 4318):
        resolved_port = target_port
    else:
        resolved_port = port

    endpoint = f"{scheme}://{host}:{resolved_port}"
    return {
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_EXPORTER_OTLP_PROTOCOL": protocol,
    }


# ──────────────────────────────────────────────
# eBPF-related labels and annotations (including OBI v1.0)
# ──────────────────────────────────────────────

EBPF_AGENT_LABELS = [
    "app.kubernetes.io/name=obi",
    "app.kubernetes.io/name=opentelemetry-ebpf-instrumentation",
    "app.kubernetes.io/name=otel-ebpf",
    "app.kubernetes.io/name=beyla",
    "app=obi",
    "app=ebpf-instrument",
    "app=grafana-beyla",
    "app=opentelemetry-ebpf",
]

EBPF_IMAGE_KEYWORDS = (
    "ebpf-instrument",
    "opentelemetry-ebpf",
    "otel-ebpf",
    "beyla",
    "obi",
    "pixie",
    "tetragon",
    "parca",
    "cilium",
)

# ──────────────────────────────────────────────
# Image-based language detection patterns
# ──────────────────────────────────────────────

# Patterns matched against the full image string (name:tag).
# Order matters — first match wins.
_IMAGE_LANGUAGE_PATTERNS: List[tuple] = [
    # Suffix patterns on image name (e.g., "my-app-java", "otel-demo-python")
    (re.compile(r"[-_/]java(?::\S+)?$", re.IGNORECASE), "java"),
    (re.compile(r"[-_/]python(?::\S+)?$", re.IGNORECASE), "python"),
    (re.compile(r"[-_/]node(?:js)?(?::\S+)?$", re.IGNORECASE), "nodejs"),
    (re.compile(r"[-_/]dotnet(?::\S+)?$", re.IGNORECASE), "dotnet"),
    (re.compile(r"[-_/]go(?:lang)?(?::\S+)?$", re.IGNORECASE), "go"),
    (re.compile(r"[-_/]ruby(?::\S+)?$", re.IGNORECASE), "ruby"),
    (re.compile(r"[-_/]php(?::\S+)?$", re.IGNORECASE), "php"),
    (re.compile(r"[-_/]rust(?::\S+)?$", re.IGNORECASE), "rust"),
    # Base image patterns (e.g., "openjdk:17", "python:3.11", "node:20")
    (re.compile(r"(?:^|/)openjdk(?::\S+)?$", re.IGNORECASE), "java"),
    (re.compile(r"(?:^|/)(?:eclipse-temurin|amazoncorretto|adoptopenjdk)(?::\S+)?$", re.IGNORECASE), "java"),
    (re.compile(r"(?:^|/)python(?::\S+)?$", re.IGNORECASE), "python"),
    (re.compile(r"(?:^|/)node(?::\S+)?$", re.IGNORECASE), "nodejs"),
    (re.compile(r"(?:^|/)golang(?::\S+)?$", re.IGNORECASE), "go"),
    (re.compile(r"(?:^|/)ruby(?::\S+)?$", re.IGNORECASE), "ruby"),
    (re.compile(r"(?:^|/)php(?::\S+)?$", re.IGNORECASE), "php"),
    (re.compile(r"(?:^|/)(?:mcr\.microsoft\.com/dotnet)(?::\S+)?$", re.IGNORECASE), "dotnet"),
    # Tag-suffix patterns (OTel Demo style, e.g., "demo:latest-java")
    (re.compile(r":[\w.]+-java$", re.IGNORECASE), "java"),
    (re.compile(r":[\w.]+-python$", re.IGNORECASE), "python"),
    (re.compile(r":[\w.]+-node(?:js)?$", re.IGNORECASE), "nodejs"),
    (re.compile(r":[\w.]+-dotnet$", re.IGNORECASE), "dotnet"),
    (re.compile(r":[\w.]+-go(?:lang)?$", re.IGNORECASE), "go"),
    (re.compile(r":[\w.]+-ruby$", re.IGNORECASE), "ruby"),
    (re.compile(r":[\w.]+-php$", re.IGNORECASE), "php"),
    (re.compile(r":[\w.]+-rust$", re.IGNORECASE), "rust"),
]

# ──────────────────────────────────────────────
# Service/container name → language heuristics
# ──────────────────────────────────────────────

_NAME_LANGUAGE_HINTS: List[tuple] = [
    (re.compile(r"(?:^|[-_/])(?:java|jvm|spring|quarkus|micronaut)", re.IGNORECASE), "java"),
    (re.compile(r"(?:^|[-_/])(?:python|django|flask|fastapi)", re.IGNORECASE), "python"),
    (re.compile(r"(?:^|[-_/])(?:node|express|nextjs|nestjs)", re.IGNORECASE), "nodejs"),
    (re.compile(r"(?:^|[-_/])(?:dotnet|aspnet|csharp)", re.IGNORECASE), "dotnet"),
    (re.compile(r"(?:^|[-_/])(?:golang|gin|fiber)", re.IGNORECASE), "go"),
    (re.compile(r"(?:^|[-_/])(?:ruby|rails|sinatra)", re.IGNORECASE), "ruby"),
    (re.compile(r"(?:^|[-_/])(?:php|laravel|symfony)", re.IGNORECASE), "php"),
    (re.compile(r"(?:^|[-_/])(?:rust|actix|axum)", re.IGNORECASE), "rust"),
]


def build_otel_operator_selector() -> str:
    """Build a label selector that matches OTel Operator-managed resources."""
    return f"{MANAGED_BY_LABEL}={MANAGED_BY_VALUE}"


def build_label_selector(labels: Dict[str, str]) -> str:
    """Build a Kubernetes label selector string from a dict."""
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def detect_language_from_annotations(
    annotations: Dict[str, str],
) -> Optional[str]:
    """Detect the auto-instrumentation language from pod/workload annotations."""
    for lang, key in LANGUAGE_ANNOTATION_KEYS.items():
        if key in annotations:
            value = str(annotations[key]).lower()
            if value in ("true", ""):
                return lang
            if value and value != "false":
                return lang
    return None


def get_instrumentation_cr_from_annotations(
    annotations: Dict[str, str],
) -> Optional[str]:
    """Extract the Instrumentation CR name from annotations."""
    for key in ALL_INSTRUMENTATION_ANNOTATIONS:
        if key in annotations:
            value = str(annotations[key]).strip()
            if value and value.lower() not in ("true", "false", ""):
                return value
    return None


def detect_language_from_image(image: str) -> Optional[str]:
    """Infer the programming language from a container image name."""
    if not image:
        return None
    for pattern, language in _IMAGE_LANGUAGE_PATTERNS:
        if pattern.search(image):
            return language
    return None


def detect_language_from_images(images: List[str]) -> Optional[str]:
    """Detect language from a list of container images."""
    for image in images:
        lang = detect_language_from_image(image)
        if lang:
            return lang
    return None


def detect_language_from_name(name: str) -> Optional[str]:
    """Infer programming language from a service/container/workload name."""
    if not name:
        return None
    for pattern, language in _NAME_LANGUAGE_HINTS:
        if pattern.search(name):
            return language
    return None


def detect_signals_from_env(env_vars: Dict[str, str]) -> List[str]:
    """Detect OTel signal types from environment variables."""
    signals: List[str] = []
    signal_env_map = {
        "OTEL_TRACES_EXPORTER": "traces",
        "OTEL_METRICS_EXPORTER": "metrics",
        "OTEL_LOGS_EXPORTER": "logs",
    }
    for env_key, signal_name in signal_env_map.items():
        if env_key in env_vars:
            value = str(env_vars[env_key]).lower()
            if value != "none":
                signals.append(signal_name)
    return signals


def has_otel_sdk_env(env_vars: Dict[str, str]) -> bool:
    """Check if env vars indicate manual OTel SDK configuration."""
    return any(k.startswith("OTEL_") for k in env_vars)


_RUNTIME_ENV_LANGUAGE_MAP: List[tuple] = [
    ({"JAVA_TOOL_OPTIONS", "JAVA_HOME", "JAVA_OPTS", "JDK_JAVA_OPTIONS"}, "java"),
    ({"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}, "python"),
    ({"DOTNET_RUNNING_IN_CONTAINER", "ASPNETCORE_URLS", "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"}, "dotnet"),
    ({"NODE_VERSION", "NODE_ENV", "NPM_CONFIG_LOGLEVEL"}, "nodejs"),
    ({"GOPATH", "GOROOT"}, "go"),
    ({"RUBY_VERSION", "GEM_HOME", "BUNDLE_APP_CONFIG"}, "ruby"),
    ({"RUSTUP_HOME", "CARGO_HOME"}, "rust"),
    ({"PHP_INI_DIR", "PHPIZE_DEPS"}, "php"),
]


def detect_language_from_runtime_env(env_vars: Dict[str, str]) -> Optional[str]:
    """Detect programming language from runtime environment variables."""
    env_keys = set(env_vars.keys())
    for runtime_keys, language in _RUNTIME_ENV_LANGUAGE_MAP:
        if env_keys & runtime_keys:
            return language
    return None
