"""Live OpenTelemetry cluster and pipeline resources.

Exposes live, redacted OpenTelemetry Collector state, pipeline profiles,
Instrumentation CRDs, Target Allocator state, Operator diagnostics, and
server capabilities as MCP resources under the ``otel://`` URI scheme.
"""

import json
from typing import Any, Dict, List

from opentelemetry_mcp_server.resources.base import BaseResource
from opentelemetry_mcp_server.utils.gitops import detect_gitops_ownership
from opentelemetry_mcp_server.utils.redaction import (
    redact_collector_config,
    redact_log_text,
    sanitize_k8s_manifest,
)
from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml


class SystemCapabilitiesResources(BaseResource):
    """Server capabilities, kubeconfig contexts, and Operator status resources."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service
        config = self.config

        @mcp_instance.resource(
            "otel://server/capabilities",
            name="Server Capabilities & Connectivity",
            description=(
                "Server execution mode (write_enabled, read_only, toolsets), "
                "bound kubeconfig context, Kubernetes API connectivity, and "
                "default Collector version."
            ),
            mime_type="application/json",
        )
        async def get_server_capabilities() -> str:
            k8s_health = await kubernetes_service.health_check()
            result = {
                "name": config.name,
                "allow_write": config.allow_write,
                "write_enabled": config.write_enabled,
                "read_only": config.read_only,
                "toolsets": config.toolsets,
                "collector_version_default": config.collector_version_default,
                "server": {
                    "name": config.name,
                    "write_enabled": config.write_enabled,
                    "allow_write": config.allow_write,
                    "read_only": config.read_only,
                    "toolsets": config.toolsets,
                    "collector_version_default": config.collector_version_default,
                },
                "kubernetes": k8s_health,
            }
            return json.dumps(result, indent=2)

        @mcp_instance.resource(
            "otel://cluster/contexts",
            name="Available Kubeconfig Contexts",
            description=(
                "Available Kubernetes contexts from kubeconfig and which context "
                "this MCP server instance is bound to."
            ),
            mime_type="application/json",
        )
        async def get_cluster_contexts() -> str:
            contexts = await kubernetes_service.list_available_contexts()
            current = next(
                (c["name"] for c in contexts if c.get("is_current")),
                config.kubernetes.context_name or "default",
            )
            return json.dumps(
                {
                    "contexts": contexts,
                    "count": len(contexts),
                    "current": current,
                },
                indent=2,
            )

        @mcp_instance.resource(
            "otel://operator/status",
            name="OpenTelemetry Operator Status",
            description=(
                "OpenTelemetry Operator pod health, mutating webhook diagnostics, "
                "recent redacted error logs, and per-namespace Instrumentation CR counts."
            ),
            mime_type="application/json",
        )
        async def get_operator_status() -> str:
            diag = await kubernetes_service.get_operator_diagnostics()
            return json.dumps(diag, indent=2)


class CollectorResources(BaseResource):
    """Resources for OpenTelemetryCollector CRDs, configs, and snapshot history."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://collectors/{namespace}",
            name="List Collectors in Namespace",
            description=(
                "Summary list of OpenTelemetryCollector CRDs in a namespace "
                "(use namespace='all' for cluster-wide listing)."
            ),
            mime_type="application/json",
        )
        async def list_collectors_resource(namespace: str) -> str:
            target_ns = None if namespace == "all" else namespace
            raw = await kubernetes_service.list_otel_collectors(
                namespace=target_ns
            )
            items = raw.get("items", [])
            collectors: List[Dict[str, Any]] = []
            for item in items:
                meta = item.get("metadata", {}) or {}
                try:
                    cfg = collector_config_service.parse_collector_config(item)
                    inst = collector_config_service.build_collector_instance(
                        item, cfg, detail_level="summary"
                    )
                    c_dict = inst.model_dump(exclude={"raw_config_yaml"})
                    c_dict["gitops"] = detect_gitops_ownership(meta)
                    collectors.append(c_dict)
                except Exception as e:
                    collectors.append({
                        "name": meta.get("name", "unknown"),
                        "namespace": meta.get("namespace", "default"),
                        "error": f"Failed to parse config: {e}",
                    })
            return json.dumps(
                {
                    "namespace": namespace,
                    "count": len(collectors),
                    "items": collectors,
                },
                indent=2,
            )

        @mcp_instance.resource(
            "otel://collector/{namespace}/{name}",
            name="OTel Collector Summary & Topology",
            description=(
                "Configuration summary, pipeline topology, deployment mode, "
                "GitOps ownership, and runtime status of an OpenTelemetryCollector CRD."
            ),
            mime_type="application/json",
        )
        async def get_collector_resource(namespace: str, name: str) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, name)
            cfg = collector_config_service.parse_collector_config(raw)
            instance = collector_config_service.build_collector_instance(
                raw, cfg, detail_level="full"
            )
            data = instance.model_dump()
            data["gitops"] = detect_gitops_ownership(raw.get("metadata"))
            return json.dumps(data, indent=2)

        @mcp_instance.resource(
            "otel://collector/{namespace}/{name}/config",
            name="Redacted OTel Collector YAML Config",
            description=(
                "Redacted YAML configuration of an OpenTelemetryCollector CRD "
                "(inline secrets masked with ***REDACTED***)."
            ),
            mime_type="application/yaml",
        )
        async def get_collector_config_resource(
            namespace: str, name: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, name)
            cfg = collector_config_service.parse_collector_config(raw)
            redacted = redact_collector_config(cfg)
            return config_to_yaml(redacted)

        @mcp_instance.resource(
            "otel://collector/{namespace}/{name}/history",
            name="Collector Config Snapshot History",
            description=(
                "Metadata and redacted preview of the pre-mutation config snapshot "
                "stored in otel.mcp/last-known-good."
            ),
            mime_type="application/json",
        )
        async def get_collector_history_resource(
            namespace: str, name: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(namespace, name)
            annotations = (raw.get("metadata", {}) or {}).get(
                "annotations", {}
            ) or {}
            snapshot_b64 = annotations.get("otel.mcp/last-known-good")
            last_mutation = annotations.get("otel.mcp/last-mutation")
            if not snapshot_b64:
                return json.dumps(
                    {
                        "collector": f"{namespace}/{name}",
                        "has_snapshot": False,
                        "last_mutation": None,
                        "snapshot_preview": None,
                    },
                    indent=2,
                )
            try:
                decompressed = kubernetes_service._decompress_config(
                    snapshot_b64
                )
                preview = redact_log_text(decompressed[:1000])
            except Exception as e:
                preview = f"<failed to decode snapshot: {e}>"
            return json.dumps(
                {
                    "collector": f"{namespace}/{name}",
                    "has_snapshot": True,
                    "last_mutation": last_mutation,
                    "snapshot_preview": preview,
                },
                indent=2,
            )


class EnrichmentResources(BaseResource):
    """Resources for k8sattributes enrichment profiles."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://k8s-enrichment/{namespace}/{collector}",
            name="K8s Enrichment Profile",
            description=(
                "k8sattributes processor profile showing extracted metadata, "
                "labels, annotations, node filtering, pod association, and pipeline positions."
            ),
            mime_type="application/json",
        )
        async def get_enrichment_resource(
            namespace: str, collector: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(
                namespace, collector
            )
            cfg = collector_config_service.parse_collector_config(raw)
            profile = collector_config_service.extract_k8s_enrichment(
                cfg, collector, namespace
            )
            return profile.model_dump_json(indent=2)


class LogsResources(BaseResource):
    """Resources for logs collection profiles."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://logs-profile/{namespace}/{collector}",
            name="Logs Collection Profile",
            description=(
                "Filelog receiver configuration, checkpoint storage, self-exclusion, "
                "and pipeline wiring for log collection."
            ),
            mime_type="application/json",
        )
        async def get_logs_resource(namespace: str, collector: str) -> str:
            raw = await kubernetes_service.get_otel_collector(
                namespace, collector
            )
            cfg = collector_config_service.parse_collector_config(raw)
            profile = collector_config_service.extract_logs_profile(
                cfg, collector, namespace
            )
            return profile.model_dump_json(indent=2)


