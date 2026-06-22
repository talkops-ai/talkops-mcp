"""Collector configuration parsing and analysis service.

Pure logic layer for parsing OpenTelemetry Collector YAML configurations
and extracting structured profiles. No Kubernetes API calls — this service
operates entirely on parsed config dictionaries.
"""

import logging
from typing import Any, Dict, List, Optional

from opentelemetry_mcp_server.exceptions import OtelConfigParseError
from opentelemetry_mcp_server.models.collector import (
    CollectorInstance,
    CollectorStatus,
    ExporterRef,
    PipelineSpec,
    ProcessorRef,
    ReceiverRef,
)
from opentelemetry_mcp_server.models.common import SamplingMode
from opentelemetry_mcp_server.models.enrichment import K8sEnrichmentProfile
from opentelemetry_mcp_server.models.logs import FilelogReceiverConfig, LogsCollectionProfile
from opentelemetry_mcp_server.models.sampling import SamplingConfig, TailSamplingPolicy
from opentelemetry_mcp_server.models.spanmetrics import (
    HistogramBucketConfig,
    SpanMetricsProfile,
)
from opentelemetry_mcp_server.utils.yaml_helpers import (
    extract_connectors,
    extract_exporters,
    extract_pipelines,
    extract_processors,
    extract_receivers,
    find_connectors_of_type,
    find_processors_of_type,
    find_receivers_of_type,
    get_component_type,
    get_pipeline_signal,
    safe_load_yaml,
)

logger = logging.getLogger(__name__)


