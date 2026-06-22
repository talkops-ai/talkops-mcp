"""Collector config builder — intent-driven config generation.

Constructs production-grade OTel Collector configs from high-level
intents (signals, exporter targets) instead of requiring users to
hand-write YAML. This is the core intelligence behind
``otel_provision_collector``.

The builder:
1. Auto-discovers backends from existing collectors and K8s services
2. Generates best-practice processor chains with correct ordering
3. Recommends deployment mode from signal requirements
4. Sizes resources from cluster node count
"""

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Well-known backend patterns for auto-discovery
# ──────────────────────────────────────────────

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
    ("loki", "logs", "loki", 3100, "http"),
]

# ──────────────────────────────────────────────
# Well-known exporter defaults
# ──────────────────────────────────────────────
# Maps exporter type → defaults automatically applied during config
# generation. This is the single source of truth for required API
# path suffixes, avoiding hardcoded path logic scattered through
# _build_exporters.
#
# Keys:
#   path_suffix — appended to the endpoint URL if not already present
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

# Best-practice processor ordering (always enforced)
_PROCESSOR_ORDER = [
    "memory_limiter",
    "k8sattributes",
    "resourcedetection",
    "resource",
    "batch",
]


class CollectorConfigBuilder:
    """Builds OTel Collector configs from high-level intent.

    This service takes human-level inputs (what signals to collect,
    which namespace) and generates a complete, production-grade
    collector config with best-practice defaults.
    """

    def __init__(self, kubernetes_service: KubernetesService) -> None:
        self._k8s = kubernetes_service

    # ──────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────

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
    ) -> Dict[str, Any]:
        """Build a complete, valid OTel Collector config dict.

        Args:
            signals: List of signals to collect (traces, metrics, logs).
            exporter_targets: Mapping of signal → backend endpoint URL.
            namespace: Target namespace (used for filelog exclusion).
            enable_spanmetrics: Add spanmetrics connector for RED metrics.
            enable_filelog: Add filelog receiver for container logs.
            prometheus_scrape: Add prometheus receiver for scrape targets.
            collector_name: Collector name (used for filelog self-exclusion).
            exporter_overrides: Per-exporter config overrides (headers,
                TLS, auth). Keys are exporter type names (e.g. 'loki',
                'opensearch'), values are config dicts deep-merged into
                the generated exporter config.

        Returns:
            Complete OTel Collector config dict ready for YAML serialization.
        """
        config: Dict[str, Any] = {}

        # Extensions
        config["extensions"] = self._build_extensions(enable_filelog)

        # Receivers
        config["receivers"] = self._build_receivers(
            signals, enable_filelog, prometheus_scrape, namespace, collector_name
        )

        # Processors (best-practice chain, always correct order)
        config["processors"] = self._build_processors()

        # Exporters
        config["exporters"] = self._build_exporters(
            exporter_targets, exporter_overrides
        )

        # Connectors (spanmetrics if requested)
        connectors = self._build_connectors(enable_spanmetrics)
        if connectors:
            config["connectors"] = connectors

        # Service (wire everything together)
        config["service"] = self._build_service(
            signals, exporter_targets, enable_spanmetrics,
            enable_filelog, prometheus_scrape,
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
        """Auto-discover where to send telemetry.

        Scans existing collectors and K8s services to find backend
        endpoints. Returns both the discovered targets and metadata
        about what was found (for transparency in the output).

        Args:
            namespace: Primary namespace to scan.
            signals: Signals that need exporter targets.
            scan_namespaces: Additional namespaces to scan. If None,
                scans the primary namespace plus well-known ones.

        Returns:
            Tuple of (exporter_targets dict, discovery_metadata dict).
        """
        targets: Dict[str, str] = {}
        discovery_meta: Dict[str, Any] = {
            "scanned_namespaces": [],
            "existing_collectors": [],
            "discovered_services": [],
            "fallbacks_used": [],
        }

        # Determine which namespaces to scan
        namespaces_to_scan = [namespace]
        if scan_namespaces:
            namespaces_to_scan.extend(scan_namespaces)
        else:
            # Add well-known observability namespaces
            well_known = [
                "monitoring", "observability", "opentelemetry",
                "opentelemetry-operator-system", "loki", "tempo",
                "prometheus",
            ]
            for ns in well_known:
                if ns != namespace:
                    namespaces_to_scan.append(ns)

        discovery_meta["scanned_namespaces"] = namespaces_to_scan

        # Strategy 1: Parse existing collectors' exporter configs
        targets = await self._discover_from_collectors(
            namespaces_to_scan, signals, targets, discovery_meta
        )

        # Strategy 2: Scan K8s services for known backend patterns
        targets = await self._discover_from_services(
            namespaces_to_scan, signals, targets, discovery_meta
        )

        # Strategy 3: For any signal still without a target, use debug
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

                    # Parse the config to find exporter endpoints
                    spec = item.get("spec", {})
                    config = spec.get("config", {})
                    if isinstance(config, str):
                        # Config might be a YAML string — skip for now
                        continue

                    exporters = config.get("exporters", {})
                    service = config.get("service", {})
                    pipelines = service.get("pipelines", {})

                    for pipeline_name, pipeline_cfg in pipelines.items():
                        if not isinstance(pipeline_cfg, dict):
                            continue
                        # Determine signal from pipeline name
                        pipeline_signal = None
                        for s in ["traces", "metrics", "logs"]:
                            if s in pipeline_name:
                                pipeline_signal = s
                                break
                        if not pipeline_signal or pipeline_signal in targets:
                            continue
                        if pipeline_signal not in signals:
                            continue

                        # Find the first non-debug, non-spanmetrics exporter
                        for exp_name in pipeline_cfg.get("exporters", []):
                            if exp_name in ("debug", "logging", "nop"):
                                continue
                            if "spanmetrics" in exp_name:
                                continue
                            exp_cfg = exporters.get(exp_name, {})
                            endpoint = self._extract_endpoint(
                                exp_name, exp_cfg
                            )
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
                # Namespace might not exist or no permissions
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
                            # Evaluate service using a generic scoring system instead of hardcoded exclusions
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
                                    if any(h in pname for h in ["otlp-grpc", "otlp-http", "otlp", "grpc-otlp", "http-otlp"]):
                                        otlp_port = p["port"]
                                        break
                                    if hint_port is None and any(h in pname for h in [protocol, signal[:5]]):
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
                                    "svc_name": svc['name'],
                                    "ns": ns,
                                    "exp_type": exp_type
                                })

                for signal in signals:
                    if signal in targets or not candidates[signal]:
                        continue
                    
                    # Sort candidates by score descending and pick the best match
                    best = sorted(candidates[signal], key=lambda x: x["score"], reverse=True)[0]
                    
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
            # Direct endpoint field
            endpoint = exporter_cfg.get("endpoint")
            if endpoint:
                return str(endpoint)
            # Nested under http/grpc
            for proto in ("http", "grpc"):
                nested = exporter_cfg.get(proto, {})
                if isinstance(nested, dict):
                    ep = nested.get("endpoint")
                    if ep:
                        return str(ep)
        return None

    # ──────────────────────────────────────────────
    # Cluster sizing
    # ──────────────────────────────────────────────

    async def discover_cluster_size(self) -> Tuple[str, int]:
        """Auto-detect cluster size from node count.

        Returns:
            Tuple of (size label, node count).
        """
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

    # ──────────────────────────────────────────────
    # Mode recommendation
    # ──────────────────────────────────────────────

    @staticmethod
    def recommend_mode(
        signals: List[str],
        enable_filelog: bool = False,
        prometheus_scrape: bool = False,
    ) -> Tuple[str, str]:
        """Recommend deployment mode with rationale.

        Args:
            signals: Signals to collect.
            enable_filelog: Whether filelog receiver is needed.
            prometheus_scrape: Whether Prometheus scraping is needed.

        Returns:
            Tuple of (mode, rationale string).
        """
        if enable_filelog:
            return (
                "daemonset",
                "DaemonSet selected: filelog receiver requires node-level "
                "access to /var/log/pods"
            )
        if prometheus_scrape:
            return (
                "statefulset",
                "StatefulSet selected: Prometheus scraping with Target "
                "Allocator needs stable collector identities for balanced "
                "target distribution"
            )
        if "logs" in signals and not enable_filelog:
            # OTLP logs don't need node access
            return (
                "deployment",
                "Deployment selected: OTLP log receiver doesn't require "
                "node-level access"
            )
        return (
            "deployment",
            "Deployment selected: traces/metrics collection via OTLP "
            "receivers doesn't require node-level access"
        )

    # ──────────────────────────────────────────────
    # Resource sizing
    # ──────────────────────────────────────────────

    @staticmethod
    def recommend_resources(cluster_size: str) -> Dict[str, Any]:
        """Recommend K8s resource requests/limits.

        Args:
            cluster_size: 'small', 'medium', or 'large'.

        Returns:
            Resource requests/limits dict.
        """
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

    # ──────────────────────────────────────────────
    # Config section builders
    # ──────────────────────────────────────────────

    @staticmethod
    def _build_extensions(enable_filelog: bool = False) -> Dict[str, Any]:
        """Build extensions config (health_check always included)."""
        exts: Dict[str, Any] = {
            "health_check": {
                "endpoint": "0.0.0.0:13133",
            },
        }
        if enable_filelog:
            exts["file_storage"] = {
                "directory": "/var/lib/otelcol/file_storage"
            }
        return exts

    @staticmethod
    def _build_receivers(
        signals: List[str],
        enable_filelog: bool,
        prometheus_scrape: bool,
        namespace: str,
        collector_name: str,
    ) -> Dict[str, Any]:
        """Build receivers config based on signals and options."""
        receivers: Dict[str, Any] = {}

        # OTLP receiver is always included (primary ingestion)
        receivers["otlp"] = {
            "protocols": {
                "grpc": {"endpoint": "0.0.0.0:4317"},
                "http": {"endpoint": "0.0.0.0:4318"},
            },
        }

        # Filelog receiver for container logs
        if enable_filelog:
            # Self-exclusion pattern to prevent feedback loops
            exclude_pattern = (
                f"/var/log/pods/{namespace}_{collector_name}*/*/*.log"
                if namespace and collector_name
                else "/var/log/pods/*/*otel-collector*/*.log"
            )
            receivers["filelog"] = {
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
            # Also need file_storage extension for checkpointing

        # Prometheus receiver for scraping
        if prometheus_scrape:
            receivers["prometheus"] = {
                "config": {
                    "scrape_configs": [
                        {
                            "job_name": "kubernetes-pods",
                            "kubernetes_sd_configs": [
                                {"role": "pod"},
                            ],
                        },
                    ],
                },
            }

        return receivers

    @staticmethod
    def _build_processors() -> Dict[str, Any]:
        """Build processors with best-practice ordering enforced.

        The order is always:
        memory_limiter → k8sattributes → resourcedetection →
        resource → batch

        Users never need to think about this.
        """
        return {
            "memory_limiter": {
                "check_interval": "5s",
                "limit_percentage": 80,
                "spike_limit_percentage": 25,
            },
            "k8sattributes": {
                "extract": {
                    "metadata": [
                        "k8s.namespace.name",
                        "k8s.pod.name",
                        "k8s.pod.uid",
                        "k8s.deployment.name",
                        "k8s.replicaset.name",
                        "k8s.daemonset.name",
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
            },
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

    @staticmethod
    def _apply_path_suffix(
        endpoint: str, exporter_type: str,
    ) -> str:
        """Append the well-known API path suffix for an exporter type.

        Uses ``_EXPORTER_DEFAULTS`` to look up the required path
        suffix (e.g. ``/loki/api/v1/push`` for Loki, ``/api/v1/otlp``
        for Prometheus OTLP-HTTP). Idempotent — will not double-append
        if the path is already present.
        """
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
        """Deep-merge user-provided overrides into an exporter config.

        Overrides are keyed by exporter type name (e.g. 'loki',
        'opensearch'). Dict values are recursively merged so that
        callers can add nested keys (like ``headers``) without
        clobbering the rest of the generated config.
        """
        if not overrides or exporter_type not in overrides:
            return config

        user_cfg = deepcopy(overrides[exporter_type])
        for key, value in user_cfg.items():
            if (
                key in config
                and isinstance(config[key], dict)
                and isinstance(value, dict)
            ):
                # Recursive merge for nested dicts (e.g. headers, tls)
                config[key].update(value)
            else:
                config[key] = value
        return config

    @staticmethod
    def _build_exporters(
        exporter_targets: Dict[str, str],
        exporter_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build exporters from discovered targets.

        Maps signal → endpoint to the appropriate exporter type
        (otlp, otlphttp, opensearch, etc.).  Automatically appends
        well-known API path suffixes from ``_EXPORTER_DEFAULTS`` and
        merges any user-provided ``exporter_overrides``.
        """
        exporters: Dict[str, Any] = {}
        used_debug = False

        for signal, endpoint in exporter_targets.items():
            if endpoint == "__debug__":
                if not used_debug:
                    exporters["debug"] = {}
                    used_debug = True
                continue

            # Determine exporter type from endpoint pattern
            endpoint_lower = endpoint.lower()

            if "prometheus" in endpoint_lower or "9090" in endpoint_lower:
                exp_name = f"prometheusremotewrite/{signal}"
                scheme_endpoint = endpoint
                if not scheme_endpoint.startswith("http"):
                    if "443" in scheme_endpoint:
                        scheme_endpoint = f"https://{scheme_endpoint}"
                    else:
                        scheme_endpoint = f"http://{scheme_endpoint}"
                
                # Apply well-known path suffix via _EXPORTER_DEFAULTS
                scheme_endpoint = CollectorConfigBuilder._apply_path_suffix(
                    scheme_endpoint, "prometheusremotewrite"
                )
                tls_config = {"insecure": False, "insecure_skip_verify": True} if scheme_endpoint.startswith("https") else {"insecure": True}
                exp_config: Dict[str, Any] = {
                    "endpoint": scheme_endpoint,
                    "tls": tls_config,
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "prometheusremotewrite", exporter_overrides
                )
            elif any(p in endpoint_lower for p in [
                "opensearch", "9200",
            ]):
                exp_name = "opensearch"
                scheme_endpoint = endpoint
                if not scheme_endpoint.startswith("http"):
                    if "443" in scheme_endpoint:
                        scheme_endpoint = f"https://{scheme_endpoint}"
                    else:
                        scheme_endpoint = f"http://{scheme_endpoint}"
                tls_config = {"insecure": False, "insecure_skip_verify": True} if scheme_endpoint.startswith("https") else {"insecure": True}
                exp_config = {
                    "http": {
                        "endpoint": scheme_endpoint,
                        "tls": tls_config,
                    },
                    "logs_index": "otel-logs",
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "opensearch", exporter_overrides
                )
            elif any(p in endpoint_lower for p in [
                "loki", "3100",
            ]):
                exp_name = "otlphttp/loki"
                scheme_endpoint = endpoint
                if not scheme_endpoint.startswith("http"):
                    if "443" in scheme_endpoint:
                        scheme_endpoint = f"https://{scheme_endpoint}"
                    else:
                        scheme_endpoint = f"http://{scheme_endpoint}"
                # Apply well-known path suffix via _EXPORTER_DEFAULTS
                scheme_endpoint = CollectorConfigBuilder._apply_path_suffix(
                    scheme_endpoint, "otlphttp/loki"
                )
                tls_config = {"insecure": False, "insecure_skip_verify": True} if scheme_endpoint.startswith("https") else {"insecure": True}
                exp_config = {
                    "endpoint": scheme_endpoint,
                    "tls": tls_config,
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "otlphttp/loki", exporter_overrides
                )
            elif any(p in endpoint_lower for p in [
                "elasticsearch", "elastic",
            ]):
                exp_name = "elasticsearch"
                scheme_endpoint = endpoint
                if not scheme_endpoint.startswith("http"):
                    if "443" in scheme_endpoint:
                        scheme_endpoint = f"https://{scheme_endpoint}"
                    else:
                        scheme_endpoint = f"http://{scheme_endpoint}"
                tls_config = {"insecure": False, "insecure_skip_verify": True} if scheme_endpoint.startswith("https") else {"insecure": True}
                exp_config = {
                    "endpoints": [scheme_endpoint],
                    "tls": tls_config,
                    "logs_index": "otel-logs",
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "elasticsearch", exporter_overrides
                )
            else:
                # Default: OTLP gRPC exporter
                exp_name = f"otlp/{signal}"
                tls_config = {"insecure": False, "insecure_skip_verify": True} if "443" in endpoint else {"insecure": True}
                exp_config = {
                    "endpoint": endpoint,
                    "tls": tls_config,
                }
                exporters[exp_name] = CollectorConfigBuilder._merge_overrides(
                    exp_config, "otlp", exporter_overrides
                )

        return exporters

    @staticmethod
    def _build_connectors(enable_spanmetrics: bool) -> Dict[str, Any]:
        """Build connectors (spanmetrics if requested)."""
        if not enable_spanmetrics:
            return {}

        return {
            "spanmetrics": {
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
            },
        }

    def _build_service(
        self,
        signals: List[str],
        exporter_targets: Dict[str, str],
        enable_spanmetrics: bool,
        enable_filelog: bool,
        prometheus_scrape: bool,
    ) -> Dict[str, Any]:
        """Build service section wiring pipelines together."""
        service_extensions = ["health_check"]
        if enable_filelog:
            service_extensions.append("file_storage")

        service: Dict[str, Any] = {
            "extensions": service_extensions,
            "pipelines": {},
        }

        processor_chain = list(_PROCESSOR_ORDER)

        for signal in signals:
            pipeline_name = signal  # traces, metrics, logs

            # Receivers
            receivers = ["otlp"]
            if signal == "logs" and enable_filelog:
                receivers.append("filelog")
            if signal == "metrics" and prometheus_scrape:
                receivers.append("prometheus")
            if signal == "metrics" and enable_spanmetrics:
                receivers.append("spanmetrics")

            # Exporters
            target = exporter_targets.get(signal, "__debug__")
            if target == "__debug__":
                pipeline_exporters = ["debug"]
            else:
                # Find the exporter name we created for this signal
                pipeline_exporters = self._resolve_exporter_names(
                    signal, target
                )

            service["pipelines"][pipeline_name] = {
                "receivers": receivers,
                "processors": processor_chain,
                "exporters": pipeline_exporters,
            }

        # Add traces → spanmetrics connector pipeline
        if enable_spanmetrics and "traces" in signals:
            traces_pipeline = service["pipelines"].get("traces", {})
            traces_exporters = traces_pipeline.get("exporters", [])
            if "spanmetrics" not in traces_exporters:
                traces_exporters.append("spanmetrics")
                traces_pipeline["exporters"] = traces_exporters

        return service

    @staticmethod
    def _resolve_exporter_names(
        signal: str, endpoint: str,
    ) -> List[str]:
        """Resolve which exporter name to use for a signal+endpoint."""
        endpoint_lower = endpoint.lower()

        if "prometheus" in endpoint_lower or "9090" in endpoint_lower:
            return [f"otlphttp/{signal}"]
        if "opensearch" in endpoint_lower or "9200" in endpoint_lower:
            return ["opensearch"]
        if "loki" in endpoint_lower or "3100" in endpoint_lower:
            return ["loki"]
        if "elasticsearch" in endpoint_lower or "elastic" in endpoint_lower:
            return ["elasticsearch"]
        return [f"otlp/{signal}"]

