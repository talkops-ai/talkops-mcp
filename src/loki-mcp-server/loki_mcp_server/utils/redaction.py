"""Secret redaction and Kubernetes manifest sanitization utilities."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED_VALUE = "***REDACTED***"

_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
    r"authorization|client[_-]?secret|bearer|credential|s3[_-]?secret)",
    re.IGNORECASE,
)


def redact_url(url: str) -> str:
    """Redact user:password credentials and sensitive query params embedded in a URL."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        netloc = parts.netloc
        if parts.username or parts.password:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            user = parts.username or "user"
            netloc = f"{user}:{REDACTED_VALUE}@{host}"
        query = parts.query
        if query:
            redacted_params = [
                (k, REDACTED_VALUE if _SENSITIVE_KEY_RE.search(k) else v)
                for k, v in parse_qsl(query, keep_blank_values=True)
            ]
            query = urlencode(redacted_params)
        return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
    except Exception:
        pass
    return url


def redact_dict(data: Any) -> Any:
    """Recursively redact sensitive keys in dictionaries and lists."""
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            if _SENSITIVE_KEY_RE.search(key_str) and not isinstance(v, (dict, list)):
                sanitized[key_str] = REDACTED_VALUE if v else v
            elif key_str.lower() in ("url", "base_url", "endpoint") and isinstance(v, str):
                sanitized[key_str] = redact_url(v)
            else:
                sanitized[key_str] = redact_dict(v)
        return sanitized
    if isinstance(data, list):
        return [redact_dict(item) for item in data]
    return data


def sanitize_k8s_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a Kubernetes custom resource manifest for safe MCP exposure.

    Strips noisy cluster metadata (`managedFields`, `last-applied-configuration`)
    and redacts secret values or inline credentials.
    """
    cleaned = copy.deepcopy(manifest)
    if str(cleaned.get("kind", "")).lower() == "secret":
        if "data" in cleaned and isinstance(cleaned["data"], dict):
            cleaned["data"] = {k: REDACTED_VALUE for k in cleaned["data"]}
        if "stringData" in cleaned and isinstance(cleaned["stringData"], dict):
            cleaned["stringData"] = {k: REDACTED_VALUE for k in cleaned["stringData"]}

    meta = cleaned.get("metadata")
    if isinstance(meta, dict):
        meta.pop("managedFields", None)
        annotations = meta.get("annotations")
        if isinstance(annotations, dict):
            annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)

    return redact_dict(cleaned)