class CollectorConfigService:
    """Service for parsing and analyzing OTel Collector configurations.

    This service is stateless and pure — all methods take config dicts
    as input and return Pydantic models as output. No side effects.
    """

    def parse_collector_config(
        self, otel_cr: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract and parse the YAML config from an OTel Collector CRD.

        Handles both ``spec.config`` (inline YAML string) and
        ``spec.configMap`` (ConfigMap reference) patterns.

        Args:
            otel_cr: Raw OpenTelemetryCollector CRD dict from K8s API.

        Returns:
            Parsed config dictionary.

        Raises:
            OtelConfigParseError: If config is missing or malformed.
        """
        spec = otel_cr.get("spec", {})
        raw_config = spec.get("config")

        if not raw_config:
            raise OtelConfigParseError(
                "No config found in OpenTelemetryCollector CRD spec"
            )

        if isinstance(raw_config, str):
            return safe_load_yaml(raw_config)
        if isinstance(raw_config, dict):
            return raw_config

        raise OtelConfigParseError(
            f"Unexpected config type: {type(raw_config).__name__}"
        )

    def build_collector_instance(
        self,
        otel_cr: Dict[str, Any],
        cfg: Dict[str, Any],
        detail_level: str = "summary",
    ) -> CollectorInstance:
        """Build a CollectorInstance model from a CRD and its parsed config.

        Args:
            otel_cr: Raw CRD dict.
            cfg: Parsed config dict.
            detail_level: 'summary' or 'full'.

        Returns:
            Populated CollectorInstance model.
        """
        metadata = otel_cr.get("metadata", {})
        spec = otel_cr.get("spec", {})
        status_raw = otel_cr.get("status", {})

        name = metadata.get("name", "unknown")
        namespace = metadata.get("namespace", "default")
        mode = spec.get("mode", "deployment")

        # Extract version: prefer status.version, fall back to spec.image tag
        version = status_raw.get("version")
        if not version:
            image = spec.get("image", "")
            version = image.split(":")[-1] if ":" in image else None

        # Extract OTel distribution from status.image
        status_image = status_raw.get("image", "")
        otel_distribution = status_image.split(":")[0] if status_image else None

        # Build pipelines
        pipelines = self.extract_pipelines(cfg)

        # Feature detection
        spanmetrics_enabled = bool(find_connectors_of_type(cfg, "spanmetrics"))
        ta_enabled = bool(spec.get("targetAllocator", {}).get("enabled", False))
        sampling_mode = self.detect_sampling_mode(cfg, None)

        # Status
        status = CollectorStatus(
            replicas=status_raw.get("replicas", spec.get("replicas", 1)),
            ready_replicas=status_raw.get("readyReplicas", 0),
            phase=status_raw.get("phase", "Unknown"),
            message=status_raw.get("message"),
        )

        # Summary line
        signal_types = list({p.signal for p in pipelines})
        summary = (
            f"{mode} collector in {namespace}/{name} with "
            f"{len(pipelines)} pipeline(s) ({', '.join(signal_types)})"
        )

        from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

        return CollectorInstance(
            name=name,
            namespace=namespace,
            mode=mode,
            version=version,
            otel_distribution=otel_distribution,
            pipelines=pipelines,
            spanmetrics_enabled=spanmetrics_enabled,
            target_allocator_enabled=ta_enabled,
            sampling_mode=sampling_mode,
            status=status,
            summary=summary,
            raw_config_yaml=(
                config_to_yaml(cfg) if detail_level == "full" else None
            ),
            labels=metadata.get("labels", {}),
            annotations=metadata.get("annotations", {}),
        )

    def extract_pipelines(self, cfg: Dict[str, Any]) -> List[PipelineSpec]:
        """Extract all pipelines from a collector config.

        Args:
            cfg: Parsed collector config.

        Returns:
            List of PipelineSpec models.
        """
        raw_pipelines = extract_pipelines(cfg)
        result: List[PipelineSpec] = []

        for pipeline_name, pipeline_cfg in raw_pipelines.items():
            if not isinstance(pipeline_cfg, dict):
                continue

            signal = get_pipeline_signal(pipeline_name)
            receivers = [
                ReceiverRef(
                    name=r,
                    type=get_component_type(r),
                )
                for r in (pipeline_cfg.get("receivers") or [])
            ]
            processors = [
                ProcessorRef(
                    name=p,
                    type=get_component_type(p),
                )
                for p in (pipeline_cfg.get("processors") or [])
            ]
            exporters = [
                ExporterRef(
                    name=e,
                    type=get_component_type(e),
                )
                for e in (pipeline_cfg.get("exporters") or [])
            ]

            result.append(
                PipelineSpec(
                    name=pipeline_name,
                    signal=signal,
                    receivers=receivers,
                    processors=processors,
                    exporters=exporters,
                )
            )

        return result

    def extract_k8s_enrichment(
        self,
        cfg: Dict[str, Any],
        collector_name: str,
        collector_namespace: str,
    ) -> K8sEnrichmentProfile:
        """Extract k8sattributes processor profile from config.

        Args:
            cfg: Parsed collector config.
            collector_name: Parent collector name.
            collector_namespace: Parent collector namespace.

        Returns:
            K8sEnrichmentProfile model.
        """
        k8s_processors = find_processors_of_type(cfg, "k8sattributes")

        if not k8s_processors:
            return K8sEnrichmentProfile(
                collector_name=collector_name,
                collector_namespace=collector_namespace,
                enabled=False,
            )

        processors_cfg = extract_processors(cfg)
        # Use the first k8sattributes processor
        proc_name = k8s_processors[0]
        proc_cfg = processors_cfg.get(proc_name, {}) or {}

        extract_section = proc_cfg.get("extract", {}) or {}
        filter_section = proc_cfg.get("filter", {}) or {}

        extract_metadata = extract_section.get("metadata", [])
        extract_labels = extract_section.get("labels", [])
        extract_annotations = extract_section.get("annotations", [])

        pod_association = []
        for assoc in proc_cfg.get("pod_association", []):
            if isinstance(assoc, dict):
                for source in assoc.get("sources", []):
                    if isinstance(source, dict):
                        pod_association.append(source.get("from", ""))

        # Find pipeline positions
        pipeline_positions = []
        raw_pipelines = extract_pipelines(cfg)
        for pname, pcfg in raw_pipelines.items():
            if isinstance(pcfg, dict):
                proc_list = pcfg.get("processors") or []
                if proc_name in proc_list:
                    idx = proc_list.index(proc_name)
                    pipeline_positions.append(f"{pname}[{idx}]")

        return K8sEnrichmentProfile(
            collector_name=collector_name,
            collector_namespace=collector_namespace,
            enabled=True,
            extract_metadata=extract_metadata,
            extract_labels=extract_labels,
            extract_annotations=extract_annotations,
            filter_namespace=filter_section.get("namespace"),
            filter_node=filter_section.get("node_from_env_var") or filter_section.get("node"),
            pod_association=pod_association,
            pipeline_positions=pipeline_positions,
        )

    def extract_logs_profile(
        self,
        cfg: Dict[str, Any],
        collector_name: str,
        collector_namespace: str,
    ) -> LogsCollectionProfile:
        """Extract logs collection profile from config.

        Args:
            cfg: Parsed collector config.
            collector_name: Parent collector name.
            collector_namespace: Parent collector namespace.

        Returns:
            LogsCollectionProfile model.
        """
        filelog_names = find_receivers_of_type(cfg, "filelog")
        receivers_cfg = extract_receivers(cfg)
        raw_pipelines = extract_pipelines(cfg)

        if not filelog_names:
            # Check if any logs pipeline exists
            has_logs = any(
                get_pipeline_signal(pn) == "logs" for pn in raw_pipelines
            )
            return LogsCollectionProfile(
                collector_name=collector_name,
                collector_namespace=collector_namespace,
                enabled=has_logs,
            )

        filelog_configs: List[FilelogReceiverConfig] = []
        warnings: List[str] = []
        has_storage = False
        has_exclude_self = False
        has_resource_detection = False

        for fname in filelog_names:
            fcfg = receivers_cfg.get(fname, {}) or {}
            include = fcfg.get("include", [])
            exclude = fcfg.get("exclude", [])
            storage = fcfg.get("storage")

            if storage:
                has_storage = True

            # Check for self-exclusion
            if any("/var/log/otel" in p or "collector" in p for p in exclude):
                has_exclude_self = True

            filelog_configs.append(
                FilelogReceiverConfig(
                    include_paths=include,
                    exclude_paths=exclude,
                    include_file_name=fcfg.get("include_file_name", True),
                    include_file_path=fcfg.get("include_file_path", False),
                    multiline_config=fcfg.get("multiline"),
                    operators=fcfg.get("operators", []),
                    storage=storage,
                )
            )

        if not has_storage:
            warnings.append(
                "No storage checkpoint configured for filelog receiver. "
                "Data may be lost on collector restart."
            )
        if not has_exclude_self:
            warnings.append(
                "Collector's own logs are not excluded from filelog collection. "
                "Risk of feedback loop."
            )

        # Check for resource detection in logs pipelines
        for pn, pcfg in raw_pipelines.items():
            if get_pipeline_signal(pn) == "logs" and isinstance(pcfg, dict):
                for proc in pcfg.get("processors", []):
                    if get_component_type(proc) == "resourcedetection":
                        has_resource_detection = True

        # Collect logs pipeline processors and exporters
        log_processors: List[str] = []
        log_exporters: List[str] = []
        for pn, pcfg in raw_pipelines.items():
            if get_pipeline_signal(pn) == "logs" and isinstance(pcfg, dict):
                log_processors.extend(pcfg.get("processors") or [])
                log_exporters.extend(pcfg.get("exporters") or [])

        return LogsCollectionProfile(
            collector_name=collector_name,
            collector_namespace=collector_namespace,
            enabled=True,
            filelog_receivers=filelog_configs,
            has_storage_checkpoint=has_storage,
            has_exclude_self=has_exclude_self,
            has_resource_detection=has_resource_detection,
            log_processors=list(dict.fromkeys(log_processors)),
            log_exporters=list(dict.fromkeys(log_exporters)),
            warnings=warnings,
        )

    def extract_spanmetrics_profile(
        self,
        cfg: Dict[str, Any],
        collector_name: str,
        collector_namespace: str,
    ) -> SpanMetricsProfile:
        """Extract SpanMetrics connector profile from config.

        Args:
            cfg: Parsed collector config.
            collector_name: Parent collector name.
            collector_namespace: Parent collector namespace.

        Returns:
            SpanMetricsProfile model.
        """
        sm_names = find_connectors_of_type(cfg, "spanmetrics")

        if not sm_names:
            return SpanMetricsProfile(
                collector_name=collector_name,
                collector_namespace=collector_namespace,
                enabled=False,
            )

        connectors_cfg = extract_connectors(cfg)
        sm_name = sm_names[0]
        sm_cfg = connectors_cfg.get(sm_name, {}) or {}

        # Dimensions
        dimensions = sm_cfg.get("dimensions", [])
        exclude_dimensions = sm_cfg.get("exclude_dimensions", [])

        # Histogram
        hist_cfg = sm_cfg.get("histogram", {}) or {}
        histogram = HistogramBucketConfig(
            type=hist_cfg.get("type", "explicit"),
            explicit_buckets=hist_cfg.get("explicit", {}).get("buckets"),
            max_size=hist_cfg.get("exponential", {}).get("max_size"),
        )

        # Pipeline wiring
        raw_pipelines = extract_pipelines(cfg)
        source_pipeline = None
        target_pipeline = None
        for pn, pcfg in raw_pipelines.items():
            if isinstance(pcfg, dict):
                # SpanMetrics acts as both exporter (from traces) and receiver (to metrics)
                if sm_name in (pcfg.get("exporters") or []):
                    source_pipeline = pn
                if sm_name in (pcfg.get("receivers") or []):
                    target_pipeline = pn

        # Cardinality estimation
        estimated_series = None
        warnings: List[str] = []
        if dimensions:
            # Rough estimate: each dimension can multiply series count
            estimated_series = 100 * max(1, len(dimensions))
            if len(dimensions) > 5:
                warnings.append(
                    f"High dimension count ({len(dimensions)}) may cause "
                    "cardinality explosion in span metrics"
                )

        return SpanMetricsProfile(
            collector_name=collector_name,
            collector_namespace=collector_namespace,
            enabled=True,
            dimensions=dimensions,
            exclude_dimensions=exclude_dimensions,
            histogram=histogram,
            namespace=sm_cfg.get("namespace"),
            metrics_flush_interval=sm_cfg.get("metrics_flush_interval"),
            source_pipeline=source_pipeline,
            target_pipeline=target_pipeline,
            estimated_series_per_service=estimated_series,
            warnings=warnings,
        )

    def detect_sampling_mode(
        self,
        cfg: Dict[str, Any],
        instrumentation_cr: Optional[Dict[str, Any]],
    ) -> SamplingMode:
        """Detect the active sampling mode from config and CRDs.

        Args:
            cfg: Parsed collector config.
            instrumentation_cr: Optional Instrumentation CRD dict.

        Returns:
            Detected SamplingMode.
        """
        has_tail = bool(find_processors_of_type(cfg, "tail_sampling"))

        has_head = False
        if instrumentation_cr:
            spec = instrumentation_cr.get("spec", {})
            sampler = spec.get("sampler", {})
            if sampler.get("type"):
                has_head = True

        if has_tail:
            return "tail"
        if has_head:
            return "head"
        return "none"

    def extract_sampling_config(
        self,
        cfg: Dict[str, Any],
        collector_name: str,
        collector_namespace: str,
        instrumentation_cr: Optional[Dict[str, Any]] = None,
    ) -> SamplingConfig:
        """Extract full sampling configuration.

        Args:
            cfg: Parsed collector config.
            collector_name: Collector name.
            collector_namespace: Collector namespace.
            instrumentation_cr: Optional Instrumentation CRD dict.

        Returns:
            SamplingConfig model.
        """
        mode = self.detect_sampling_mode(cfg, instrumentation_cr)
        warnings: List[str] = []

        # Head sampling from Instrumentation CRD
        head_sampler_type = None
        head_sample_rate = None
        head_source = None
        if instrumentation_cr:
            spec = instrumentation_cr.get("spec", {})
            sampler = spec.get("sampler", {})
            head_sampler_type = sampler.get("type")
            arg = sampler.get("argument")
            if arg:
                try:
                    head_sample_rate = float(arg)
                except ValueError:
                    pass
            head_source = instrumentation_cr.get("metadata", {}).get("name")

        # Tail sampling from collector config
        tail_proc_names = find_processors_of_type(cfg, "tail_sampling")
        tail_processor = tail_proc_names[0] if tail_proc_names else None
        tail_policies: List[TailSamplingPolicy] = []
        tail_decision_wait = None
        tail_num_traces = None

        if tail_processor:
            processors_cfg = extract_processors(cfg)
            ts_cfg = processors_cfg.get(tail_processor, {}) or {}
            tail_decision_wait = ts_cfg.get("decision_wait")
            tail_num_traces = ts_cfg.get("num_traces")

            for policy in ts_cfg.get("policies", []):
                if isinstance(policy, dict):
                    tail_policies.append(
                        TailSamplingPolicy(
                            name=policy.get("name", "unnamed"),
                            type=policy.get("type", "unknown"),
                            config={
                                k: v
                                for k, v in policy.items()
                                if k not in ("name", "type")
                            },
                        )
                    )

        # Conflict detection
        if head_sampler_type and tail_processor:
            warnings.append(
                "Both head and tail sampling are configured. "
                "Head sampling at the SDK reduces spans before tail "
                "sampling can make intelligent decisions."
            )

        return SamplingConfig(
            collector_name=collector_name,
            collector_namespace=collector_namespace,
            mode=mode,
            head_sampler_type=head_sampler_type,
            head_sample_rate=head_sample_rate,
            head_source=head_source,
            tail_sampling_processor=tail_processor,
            tail_policies=tail_policies,
            tail_decision_wait=tail_decision_wait,
            tail_num_traces=tail_num_traces,
            warnings=warnings,
        )

    def validate_processor_order(
        self,
        cfg: Dict[str, Any],
        pipeline_name: str,
        expected_order: List[str],
    ) -> Dict[str, Any]:
        """Validate processor ordering in a pipeline.

        Args:
            cfg: Parsed collector config.
            pipeline_name: Pipeline to validate.
            expected_order: Expected processor type order
                (e.g., ['memory_limiter', 'k8sattributes', 'batch']).

        Returns:
            Validation result dict with ``valid``, ``actual_order``,
            ``expected_order``, and ``issues``.
        """
        raw_pipelines = extract_pipelines(cfg)
        pipeline_cfg = raw_pipelines.get(pipeline_name)
        if not pipeline_cfg or not isinstance(pipeline_cfg, dict):
            return {
                "valid": False,
                "pipeline": pipeline_name,
                "issues": [f"Pipeline '{pipeline_name}' not found"],
                "actual_order": [],
                "expected_order": expected_order,
            }

        actual_processors = pipeline_cfg.get("processors") or []
        actual_types = [get_component_type(p) for p in actual_processors]

        # Check ordering
        issues: List[str] = []
        last_idx = -1
        for expected_type in expected_order:
            if expected_type in actual_types:
                idx = actual_types.index(expected_type)
                if idx < last_idx:
                    issues.append(
                        f"'{expected_type}' should appear before "
                        f"'{actual_types[last_idx]}' in the pipeline"
                    )
                last_idx = idx

        return {
            "valid": len(issues) == 0,
            "pipeline": pipeline_name,
            "actual_order": actual_types,
            "expected_order": expected_order,
            "issues": issues,
        }

    def generate_transform_snippet(
        self, attributes_to_drop: List[str]
    ) -> str:
        """Generate a transform processor YAML snippet to drop attributes.

        Args:
            attributes_to_drop: List of attribute names to drop.

        Returns:
            YAML string for the transform processor config.
        """
        if not attributes_to_drop:
            return "# No attributes specified for dropping"

        from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

        config = {
            "processors": {
                "transform/drop_attributes": {
                    "metric_statements": [
                        {
                            "context": "datapoint",
                            "statements": [
                                f'delete_key(attributes, "{attr}")'
                                for attr in attributes_to_drop
                            ],
                        }
                    ]
                }
            }
        }
        return config_to_yaml(config)

    def generate_tail_sampling_patch(
        self, policies: List[Dict[str, Any]]
    ) -> str:
        """Generate tail-sampling processor YAML.

        Args:
            policies: List of policy dicts with 'name', 'type', and config.

        Returns:
            YAML string for the tail_sampling processor config.
        """
        from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

        config = {
            "processors": {
                "tail_sampling": {
                    "decision_wait": "10s",
                    "num_traces": 50000,
                    "policies": policies,
                }
            }
        }
        return config_to_yaml(config)

    def generate_instrumentation_annotation(
        self, language: str
    ) -> Dict[str, str]:
        """Generate the Kubernetes annotation for auto-instrumentation.

        Args:
            language: Language identifier (java, python, nodejs, dotnet, go).

        Returns:
            Dict with annotation key-value pair.
        """
        from opentelemetry_mcp_server.utils.k8s_labels import LANGUAGE_ANNOTATION_KEYS

        key = LANGUAGE_ANNOTATION_KEYS.get(language)
        if not key:
            return {"error": f"Unsupported language: {language}"}
        return {key: "true"}