class SpanMetricsResources(BaseResource):
    """Resources for SpanMetrics connector profiles."""

    def register(self, mcp_instance: Any) -> None:
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
            raw = await kubernetes_service.get_otel_collector(
                namespace, collector
            )
            cfg = collector_config_service.parse_collector_config(raw)
            profile = collector_config_service.extract_spanmetrics_profile(
                cfg, collector, namespace
            )
            return profile.model_dump_json(indent=2)


class SamplingResources(BaseResource):
    """Resources for head and tail sampling profiles."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.resource(
            "otel://sampling/{namespace}/{collector}",
            name="Sampling Configuration Profile",
            description=(
                "Combined head sampling (Instrumentation CRD) and tail sampling "
                "(collector tail_sampling processor) configuration and conflict warnings."
            ),
            mime_type="application/json",
        )
        async def get_sampling_resource(
            namespace: str, collector: str
        ) -> str:
            raw = await kubernetes_service.get_otel_collector(
                namespace, collector
            )
            cfg = collector_config_service.parse_collector_config(raw)
            instr_cr = None
            try:
                instrs = await kubernetes_service.list_instrumentations(
                    namespace=namespace
                )
                items = instrs.get("items", [])
                if items:
                    instr_cr = items[0]
            except Exception:
                instr_cr = None

            profile = collector_config_service.extract_sampling_config(
                cfg, collector, namespace, instr_cr
            )
            return profile.model_dump_json(indent=2)


class InstrumentationResources(BaseResource):
    """Resources for Instrumentation CRDs."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "otel://instrumentations/{namespace}",
            name="List Instrumentation CRDs in Namespace",
            description=(
                "Summary list of Instrumentation CRDs in a namespace "
                "(use namespace='all' for cluster-wide listing)."
            ),
            mime_type="application/json",
        )
        async def list_instrumentations_resource(namespace: str) -> str:
            target_ns = None if namespace == "all" else namespace
            raw = await kubernetes_service.list_instrumentations(
                namespace=target_ns
            )
            items = []
            for item in raw.get("items", []):
                meta = item.get("metadata", {}) or {}
                spec = sanitize_k8s_manifest(item.get("spec", {}) or {})
                langs = [
                    lang
                    for lang in ("java", "python", "nodejs", "dotnet", "go")
                    if lang in spec
                ]
                items.append({
                    "name": meta.get("name"),
                    "namespace": meta.get("namespace"),
                    "exporter": spec.get("exporter", {}),
                    "propagators": spec.get("propagators", []),
                    "sampler": spec.get("sampler", {}),
                    "languages_configured": langs,
                    "gitops": detect_gitops_ownership(meta),
                })
            return json.dumps(
                {
                    "namespace": namespace,
                    "count": len(items),
                    "items": items,
                },
                indent=2,
            )

        @mcp_instance.resource(
            "otel://instrumentation/{namespace}/{name}",
            name="Instrumentation CRD",
            description=(
                "Redacted Instrumentation CRD details: exporter endpoint, propagators, "
                "sampler config, per-language specs, and resource attributes."
            ),
            mime_type="application/json",
        )
        async def get_instrumentation_resource(
            namespace: str, name: str
        ) -> str:
            raw = await kubernetes_service.get_instrumentation(
                namespace, name
            )
            sanitized = sanitize_k8s_manifest(raw)
            spec = sanitized.get("spec", {}) or {}
            metadata = sanitized.get("metadata", {}) or {}

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
                "gitops": detect_gitops_ownership(raw.get("metadata")),
            }

            for lang in [
                "java",
                "python",
                "nodejs",
                "dotnet",
                "go",
                "apache-httpd",
                "nginx",
            ]:
                if lang in spec:
                    result["languages"][lang] = spec[lang]

            return json.dumps(result, indent=2)


