"""Sanitization and secret redaction utilities for Kubernetes and Argo Rollouts manifests."""

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

_CONTAINER_LIST_KEYS = (
    "containers",
    "initContainers",
    "init_containers",
    "ephemeralContainers",
    "ephemeral_containers",
)


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
                # Redact raw literal values, keep valueFrom references (secretKeyRef, configMapKeyRef, etc.)
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

    # 3. Redact pod specs at top-level, spec, spec.template.spec, and experiment templates
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
