"""Safe collector config merge utilities.

Provides deterministic, position-aware merging of partial OTel Collector
config snippets into existing collector configurations. Used by mutation
tools (``otel_toggle_sampling_strategy``, ``otel_enable_spanmetrics_for_service``)
to apply config changes without requiring the caller to do raw YAML manipulation.

Design notes
------------
* **No annotation-based backup** — industry best practice for OTel Operator
  CRDs is GitOps-managed rollback (``git revert`` + ArgoCD/Flux re-deploy).
  The tools enforce a ``dry_run=True`` default to allow human review.
* **Merge, not replace** — all functions perform additive merges.
  Existing config sections are preserved; only the specified component
  and pipeline wiring are added or updated.
* **Position-aware pipeline insertion** — processors are inserted at
  a configurable position relative to other processors (e.g., ``batch``).
"""

import copy
from typing import Any, Dict, List, Optional, Tuple


def _ensure_section(cfg: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Ensure a top-level config section exists and return it."""
    if key not in cfg:
        cfg[key] = {}
    return cfg[key]


def _ensure_pipeline(cfg: Dict[str, Any], pipeline_name: str) -> Dict[str, Any]:
    """Ensure a pipeline exists under ``service.pipelines`` and return it."""
    service = _ensure_section(cfg, "service")
    pipelines = service.setdefault("pipelines", {})
    if pipeline_name not in pipelines:
        pipelines[pipeline_name] = {
            "receivers": [],
            "processors": [],
            "exporters": [],
        }
    return pipelines[pipeline_name]


def merge_processor(
    cfg: Dict[str, Any],
    processor_name: str,
    processor_config: Dict[str, Any],
    pipeline: str,
    *,
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Add a processor to a collector config and wire it into a pipeline.

    Args:
        cfg: Collector config dict (will be deep-copied).
        processor_name: Processor instance name (e.g., ``tail_sampling``).
        processor_config: Processor configuration dict.
        pipeline: Pipeline name to wire into (e.g., ``traces``).
        before: Insert before this processor in the pipeline list.
        after: Insert after this processor in the pipeline list.

    Returns:
        Tuple of (merged_config, changes_log).
    """
    merged = copy.deepcopy(cfg)
    changes: List[str] = []

    # Add processor definition
    processors = _ensure_section(merged, "processors")
    if processor_name in processors:
        processors[processor_name] = processor_config
        changes.append(f"Updated processor '{processor_name}' definition")
    else:
        processors[processor_name] = processor_config
        changes.append(f"Added processor '{processor_name}' definition")

    # Wire into pipeline
    pipe = _ensure_pipeline(merged, pipeline)
    proc_list: List[str] = pipe.get("processors", [])
    if processor_name not in proc_list:
        if before and before in proc_list:
            idx = proc_list.index(before)
            proc_list.insert(idx, processor_name)
            changes.append(
                f"Inserted '{processor_name}' before '{before}' in {pipeline} pipeline"
            )
        elif after and after in proc_list:
            idx = proc_list.index(after) + 1
            proc_list.insert(idx, processor_name)
            changes.append(
                f"Inserted '{processor_name}' after '{after}' in {pipeline} pipeline"
            )
        else:
            # Default: append before 'batch' if exists, else at end
            if "batch" in proc_list:
                idx = proc_list.index("batch")
                proc_list.insert(idx, processor_name)
                changes.append(
                    f"Inserted '{processor_name}' before 'batch' in {pipeline} pipeline"
                )
            else:
                proc_list.append(processor_name)
                changes.append(
                    f"Appended '{processor_name}' to {pipeline} pipeline"
                )
        pipe["processors"] = proc_list
    else:
        changes.append(
            f"Processor '{processor_name}' already in {pipeline} pipeline"
        )

    return merged, changes


def remove_processor(
    cfg: Dict[str, Any],
    processor_name: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Remove a processor from config and all pipelines.

    Args:
        cfg: Collector config dict (will be deep-copied).
        processor_name: Processor instance name to remove.

    Returns:
        Tuple of (merged_config, changes_log).
    """
    merged = copy.deepcopy(cfg)
    changes: List[str] = []

    # Remove definition
    processors = merged.get("processors", {})
    if processor_name in processors:
        del processors[processor_name]
        changes.append(f"Removed processor '{processor_name}' definition")

    # Remove from all pipelines
    pipelines = merged.get("service", {}).get("pipelines", {})
    for pname, pcfg in pipelines.items():
        if isinstance(pcfg, dict):
            proc_list = pcfg.get("processors", [])
            if processor_name in proc_list:
                proc_list.remove(processor_name)
                changes.append(
                    f"Removed '{processor_name}' from {pname} pipeline"
                )

    return merged, changes


def merge_connector(
    cfg: Dict[str, Any],
    connector_name: str,
    connector_config: Dict[str, Any],
    source_pipeline: str,
    target_pipeline: str,
    target_pipeline_exporters: Optional[List[str]] = None,
    target_pipeline_processors: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Add a connector to a collector config and wire the pipeline topology.

    A connector acts as both an exporter in the source pipeline and a
    receiver in the target pipeline. This function:

    1. Adds the connector definition under ``connectors``.
    2. Adds the connector as an exporter in ``source_pipeline``.
    3. Creates ``target_pipeline`` with the connector as receiver.

    Args:
        cfg: Collector config dict (will be deep-copied).
        connector_name: Connector instance name (e.g., ``spanmetrics``).
        connector_config: Connector configuration dict.
        source_pipeline: Pipeline where connector is an exporter (e.g., ``traces``).
        target_pipeline: Pipeline where connector is a receiver (e.g., ``metrics/spanmetrics``).
        target_pipeline_exporters: Exporters for the target pipeline.
        target_pipeline_processors: Processors for the target pipeline (defaults to ``[batch]``).

    Returns:
        Tuple of (merged_config, changes_log).
    """
    merged = copy.deepcopy(cfg)
    changes: List[str] = []

    # Add connector definition
    connectors = _ensure_section(merged, "connectors")
    if connector_name in connectors:
        connectors[connector_name] = connector_config
        changes.append(f"Updated connector '{connector_name}' definition")
    else:
        connectors[connector_name] = connector_config
        changes.append(f"Added connector '{connector_name}' definition")

    # Wire as exporter in source pipeline
    source_pipe = _ensure_pipeline(merged, source_pipeline)
    source_exporters: List[str] = source_pipe.get("exporters", [])
    if connector_name not in source_exporters:
        source_exporters.insert(0, connector_name)
        source_pipe["exporters"] = source_exporters
        changes.append(
            f"Added '{connector_name}' as exporter in {source_pipeline} pipeline"
        )

    # Create/update target pipeline with connector as receiver
    target_pipe = _ensure_pipeline(merged, target_pipeline)
    target_receivers: List[str] = target_pipe.get("receivers", [])
    if connector_name not in target_receivers:
        target_receivers.append(connector_name)
        target_pipe["receivers"] = target_receivers
        changes.append(
            f"Added '{connector_name}' as receiver in {target_pipeline} pipeline"
        )

    if target_pipeline_processors is not None:
        target_pipe["processors"] = target_pipeline_processors
    elif not target_pipe.get("processors"):
        target_pipe["processors"] = ["batch"]
    changes.append(f"Set processors for {target_pipeline} pipeline")

    if target_pipeline_exporters is not None:
        target_pipe["exporters"] = target_pipeline_exporters
        changes.append(
            f"Set exporters for {target_pipeline} pipeline: {target_pipeline_exporters}"
        )
    elif not target_pipe.get("exporters"):
        # Try to inherit the first exporter from the source pipeline
        # (excluding the connector itself)
        other_exporters = [
            e for e in source_exporters if e != connector_name
        ]
        if other_exporters:
            target_pipe["exporters"] = other_exporters[:1]
            changes.append(
                f"Inherited exporter '{other_exporters[0]}' for {target_pipeline} pipeline"
            )

    return merged, changes


def remove_connector(
    cfg: Dict[str, Any],
    connector_name: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Remove a connector from config and all pipeline references.

    Args:
        cfg: Collector config dict (will be deep-copied).
        connector_name: Connector instance name to remove.

    Returns:
        Tuple of (merged_config, changes_log).
    """
    merged = copy.deepcopy(cfg)
    changes: List[str] = []

    # Remove definition
    connectors = merged.get("connectors", {})
    if connector_name in connectors:
        del connectors[connector_name]
        changes.append(f"Removed connector '{connector_name}' definition")

    # Remove from pipeline receivers/exporters and clean up empty target pipelines
    pipelines = merged.get("service", {}).get("pipelines", {})
    pipelines_to_remove: List[str] = []
    for pname, pcfg in pipelines.items():
        if isinstance(pcfg, dict):
            for role in ("receivers", "exporters"):
                items = pcfg.get(role, [])
                if connector_name in items:
                    items.remove(connector_name)
                    changes.append(
                        f"Removed '{connector_name}' from {pname}.{role}"
                    )
            # If pipeline has no receivers left, mark for cleanup
            if not pcfg.get("receivers"):
                pipelines_to_remove.append(pname)

    for pname in pipelines_to_remove:
        del pipelines[pname]
        changes.append(f"Removed empty pipeline '{pname}'")

    return merged, changes
