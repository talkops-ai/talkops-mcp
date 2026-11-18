"""Redaction, manifest sanitization, safe config extraction, and YAML diff utilities.

Enforces the 0->1 omission boundary for secrets and credentials across:
1. Kubernetes TempoStack / TempoMonolithic manifests
2. Tempo /status/config runtime configuration (strict allow-list extraction)
3. Backend connection profiles
"""

import copy
import difflib
import re
from typing import Any, Dict, List, Optional

import yaml

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(secret|password|passwd|token|access_key|secret_key|private_key|"
    r"client_secret|auth_header|authorization|api_key|apikey|credentials|"
    r"connection_string|sas_token|account_key|bearer)",
    re.IGNORECASE,
)

REDACTED_VALUE = "***REDACTED***"


def redact_sensitive_dict(data: Any) -> Any:
    """Recursively redact sensitive keys in dicts and lists."""
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            # In TempoStack, storage.secret is a reference {name, type}, not a raw secret value,
            # unless a nested key is an actual secret value.
            if key_str == "secret" and isinstance(v, dict) and set(v.keys()) <= {"name", "type", "credentialMode"}:
                sanitized[key_str] = copy.deepcopy(v)
            elif _SENSITIVE_KEY_PATTERN.search(key_str) and not isinstance(v, (dict, list)):
                sanitized[key_str] = REDACTED_VALUE if v is not None else None
            else:
                sanitized[key_str] = redact_sensitive_dict(v)
        return sanitized
    if isinstance(data, list):
        return [redact_sensitive_dict(item) for item in data]
    return data


