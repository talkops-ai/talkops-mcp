"""Sanitization and secret redaction utilities for Kubernetes and Traefik manifests, headers, and static config."""

import copy
import re
from typing import Any, Dict, Optional

REDACTED_PLACEHOLDER = "[REDACTED]"

_STRIP_METADATA_KEYS = {
    "managedFields",
    "managed_fields",
    "uid",
}

_STRIP_ANNOTATION_KEYS = {
    "kubectl.kubernetes.io/last-applied-configuration",
}

_CONTAINER_LIST_KEYS = (
    "containers",
    "initContainers",
    "init_containers",
    "ephemeralContainers",
    "ephemeral_containers",
)

_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}

_SENSITIVE_CONFIG_KEYS = {
    "token",
    "password",
    "secret",
    "apikey",
    "api_key",
    "privatekey",
    "private_key",
    "key",
    "users",
}


def _redact_container_list(containers: Any) -> None:
    if not isinstance(containers, list):
        return
    for container in containers:
        if not isinstance(container, dict):
            continue
        env_list = container.get("env")
        if isinstance(env_list, list):
            for env_item in env_list:
                if not isinstance(env_item, dict):
                    continue
                if "value" in env_item and env_item["value"] is not None:
                    env_item["value"] = REDACTED_PLACEHOLDER


def _redact_pod_spec(pod_spec: Any) -> None:
    if not isinstance(pod_spec, dict):
        return
    for key in _CONTAINER_LIST_KEYS:
        if key in pod_spec:
            _redact_container_list(pod_spec[key])


def sanitize_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep-copied, sanitized manifest with secrets redacted and noisy metadata stripped.

    - Strips ``metadata.managedFields`` / ``metadata.managed_fields``
    - Strips ``kubectl.kubernetes.io/last-applied-configuration`` annotation
    - Redacts literal ``env[*].value`` in ``containers``, ``initContainers``,
      and ``ephemeralContainers`` while keeping ``valueFrom`` references intact
    - Redacts ``data`` and ``stringData`` on ``Secret`` objects
    - Redacts inline ``users`` arrays in basicAuth/digestAuth Middleware specs if present
    """
    if not isinstance(manifest, dict):
        return manifest

    cleaned = copy.deepcopy(manifest)

    # 1. Strip noisy metadata and last-applied-configuration
    metadata = cleaned.get("metadata")
    if isinstance(metadata, dict):
        for k in _STRIP_METADATA_KEYS:
            metadata.pop(k, None)
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            for k in _STRIP_ANNOTATION_KEYS:
                annotations.pop(k, None)
            if not annotations:
                metadata.pop("annotations", None)

    # 2. Redact Secret data if kind == Secret
    if cleaned.get("kind") == "Secret":
        for sec_key in ("data", "stringData"):
            if isinstance(cleaned.get(sec_key), dict):
                cleaned[sec_key] = {k: REDACTED_PLACEHOLDER for k in cleaned[sec_key]}

    # 3. Redact pod specs at top-level, spec, spec.template.spec
    _redact_pod_spec(cleaned)
    spec = cleaned.get("spec")
    if isinstance(spec, dict):
        _redact_pod_spec(spec)
        template = spec.get("template")
        if isinstance(template, dict):
            _redact_pod_spec(template.get("spec"))
        # Redact accidental inline users on Middleware basicAuth/digestAuth
        for auth_key in ("basicAuth", "digestAuth"):
            auth_block = spec.get(auth_key)
            if isinstance(auth_block, dict) and "users" in auth_block:
                auth_block["users"] = [REDACTED_PLACEHOLDER]

    return cleaned


def redact_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Redact sensitive HTTP headers (Authorization, Cookie, Set-Cookie, X-Api-Key, etc.)."""
    if not headers or not isinstance(headers, dict):
        return {}
    result: Dict[str, str] = {}
    for k, v in headers.items():
        if k.strip().lower() in _SENSITIVE_HEADER_NAMES or "token" in k.lower() or "secret" in k.lower():
            result[k] = REDACTED_PLACEHOLDER
        else:
            result[k] = REDACTED_PLACEHOLDER if isinstance(v, str) and "bearer " in v.lower() else str(v)
    return result


def redact_static_config(obj: Any) -> Any:
    """Recursively redact sensitive tokens, passwords, or keys from static config structures."""
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if k_lower in _SENSITIVE_CONFIG_KEYS or any(
                sub in k_lower for sub in ("password", "secret", "token", "privatekey", "apikey")
            ):
                out[k] = REDACTED_PLACEHOLDER
            else:
                out[k] = redact_static_config(v)
        return out
    if isinstance(obj, list):
        return [redact_static_config(item) for item in obj]
    if isinstance(obj, str) and re.search(r"(--[^\s=]*(?:token|password|secret|key)\s*=\s*)(\S+)", obj, re.I):
        return re.sub(
            r"(--[^\s=]*(?:token|password|secret|key)\s*=\s*)(\S+)",
            rf"\1{REDACTED_PLACEHOLDER}",
            obj,
            flags=re.I,
        )
    return obj
