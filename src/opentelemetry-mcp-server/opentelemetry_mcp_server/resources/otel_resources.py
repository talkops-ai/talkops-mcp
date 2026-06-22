"""Collector, enrichment, logs, spanmetrics, and static resources.

Exposes OTel Collector state and pipeline profiles as MCP resources
with the ``otel://`` URI scheme.
"""

import json
from pathlib import Path
from typing import Any, Dict

from opentelemetry_mcp_server.resources.base import BaseResource


class CollectorResources(BaseResource):
    """Resources for OpenTelemetryCollector CRDs."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://collector/{namespace}/{name}",
            name="OTel Collector Configuration",
            description=(
                "Full configuration and status of an OpenTelemetryCollector CRD. "
                "Returns pipeline topology, receivers, processors, exporters, "
                "deployment mode, and runtime status."
            ),
            mime_type="application/json",
        )
        async def get_collector_resource(
            namespace: str, name: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, name)
            cfg = collector_config_service.parse_collector_config(raw)
            instance = collector_config_service.build_collector_instance(
                raw, cfg, detail_level="full"
            )
            return instance.model_dump_json(indent=2)


class EnrichmentResources(BaseResource):
    """Resources for k8sattributes enrichment profiles."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://k8s-enrichment/{namespace}/{collector}",
            name="K8s Enrichment Profile",
            description=(
                "k8sattributes processor profile showing extracted metadata, "
                "labels, annotations, pod association, and pipeline positions."
            ),
            mime_type="application/json",
        )
        async def get_enrichment_resource(
            namespace: str, collector: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, collector)
            cfg = collector_config_service.parse_collector_config(raw)
            profile = collector_config_service.extract_k8s_enrichment(
                cfg, collector, namespace
            )
            return profile.model_dump_json(indent=2)


class LogsResources(BaseResource):
    """Resources for logs collection profiles."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://logs-profile/{namespace}/{collector}",
            name="Logs Collection Profile",
            description=(
                "Filelog receiver configuration, safety analysis, and "
                "pipeline wiring for log collection."
            ),
            mime_type="application/json",
        )
        async def get_logs_resource(
            namespace: str, collector: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, collector)
            cfg = collector_config_service.parse_collector_config(raw)
            profile = collector_config_service.extract_logs_profile(
                cfg, collector, namespace
            )
            return profile.model_dump_json(indent=2)


class SpanMetricsResources(BaseResource):
    """Resources for SpanMetrics connector profiles."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://spanmetrics/{namespace}/{collector}",
            name="SpanMetrics Connector Profile",
            description=(
                "SpanMetrics connector configuration showing dimensions, "
                "histogram config, pipeline wiring, and cardinality estimates."
            ),
            mime_type="application/json",
        )
        async def get_spanmetrics_resource(
            namespace: str, collector: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, collector)
            cfg = collector_config_service.parse_collector_config(raw)
            profile = collector_config_service.extract_spanmetrics_profile(
                cfg, collector, namespace
            )
            return profile.model_dump_json(indent=2)


