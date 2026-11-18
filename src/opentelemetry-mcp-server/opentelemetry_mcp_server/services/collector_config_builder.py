"""Collector config builder — intent-driven config generation.

Constructs production-grade OTel Collector configs from high-level
intents (signals, role, exporter targets, receivers, connectors) instead
of requiring users to hand-write YAML.

Enforces production invariants:
1. Single source of truth for exporter keys and pipeline references (no B1 mismatch)
2. memory_limiter first in every pipeline processor chain
3. DaemonSet k8sattributes scoped via filter.node_from_env_var: K8S_NODE_NAME (B6)
4. Modern service.telemetry.metrics.readers pull Prometheus on 0.0.0.0:8888 (B5)
5. Exporter sending_queue + retry_on_failure enabled by default
6. Strict TLS verification on HTTPS endpoints unless explicitly overridden (S1)
"""

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService

logger = logging.getLogger(__name__)

# Service name patterns → (signal, exporter_type, default_port, protocol)
_BACKEND_PATTERNS: List[Tuple[str, str, str, int, str]] = [
    # Traces backends
    ("jaeger", "traces", "otlp", 4317, "grpc"),
    ("tempo", "traces", "otlp", 4317, "grpc"),
    ("zipkin", "traces", "zipkin", 9411, "http"),
    # Metrics backends
    ("prometheus", "metrics", "prometheusremotewrite", 9090, "http"),
    ("thanos", "metrics", "otlphttp", 9090, "http"),
    ("mimir", "metrics", "otlphttp", 9009, "http"),
    ("victoriametrics", "metrics", "otlphttp", 8428, "http"),
    # Logs backends
    ("opensearch", "logs", "opensearch", 9200, "http"),
    ("elasticsearch", "logs", "elasticsearch", 9200, "http"),
    ("loki", "logs", "otlphttp/loki", 3100, "http"),
]

_EXPORTER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "loki": {
        "path_suffix": "/loki/api/v1/push",
    },
    "otlphttp": {
        "path_suffix": "/api/v1/otlp",
    },
    "otlphttp/loki": {
        "path_suffix": "/otlp",
    },
    "prometheusremotewrite": {
        "path_suffix": "/api/v1/write",
    },
}

_PROCESSOR_ORDER = [
    "memory_limiter",
    "k8sattributes",
    "resourcedetection",
    "resource",
    "batch",
]


