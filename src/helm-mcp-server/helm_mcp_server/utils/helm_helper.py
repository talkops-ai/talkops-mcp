"""Execution-layer utilities for Helm MCP server: secret redaction, semver comparison, and manifest diffing."""

from __future__ import annotations

import copy
import re
import shutil
from typing import Any, Dict, List, Tuple

import yaml

REDACTED_PLACEHOLDER = "***REDACTED***"

SENSITIVE_KEY_REGEX = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret|connection[_-]?string|credentials)",
    re.IGNORECASE,
)

SAFE_KEY_REGEX = re.compile(
    r"(existing[_-]?secret|secret[_-]?name|secret[_-]?key|secret[_-]?ref|pull[_-]?secret|service[_-]?account|password[_-]?key|token[_-]?key)",
    re.IGNORECASE,
)

SEMVER_REGEX = re.compile(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def is_helm_installed() -> bool:
    """Check if the helm binary is available in the system PATH."""
    return shutil.which("helm") is not None


def is_sensitive_key(key: str) -> bool:
    """Return True if a configuration key name represents a secret value rather than a secret reference."""
    if SAFE_KEY_REGEX.search(key):
        return False
    return bool(SENSITIVE_KEY_REGEX.search(key))


def redact_sensitive_values(data: Any) -> Any:
    """Recursively mask sensitive keys in a values dictionary or list."""
    if isinstance(data, dict):
        redacted: Dict[str, Any] = {}
        is_named_env_secret = (
            "name" in data
            and "value" in data
            and is_sensitive_key(str(data.get("name", "")))
        )
        for k, v in data.items():
            key_str = str(k)
            if key_str == "value" and is_named_env_secret and v not in (None, "", False):
                redacted[k] = REDACTED_PLACEHOLDER
            elif is_sensitive_key(key_str) and not isinstance(v, (dict, list)) and v not in (None, "", False):
                redacted[k] = REDACTED_PLACEHOLDER
            else:
                redacted[k] = redact_sensitive_values(v)
        return redacted
    if isinstance(data, list):
        return [redact_sensitive_values(item) for item in data]
    return data


def _redact_pod_spec_env(pod_spec: Dict[str, Any]) -> None:
    """Redact sensitive inline env values inside container specs."""
    for container_key in ("containers", "initContainers"):
        containers = pod_spec.get(container_key)
        if not isinstance(containers, list):
            continue
        for container in containers:
            if not isinstance(container, dict):
                continue
            env_list = container.get("env")
            if not isinstance(env_list, list):
                continue
            for env_item in env_list:
                if (
                    isinstance(env_item, dict)
                    and "value" in env_item
                    and is_sensitive_key(str(env_item.get("name", "")))
                ):
                    env_item["value"] = REDACTED_PLACEHOLDER


def redact_secrets_in_manifests(manifests: str) -> str:
    """Mask Secret.data, Secret.stringData, and sensitive inline env vars in multi-doc YAML manifests."""
    if not manifests or not manifests.strip():
        return manifests

    try:
        docs = list(yaml.safe_load_all(manifests))
    except yaml.YAMLError:
        return manifests

    redacted_docs: List[Dict[str, Any]] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        doc_copy = copy.deepcopy(doc)
        kind = str(doc_copy.get("kind") or "")

        if kind == "Secret":
            for secret_field in ("data", "stringData"):
                field_val = doc_copy.get(secret_field)
                if isinstance(field_val, dict):
                    doc_copy[secret_field] = {k: REDACTED_PLACEHOLDER for k in field_val}
        else:
            spec = doc_copy.get("spec")
            if isinstance(spec, dict):
                if kind == "Pod":
                    _redact_pod_spec_env(spec)
                elif kind == "CronJob":
                    pod_spec = (
                        spec.get("jobTemplate", {})
                        .get("spec", {})
                        .get("template", {})
                        .get("spec")
                    )
                    if isinstance(pod_spec, dict):
                        _redact_pod_spec_env(pod_spec)
                else:
                    pod_spec = spec.get("template", {}).get("spec")
                    if isinstance(pod_spec, dict):
                        _redact_pod_spec_env(pod_spec)

        redacted_docs.append(doc_copy)

    if not redacted_docs:
        return manifests

    return yaml.safe_dump_all(redacted_docs, sort_keys=False)


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Parse a Kubernetes or Helm version string into a (major, minor, patch) tuple."""
    if not version_str:
        return (0, 0, 0)
    match = SEMVER_REGEX.search(str(version_str).strip())
    if not match:
        return (0, 0, 0)
    major = int(match.group(1) or 0)
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    return (major, minor, patch)


def compare_k8s_versions(current_version: str, required_version: str) -> bool:
    """Return True if current_version >= required_version using semantic version comparison."""
    return parse_semver(current_version) >= parse_semver(required_version)


def _extract_images(doc: Dict[str, Any]) -> Dict[str, str]:
    """Extract container_name -> image map from a workload document."""
    kind = doc.get("kind")
    raw_spec = doc.get("spec")
    spec: Dict[str, Any] = raw_spec if isinstance(raw_spec, dict) else {}
    if kind == "Pod":
        pod_spec = spec
    elif kind == "CronJob":
        jt = spec.get("jobTemplate")
        jt_spec = jt.get("spec") if isinstance(jt, dict) else None
        tpl = jt_spec.get("template") if isinstance(jt_spec, dict) else None
        pod_spec = tpl.get("spec") if isinstance(tpl, dict) else {}
    else:
        tpl = spec.get("template")
        pod_spec = tpl.get("spec") if isinstance(tpl, dict) else {}

    images: Dict[str, str] = {}
    if isinstance(pod_spec, dict):
        for c in list(pod_spec.get("containers") or []) + list(pod_spec.get("initContainers") or []):
            if isinstance(c, dict) and c.get("name"):
                images[str(c["name"])] = str(c.get("image") or "")
    return images


def _index_manifest_docs(manifests: str, default_namespace: str = "default") -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Index YAML documents by (kind, namespace, name)."""
    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    if not manifests or not manifests.strip():
        return index
    try:
        docs = list(yaml.safe_load_all(manifests))
    except yaml.YAMLError:
        return index

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = str(doc.get("kind") or "Unknown")
        raw_meta = doc.get("metadata")
        meta: Dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        name = str(meta.get("name") or "unnamed")
        ns = str(meta.get("namespace") or default_namespace)
        index[(kind, ns, name)] = doc
    return index


def compute_manifest_diff(
    current_manifest: str,
    proposed_manifest: str,
    default_namespace: str = "default",
) -> Dict[str, Any]:
    """Compute a structured resource diff between live and proposed Kubernetes manifests."""
    current_idx = _index_manifest_docs(current_manifest, default_namespace)
    proposed_idx = _index_manifest_docs(proposed_manifest, default_namespace)

    added: List[Dict[str, str]] = []
    removed: List[Dict[str, str]] = []
    modified: List[Dict[str, Any]] = []
    image_changes: List[Dict[str, str]] = []
    replica_changes: List[Dict[str, Any]] = []
    unchanged_count = 0

    for key in sorted(proposed_idx.keys() - current_idx.keys()):
        kind, ns, name = key
        added.append({"kind": kind, "namespace": ns, "name": name})

    for key in sorted(current_idx.keys() - proposed_idx.keys()):
        kind, ns, name = key
        removed.append({"kind": kind, "namespace": ns, "name": name})

    for key in sorted(current_idx.keys() & proposed_idx.keys()):
        kind, ns, name = key
        cur_doc = current_idx[key]
        prop_doc = proposed_idx[key]

        if cur_doc == prop_doc:
            unchanged_count += 1
            continue

        changed_fields: List[str] = []
        for top_key in sorted(set(cur_doc.keys()) | set(prop_doc.keys())):
            if cur_doc.get(top_key) != prop_doc.get(top_key):
                changed_fields.append(str(top_key))

        modified.append({
            "kind": kind,
            "namespace": ns,
            "name": name,
            "changed_fields": changed_fields,
        })

        # Track image changes
        cur_images = _extract_images(cur_doc)
        prop_images = _extract_images(prop_doc)
        for c_name in sorted(set(cur_images.keys()) | set(prop_images.keys())):
            if cur_images.get(c_name) != prop_images.get(c_name):
                image_changes.append({
                    "resource": f"{kind}/{name}",
                    "container": c_name,
                    "from": cur_images.get(c_name, "<none>"),
                    "to": prop_images.get(c_name, "<none>"),
                })

        # Track replica changes
        cur_replicas = cur_doc.get("spec", {}).get("replicas") if isinstance(cur_doc.get("spec"), dict) else None
        prop_replicas = prop_doc.get("spec", {}).get("replicas") if isinstance(prop_doc.get("spec"), dict) else None
        if cur_replicas != prop_replicas and (cur_replicas is not None or prop_replicas is not None):
            replica_changes.append({
                "resource": f"{kind}/{name}",
                "from": cur_replicas,
                "to": prop_replicas,
            })

    return {
        "has_changes": bool(added or removed or modified),
        "added_resources": added,
        "removed_resources": removed,
        "modified_resources": modified,
        "unchanged_count": unchanged_count,
        "image_changes": image_changes,
        "replica_changes": replica_changes,
    }
