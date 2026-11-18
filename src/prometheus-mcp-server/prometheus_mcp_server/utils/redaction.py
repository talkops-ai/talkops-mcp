"""Deep secret redaction for Prometheus configs, Kubernetes CRDs, URLs, and exporter DSNs.

Prevents leaking basic_auth passwords, bearer_tokens, oauth2 client_secrets,
tls_config keys, webhook URLs, embedded URL userinfo, K8s Secret values, and
exporter DATA_SOURCE_NAME / password flags across MCP tools and resources.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

REDACTED_VALUE = "***REDACTED***"

_EXACT_SECRET_KEYS = frozenset(
    {
        "password",
        "password_file",
        "bearer_token",
        "bearer_token_file",
        "auth_token",
        "auth_password",
        "auth_secret",
        "client_secret",
        "client_secret_file",
        "secret",
        "secret_key",
        "access_key",
        "private_key",
        "key_file",
        "token",
        "api_key",
        "apikey",
        "api_secret",
        "credentials",
        "credentials_file",
        "authorization",
        "proxy_url",
        "webhook_url",
        "data_source_name",
        "data_source_pass",
        "redis_password",
        "rabbit_password",
        "kafka_sasl_password",
        "pgpassword",
        "mysql_pwd",
        "stringdata",
    }
)

_SECRET_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
    "credential",
    "data_source_name",
    "dsn",
)

# Matches URLs with embedded userinfo: https://user:pass@example.com/path or postgres://user:pass@host:5432/db
_URL_USERINFO_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*://)([^/@\s]+:[^/@\s]+)@(.+)$")

# Matches key=value pairs with passwords in DSN strings (e.g. "user=postgres password=secret host=db")
_DSN_KV_PASSWORD_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token)\s*=\s*([^\s'\"&;]+|'[^']*'|\"[^\"]*\")"
)


_NON_SECRET_REFERENCE_KEYS = frozenset(
    {
        "secretkeyref",
        "secretref",
        "secretname",
        "existingsecret",
        "secret_env",
        "secret_name",
    }
)


def is_secret_key(key: str) -> bool:
    """Return True if a configuration or manifest key name represents a secret or credential."""
    k_lower = key.strip().lower()
    if k_lower in _NON_SECRET_REFERENCE_KEYS:
        return False
    if k_lower in _EXACT_SECRET_KEYS:
        return True
    return any(sub in k_lower for sub in _SECRET_SUBSTRINGS)


def redact_string_secrets(value: str) -> str:
    """Mask embedded `user:password@` URL userinfo and `password=...` DSN fragments."""
    stripped = value.strip()
    m = _URL_USERINFO_RE.match(stripped)
    if m:
        stripped = f"{m.group(1)}***:***@{m.group(3)}"
    if _DSN_KV_PASSWORD_RE.search(stripped):
        stripped = _DSN_KV_PASSWORD_RE.sub(r"\1=" + REDACTED_VALUE, stripped)
    return stripped


def redact_sensitive_data(obj: Any, *, parent_key: str = "") -> Any:
    """Recursively redact sensitive fields in Prometheus configs, K8s manifests, or dicts."""
    if isinstance(obj, Mapping):
        redacted: dict[str, Any] = {}
        parent_lower = parent_key.strip().lower()
        is_k8s_secret = str(obj.get("kind", "")).lower() == "secret"

        for raw_k, raw_v in obj.items():
            k = str(raw_k)
            k_lower = k.strip().lower()

            if parent_lower in ("headers", "http_headers") or (
                is_k8s_secret and k_lower in ("data", "stringdata")
            ):
                if isinstance(raw_v, Mapping):
                    redacted[k] = {str(sk): REDACTED_VALUE for sk in raw_v.keys()}
                else:
                    redacted[k] = REDACTED_VALUE
                continue

            # Handle Kubernetes container env entry: {"name": "REDIS_PASSWORD", "value": "secret"}
            if k_lower == "value" and isinstance(obj.get("name"), str) and is_secret_key(obj["name"]):
                redacted[k] = REDACTED_VALUE
                continue

            if is_secret_key(k):
                if isinstance(raw_v, Mapping):
                    redacted[k] = {str(sub_k): REDACTED_VALUE for sub_k in raw_v.keys()}
                elif isinstance(raw_v, list):
                    redacted[k] = [REDACTED_VALUE for _ in raw_v]
                elif raw_v is not None:
                    redacted[k] = REDACTED_VALUE
                else:
                    redacted[k] = None
                continue

            redacted[k] = redact_sensitive_data(raw_v, parent_key=k)
        return redacted

    if isinstance(obj, list):
        return [redact_sensitive_data(item, parent_key=parent_key) for item in obj]

    if isinstance(obj, str):
        return redact_string_secrets(obj)

    return obj