class CollectorConfigBuilder:
    """Builds OTel Collector configs from high-level intent."""

    def __init__(self, kubernetes_service: KubernetesService) -> None:
        self._k8s = kubernetes_service

    def build_config(
        self,
        signals: List[str],
        exporter_targets: Dict[str, str],
        namespace: str = "",
        enable_spanmetrics: bool = False,
        enable_filelog: bool = False,
        prometheus_scrape: bool = False,
        collector_name: str = "",
        exporter_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        *,
        mode: str = "deployment",
        role: str = "all-in-one",
        enable_servicegraph: bool = False,
        extra_receivers: Optional[List[str]] = None,
        infrastructure_receivers: Optional[List[str]] = None,
        persistent_queue: bool = False,
        use_prometheus_otlp: bool = False,
    ) -> Dict[str, Any]:
        """Build a complete, valid OTel Collector config dict."""
        config: Dict[str, Any] = {}
        combined_recs = list(extra_receivers or []) + list(infrastructure_receivers or [])
        extra_recs = [r.lower().strip() for r in combined_recs]
        if "filelog" in extra_recs:
            enable_filelog = True
        if "prometheus_ta" in extra_recs or "prometheus" in extra_recs:
            prometheus_scrape = True

        need_file_storage = enable_filelog or persistent_queue

        # Extensions
        config["extensions"] = self._build_extensions(need_file_storage)

        # Receivers
        config["receivers"] = self._build_receivers(
            signals,
            enable_filelog,
            prometheus_scrape,
            namespace,
            collector_name,
            extra_receivers=extra_recs,
            mode=mode,
        )

        # Processors (best-practice chain, always correct order)
        config["processors"] = self._build_processors(mode=mode, role=role)

        # Exporters
        config["exporters"] = self._build_exporters(
            exporter_targets,
            exporter_overrides,
            persistent_queue=persistent_queue,
            use_prometheus_otlp=use_prometheus_otlp,
        )

        # Connectors (spanmetrics and/or servicegraph if requested)
        connectors = self._build_connectors(
            enable_spanmetrics=enable_spanmetrics,
            enable_servicegraph=enable_servicegraph,
        )
        if connectors:
            config["connectors"] = connectors

        # Service (wire everything together)
        config["service"] = self._build_service(
            signals=signals,
            exporter_targets=exporter_targets,
            enable_spanmetrics=enable_spanmetrics,
            enable_filelog=enable_filelog,
            prometheus_scrape=prometheus_scrape,
            enable_servicegraph=enable_servicegraph,
            extra_receivers=extra_recs,
            need_file_storage=need_file_storage,
            use_prometheus_otlp=use_prometheus_otlp,
            role=role,
        )

        return config

    # ──────────────────────────────────────────────
    # Auto-discovery engine
    # ──────────────────────────────────────────────

    async def discover_exporter_targets(
        self,
        namespace: str,
        signals: List[str],
        scan_namespaces: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """Auto-discover where to send telemetry."""
        targets: Dict[str, str] = {}
        discovery_meta: Dict[str, Any] = {
            "scanned_namespaces": [],
            "existing_collectors": [],
            "discovered_services": [],
            "fallbacks_used": [],
        }

        namespaces_to_scan = [namespace]
        if scan_namespaces:
            for ns in scan_namespaces:
                if ns not in namespaces_to_scan:
                    namespaces_to_scan.append(ns)
        else:
            well_known = [
                "monitoring",
                "observability",
                "opentelemetry",
                "opentelemetry-operator-system",
                "loki",
                "tempo",
                "prometheus",
            ]
            for ns in well_known:
                if ns != namespace and ns not in namespaces_to_scan:
                    namespaces_to_scan.append(ns)

        discovery_meta["scanned_namespaces"] = namespaces_to_scan

        targets = await self._discover_from_collectors(
            namespaces_to_scan, signals, targets, discovery_meta
        )
        targets = await self._discover_from_services(
            namespaces_to_scan, signals, targets, discovery_meta
        )

        for signal in signals:
            if signal not in targets:
                targets[signal] = "__debug__"
                discovery_meta["fallbacks_used"].append({
                    "signal": signal,
                    "reason": f"No backend found for '{signal}' in scanned namespaces",
                    "action": "Using 'debug' exporter — telemetry will be logged to stdout",
                })

        return targets, discovery_meta

    async def _discover_from_collectors(
        self,
        namespaces: List[str],
        signals: List[str],
        targets: Dict[str, str],
        meta: Dict[str, Any],
    ) -> Dict[str, str]:
        """Discover targets by parsing existing collectors' exporters."""
        for ns in namespaces:
            try:
                raw = await self._k8s.list_otel_collectors(namespace=ns)
                for item in raw.get("items", []):
                    coll_name = item.get("metadata", {}).get("name", "unknown")
                    coll_ns = item.get("metadata", {}).get("namespace", ns)
                    meta["existing_collectors"].append(f"{coll_ns}/{coll_name}")

                    spec = item.get("spec", {})
                    config = spec.get("config", {})
                    if isinstance(config, str):
                        continue

                    exporters = config.get("exporters", {})
                    service = config.get("service", {})
                    pipelines = service.get("pipelines", {})

                    for pipeline_name, pipeline_cfg in pipelines.items():
                        if not isinstance(pipeline_cfg, dict):
                            continue
                        pipeline_signal = None
                        for s in ["traces", "metrics", "logs"]:
                            if s in pipeline_name:
                                pipeline_signal = s
                                break
                        if not pipeline_signal or pipeline_signal in targets:
                            continue
                        if pipeline_signal not in signals:
                            continue

                        for exp_name in pipeline_cfg.get("exporters", []):
                            if exp_name in ("debug", "logging", "nop"):
                                continue
                            if "spanmetrics" in exp_name or "servicegraph" in exp_name:
                                continue
                            exp_cfg = exporters.get(exp_name, {})
                            endpoint = self._extract_endpoint(exp_name, exp_cfg)
                            if endpoint:
                                targets[pipeline_signal] = endpoint
                                meta["discovered_services"].append({
                                    "signal": pipeline_signal,
                                    "source": f"collector:{coll_ns}/{coll_name}",
                                    "exporter": exp_name,
                                    "endpoint": endpoint,
                                })
                                break
            except Exception:
                continue

        return targets

    async def _discover_from_services(
        self,
        namespaces: List[str],
        signals: List[str],
        targets: Dict[str, str],
        meta: Dict[str, Any],
    ) -> Dict[str, str]:
        """Discover targets by scanning K8s services for known backends."""
        for ns in namespaces:
            try:
                services = await self._k8s.list_services(namespace=ns)
                candidates: Dict[str, List[Dict[str, Any]]] = {s: [] for s in signals}

                for svc in services:
                    svc_name = svc["name"].lower()
                    svc_ports = svc.get("ports", [])
                    port_nums = [p["port"] for p in svc_ports]

                    for pattern, signal, exp_type, default_port, protocol in _BACKEND_PATTERNS:
                        if signal in targets or signal not in signals:
                            continue

                        if pattern in svc_name:
                            score = 0
                            port = None

                            if svc_name == pattern:
                                score += 50

                            if default_port in port_nums:
                                score += 30
                                port = default_port
                            elif svc_ports:
                                otlp_port = None
                                hint_port = None
                                for p in svc_ports:
                                    pname = (p.get("name") or "").lower()
                                    if any(
                                        h in pname
                                        for h in [
                                            "otlp-grpc",
                                            "otlp-http",
                                            "otlp",
                                            "grpc-otlp",
                                            "http-otlp",
                                        ]
                                    ):
                                        otlp_port = p["port"]
                                        break
                                    if hint_port is None and any(
                                        h in pname for h in [protocol, signal[:5]]
                                    ):
                                        hint_port = p["port"]

                                if otlp_port is not None:
                                    score += 20
                                    port = otlp_port
                                elif hint_port is not None:
                                    score += 10
                                    port = hint_port
                                else:
                                    port = svc_ports[0]["port"]

                            if port is not None:
                                candidates[signal].append({
                                    "score": score,
                                    "port": port,
                                    "svc_name": svc["name"],
                                    "ns": ns,
                                    "exp_type": exp_type,
                                })

                for signal in signals:
                    if signal in targets or not candidates[signal]:
                        continue

                    best = sorted(
                        candidates[signal], key=lambda x: x["score"], reverse=True
                    )[0]

                    scheme = "http"
                    dns_name = f"{best['svc_name']}.{best['ns']}"
                    if best["exp_type"] == "otlp":
                        endpoint = f"{dns_name}:{best['port']}"
                    else:
                        endpoint = f"{scheme}://{dns_name}:{best['port']}"

                    targets[signal] = endpoint
                    meta["discovered_services"].append({
                        "signal": signal,
                        "source": f"service:{best['ns']}/{best['svc_name']}",
                        "exporter_type": best["exp_type"],
                        "endpoint": endpoint,
                    })

            except Exception:
                continue

        return targets

    @staticmethod
    def _extract_endpoint(
        exporter_name: str, exporter_cfg: Dict[str, Any]
    ) -> Optional[str]:
        """Extract endpoint URL from an exporter config."""
        if isinstance(exporter_cfg, dict):
            endpoint = exporter_cfg.get("endpoint")
            if endpoint:
                return str(endpoint)
            for proto in ("http", "grpc"):
                nested = exporter_cfg.get(proto, {})
                if isinstance(nested, dict):
                    ep = nested.get("endpoint")
                    if ep:
                        return str(ep)
        return None

    async def discover_cluster_size(self) -> Tuple[str, int]:
        """Auto-detect cluster size from node count."""
        try:
            node_count = await self._k8s.count_nodes()
        except Exception:
            return "medium", 0

        if node_count <= 5:
            return "small", node_count
        elif node_count <= 50:
            return "medium", node_count
        else:
            return "large", node_count

    @staticmethod
    def recommend_mode(
        signals: List[str],
        enable_filelog: bool = False,
        prometheus_scrape: bool = False,
        role: str = "all-in-one",
        extra_receivers: Optional[List[str]] = None,
    ) -> Tuple[str, str]:
        """Recommend deployment mode with rationale."""
        extra_recs = [r.lower().strip() for r in (extra_receivers or [])]
        role_lower = role.lower().strip()
        if role_lower == "agent":
            return (
                "daemonset",
                "DaemonSet selected: 'agent' role collects node-local telemetry",
            )
        if role_lower == "tail-sampler":
            return (
                "statefulset",
                "StatefulSet selected: 'tail-sampler' role requires stable pod identities behind a headless Service for traceID hash routing",
            )
        if role_lower == "gateway":
            return (
                "deployment",
                "Deployment selected: 'gateway' role runs as a stateless, horizontally scalable tier",
            )
        if enable_filelog or any(r in extra_recs for r in ("filelog", "kubeletstats", "hostmetrics")):
            return (
                "daemonset",
                "DaemonSet selected: node-local receivers (filelog/kubeletstats/hostmetrics) require per-node scheduling",
            )
        if prometheus_scrape or "prometheus_ta" in extra_recs:
            return (
                "statefulset",
                "StatefulSet selected: Prometheus scraping with Target Allocator needs stable collector identities for balanced target distribution",
            )
        if "logs" in signals and not enable_filelog:
            return (
                "deployment",
                "Deployment selected: OTLP log receiver doesn't require node-level access",
            )
        return (
            "deployment",
            "Deployment selected: traces/metrics collection via OTLP receivers doesn't require node-level access",
        )

    @staticmethod
    def recommend_resources(cluster_size: str) -> Dict[str, Any]:
        """Recommend K8s resource requests/limits."""
        sizing = {
            "small": {
                "requests": {"cpu": "100m", "memory": "256Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
            "medium": {
                "requests": {"cpu": "250m", "memory": "512Mi"},
                "limits": {"cpu": "1", "memory": "1Gi"},
            },
            "large": {
                "requests": {"cpu": "500m", "memory": "1Gi"},
                "limits": {"cpu": "2", "memory": "2Gi"},
            },
        }
        return sizing.get(cluster_size, sizing["medium"])

    @staticmethod
    def recommend_gomemlimit(cluster_size: str) -> str:
        """Recommend GOMEMLIMIT (~80% of container memory limit)."""
        limits = {
            "small": "400MiB",
            "medium": "800MiB",
            "large": "1600MiB",
        }
        return limits.get(cluster_size, "800MiB")

    # ──────────────────────────────────────────────
    # Config section builders
    # ──────────────────────────────────────────────

    @staticmethod
    def _build_extensions(enable_file_storage: bool = False) -> Dict[str, Any]:
        """Build extensions config (health_check always included)."""
        exts: Dict[str, Any] = {
            "health_check": {
                "endpoint": "0.0.0.0:13133",
            },
        }
        if enable_file_storage:
            exts["file_storage"] = {
                "directory": "/var/lib/otelcol/file_storage",
            }
        return exts

    @staticmethod
    def _build_filelog_receiver(
        namespace: str = "",
        collector_name: str = "",
    ) -> Dict[str, Any]:
        """Build filelog receiver config with self-exclusion and file_storage checkpointing."""
        exclude_pattern = (
            f"/var/log/pods/{namespace}_{collector_name}*/*/*.log"
            if namespace and collector_name
            else "/var/log/pods/*/*otel-collector*/*.log"
        )
        return {
            "include": [
                f"/var/log/pods/{namespace}_*/*/*.log"
                if namespace
                else "/var/log/pods/*/*/*.log"
            ],
            "exclude": [exclude_pattern],
            "include_file_name": False,
            "include_file_path": True,
            "operators": [
                {"id": "container-parser", "type": "container"},
            ],
            "start_at": "end",
            "storage": "file_storage",
        }

    @staticmethod
    def _build_prometheus_receiver() -> Dict[str, Any]:
        """Build minimal Prometheus receiver config for Target Allocator dynamic injection."""
        return {
            "config": {
                "scrape_configs": [
                    {
                        "job_name": "otel-collector-self",
                        "scrape_interval": "30s",
                        "static_configs": [
                            {"targets": ["0.0.0.0:8888"]},
                        ],
                    },
                ],
            },
        }

    @staticmethod
    def _build_kubeletstats_receiver() -> Dict[str, Any]:
        """Build node-local kubeletstats receiver config."""
        return {
            "collection_interval": "20s",
            "auth_type": "serviceAccount",
            "endpoint": "https://${env:K8S_NODE_NAME}:10250",
            "metric_groups": ["node", "pod", "container"],
        }

    @staticmethod
    def _build_hostmetrics_receiver() -> Dict[str, Any]:
        """Build node-local hostmetrics receiver config."""
        return {
            "collection_interval": "30s",
            "root_path": "/hostfs",
            "scrapers": {
                "cpu": {},
                "disk": {},
                "filesystem": {},
                "load": {},
                "memory": {},
                "network": {},
            },
        }

    @staticmethod
    def _build_k8s_cluster_receiver() -> Dict[str, Any]:
        """Build cluster-scoped k8s_cluster receiver config."""
        return {
            "collection_interval": "30s",
            "node_conditions_to_report": ["Ready", "MemoryPressure", "DiskPressure"],
            "allocatable_types_to_report": ["cpu", "memory"],
        }

    @staticmethod
    def _build_k8sobjects_receiver() -> Dict[str, Any]:
        """Build cluster-scoped k8sobjects events watch receiver config."""
        return {
            "objects": [
                {"name": "events", "mode": "watch"},
            ],
        }

    @staticmethod
    def _build_receivers(
        signals: List[str],
        enable_filelog: bool,
        prometheus_scrape: bool,
        namespace: str,
        collector_name: str,
        *,
        extra_receivers: Optional[List[str]] = None,
        mode: str = "deployment",
    ) -> Dict[str, Any]:
        """Build receivers config based on signals and options."""
        receivers: Dict[str, Any] = {
            "otlp": {
                "protocols": {
                    "grpc": {"endpoint": "0.0.0.0:4317"},
                    "http": {"endpoint": "0.0.0.0:4318"},
                },
            }
        }
        extra_recs = set(r.lower().strip() for r in (extra_receivers or []))

        if enable_filelog or "filelog" in extra_recs:
            receivers["filelog"] = CollectorConfigBuilder._build_filelog_receiver(
                namespace, collector_name
            )

        if prometheus_scrape or "prometheus_ta" in extra_recs or "prometheus" in extra_recs:
            receivers["prometheus"] = CollectorConfigBuilder._build_prometheus_receiver()

        if "kubeletstats" in extra_recs:
            receivers["kubeletstats"] = CollectorConfigBuilder._build_kubeletstats_receiver()

        if "hostmetrics" in extra_recs:
            receivers["hostmetrics"] = CollectorConfigBuilder._build_hostmetrics_receiver()

        if "k8s_cluster" in extra_recs:
            receivers["k8s_cluster"] = CollectorConfigBuilder._build_k8s_cluster_receiver()

        if "k8s_events" in extra_recs or "k8sobjects" in extra_recs:
            receivers["k8sobjects"] = CollectorConfigBuilder._build_k8sobjects_receiver()

        return receivers

    @staticmethod
    def _build_processors(
        mode: str = "deployment",
        role: str = "all-in-one",
    ) -> Dict[str, Any]:
        """Build processors with best-practice ordering enforced.

        DaemonSet collectors automatically receive `filter.node_from_env_var: K8S_NODE_NAME`
        on `k8sattributes` to prevent cluster-wide pod watch bloat (B6).
        """
        k8s_attr: Dict[str, Any] = {
            "extract": {
                "metadata": [
                    "k8s.namespace.name",
                    "k8s.pod.name",
                    "k8s.pod.uid",
                    "k8s.deployment.name",
                    "k8s.statefulset.name",
                    "k8s.daemonset.name",
                    "k8s.replicaset.name",
                    "k8s.node.name",
                    "k8s.container.name",
                    "container.image.name",
                    "container.image.tag",
                ],
            },
            "passthrough": False,
            "pod_association": [
                {
                    "sources": [
                        {"from": "resource_attribute", "name": "k8s.pod.ip"},
                    ],
                },
                {
                    "sources": [
                        {"from": "resource_attribute", "name": "k8s.pod.uid"},
                    ],
                },
                {
                    "sources": [
                        {"from": "connection"},
                    ],
                },
            ],
        }
        if mode.lower().strip() == "daemonset":
            k8s_attr["filter"] = {
                "node_from_env_var": "K8S_NODE_NAME",
            }

        processors: Dict[str, Any] = {
            "memory_limiter": {
                "check_interval": "5s",
                "limit_percentage": 80,
                "spike_limit_percentage": 25,
            },
            "k8sattributes": k8s_attr,
            "resourcedetection": {
                "detectors": ["env", "system"],
            },
            "resource": {
                "attributes": [
                    {
                        "action": "insert",
                        "from_attribute": "k8s.pod.uid",
                        "key": "service.instance.id",
                    },
                ],
            },
            "batch": {},
        }

        if role.lower().strip() == "tail-sampler":
            processors["tail_sampling"] = {
                "decision_wait": "10s",
                "num_traces": 50000,
                "expected_new_traces_per_sec": 1000,
                "policies": [
                    {
                        "name": "errors-policy",
                        "type": "status_code",
                        "status_code": {"status_codes": ["ERROR"]},
                    },
                    {
                        "name": "latency-policy",
                        "type": "latency",
                        "latency": {"threshold_ms": 1000},
                    },
                    {
                        "name": "probabilistic-baseline",
                        "type": "probabilistic",
                        "probabilistic": {"sampling_percentage": 10.0},
                    },
                ],
            }

        return processors

    @staticmethod
    def _apply_path_suffix(endpoint: str, exporter_type: str) -> str:
        """Append the well-known API path suffix for an exporter type."""
        defaults = _EXPORTER_DEFAULTS.get(exporter_type, {})
        path_suffix = defaults.get("path_suffix", "")
        if path_suffix and not endpoint.endswith(path_suffix):
            endpoint = f"{endpoint.rstrip('/')}{path_suffix}"
        return endpoint

    @staticmethod
    def _merge_overrides(
        config: Dict[str, Any],
        exporter_type: str,
        overrides: Optional[Dict[str, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Deep-merge user-provided overrides into an exporter config."""
        if not overrides:
            return config

        # Support matching either exact key ('otlphttp/loki') or base key ('loki')
        matched_keys = [exporter_type]
        if exporter_type == "otlphttp/loki" and "loki" in overrides and "otlphttp/loki" not in overrides:
            matched_keys.append("loki")

        for mkey in matched_keys:
            if mkey not in overrides:
                continue
            user_cfg = deepcopy(overrides[mkey])
            for key, value in user_cfg.items():
                if (
                    key in config
                    and isinstance(config[key], dict)
                    and isinstance(value, dict)
                ):
                    config[key].update(value)
                else:
                    config[key] = value
        return config

    @staticmethod
    def _default_resiliency(persistent_queue: bool = False) -> Dict[str, Any]:
        """Return default sending_queue and retry_on_failure config."""
        sq: Dict[str, Any] = {
            "enabled": True,
            "num_consumers": 10,
            "queue_size": 1000,
        }
        if persistent_queue:
            sq["storage"] = "file_storage"
        return {
            "sending_queue": sq,
            "retry_on_failure": {
                "enabled": True,
                "initial_interval": "5s",
                "max_interval": "30s",
                "max_elapsed_time": "300s",
            },
        }

    @staticmethod
    def _classify_exporter(
        signal: str,
        endpoint: str,
        use_prometheus_otlp: bool = False,
    ) -> Tuple[str, str]:
        """Single source of truth mapping (signal, endpoint) -> (exporter_name, exporter_type).

        Fixes B1 so that `_build_exporters` and `_resolve_exporter_names` are
        guaranteed to use identical exporter keys.
        """
        endpoint_lower = endpoint.lower()

        if "prometheus" in endpoint_lower or "9090" in endpoint_lower:
            if use_prometheus_otlp or "/api/v1/otlp" in endpoint_lower:
                return f"otlphttp/{signal}", "otlphttp"
            return f"prometheusremotewrite/{signal}", "prometheusremotewrite"
        if any(p in endpoint_lower for p in ("thanos", "mimir", "victoriametrics", "/api/v1/otlp")):
            return f"otlphttp/{signal}", "otlphttp"
        if any(p in endpoint_lower for p in ("opensearch", "9200")):
            return "opensearch", "opensearch"
        if any(p in endpoint_lower for p in ("loki", "3100")):
            return "otlphttp/loki", "otlphttp/loki"
        if any(p in endpoint_lower for p in ("elasticsearch", "elastic")):
            return "elasticsearch", "elasticsearch"
        return f"otlp/{signal}", "otlp"

    @staticmethod
    def _build_tls_config(scheme_or_endpoint: str) -> Dict[str, Any]:
        """Build secure TLS config (fixes S1: never set insecure_skip_verify=True by default)."""
        lower = scheme_or_endpoint.lower()
        if lower.startswith("https://") or ":443" in lower:
            return {"insecure": False}
        return {"insecure": True}

    @staticmethod
    def _ensure_http_scheme(endpoint: str) -> str:
        """Ensure HTTP/HTTPS scheme prefix on an HTTP exporter endpoint."""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        if ":443" in endpoint or endpoint.endswith("443"):
            return f"https://{endpoint}"
        return f"http://{endpoint}"

    @staticmethod
    def _build_exporters(
        exporter_targets: Dict[str, str],
        exporter_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        *,
        persistent_queue: bool = False,
        use_prometheus_otlp: bool = False,
    ) -> Dict[str, Any]:
        """Build exporters from discovered targets with resiliency and strict TLS."""
        exporters: Dict[str, Any] = {}
        used_debug = False
        resiliency = CollectorConfigBuilder._default_resiliency(persistent_queue)

        for signal, endpoint in exporter_targets.items():
            if endpoint == "__debug__":
                if not used_debug:
                    exporters["debug"] = {"verbosity": "basic"}
                    used_debug = True
                continue

            exp_name, exp_type = CollectorConfigBuilder._classify_exporter(
                signal, endpoint, use_prometheus_otlp=use_prometheus_otlp
            )

            if exp_type == "prometheusremotewrite":
                scheme_endpoint = CollectorConfigBuilder._ensure_http_scheme(endpoint)
                scheme_endpoint = CollectorConfigBuilder._apply_path_suffix(
                    scheme_endpoint, exp_type
                )
                exp_config: Dict[str, Any] = {
                    "endpoint": scheme_endpoint,
                    "tls": CollectorConfigBuilder._build_tls_config(scheme_endpoint),
                    "remote_write_queue": {
                        "enabled": True,
                        "queue_size": 1000,
                        "num_consumers": 4,
                    },
                    "retry_on_failure": deepcopy(resiliency["retry_on_failure"]),
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, exp_type, exporter_overrides
                )
            elif exp_type in ("otlphttp", "otlphttp/loki"):
                scheme_endpoint = CollectorConfigBuilder._ensure_http_scheme(endpoint)
                scheme_endpoint = CollectorConfigBuilder._apply_path_suffix(
                    scheme_endpoint, exp_type
                )
                exp_config = {
                    "endpoint": scheme_endpoint,
                    "tls": CollectorConfigBuilder._build_tls_config(scheme_endpoint),
                    **deepcopy(resiliency),
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, exp_type, exporter_overrides
                )
            elif exp_type == "opensearch":
                scheme_endpoint = CollectorConfigBuilder._ensure_http_scheme(endpoint)
                exp_config = {
                    "http": {
                        "endpoint": scheme_endpoint,
                        "tls": CollectorConfigBuilder._build_tls_config(scheme_endpoint),
                    },
                    "logs_index": "otel-logs",
                    **deepcopy(resiliency),
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "opensearch", exporter_overrides
                )
            elif exp_type == "elasticsearch":
                scheme_endpoint = CollectorConfigBuilder._ensure_http_scheme(endpoint)
                exp_config = {
                    "endpoints": [scheme_endpoint],
                    "tls": CollectorConfigBuilder._build_tls_config(scheme_endpoint),
                    "logs_index": "otel-logs",
                    **deepcopy(resiliency),
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "elasticsearch", exporter_overrides
                )
            else:
                exp_config = {
                    "endpoint": endpoint,
                    "tls": CollectorConfigBuilder._build_tls_config(endpoint),
                    **deepcopy(resiliency),
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "otlp", exporter_overrides
                )

        return exporters

    @staticmethod
    def _build_connectors(
        enable_spanmetrics: bool,
        enable_servicegraph: bool = False,
    ) -> Dict[str, Any]:
        """Build connectors (spanmetrics and/or servicegraph if requested)."""
        connectors: Dict[str, Any] = {}
        if enable_spanmetrics:
            connectors["spanmetrics"] = {
                "dimensions": [
                    {"name": "http.method"},
                    {"name": "http.status_code"},
                    {"name": "rpc.method"},
                    {"name": "rpc.service"},
                ],
                "histogram": {
                    "explicit": {
                        "buckets": [
                            "2ms", "4ms", "6ms", "8ms", "10ms",
                            "50ms", "100ms", "200ms", "400ms", "800ms",
                            "1s", "1400ms", "2s", "5s", "10s", "15s",
                        ],
                    },
                },
            }
        if enable_servicegraph:
            connectors["servicegraph"] = {
                "latency_histogram_buckets": [
                    "2ms", "10ms", "50ms", "100ms", "250ms", "500ms", "1s", "2.5s", "5s", "10s"
                ],
                "dimensions": ["http.method", "http.status_code"],
                "store": {
                    "ttl": "2s",
                    "max_items": 1000,
                },
            }
        return connectors

    def _build_service(
        self,
        signals: List[str],
        exporter_targets: Dict[str, str],
        enable_spanmetrics: bool,
        enable_filelog: bool,
        prometheus_scrape: bool,
        *,
        enable_servicegraph: bool = False,
        extra_receivers: Optional[List[str]] = None,
        need_file_storage: bool = False,
        use_prometheus_otlp: bool = False,
        role: str = "all-in-one",
    ) -> Dict[str, Any]:
        """Build service section wiring pipelines and internal telemetry readers together."""
        service_extensions = ["health_check"]
        if enable_filelog or need_file_storage:
            service_extensions.append("file_storage")

        service: Dict[str, Any] = {
            "extensions": service_extensions,
            "telemetry": {
                "metrics": {
                    "level": "normal",
                    "readers": [
                        {
                            "pull": {
                                "exporter": {
                                    "prometheus": {
                                        "host": "0.0.0.0",
                                        "port": 8888,
                                    }
                                }
                            }
                        }
                    ],
                }
            },
            "pipelines": {},
        }

        extra_recs = set(r.lower().strip() for r in (extra_receivers or []))
        base_chain = list(_PROCESSOR_ORDER)

        for signal in signals:
            pipeline_name = signal
            receivers = ["otlp"]
            if signal == "logs":
                if enable_filelog or "filelog" in extra_recs:
                    receivers.append("filelog")
                if "k8s_events" in extra_recs or "k8sobjects" in extra_recs:
                    receivers.append("k8sobjects")
            if signal == "metrics":
                if prometheus_scrape or "prometheus_ta" in extra_recs or "prometheus" in extra_recs:
                    receivers.append("prometheus")
                if "kubeletstats" in extra_recs:
                    receivers.append("kubeletstats")
                if "hostmetrics" in extra_recs:
                    receivers.append("hostmetrics")
                if "k8s_cluster" in extra_recs:
                    receivers.append("k8s_cluster")
                if enable_spanmetrics:
                    receivers.append("spanmetrics")
                if enable_servicegraph:
                    receivers.append("servicegraph")

            target = exporter_targets.get(signal, "__debug__")
            if target == "__debug__":
                pipeline_exporters = ["debug"]
            else:
                pipeline_exporters = self._resolve_exporter_names(
                    signal, target, use_prometheus_otlp=use_prometheus_otlp
                )

            processor_chain = list(base_chain)
            if signal == "traces" and role.lower().strip() == "tail-sampler":
                # Insert tail_sampling right before batch
                if "batch" in processor_chain:
                    idx = processor_chain.index("batch")
                    processor_chain.insert(idx, "tail_sampling")
                else:
                    processor_chain.append("tail_sampling")

            service["pipelines"][pipeline_name] = {
                "receivers": receivers,
                "processors": processor_chain,
                "exporters": pipeline_exporters,
            }

        # Wire traces -> spanmetrics / servicegraph connectors
        if "traces" in signals:
            traces_pipeline = service["pipelines"].get("traces", {})
            traces_exporters = traces_pipeline.get("exporters", [])
            if enable_spanmetrics and "spanmetrics" not in traces_exporters:
                traces_exporters.append("spanmetrics")
            if enable_servicegraph and "servicegraph" not in traces_exporters:
                traces_exporters.append("servicegraph")
            traces_pipeline["exporters"] = traces_exporters

        return service

    @staticmethod
    def _resolve_exporter_names(
        signal: str,
        endpoint: str,
        *,
        use_prometheus_otlp: bool = False,
    ) -> List[str]:
        """Resolve which exporter name to use for a signal+endpoint (matches _build_exporters)."""
        exp_name, _ = CollectorConfigBuilder._classify_exporter(
            signal, endpoint, use_prometheus_otlp=use_prometheus_otlp
        )
        return [exp_name]
