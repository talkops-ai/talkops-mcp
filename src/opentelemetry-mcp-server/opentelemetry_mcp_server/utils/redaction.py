"""Secret redaction, Kubernetes manifest sanitization, and inline secret detection.

Ensures that no MCP tool or resource ever reveals raw secret values, API keys,
Bearer tokens, or noisy Kubernetes internal metadata (`managedFields`,
`kubectl.kubernetes.io/last-applied-configuration`).
"""

import re
from copy import deepcopy
from typing import Any, Dict, List

import yaml

REDACTED_VALUE = "***REDACTED***"

_SENSITIVE_KEY_EXACT = frozenset({
    "authorization",
    "proxy-authorization",
    "api_key",
    "api-key",
    "apikey",
    "x-api-key",
    "dd-api-key",
    "x-honeycomb-team",
    "x-Ingestion-key",
    "token",
    "access_token",
    "refresh_token",
    "bearer_token",
    "id_token",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "private_key",
    "secret_key",
    "access_key",
    "connection_string",
})

_SENSITIVE_KEY_SUBSTRINGS = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "api-key",
    "apikey",
    "private_key",
    "authorization",
    "credential",
)

# Env variable reference syntax used by OpenTelemetry Collector (${env:VAR} or ${VAR})
_ENV_REF_PATTERN = re.compile(r"^\$\{(?:env:)?[A-Za-z_][A-Za-z0-9_]*\}$")

# Inline secret value patterns (Bearer tokens, AWS keys, JWTs, Basic auth)
_INLINE_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
)

_LOG_REDACTION_PATTERNS = (
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*['\"]?(?:bearer|basic)\s+)[^\s,'\"]+"),
        r"\1" + REDACTED_VALUE,
    ),
    (
        re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?)[^\s,'\"]+"),
        r"\1" + REDACTED_VALUE,
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        REDACTED_VALUE,
    ),
)