class TargetAllocatorResources(BaseResource):
    """Resources for Target Allocator state."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service

        @mcp_instance.resource(
            "otel://target-allocator/{namespace}/{name}",
            name="Target Allocator State",
            description=(
                "Target Allocator configuration and state: allocation strategy, "
                "ServiceMonitor/PodMonitor selectors, CRD API version, and Prometheus CR status."
            ),
            mime_type="application/json",
        )
        async def get_target_allocator_resource(
            namespace: str, name: str
        ) -> str:
            ta_spec: Dict[str, Any] = {}
            collector_mode: Any = None
            collector_replicas: Any = None
            standalone_cr: Any = None

            collector_api_version: str = "opentelemetry.io/v1beta1"
            try:
                raw = await kubernetes_service.get_otel_collector(namespace, name)
                collector_api_version = str(
                    raw.get("apiVersion", "opentelemetry.io/v1beta1")
                )
                spec = raw.get("spec", {}) or {}
                ta_spec = dict(spec.get("targetAllocator", {}) or {})
                collector_mode = spec.get("mode", "deployment")
                collector_replicas = spec.get("replicas", 1)
            except Exception:
                pass

            for cand_name in (name, f"{name}-targetallocator", f"{name}-ta"):
                try:
                    standalone_cr = await kubernetes_service.get_target_allocator(
                        namespace, cand_name
                    )
                    if standalone_cr:
                        if not ta_spec:
                            ta_spec = dict(standalone_cr.get("spec", {}) or {})
                        break
                except Exception:
                    continue

            ta_pods: List[Dict[str, Any]] = []
            monitoring_rbac: Dict[str, Any] = {
                "api_group": "monitoring.coreos.com",
                "cluster_roles": [],
                "resources": [],
                "verbs": [],
            }
            try:
                ns_pods = await kubernetes_service.list_pods(namespace=namespace)
                ta_pods = [
                    {
                        "name": p.get("name"),
                        "phase": p.get("phase"),
                        "ready": p.get("ready"),
                    }
                    for p in ns_pods
                    if "targetallocator" in str(p.get("name", "")).lower()
                    and str(p.get("name", "")).startswith(name)
                ]
            except Exception:
                ta_pods = []
            try:
                roles = await kubernetes_service.list_otel_cluster_roles(
                    namespace=namespace
                )
                r_names = set()
                r_res = set()
                r_verbs = set()
                for role in roles:
                    rname = str(role.get("name", ""))
                    if name not in rname and (role.get("labels") or {}).get("talkops.ai/collector") != name:
                        continue
                    for rule in role.get("rules", []) or []:
                        if "monitoring.coreos.com" in (
                            rule.get("api_groups") or rule.get("apiGroups") or []
                        ):
                            r_names.add(rname)
                            r_res.update(rule.get("resources", []) or [])
                            r_verbs.update(rule.get("verbs", []) or [])
                monitoring_rbac = {
                    "api_group": "monitoring.coreos.com",
                    "cluster_roles": sorted(r_names),
                    "resources": sorted(r_res),
                    "verbs": sorted(r_verbs),
                }
            except Exception:
                pass

            prom_cr = ta_spec.get("prometheusCR", {}) or {}
            result = {
                "name": name,
                "namespace": namespace,
                "enabled": bool(ta_spec.get("enabled", bool(standalone_cr))),
                "collector_crd_api_version": collector_api_version,
                "crd_api_version": (
                    standalone_cr.get("apiVersion", "opentelemetry.io/v1alpha1")
                    if isinstance(standalone_cr, dict)
                    else collector_api_version
                ),
                "standalone_target_allocator_cr": (
                    (standalone_cr.get("metadata", {}) or {}).get("name")
                    if isinstance(standalone_cr, dict)
                    else None
                ),
                "collector_mode": collector_mode,
                "collector_replicas": collector_replicas,
                "allocation_strategy": ta_spec.get(
                    "allocationStrategy", "consistent-hashing"
                ),
                "filter_strategy": ta_spec.get("filterStrategy"),
                "replicas": ta_spec.get("replicas", 1),
                "image": ta_spec.get("image"),
                "service_monitor_selector": prom_cr.get(
                    "serviceMonitorSelector",
                    ta_spec.get("serviceMonitorSelector", {}),
                ),
                "pod_monitor_selector": prom_cr.get(
                    "podMonitorSelector",
                    ta_spec.get("podMonitorSelector", {}),
                ),
                "prometheus_cr_enabled": bool(prom_cr.get("enabled", False)),
                "target_allocator_pods": ta_pods,
                "monitoring_coreos_rbac": monitoring_rbac,
            }

            return json.dumps(result, indent=2)
