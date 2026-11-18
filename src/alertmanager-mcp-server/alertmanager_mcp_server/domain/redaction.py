"""Deep configuration and receiver secret redaction for Alertmanager configs.

Prevents leaking webhook tokens, SMTP passwords, OAuth2 client secrets,
HTTP bearer credentials, custom authorization headers, and URL userinfo
in MCP resources (`am://backends/{id}/config`, `am://backends/{id}/receivers`).
"""

from __future__ import annotations

import re
from typing import Any, Mapping

REDACTED_VALUE = "***REDACTED***"

_EXACT_SECRET_KEYS = frozenset(
    {
        "api_url",
        "webhook_url",
        "slack_api_url",
        "pagerduty_url",
        "victorops_api_key",
        "opsgenie_api_key",
        "wechat_api_secret",
        "auth_password",
        "auth_secret",
        "auth_token",
        "bearer_token",
        "bot_token",
        "user_key",
        "service_key",
        "routing_key",
        "api_key",
        "apikey",
        "api_secret",
        "client_secret",
        "secret_key",
        "access_key",
        "private_key",
        "password",
        "secret",
        "token",
        "credentials",
        "credentials_file",
        "password_file",
        "bearer_token_file",
        "authorization_Header",
    }
)

_SECRET_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "service_key",
    "routing_key",
    "user_key",
    "access_key",
    "private_key",
    "credential",
    "webhook_url",
    "api_url",
)

# Matches URLs with embedded userinfo: https://user:pass@example.com/path
_URL_USERINFO_RE = re.compile(r"^(https?://)([^/@\s]+:[^/@\s]+)@(.+)$", re.IGNORECASE)


def is_secret_key(key: str) -> bool:
    """Return True if a configuration key name represents a secret or credential."""
    k_lower = key.strip().lower()
    if k_lower in _EXACT_SECRET_KEYS:
        return True
    return any(sub in k_lower for sub in _SECRET_SUBSTRINGS)


def redact_url_userinfo(value: str) -> str:
    """Mask `user:password@` userinfo embedded in HTTP(S) URLs."""
    m = _URL_USERINFO_RE.match(value.strip())
    if m:
        return f"{m.group(1)}***:***@{m.group(3)}"
    return value


def redact_config_data(obj: Any, *, parent_key: str = "") -> Any:
    """Recursively redact sensitive fields in a parsed Alertmanager config structure."""
    if isinstance(obj, Mapping):
        redacted: dict[str, Any] = {}
        parent_lower = parent_key.strip().lower()
        for raw_k, raw_v in obj.items():
            k = str(raw_k)
            k_lower = k.strip().lower()

            # Inside an http_config.headers block, redact all header values
            if parent_lower == "headers":
                redacted[k] = REDACTED_VALUE
                continue

            if is_secret_key(k):
                if isinstance(raw_v, Mapping):
                    # Preserve structure but redact leaf values inside secret blocks
                    redacted[k] = {
                        str(sub_k): REDACTED_VALUE for sub_k in raw_v.keys()
                    }
                elif isinstance(raw_v, list):
                    redacted[k] = [REDACTED_VALUE for _ in raw_v]
                elif raw_v is not None:
                    redacted[k] = REDACTED_VALUE
                else:
                    redacted[k] = None
                continue

            redacted[k] = redact_config_data(raw_v, parent_key=k)
        return redacted

    if isinstance(obj, list):
        return [redact_config_data(item, parent_key=parent_key) for item in obj]

    if isinstance(obj, str):
        return redact_url_userinfo(obj)

    return obj