def sanitize_k8s_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Strip noisy Kubernetes metadata and redact sensitive values from a manifest."""
    cleaned = copy.deepcopy(manifest)
    metadata = cleaned.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("managedFields", None)
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)
            if not annotations:
                metadata.pop("annotations", None)
    return redact_sensitive_dict(cleaned)


def extract_safe_status_config(raw_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract only allow-listed, non-secret operational facts from Tempo /status/config.

    Raw /status/config contains object storage credentials, auth tokens, and TLS keys.
    This function implements the 0->1 omission rule by never returning raw config blocks.
    """
    if not raw_config or not isinstance(raw_config, dict):
        return {}

    facts: Dict[str, Any] = {}

    # 1. Multi-tenancy
    if "multitenancy_enabled" in raw_config:
        facts["multitenancy_enabled"] = bool(raw_config.get("multitenancy_enabled"))

    # 2. Query frontend & built-in MCP server
    qf = raw_config.get("query_frontend")
    if isinstance(qf, dict):
        mcp_srv = qf.get("mcp_server")
        if isinstance(mcp_srv, dict):
            facts["builtin_mcp_server_enabled"] = bool(mcp_srv.get("enabled", False))
        search_cfg = qf.get("search")
        if isinstance(search_cfg, dict):
            if "max_duration" in search_cfg:
                facts["max_search_duration"] = search_cfg.get("max_duration")
            if "default_result_limit" in search_cfg:
                facts["default_result_limit"] = search_cfg.get("default_result_limit")
            if "max_result_limit" in search_cfg:
                facts["max_result_limit"] = search_cfg.get("max_result_limit")
        metrics_cfg = qf.get("metrics")
        if isinstance(metrics_cfg, dict):
            if "max_duration" in metrics_cfg:
                facts["max_metrics_duration"] = metrics_cfg.get("max_duration")

    # 3. Metrics generator processors
    overrides = raw_config.get("overrides")
    override_default_procs: Optional[List[str]] = None
    if isinstance(overrides, dict):
        defs = overrides.get("defaults")
        if isinstance(defs, dict):
            mg_defs = defs.get("metrics_generator")
            if isinstance(mg_defs, dict) and isinstance(mg_defs.get("processors"), list):
                override_default_procs = [str(p).replace("_", "-") for p in mg_defs["processors"]]
            elif isinstance(defs.get("metrics_generator_processors"), list):
                override_default_procs = [str(p).replace("_", "-") for p in defs["metrics_generator_processors"]]

    mg = raw_config.get("metrics_generator")
    if override_default_procs is not None:
        facts["metrics_generator_processors"] = override_default_procs
    if isinstance(mg, dict):
        if "metrics_generator_processors" not in facts:
            processor_cfg = mg.get("processor") or mg.get("processors")
            if isinstance(processor_cfg, dict):
                facts["metrics_generator_processors"] = sorted(
                    str(k).replace("_", "-")
                    for k, v in processor_cfg.items()
                    if v not in (None, False)
                )
            elif isinstance(processor_cfg, list):
                facts["metrics_generator_processors"] = [str(p).replace("_", "-") for p in processor_cfg]
        storage_cfg = mg.get("storage")
        if isinstance(storage_cfg, dict):
            facts["metrics_generator_remote_write_enabled"] = bool(storage_cfg.get("remote_write"))

    # 4. Overrides & default limits
    if isinstance(overrides, dict):
        uco = overrides.get("user_configurable_overrides")
        if isinstance(uco, dict):
            facts["user_configurable_overrides_enabled"] = bool(uco.get("enabled", False))
        defaults = overrides.get("defaults")
        if isinstance(defaults, dict):
            limit_facts: Dict[str, Any] = {}
            for section_key in ("ingestion", "read", "global", "metrics_generator"):
                sec = defaults.get(section_key)
                if isinstance(sec, dict):
                    for k in (
                        "rate_limit_bytes",
                        "burst_size_bytes",
                        "max_traces_per_user",
                        "max_bytes_per_trace",
                        "max_bytes_per_tag_values_query",
                        "max_search_duration",
                        "processors",
                    ):
                        if k in sec:
                            limit_facts[f"{section_key}.{k}"] = sec[k]
            for flat_key in (
                "ingestion_rate_limit_bytes",
                "ingestion_burst_size_bytes",
                "max_bytes_per_trace",
                "max_traces_per_user",
                "metrics_generator_processors",
            ):
                if flat_key in defaults:
                    limit_facts[flat_key] = defaults[flat_key]
            if limit_facts:
                facts["default_limits"] = limit_facts

    # 5. Storage layout (backend type, block version, dedicated columns) — never credentials
    storage = raw_config.get("storage")
    if isinstance(storage, dict):
        trace_storage = storage.get("trace")
        if isinstance(trace_storage, dict):
            if "backend" in trace_storage:
                facts["storage_backend"] = trace_storage.get("backend")
            block = trace_storage.get("block")
            if isinstance(block, dict):
                if "version" in block:
                    facts["block_version"] = block.get("version")
                if "dedicated_columns" in block and isinstance(block["dedicated_columns"], list):
                    cols: List[Dict[str, Any]] = []
                    for col in block["dedicated_columns"]:
                        if isinstance(col, dict):
                            cols.append({
                                k: col[k]
                                for k in ("name", "type", "scope")
                                if k in col
                            })
                    facts["dedicated_columns"] = cols

    # 6. Tempo 3.0 architecture indicators (live_store / block_builder / ingest)
    for v3_key in ("live_store", "block_builder", "ingest", "backend_scheduler", "backend_worker"):
        if v3_key in raw_config and raw_config[v3_key]:
            facts.setdefault("v3_components_configured", []).append(v3_key)

    return facts


def compute_unified_diff(
    before_obj: Optional[Dict[str, Any]],
    after_obj: Dict[str, Any],
    fromfile: str = "current",
    tofile: str = "desired",
) -> str:
    """Compute a deterministic unified YAML diff between two objects after redaction."""
    before_clean = sanitize_k8s_manifest(before_obj) if before_obj else {}
    after_clean = sanitize_k8s_manifest(after_obj)

    before_lines = (
        yaml.safe_dump(before_clean, sort_keys=True).splitlines(keepends=True)
        if before_clean
        else []
    )
    after_lines = yaml.safe_dump(after_clean, sort_keys=True).splitlines(keepends=True)

    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=fromfile,
        tofile=tofile,
    )
    return "".join(diff)
