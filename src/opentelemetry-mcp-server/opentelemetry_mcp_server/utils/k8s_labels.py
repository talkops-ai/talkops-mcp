"""Kubernetes label constants and selector utilities for OpenTelemetry."""

import re
from typing import Dict, List, Optional

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

# All known annotation keys for scanning
ALL_INSTRUMENTATION_ANNOTATIONS = list(LANGUAGE_ANNOTATION_KEYS.values())

# ──────────────────────────────────────────────
# eBPF-related labels and annotations
# ──────────────────────────────────────────────

EBPF_AGENT_LABELS = [
    "app.kubernetes.io/name=otel-ebpf",
    "app.kubernetes.io/name=beyla",
    "app=grafana-beyla",
    "app=opentelemetry-ebpf",
]

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

# Known OTel Demo and common service name suffixes/keywords.
# Only used as a last-resort fallback when image detection fails
# and OTEL_* env vars confirm SDK usage.
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
    """Build a label selector that matches OTel Operator-managed resources.

    Returns:
        Kubernetes label selector string.
    """
    return f"{MANAGED_BY_LABEL}={MANAGED_BY_VALUE}"


def build_label_selector(labels: Dict[str, str]) -> str:
    """Build a Kubernetes label selector string from a dict.

    Args:
        labels: Dictionary of label key-value pairs.

    Returns:
        Comma-separated label selector string.
    """
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def detect_language_from_annotations(
    annotations: Dict[str, str],
) -> Optional[str]:
    """Detect the auto-instrumentation language from pod/deployment annotations.

    Args:
        annotations: Kubernetes annotations dict.

    Returns:
        Language identifier (e.g., 'java', 'python') or None.
    """
    for lang, key in LANGUAGE_ANNOTATION_KEYS.items():
        if key in annotations:
            value = annotations[key].lower()
            if value in ("true", ""):
                return lang
            # The value can also be the Instrumentation CR name
            if value and value != "false":
                return lang
    return None


def get_instrumentation_cr_from_annotations(
    annotations: Dict[str, str],
) -> Optional[str]:
    """Extract the Instrumentation CR name from annotations.

    When the annotation value is neither 'true' nor empty, it references
    a specific Instrumentation CR name.

    Args:
        annotations: Kubernetes annotations dict.

    Returns:
        Instrumentation CR name, or None if using the default.
    """
    for key in ALL_INSTRUMENTATION_ANNOTATIONS:
        if key in annotations:
            value = annotations[key].strip()
            if value and value.lower() not in ("true", "false", ""):
                return value
    return None


def detect_language_from_image(image: str) -> Optional[str]:
    """Infer the programming language from a container image name.

    Uses pattern matching against common image naming conventions
    (e.g., ``otel-demo-python:latest``, ``openjdk:17``).

    Args:
        image: Container image string (e.g., ``"my-app-java:latest"``).

    Returns:
        Language identifier or None if no match.
    """
    if not image:
        return None
    for pattern, language in _IMAGE_LANGUAGE_PATTERNS:
        if pattern.search(image):
            return language
    return None


def detect_language_from_images(images: List[str]) -> Optional[str]:
    """Detect language from a list of container images.

    Returns the first detected language across all images.

    Args:
        images: List of container image strings.

    Returns:
        Language identifier or None.
    """
    for image in images:
        lang = detect_language_from_image(image)
        if lang:
            return lang
    return None


def detect_language_from_name(name: str) -> Optional[str]:
    """Infer programming language from a service/container/deployment name.

    Uses heuristic pattern matching against common naming conventions
    (e.g., ``adservice`` → Java is NOT detected — only explicit keywords
    like ``spring-app``, ``flask-api``, ``express-server``).

    This is a **last-resort fallback** with lower confidence than image
    detection. Should only be used when image detection fails and OTEL_*
    env vars confirm SDK usage.

    Args:
        name: Deployment, service, or container name.

    Returns:
        Language identifier or None if no match.
    """
    if not name:
        return None
    for pattern, language in _NAME_LANGUAGE_HINTS:
        if pattern.search(name):
            return language
    return None


def detect_signals_from_env(env_vars: Dict[str, str]) -> List[str]:
    """Detect OTel signal types from environment variables.

    Checks for ``OTEL_TRACES_EXPORTER``, ``OTEL_METRICS_EXPORTER``,
    and ``OTEL_LOGS_EXPORTER`` env vars.

    Args:
        env_vars: Dictionary of environment variable name-value pairs.

    Returns:
        List of detected signal types (e.g., ``["traces", "metrics"]``).
    """
    signals: List[str] = []
    signal_env_map = {
        "OTEL_TRACES_EXPORTER": "traces",
        "OTEL_METRICS_EXPORTER": "metrics",
        "OTEL_LOGS_EXPORTER": "logs",
    }
    for env_key, signal_name in signal_env_map.items():
        if env_key in env_vars:
            value = env_vars[env_key].lower()
            # "none" means the signal is explicitly disabled;
            # "<from-ref>" means value comes from configMap/secret — assume enabled
            if value != "none":
                signals.append(signal_name)
    return signals

def has_otel_sdk_env(env_vars: Dict[str, str]) -> bool:
    """Check if env vars indicate manual OTel SDK configuration.

    Looks for common SDK env vars beyond just signal exporters:
    ``OTEL_SERVICE_NAME``, ``OTEL_EXPORTER_OTLP_ENDPOINT``,
    ``OTEL_RESOURCE_ATTRIBUTES``, etc.

    Args:
        env_vars: Dictionary of environment variable name-value pairs.

    Returns:
        True if OTel SDK env vars are present.
    """
    return any(k.startswith("OTEL_") for k in env_vars)


# ──────────────────────────────────────────────
# Runtime env var → language detection
# ──────────────────────────────────────────────

# Well-known env vars injected by base images or language runtimes.
# Checked against container env var *names* — values don't matter.
_RUNTIME_ENV_LANGUAGE_MAP: List[tuple] = [
    # Java / Kotlin / JVM
    ({"JAVA_TOOL_OPTIONS", "JAVA_HOME", "JAVA_OPTS", "JDK_JAVA_OPTIONS"}, "java"),
    # Python
    ({"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}, "python"),
    # .NET
    ({"DOTNET_RUNNING_IN_CONTAINER", "ASPNETCORE_URLS", "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"}, "dotnet"),
    # Node.js
    ({"NODE_VERSION", "NODE_ENV", "NPM_CONFIG_LOGLEVEL"}, "nodejs"),
    # Go
    ({"GOPATH", "GOROOT"}, "go"),
    # Ruby
    ({"RUBY_VERSION", "GEM_HOME", "BUNDLE_APP_CONFIG"}, "ruby"),
    # Rust
    ({"RUSTUP_HOME", "CARGO_HOME"}, "rust"),
    # PHP
    ({"PHP_INI_DIR", "PHPIZE_DEPS"}, "php"),
]


def detect_language_from_runtime_env(env_vars: Dict[str, str]) -> Optional[str]:
    """Detect programming language from runtime environment variables.

    Checks for well-known env vars that base images and language runtimes
    inject automatically (e.g., ``JAVA_HOME``, ``PYTHONPATH``,
    ``NODE_VERSION``). This works universally regardless of image naming
    conventions.

    Args:
        env_vars: Dictionary of environment variable name-value pairs.

    Returns:
        Language identifier or None if no match.
    """
    env_keys = set(env_vars.keys())
    for runtime_keys, language in _RUNTIME_ENV_LANGUAGE_MAP:
        if env_keys & runtime_keys:
            return language
    return None
