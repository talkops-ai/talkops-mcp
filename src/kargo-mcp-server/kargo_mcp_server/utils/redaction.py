"""Sanitization and secret redaction utilities for Kargo and Kubernetes manifests."""

import copy
from typing import Any, Dict, List

REDACTED_PLACEHOLDER = "***REDACTED***"

_STRIP_METADATA_KEYS = {
    "managedFields",
    "managed_fields",
}

_STRIP_ANNOTATION_KEYS = {
    "kubectl.kubernetes.io/last-applied-configuration",
}

_SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "privatekey",
    "private_key",
    "sshprivatekey",
    "githubappprivatekey",
    "authheader",
    "auth-header",
)

_CONTAINER_LIST_KEYS = (
    "containers",
    "initContainers",
    "init_containers",
    "ephemeralContainers",
    "ephemeral_containers",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("_", "").replace("-", "")
    # Do not redact secretRef / signingKeySecret / secretKeyRef object pointers
    if lowered.endswith("ref") or lowered.endswith("secretname") or lowered == "signingkeysecret":
        return False
    return any(s.replace("-", "").replace("_", "") in lowered for s in _SENSITIVE_KEY_SUBSTRINGS)


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


def redact_credentials_dict(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a Kargo credential/secret dict with all secret values redacted."""
    if not isinstance(item, dict):
        return item
    cleaned = copy.deepcopy(item)
    for sec_key in ("data", "stringData"):
        if isinstance(cleaned.get(sec_key), dict):
            cleaned[sec_key] = {
                k: (cleaned[sec_key][k] if k in ("repoURL", "repoUrl", "repoURLIsRegex", "username") else REDACTED_PLACEHOLDER)
                for k in cleaned[sec_key]
            }
    for k in list(cleaned.keys()):
        if isinstance(cleaned[k], str) and _is_sensitive_key(k):
            cleaned[k] = REDACTED_PLACEHOLDER
    return cleaned


def sanitize_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep-copied, sanitized manifest with secrets redacted and noisy metadata stripped.

    - Strips ``metadata.managedFields`` / ``metadata.managed_fields``
    - Strips ``kubectl.kubernetes.io/last-applied-configuration`` annotation
    - Redacts literal ``env[*].value`` in ``containers``, ``initContainers``,
      and ``ephemeralContainers`` while keeping ``valueFrom`` references intact
    - Redacts ``data`` and ``stringData`` on ``Secret`` objects
    - Redacts top-level sensitive fields (``password``, ``token``, ``sshPrivateKey``)
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

    # 3. Redact sensitive top-level keys on credential responses
    for k in list(cleaned.keys()):
        if isinstance(cleaned[k], str) and _is_sensitive_key(k):
            cleaned[k] = REDACTED_PLACEHOLDER

    # 4. Redact pod specs at top-level, spec, spec.template.spec, and templates
    _redact_pod_spec(cleaned)
    spec = cleaned.get("spec")
    if isinstance(spec, dict):
        _redact_pod_spec(spec)
        template = spec.get("template")
        if isinstance(template, dict):
            _redact_pod_spec(template.get("spec"))
        templates = spec.get("templates")
        if isinstance(templates, list):
            for tmpl in templates:
                if isinstance(tmpl, dict):
                    _redact_pod_spec(tmpl.get("spec"))
                    inner = tmpl.get("template")
                    if isinstance(inner, dict):
                        _redact_pod_spec(inner.get("spec"))

    return cleaned