class InstrumentationResources(BaseResource):
    """Resources for Instrumentation CRDs."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "otel://instrumentation/{namespace}/{name}",
            name="Instrumentation CRD",
            description=(
                "Instrumentation CRD details: exporter endpoint, propagators, "
                "sampler config, per-language specs, and resource attributes."
            ),
            mime_type="application/json",
        )
        async def get_instrumentation_resource(
            namespace: str, name: str
        ) -> str:
            raw = await kubernetes_service.get_instrumentation(namespace, name)
            spec = raw.get("spec", {})
            metadata = raw.get("metadata", {})

            result = {
                "name": metadata.get("name"),
                "namespace": metadata.get("namespace"),
                "exporter": spec.get("exporter", {}),
                "propagators": spec.get("propagators", []),
                "sampler": spec.get("sampler", {}),
                "resource": spec.get("resource", {}),
                "env": spec.get("env", []),
                "languages": {},
                "labels": metadata.get("labels", {}),
                "annotations": metadata.get("annotations", {}),
            }

            # Extract per-language configs
            for lang in ["java", "python", "nodejs", "dotnet", "go", "apache-httpd", "nginx"]:
                if lang in spec:
                    result["languages"][lang] = spec[lang]

            return json.dumps(result, indent=2)


class TargetAllocatorResources(BaseResource):
    """Resources for Target Allocator state."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "otel://target-allocator/{namespace}/{name}",
            name="Target Allocator State",
            description=(
                "Target Allocator configuration and state: allocation strategy, "
                "ServiceMonitor/PodMonitor selectors, and health."
            ),
            mime_type="application/json",
        )
        async def get_target_allocator_resource(
            namespace: str, name: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, name)
            spec = raw.get("spec", {})
            ta_spec = spec.get("targetAllocator", {})

            result = {
                "name": name,
                "namespace": namespace,
                "enabled": ta_spec.get("enabled", False),
                "allocation_strategy": ta_spec.get(
                    "allocationStrategy", "consistent-hashing"
                ),
                "filter_strategy": ta_spec.get("filterStrategy"),
                "replicas": ta_spec.get("replicas", 1),
                "image": ta_spec.get("image"),
                "service_monitor_selector": ta_spec.get(
                    "serviceMonitorSelector", {}
                ),
                "pod_monitor_selector": ta_spec.get("podMonitorSelector", {}),
                "prometheus_cr_enabled": ta_spec.get("prometheusCR", {}).get(
                    "enabled", False
                ),
            }

            return json.dumps(result, indent=2)


class LanguageResources(BaseResource):
    """Resources for language instrumentation capabilities."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "otel://lang/{language}",
            name="Language Instrumentation Capabilities",
            description=(
                "Per-language OTel instrumentation support matrix: "
                "signal support, auto-instrumentation availability, "
                "framework support, and SDK package info."
            ),
            mime_type="application/json",
        )
        async def get_language_resource(language: str) -> str:
            import os

            override = os.getenv("OTEL_LANG_REGISTRY_PATH")
            if override:
                path = Path(override)
            else:
                path = (
                    Path(__file__).parent.parent
                    / "static"
                    / "otel_lang_registry.json"
                )

            try:
                registry = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                return json.dumps({"error": "Language registry not found"})

            lang_data = registry.get("languages", {}).get(language.lower())
            if not lang_data:
                return json.dumps({
                    "error": f"Language '{language}' not found",
                    "available": list(registry.get("languages", {}).keys()),
                })

            return json.dumps(lang_data, indent=2)

        @mcp_instance.resource(
            "otel://registry/languages",
            name="Language Support Catalog",
            description=(
                "Full catalog of all supported languages with "
                "signal stability, auto-instrumentation availability, "
                "and framework support matrices."
            ),
            mime_type="application/json",
        )
        async def get_language_registry_resource() -> str:
            import os

            override = os.getenv("OTEL_LANG_REGISTRY_PATH")
            if override:
                path = Path(override)
            else:
                path = (
                    Path(__file__).parent.parent
                    / "static"
                    / "otel_lang_registry.json"
                )

            try:
                return path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return json.dumps({"error": "Language registry not found"})


class StaticResources(BaseResource):
    """System health and static resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "otel://system/health",
            name="System Health",
            description=(
                "Server health status including Kubernetes connectivity, "
                "OTel CRD availability, and server version."
            ),
            mime_type="application/json",
        )
        async def get_system_health() -> str:
            k8s_health = await kubernetes_service.health_check()

            result = {
                "server": {
                    "name": "opentelemetry-mcp-server",
                    "status": "healthy",
                },
                "kubernetes": k8s_health,
            }

            return json.dumps(result, indent=2)


class OperatorDiagnosticsResources(BaseResource):
    """Resources for OTel Operator health and diagnostics."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "otel://operator/diagnostics",
            name="OTel Operator Diagnostics",
            description=(
                "OTel Operator health diagnostics: pod status, recent errors "
                "from operator logs, webhook health, and per-namespace "
                "Instrumentation CRD counts (to detect the common "
                "'multiple Instrumentation instances' problem)."
            ),
            mime_type="application/json",
        )
        async def get_operator_diagnostics() -> str:
            diag = await kubernetes_service.get_operator_diagnostics()
            return json.dumps(diag, indent=2)