def is_env_placeholder(value: Any) -> bool:
    """Return True if value is an OTel Collector ${env:VAR} or ${VAR} placeholder."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if _ENV_REF_PATTERN.match(stripped):
        return True
    # Also allow "Bearer ${env:TOKEN}"
    if "${" in stripped and "}" in stripped:
        without_refs = re.sub(r"\$\{(?:env:)?[A-Za-z_][A-Za-z0-9_]*\}", "", stripped)
        without_prefix = re.sub(r"(?i)^(bearer|basic)\s*", "", without_refs).strip()
        return without_prefix == ""
    return False


def _is_sensitive_key(key: str) -> bool:
    """Return True if a dictionary key or env var name represents a secret."""
    k = key.strip().lower()
    if k in _SENSITIVE_KEY_EXACT:
        return True
    return any(sub in k for sub in _SENSITIVE_KEY_SUBSTRINGS)


def _matches_inline_secret_value(value: str) -> bool:
    """Return True if a string value looks like a raw token or credential."""
    if is_env_placeholder(value):
        return False
    return any(pat.search(value) for pat in _INLINE_SECRET_VALUE_PATTERNS)


def detect_inline_secrets(
    data: Any, path: str = "", base_path: str = ""
) -> List[Dict[str, str]]:
    """Scan a Collector config dict or Kubernetes CR dict for plaintext secrets.

    Flags any sensitive key (or header value) that contains a literal secret
    string instead of an `${env:VAR}` reference or Kubernetes `secretKeyRef`.
    """
    path = path or base_path
    issues: List[Dict[str, str]] = []

    if isinstance(data, dict):
        # Special case: Kubernetes env list item {"name": "...", "value": "..."}
        if "name" in data and ("value" in data or "valueFrom" in data):
            env_name = str(data.get("name", ""))
            if "value" in data and data["value"] is not None and "valueFrom" not in data:
                val_str = str(data["value"])
                if (
                    _is_sensitive_key(env_name) and not is_env_placeholder(val_str)
                ) or _matches_inline_secret_value(val_str):
                    issues.append({
                        "path": f"{path}.env[{env_name}]" if path else f"env[{env_name}]",
                        "key": env_name,
                        "reason": (
                            f"Environment variable '{env_name}' has a literal plaintext "
                            "value instead of 'valueFrom.secretKeyRef'."
                        ),
                    })
            return issues

        for k, v in data.items():
            key_str = str(k)
            child_path = f"{path}.{key_str}" if path else key_str

            # Skip internal K8s metadata annotations that hold compressed snapshots
            if path.endswith("metadata.annotations") and key_str in (
                "otel.mcp/previous-config",
                "kubectl.kubernetes.io/last-applied-configuration",
            ):
                continue

            if isinstance(v, (dict, list)):
                issues.extend(detect_inline_secrets(v, child_path))
            elif isinstance(v, str) and v.strip():
                if _is_sensitive_key(key_str) and not is_env_placeholder(v):
                    issues.append({
                        "path": child_path,
                        "key": key_str,
                        "reason": (
                            f"Key '{key_str}' contains a plaintext value instead of "
                            "an '${env:VAR_NAME}' reference."
                        ),
                    })
                elif _matches_inline_secret_value(v):
                    issues.append({
                        "path": child_path,
                        "key": key_str,
                        "reason": (
                            f"Field '{child_path}' contains an inline token/credential pattern."
                        ),
                    })
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            issues.extend(detect_inline_secrets(item, f"{path}[{idx}]"))

    return issues


def redact_collector_config(config: Any) -> Any:
    """Recursively redact sensitive fields in a parsed Collector config dict or YAML string."""
    if isinstance(config, str):
        try:
            parsed = yaml.safe_load(config)
            if isinstance(parsed, dict):
                redacted = _redact_recursive(parsed)
                return yaml.safe_dump(redacted, sort_keys=False)
        except Exception:
            pass
        return redact_log_text(config)

    if isinstance(config, (dict, list)):
        return _redact_recursive(deepcopy(config))
    return config


def _redact_recursive(node: Any, parent_key: str = "") -> Any:
    """Internal helper to recursively mask secrets in dicts and lists."""
    if isinstance(node, dict):
        # K8s env entry {"name": "...", "value": "..."}
        if "name" in node and "value" in node and isinstance(node.get("name"), str):
            env_name = node["name"]
            val = node.get("value")
            if isinstance(val, str) and (
                (_is_sensitive_key(env_name) and not is_env_placeholder(val))
                or _matches_inline_secret_value(val)
            ):
                updated = dict(node)
                updated["value"] = REDACTED_VALUE
                return updated

        result: Dict[str, Any] = {}
        for k, v in node.items():
            key_str = str(k)
            if isinstance(v, (dict, list)):
                result[k] = _redact_recursive(v, parent_key=key_str.lower())
            elif isinstance(v, str):
                if (
                    (_is_sensitive_key(key_str) and not is_env_placeholder(v))
                    or _matches_inline_secret_value(v)
                    or (
                        parent_key == "headers"
                        and _is_sensitive_key(key_str)
                        and not is_env_placeholder(v)
                    )
                ):
                    result[k] = REDACTED_VALUE
                else:
                    result[k] = v
            else:
                result[k] = v
        return result

    if isinstance(node, list):
        return [_redact_recursive(item, parent_key=parent_key) for item in node]

    return node


def sanitize_k8s_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a Kubernetes resource manifest by stripping noisy fields and redacting secrets.

    - Removes `metadata.managedFields`
    - Removes `metadata.annotations['kubectl.kubernetes.io/last-applied-configuration']`
    - Replaces `metadata.annotations['otel.mcp/previous-config']` with `<snapshot-present>`
    - Redacts sensitive values in `spec.config`, `spec.env`, and container env lists
    """
    cleaned = deepcopy(manifest)
    metadata = cleaned.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("managedFields", None)
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)
            if "otel.mcp/previous-config" in annotations:
                annotations["otel.mcp/previous-config"] = "<snapshot-present>"

    return _redact_recursive(cleaned)


def redact_log_text(text: str) -> str:
    """Redact credentials, tokens, and API keys from raw log lines."""
    if not text:
        return text
    redacted = text
    for pattern, replacement in _LOG_REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
