#!/usr/bin/env python3
"""Domain 10 (OpenTelemetry & Cross-Pillar Observability Security) Live Battleground Deployer & Stager.

Deploys and stages a complete, real OpenTelemetry battleground on `docker-desktop`:
1. Installs `open-telemetry/opentelemetry-operator` in `opentelemetry-operator-system`
   (backed by `cert-manager`) exposing `OpenTelemetryCollector` (`v1beta1`),
   `Instrumentation` (`v1alpha1`), `TargetAllocator` (`v1beta1`/`v1alpha1`), and
   `OpAMPBridge` (`v1alpha1`) CRDs + live mutating/validating webhooks.
2. Deploys non-conflicting observability backends/gateways in `observability`:
   - `tempo-distributor` (`grafana/tempo:2.7.1` on `:4317` OTLP gRPC, `:4318` OTLP HTTP, `:3200` HTTP)
   - `otel-backend-router` fronting `Service/mimir-distributor` (`:9009` -> `prometheus-d6` OTLP & remote-write)
     and `Service/loki-gateway` (`:80` -> `loki:3100` with `X-Scope-OrgID: otel-demo` header injection).
3. Deploys real `OpenTelemetryCollector` (`0.152.1`) pipelines receiving live OTLP traces, metrics, and logs
   from ArgoCD-onboarded `OTEL-APP` microservices in `otel-demo` and routing them to Tempo, Prometheus, and Loki,
   plus scenario-specific collectors, TargetAllocators, Instrumentation CRs, RBAC roles, and workloads.

Usage:
  python3 scripts/stage_d10_opentelemetry.py deploy
  python3 scripts/stage_d10_opentelemetry.py reset [skill-name]
  python3 scripts/stage_d10_opentelemetry.py verify
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

KUBE_CONTEXT = "docker-desktop"
OBS_NS = "observability"
OTEL_NS = "otel-demo"
COMPLIANT_NS = "otel-demo-prod-us"
OPERATOR_NS = "opentelemetry-operator-system"
COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib:0.152.1"
LEGACY_COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib:0.118.0"
TEMPO_IMAGE = "grafana/tempo:2.7.1"

DEVOPS_PLUGINS_ROOT = Path(os.environ.get("DEVOPS_PLUGINS_ROOT", Path(__file__).resolve().parents[4] / "devops-plugins"))
WORKSPACES_DIR = DEVOPS_PLUGINS_ROOT / "evals" / "workspaces"
OTEL_ENV_FILE = WORKSPACES_DIR / ".opentelemetry.env"


def run_cmd(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(args)}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
    return proc


def kubectl(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 120,
) -> str:
    proc = run_cmd(
        ["kubectl", "--context", KUBE_CONTEXT, *args],
        input_text=input_text,
        check=check,
        timeout=timeout,
    )
    return proc.stdout


def apply_manifests(docs: list[dict[str, Any]]) -> None:
    payload = "\n---\n".join(yaml.safe_dump(d, sort_keys=False) for d in docs if d)
    kubectl(["apply", "-f", "-"], input_text=payload)


def compress_snapshot(cfg: dict[str, Any]) -> str:
    raw_json = json.dumps(cfg, sort_keys=True).encode("utf-8")
    return base64.b64encode(gzip.compress(raw_json)).decode("ascii")


def write_env_file() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    content = (
        "K8S_ENABLED=true\n"
        f"K8S_CONTEXT={KUBE_CONTEXT}\n"
        f"KUBE_CONTEXT={KUBE_CONTEXT}\n"
        "PROMETHEUS_URL=http://localhost:29090\n"
        "PROMETHEUS_BASE_URL=http://localhost:29090\n"
        "MCP_TOOLSETS=all\n"
    )
    OTEL_ENV_FILE.write_text(content, encoding="utf-8")
    OTEL_ENV_FILE.chmod(0o600)
    print(f"[stage_d10] Wrote {OTEL_ENV_FILE}")


def ensure_namespaces() -> None:
    for ns in (OBS_NS, OTEL_NS, COMPLIANT_NS, OPERATOR_NS):
        kubectl(
            ["create", "namespace", ns, "--dry-run=client", "-o", "yaml"],
        )
        ns_yaml = kubectl(["create", "namespace", ns, "--dry-run=client", "-o", "yaml"])
        kubectl(["apply", "-f", "-"], input_text=ns_yaml)


def install_otel_operator() -> None:
    print("[stage_d10] Ensuring OpenTelemetry Operator is installed in opentelemetry-operator-system...")
    rel_out = run_cmd(
        ["helm", "--kube-context", KUBE_CONTEXT, "status", "opentelemetry-operator", "-n", OPERATOR_NS],
        check=False,
    )
    if rel_out.returncode != 0:
        for kind, rname in [
            ("clusterrole", "opentelemetry-operator-manager"),
            ("clusterrole", "opentelemetry-operator-metrics"),
            ("clusterrolebinding", "opentelemetry-operator-manager"),
            ("clusterrolebinding", "opentelemetry-operator-metrics"),
            ("mutatingwebhookconfiguration", "opentelemetry-operator-mutation"),
            ("validatingwebhookconfiguration", "opentelemetry-operator-validation"),
        ]:
            kubectl(["delete", kind, rname, "--ignore-not-found=true"], check=False)
        run_cmd(
            [
                "helm",
                "--kube-context",
                KUBE_CONTEXT,
                "upgrade",
                "--install",
                "opentelemetry-operator",
                "open-telemetry/opentelemetry-operator",
                "-n",
                OPERATOR_NS,
                "--create-namespace",
                "--set",
                "admissionWebhooks.certManager.enabled=true",
                "--set",
                "manager.collectorImage.repository=otel/opentelemetry-collector-contrib",
                "--set",
                "manager.collectorImage.tag=0.152.1",
                "--wait",
                "--timeout",
                "180s",
            ],
            timeout=240,
        )
    kubectl(
        [
            "rollout",
            "status",
            "deploy/opentelemetry-operator",
            "-n",
            OPERATOR_NS,
            "--timeout=120s",
        ]
    )
    print("[stage_d10] OpenTelemetry Operator and admission webhook are Ready.")


TEMPO_DISTRIBUTOR_YAML = """stream_over_http_enabled: true
server:
  http_listen_port: 3200
  log_level: warn

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"
        http:
          endpoint: "0.0.0.0:4318"

ingester:
  max_block_duration: 5m

compactor:
  compaction:
    block_retention: 24h

storage:
  trace:
    backend: local
    wal:
      path: /var/tempo/wal
    local:
      path: /var/tempo/blocks
"""

BACKEND_ROUTER_PY = r"""import http.server, socketserver, threading, urllib.error, urllib.request

PROM_BASE = "http://prometheus-d6.observability.svc.cluster.local:29090"
LOKI_BASE = "http://loki.observability.svc.cluster.local:3100"

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, fmt, *args):
        pass
    def _forward(self, target_base, path_override=None, inject_org=False):
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""
        path = path_override or self.path
        url = f"{target_base}{path}"
        headers = {}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl in ("host", "connection", "transfer-encoding"):
                continue
            headers[k] = v
        if inject_org and "X-Scope-OrgID" not in headers and "x-scope-orgid" not in {k.lower() for k in headers}:
            headers["X-Scope-OrgID"] = "otel-demo"
        req = urllib.request.Request(url, data=body if self.command in ("POST", "PUT") else None, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Length", str(len(resp_body)))
                ct = resp.headers.get("Content-Type")
                if ct:
                    self.send_header("Content-Type", ct)
                self.end_headers()
                if resp_body:
                    self.wfile.write(resp_body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read() if exc.fp else b""
            self.send_response(exc.code)
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            if err_body:
                self.wfile.write(err_body)
        except Exception as exc:
            msg = str(exc).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

class MimirHandler(ProxyHandler):
    def do_POST(self):
        p = self.path
        if p.startswith("/otlp/v1/metrics") or p.startswith("/v1/metrics"):
            p = "/api/v1/otlp/v1/metrics"
        elif p.endswith("/otlp"):
            p = "/api/v1/otlp/v1/metrics"
        self._forward(PROM_BASE, path_override=p)
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

class LokiGwHandler(ProxyHandler):
    def do_POST(self):
        self._forward(LOKI_BASE, inject_org=True)
    def do_GET(self):
        self._forward(LOKI_BASE, inject_org=True)

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

s1 = ThreadedTCPServer(("0.0.0.0", 9009), MimirHandler)
s2 = ThreadedTCPServer(("0.0.0.0", 8080), LokiGwHandler)
threading.Thread(target=s1.serve_forever, daemon=True).start()
s2.serve_forever()
"""


def deploy_observability_gateways() -> None:
    print("[stage_d10] Deploying Tempo distributor and Prometheus/Loki OTLP gateways in observability...")
    docs: list[dict[str, Any]] = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "tempo-distributor-config", "namespace": OBS_NS},
            "data": {"tempo.yaml": TEMPO_DISTRIBUTOR_YAML},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "tempo-distributor", "namespace": OBS_NS},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "tempo-distributor"}},
                "template": {
                    "metadata": {"labels": {"app": "tempo-distributor"}},
                    "spec": {
                        "containers": [
                            {
                                "name": "tempo",
                                "image": TEMPO_IMAGE,
                                "args": ["-config.file=/etc/tempo/tempo.yaml"],
                                "ports": [
                                    {"name": "http", "containerPort": 3200},
                                    {"name": "otlp-grpc", "containerPort": 4317},
                                    {"name": "otlp-http", "containerPort": 4318},
                                ],
                                "readinessProbe": {
                                    "httpGet": {"path": "/ready", "port": 3200},
                                    "initialDelaySeconds": 3,
                                    "periodSeconds": 5,
                                },
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/etc/tempo"},
                                    {"name": "data", "mountPath": "/var/tempo"},
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": "config", "configMap": {"name": "tempo-distributor-config"}},
                            {"name": "data", "emptyDir": {}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "tempo-distributor", "namespace": OBS_NS},
            "spec": {
                "selector": {"app": "tempo-distributor"},
                "ports": [
                    {"name": "otlp-grpc", "port": 4317, "targetPort": 4317},
                    {"name": "otlp-http", "port": 4318, "targetPort": 4318},
                    {"name": "http", "port": 3200, "targetPort": 3200},
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "otel-backend-router-script", "namespace": OBS_NS},
            "data": {"router.py": BACKEND_ROUTER_PY},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "otel-backend-router", "namespace": OBS_NS},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "otel-backend-router"}},
                "template": {
                    "metadata": {"labels": {"app": "otel-backend-router"}},
                    "spec": {
                        "containers": [
                            {
                                "name": "router",
                                "image": "python:3.12-alpine",
                                "command": ["python3", "/app/router.py"],
                                "ports": [
                                    {"name": "mimir", "containerPort": 9009},
                                    {"name": "loki-gw", "containerPort": 8080},
                                ],
                                "volumeMounts": [
                                    {"name": "script", "mountPath": "/app"},
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": "script", "configMap": {"name": "otel-backend-router-script"}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "mimir-distributor", "namespace": OBS_NS},
            "spec": {
                "selector": {"app": "otel-backend-router"},
                "ports": [
                    {"name": "http-otlp", "port": 9009, "targetPort": 9009},
                    {"name": "http-prom", "port": 9090, "targetPort": 9009},
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "loki-gateway", "namespace": OBS_NS},
            "spec": {
                "selector": {"app": "otel-backend-router"},
                "ports": [
                    {"name": "http", "port": 80, "targetPort": 8080},
                    {"name": "loki", "port": 3100, "targetPort": 8080},
                ],
            },
        },
    ]
    apply_manifests(docs)
    kubectl(["rollout", "status", "deploy/tempo-distributor", "-n", OBS_NS, "--timeout=90s"])
    kubectl(["rollout", "status", "deploy/otel-backend-router", "-n", OBS_NS, "--timeout=60s"])


LIVE_OTLP_EMITTER_PY = r"""import json, os, random, time, urllib.request

COLLECTOR_HTTP = os.environ.get(
    "COLLECTOR_HTTP",
    "http://opentelemetry-otel-collector.otel-demo.svc.cluster.local:4318",
)
FRONTEND_URL = "http://frontend.otel-demo.svc.cluster.local:8080/"

def post_json(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{COLLECTOR_HTTP}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
    except Exception:
        pass

while True:
    now_ns = int(time.time() * 1_000_000_000)
    trace_id = f"{random.getrandbits(128):032x}"
    root_span = f"{random.getrandbits(64):016x}"
    child_span = f"{random.getrandbits(64):016x}"

    # Trigger real OTEL-APP HTTP traffic too
    try:
        urllib.request.urlopen(FRONTEND_URL, timeout=2).read(256)
    except Exception:
        pass

    traces_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout-service"}},
                        {"key": "service.namespace", "value": {"stringValue": "otel-demo"}},
                        {"key": "k8s.namespace.name", "value": {"stringValue": "otel-demo"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "otel-app.checkout"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": root_span,
                                "name": "POST /api/checkout",
                                "kind": 2,
                                "startTimeUnixNano": str(now_ns - 45_000_000),
                                "endTimeUnixNano": str(now_ns),
                                "attributes": [
                                    {"key": "http.request.method", "value": {"stringValue": "POST"}},
                                    {"key": "http.response.status_code", "value": {"intValue": "200"}},
                                    {"key": "url.path", "value": {"stringValue": "/api/checkout"}},
                                ],
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "payment"}},
                        {"key": "service.namespace", "value": {"stringValue": "otel-demo"}},
                        {"key": "k8s.namespace.name", "value": {"stringValue": "otel-demo"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "otel-app.payment"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": child_span,
                                "parentSpanId": root_span,
                                "name": "oteldemo.PaymentService/Charge",
                                "kind": 2,
                                "startTimeUnixNano": str(now_ns - 25_000_000),
                                "endTimeUnixNano": str(now_ns - 5_000_000),
                                "attributes": [
                                    {"key": "rpc.system", "value": {"stringValue": "grpc"}},
                                    {"key": "rpc.grpc.status_code", "value": {"intValue": "0"}},
                                ],
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            },
        ]
    }
    post_json("/v1/traces", traces_payload)

    metrics_payload = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout-service"}},
                        {"key": "service.namespace", "value": {"stringValue": "otel-demo"}},
                    ]
                },
                "scopeMetrics": [
                    {
                        "scope": {"name": "otel-app.checkout"},
                        "metrics": [
                            {
                                "name": "app_checkout_orders_processed_total",
                                "unit": "1",
                                "sum": {
                                    "aggregationTemporality": 2,
                                    "isMonotonic": True,
                                    "dataPoints": [
                                        {
                                            "startTimeUnixNano": str(now_ns - 60_000_000_000),
                                            "timeUnixNano": str(now_ns),
                                            "asDouble": float(int(time.time()) % 10000),
                                            "attributes": [
                                                {"key": "currency", "value": {"stringValue": "USD"}},
                                            ],
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    post_json("/v1/metrics", metrics_payload)

    logs_payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout-service"}},
                        {"key": "service.namespace", "value": {"stringValue": "otel-demo"}},
                        {"key": "k8s.namespace.name", "value": {"stringValue": "otel-demo"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "otel-app.checkout"},
                        "logRecords": [
                            {
                                "timeUnixNano": str(now_ns),
                                "severityNumber": 9,
                                "severityText": "INFO",
                                "traceId": trace_id,
                                "spanId": root_span,
                                "body": {
                                    "stringValue": json.dumps(
                                        {
                                            "level": "info",
                                            "msg": "Order completed via OpenTelemetry Collector",
                                            "trace_id": trace_id,
                                            "span_id": root_span,
                                        }
                                    )
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    post_json("/v1/logs", logs_payload)
    time.sleep(4)
"""


def build_least_privilege_rbac(
    role_name: str,
    sa_name: str,
    sa_namespace: str,
    *,
    include_kubeletstats: bool = False,
    include_ta: bool = False,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = [
        {
            "apiGroups": [""],
            "resources": ["pods", "namespaces", "nodes", "services", "endpoints", "events"],
            "verbs": ["get", "list", "watch"],
        },
        {
            "apiGroups": ["apps"],
            "resources": ["replicasets", "deployments", "statefulsets", "daemonsets"],
            "verbs": ["get", "list", "watch"],
        },
        {
            "apiGroups": ["batch"],
            "resources": ["jobs", "cronjobs"],
            "verbs": ["get", "list", "watch"],
        },
    ]
    if include_kubeletstats:
        rules.append(
            {
                "apiGroups": [""],
                "resources": ["nodes/stats", "nodes/metrics", "nodes/proxy"],
                "verbs": ["get", "list", "watch"],
            }
        )
    if include_ta:
        rules.extend(
            [
                {
                    "apiGroups": ["discovery.k8s.io"],
                    "resources": ["endpointslices"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["monitoring.coreos.com"],
                    "resources": ["servicemonitors", "podmonitors", "scrapeconfigs", "probes"],
                    "verbs": ["get", "list", "watch"],
                },
            ]
        )
    subjects = [
        {
            "kind": "ServiceAccount",
            "name": sa_name,
            "namespace": sa_namespace,
        }
    ]
    if include_ta:
        subjects.append(
            {
                "kind": "ServiceAccount",
                "name": f"{sa_name.removesuffix('-collector')}-targetallocator",
                "namespace": sa_namespace,
            }
        )
    return [
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {
                "name": role_name,
                "labels": {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "talkops.ai/collector": sa_name.removesuffix("-collector"),
                    "talkops.ai/namespace": sa_namespace,
                },
            },
            "rules": rules,
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {
                "name": role_name,
                "labels": {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "talkops.ai/collector": sa_name.removesuffix("-collector"),
                    "talkops.ai/namespace": sa_namespace,
                },
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "ClusterRole",
                "name": role_name,
            },
            "subjects": subjects,
        },
    ]


def standard_collector_config(
    *,
    mode: str = "deployment",
    extra_pipelines: dict[str, Any] | None = None,
) -> dict[str, Any]:
    k8s_attr: dict[str, Any] = {
        "extract": {
            "metadata": [
                "k8s.namespace.name",
                "k8s.pod.name",
                "k8s.pod.uid",
                "k8s.deployment.name",
                "k8s.node.name",
            ]
        },
        "passthrough": False,
        "pod_association": [
            {"sources": [{"from": "resource_attribute", "name": "k8s.pod.ip"}]},
            {"sources": [{"from": "connection"}]},
        ],
    }
    if mode == "daemonset":
        k8s_attr["filter"] = {"node_from_env_var": "K8S_NODE_NAME"}

    pipelines: dict[str, Any] = {
        "traces": {
            "receivers": ["otlp"],
            "processors": ["memory_limiter", "k8sattributes", "batch"],
            "exporters": ["otlp/tempo"],
        },
        "metrics": {
            "receivers": ["otlp"],
            "processors": ["memory_limiter", "k8sattributes", "batch"],
            "exporters": ["prometheusremotewrite/metrics"],
        },
        "logs": {
            "receivers": ["otlp"],
            "processors": ["memory_limiter", "k8sattributes", "batch"],
            "exporters": ["otlphttp/loki"],
        },
    }
    if extra_pipelines:
        pipelines.update(extra_pipelines)

    return {
        "extensions": {"health_check": {"endpoint": "0.0.0.0:13133"}},
        "receivers": {
            "otlp": {
                "protocols": {
                    "grpc": {"endpoint": "0.0.0.0:4317"},
                    "http": {"endpoint": "0.0.0.0:4318"},
                }
            }
        },
        "processors": {
            "memory_limiter": {
                "check_interval": "5s",
                "limit_percentage": 80,
                "spike_limit_percentage": 25,
            },
            "k8sattributes": k8s_attr,
            "batch": {"send_batch_size": 1024, "timeout": "1s"},
        },
        "exporters": {
            "otlp/tempo": {
                "endpoint": "tempo-distributor.observability.svc.cluster.local:4317",
                "tls": {"insecure": True},
                "sending_queue": {"enabled": True, "num_consumers": 4, "queue_size": 1000},
                "retry_on_failure": {"enabled": True},
            },
            "prometheusremotewrite/metrics": {
                "endpoint": "http://mimir-distributor.observability.svc.cluster.local:9009/api/v1/write",
                "tls": {"insecure": True},
                "remote_write_queue": {"enabled": True, "num_consumers": 4, "queue_size": 1000},
                "retry_on_failure": {"enabled": True},
            },
            "otlphttp/loki": {
                "endpoint": "http://loki-gateway.observability.svc.cluster.local:80/otlp",
                "tls": {"insecure": True},
                "sending_queue": {"enabled": True, "num_consumers": 4, "queue_size": 1000},
                "retry_on_failure": {"enabled": True},
            },
        },
        "service": {
            "extensions": ["health_check"],
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
            "pipelines": pipelines,
        },
    }


def make_collector_cr(
    name: str,
    namespace: str,
    *,
    mode: str = "deployment",
    replicas: int | None = 1,
    image: str = COLLECTOR_IMAGE,
    config: dict[str, Any] | None = None,
    annotations: dict[str, str] | None = None,
    env: list[dict[str, Any]] | None = None,
    volumes: list[dict[str, Any]] | None = None,
    volume_mounts: list[dict[str, Any]] | None = None,
    target_allocator: dict[str, Any] | None = None,
    pod_security_context: dict[str, Any] | None = None,
    security_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env_list = list(env or [{"name": "GOMEMLIMIT", "value": "400MiB"}])
    if mode == "daemonset" and not any(e.get("name") == "K8S_NODE_NAME" for e in env_list):
        env_list.append(
            {
                "name": "K8S_NODE_NAME",
                "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}},
            }
        )
    spec: dict[str, Any] = {
        "mode": mode,
        "image": image,
        "resources": {
            "requests": {"cpu": "50m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        },
        "env": env_list,
        "config": config or standard_collector_config(mode=mode),
    }
    if mode != "daemonset" and replicas is not None:
        spec["replicas"] = replicas
    if volumes:
        spec["volumes"] = volumes
    if volume_mounts:
        spec["volumeMounts"] = volume_mounts
    if target_allocator:
        spec["targetAllocator"] = target_allocator
    if pod_security_context:
        spec["podSecurityContext"] = pod_security_context
    if security_context:
        spec["securityContext"] = security_context

    return {
        "apiVersion": "opentelemetry.io/v1beta1",
        "kind": "OpenTelemetryCollector",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": annotations or {},
        },
        "spec": spec,
    }


def make_sample_deployment(
    name: str,
    namespace: str,
    *,
    lang_label: str,
    pod_annotations: dict[str, str] | None = None,
    containers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    default_containers = containers or [
        {
            "name": name,
            "image": "python:3.12-alpine",
            "command": ["python3", "-m", "http.server", "8080"],
            "ports": [{"containerPort": 8080}],
            "resources": {
                "requests": {"cpu": "10m", "memory": "32Mi"},
                "limits": {"cpu": "100m", "memory": "128Mi"},
            },
        }
    ]
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/name": name,
                "app.kubernetes.io/part-of": "opentelemetry-demo",
                "app.kubernetes.io/runtime": lang_label,
            },
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app.kubernetes.io/name": name}},
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/name": name,
                        "app.kubernetes.io/part-of": "opentelemetry-demo",
                        "app.kubernetes.io/runtime": lang_label,
                    },
                    "annotations": pod_annotations or {},
                },
                "spec": {"containers": default_containers},
            },
        },
    }


def reset_battleground(skill_filter: str | None = None) -> None:
    print(f"[stage_d10] Staging idempotent OpenTelemetry battleground (skill={skill_filter or 'all'})...")

    # Clean up transient CRs created by prior eval runs so every suite starts deterministic
    for ns, kind, name in [
        (OTEL_NS, "opentelemetrycollector", "otel-dev-collector"),
        (OTEL_NS, "opentelemetrycollector", "otel-cluster-stats"),
        (OBS_NS, "opentelemetrycollector", "otel-cluster-stats"),
        (OBS_NS, "opentelemetrycollector", "otel-ro-gateway"),
        (OTEL_NS, "opentelemetrycollector", "otel-crashloop-collector"),
        (OTEL_NS, "opentelemetrycollector", "otel-upgrade-rollback"),
        (OTEL_NS, "opentelemetrycollector", "otel-legacy-collector"),
        (OTEL_NS, "instrumentation", "otel-demo-instrumentation"),
        (OTEL_NS, "instrumentation", "legacy-jaeger-inst"),
        (OTEL_NS, "instrumentation", "default-instrumentation"),
        (OTEL_NS, "deployment", "load-generator"),
        (OTEL_NS, "deployment", "ad"),
        (OTEL_NS, "deployment", "flagd"),
        (OTEL_NS, "deployment", "cart"),
        (OTEL_NS, "deployment", "email"),
        (OTEL_NS, "deployment", "payment-legacy"),
        (OTEL_NS, "deployment", "recommendation"),
    ]:
        kubectl(["delete", kind, name, "-n", ns, "--ignore-not-found=true"], check=False)

    # 1. Core RBAC + Live Collectors + OpAMPBridge + Compliant Namespace
    rbac_docs: list[dict[str, Any]] = []
    for cname, cns, kstats, ta in [
        ("opentelemetry-otel-collector", OTEL_NS, False, False),
        ("otel-ta-collector", OTEL_NS, False, True),
        ("otel-split-logs-collector", OTEL_NS, False, False),
        ("otel-broken-pipeline", OTEL_NS, False, False),
        ("otel-gitops-collector", OTEL_NS, False, False),
        ("otel-oom-collector", OTEL_NS, False, False),
        ("otel-legacy-collector", OTEL_NS, False, False),
        ("otel-legacy-address-collector", OTEL_NS, False, False),
        ("otel-agent", OBS_NS, True, False),
        ("otel-tail-sampler", OBS_NS, False, False),
        ("otel-gateway", OBS_NS, False, False),
        ("otel-prod-us-collector", COMPLIANT_NS, False, False),
    ]:
        rbac_docs.extend(
            build_least_privilege_rbac(
                f"otel-k8sattr-{cname}",
                f"{cname}-collector",
                cns,
                include_kubeletstats=kstats,
                include_ta=ta,
            )
        )

    # Deliberately restricted ClusterRole for otel-node-agent (missing nodes/stats -> 403 Forbidden!)
    rbac_docs.extend(
        [
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {
                    "name": "otel-k8sattr-otel-node-agent",
                    "labels": {
                        "app.kubernetes.io/managed-by": "talkops-mcp",
                        "talkops.ai/collector": "otel-node-agent",
                        "talkops.ai/namespace": OBS_NS,
                    },
                },
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["pods", "namespaces"],
                        "verbs": ["get", "list", "watch"],
                    }
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": "otel-k8sattr-otel-node-agent"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "otel-k8sattr-otel-node-agent",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": "otel-node-agent-collector",
                        "namespace": OBS_NS,
                    }
                ],
            },
        ]
    )

    # Deliberately wildcard/secrets ClusterRole ONLY when not running clean-cluster check,
    # bound strictly to otel-insecure-collector in otel-demo!
    rbac_docs.extend(
        [
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {
                    "name": "otel-insecure-collector-wildcard",
                    "labels": {
                        "app.kubernetes.io/managed-by": "talkops-mcp",
                        "talkops.ai/collector": "otel-insecure-collector",
                        "talkops.ai/namespace": OTEL_NS,
                    },
                },
                "rules": [
                    {
                        "apiGroups": ["*"],
                        "resources": ["*", "secrets"],
                        "verbs": ["*"],
                    }
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": "otel-insecure-collector-wildcard"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "otel-insecure-collector-wildcard",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": "otel-insecure-collector-collector",
                        "namespace": OTEL_NS,
                    }
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": "otel-opamp-bridge-reader"},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["namespaces", "pods"],
                        "verbs": ["get", "list", "watch"],
                    },
                    {
                        "apiGroups": ["opentelemetry.io"],
                        "resources": ["opentelemetrycollectors"],
                        "verbs": ["get", "list", "watch"],
                    },
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": "otel-opamp-bridge-reader"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "otel-opamp-bridge-reader",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": "otel-fleet-bridge-opamp-bridge",
                        "namespace": OTEL_NS,
                    }
                ],
            },
        ]
    )
    apply_manifests(rbac_docs)

    # Secret for secretKeyRef remediation in otel-demo
    secret_doc = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "otel-demo-telemetry-secrets", "namespace": OTEL_NS},
        "type": "Opaque",
        "stringData": {
            "auth-token": "placeholder-non-production-test-token",
            "postgres-password": "placeholder-non-production-db-pass",
        },
    }
    apply_manifests([secret_doc])

    # Split-logs collector config (controlling-telemetry-cardinality-and-noise eval-09)
    split_logs_cfg = standard_collector_config(
        extra_pipelines={
            "logs/storefront-app": {
                "receivers": ["otlp"],
                "processors": ["memory_limiter", "k8sattributes", "batch"],
                "exporters": ["otlphttp/loki"],
            },
            "logs/payment-audit": {
                "receivers": ["otlp"],
                "processors": ["memory_limiter", "k8sattributes", "batch"],
                "exporters": ["otlphttp/loki"],
            },
        }
    )

    # Broken pipeline config (otlp/tempo defined in exporters, omitted from traces.exporters!)
    broken_cfg = standard_collector_config()
    broken_cfg["exporters"]["debug"] = {"verbosity": "basic"}
    broken_cfg["service"]["pipelines"]["traces"]["exporters"] = ["debug"]

    # OOM-vulnerable config (missing memory_limiter first)
    oom_cfg = standard_collector_config()
    oom_cfg["service"]["pipelines"]["traces"]["processors"] = ["k8sattributes", "batch"]

    # Node agent missing nodes/stats RBAC (emits real 403 Forbidden in logs!)
    node_agent_cfg = standard_collector_config(mode="daemonset")
    node_agent_cfg["receivers"]["kubeletstats"] = {
        "collection_interval": "10s",
        "auth_type": "serviceAccount",
        "endpoint": "https://${env:K8S_NODE_NAME}:10250",
        "insecure_skip_verify": True,
    }
    node_agent_cfg["service"]["pipelines"]["metrics"]["receivers"] = ["otlp", "kubeletstats"]

    # Legacy collector config (0.118.0 with deprecated logging / metrics.address)
    legacy_cfg = {
        "receivers": {
            "otlp": {
                "protocols": {
                    "grpc": {"endpoint": "0.0.0.0:4317"},
                    "http": {"endpoint": "0.0.0.0:4318"},
                }
            }
        },
        "processors": {
            "memory_limiter": {
                "check_interval": "5s",
                "limit_percentage": 80,
                "spike_limit_percentage": 25,
            },
            "batch": {},
        },
        "exporters": {
            "debug": {"verbosity": "basic"},
            "otlp/tempo": {
                "endpoint": "tempo-distributor.observability.svc.cluster.local:4317",
                "tls": {"insecure": True},
                "sending_queue": {"enabled": True, "queue_size": 1000},
                "retry_on_failure": {"enabled": True},
            },
        },
        "service": {
            "telemetry": {"metrics": {"address": "0.0.0.0:8888"}},
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp/tempo", "debug"],
                }
            },
        },
    }

    # CrashLooping collectors with valid last-known-good snapshot in annotations!
    good_snapshot_b64 = compress_snapshot(standard_collector_config())
    snap_ts = datetime.now(timezone.utc).isoformat()
    crash_cfg = standard_collector_config()
    crash_cfg["exporters"]["logging"] = {"loglevel": "debug"}
    crash_cfg["service"]["pipelines"]["traces"]["exporters"] = ["logging"]

    # Insecure collector in otel-demo (for auditing-observability-security-posture)
    insecure_cfg = standard_collector_config()
    insecure_cfg["extensions"]["pprof"] = {"endpoint": "0.0.0.0:1777"}
    insecure_cfg["extensions"]["zpages"] = {"endpoint": "0.0.0.0:55679"}
    insecure_cfg["service"]["extensions"] = ["health_check", "pprof", "zpages"]
    insecure_cfg["exporters"]["otlphttp/vendor"] = {
        "endpoint": "https://otlp-ingest.observability-cloud.io",
        "headers": {"Authorization": "Bearer sk_live_audit_fixture_placeholder_123456"},
        "tls": {"insecure": True, "insecure_skip_verify": True},
        "sending_queue": {"enabled": True, "queue_size": 500},
        "retry_on_failure": {"enabled": True},
    }
    insecure_cfg["service"]["pipelines"]["traces"]["exporters"] = [
        "otlp/tempo",
        "otlphttp/vendor",
    ]

    # TargetAllocator-enabled collector config (requires prometheus receiver for Operator webhook!)
    ta_collector_cfg = standard_collector_config()
    ta_collector_cfg["receivers"]["prometheus"] = {
        "config": {"scrape_configs": []}
    }
    ta_collector_cfg["service"]["pipelines"]["metrics"]["receivers"] = [
        "otlp",
        "prometheus",
    ]

    collector_docs: list[dict[str, Any]] = [
        # Primary live production collector in otel-demo
        make_collector_cr(
            "opentelemetry-otel-collector",
            OTEL_NS,
            mode="deployment",
            replicas=1,
            pod_security_context={"runAsNonRoot": True, "runAsUser": 10001},
            security_context={
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
            },
        ),
        # DaemonSet agent + Tail-sampler StatefulSet + Gateway in observability
        make_collector_cr("otel-agent", OBS_NS, mode="daemonset"),
        make_collector_cr("otel-tail-sampler", OBS_NS, mode="statefulset", replicas=2),
        make_collector_cr("otel-gateway", OBS_NS, mode="deployment", replicas=1),
        # Scenario collectors in otel-demo & observability
        make_collector_cr(
            "otel-ta-collector",
            OTEL_NS,
            mode="statefulset",
            replicas=3 if skill_filter == "provisioning-opentelemetry-collectors" else 2,
            config=(
                standard_collector_config()
                if skill_filter == "provisioning-opentelemetry-collectors"
                else ta_collector_cfg
            ),
            target_allocator=(
                None
                if skill_filter == "provisioning-opentelemetry-collectors"
                else {
                    "enabled": True,
                    "allocationStrategy": "consistent-hashing",
                    "prometheusCR": {
                        "enabled": True,
                        "serviceMonitorSelector": {"matchLabels": {"release": "kube-prometheus-stack"}},
                        "podMonitorSelector": {},
                    },
                }
            ),
        ),
        make_collector_cr("otel-demo-canary-old", OTEL_NS, mode="deployment", replicas=0),
        {
            "apiVersion": "opentelemetry.io/v1alpha1",
            "kind": "TargetAllocator",
            "metadata": {"name": "otel-demo-canary-old-ta", "namespace": OTEL_NS},
            "spec": {
                "replicas": 0,
                "allocationStrategy": "consistent-hashing",
                "prometheusCR": {"enabled": True},
            },
        },
        {
            "apiVersion": "opentelemetry.io/v1alpha1",
            "kind": "OpAMPBridge",
            "metadata": {"name": "otel-fleet-bridge", "namespace": OTEL_NS},
            "spec": {
                "endpoint": "ws://opamp-server.observability.svc.cluster.local:4320/v1/opamp",
                "capabilities": {"ReportsStatus": True, "ReportsEffectiveConfig": True},
            },
        },
        make_collector_cr("otel-split-logs-collector", OTEL_NS, config=split_logs_cfg),
        make_collector_cr("otel-broken-pipeline", OTEL_NS, config=broken_cfg),
        make_collector_cr("otel-oom-collector", OTEL_NS, config=oom_cfg, env=[]),
        make_collector_cr(
            "otel-gitops-collector",
            OTEL_NS,
            annotations={
                "argocd.argoproj.io/tracking-id": (
                    "otel-collector:opentelemetry.io/OpenTelemetryCollector:otel-demo/otel-gitops-collector"
                )
            },
        ),
        make_collector_cr(
            "otel-crashloop-collector",
            OTEL_NS,
            config=crash_cfg,
            annotations={
                "otel.mcp/last-known-good": good_snapshot_b64,
                "otel.mcp/last-mutation": snap_ts,
            },
        ),
        make_collector_cr(
            "otel-upgrade-rollback",
            OTEL_NS,
            config=crash_cfg,
            annotations={
                "otel.mcp/last-known-good": good_snapshot_b64,
                "otel.mcp/last-mutation": snap_ts,
            },
        ),
        make_collector_cr(
            "otel-legacy-collector",
            OTEL_NS,
            image=LEGACY_COLLECTOR_IMAGE,
            config=legacy_cfg,
            env=[],
        ),
        make_collector_cr(
            "otel-legacy-address-collector",
            OTEL_NS,
            image=LEGACY_COLLECTOR_IMAGE,
            config=legacy_cfg,
        ),
        make_collector_cr("otel-node-agent", OBS_NS, mode="daemonset", config=node_agent_cfg),
        make_collector_cr("otel-insecure-collector", OTEL_NS, config=insecure_cfg),
        make_collector_cr(
            "otel-insecure-agent",
            OBS_NS,
            mode="daemonset",
            volumes=[{"name": "varlogpods", "hostPath": {"path": "/var/log/pods"}}],
            volume_mounts=[{"name": "varlogpods", "mountPath": "/var/log/pods", "readOnly": False}],
        ),
        # 100% Compliant collector in otel-demo-prod-us
        make_collector_cr(
            "otel-prod-us-collector",
            COMPLIANT_NS,
            mode="deployment",
            replicas=1,
            pod_security_context={"runAsNonRoot": True, "runAsUser": 10001},
            security_context={
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
            },
        ),
    ]
    apply_manifests(collector_docs)

    # Point Service/opentelemetry-otel-collector in otel-demo to the real Operator-managed collector pods!
    svc_alias = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "opentelemetry-otel-collector", "namespace": OTEL_NS},
        "spec": {
            "selector": {
                "app.kubernetes.io/instance": f"{OTEL_NS}.opentelemetry-otel-collector",
                "app.kubernetes.io/component": "opentelemetry-collector",
            },
            "ports": [
                {"name": "otlp-grpc", "port": 4317, "targetPort": 4317, "protocol": "TCP"},
                {"name": "otlp-http", "port": 4318, "targetPort": 4318, "protocol": "TCP"},
                {"name": "monitoring", "port": 8888, "targetPort": 8888, "protocol": "TCP"},
            ],
        },
    }
    apply_manifests([svc_alias])

    # Stage OTEL-APP workloads BEFORE creating Instrumentation CR so load-generator predates the CR (eval-07)!
    workload_docs: list[dict[str, Any]] = [
        make_sample_deployment(
            "load-generator",
            OTEL_NS,
            lang_label="python",
            pod_annotations={"instrumentation.opentelemetry.io/inject-python": "otel-demo-instrumentation"},
        ),
        make_sample_deployment(
            "ad",
            OTEL_NS,
            lang_label="java",
            containers=[
                {
                    "name": "ad",
                    "image": "python:3.12-alpine",
                    "command": ["python3", "-m", "http.server", "8080"],
                    "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "100m", "memory": "128Mi"}},
                },
                {
                    "name": "envoy-sidecar",
                    "image": "python:3.12-alpine",
                    "command": ["python3", "-m", "http.server", "15001"],
                    "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "100m", "memory": "128Mi"}},
                },
            ],
        ),
        make_sample_deployment(
            "flagd",
            OTEL_NS,
            lang_label="go",
            pod_annotations={"instrumentation.opentelemetry.io/inject-go": "true"},
        ),
        make_sample_deployment(
            "cart",
            OTEL_NS,
            lang_label="dotnet",
            pod_annotations={},
        ),
        make_sample_deployment(
            "email",
            OTEL_NS,
            lang_label="ruby",
            pod_annotations={"instrumentation.opentelemetry.io/inject-python": "true"},
        ),
        make_sample_deployment(
            "payment-legacy",
            OTEL_NS,
            lang_label="nodejs",
            containers=[
                {
                    "name": "payment-legacy",
                    "image": "python:3.12-alpine",
                    "command": ["python3", "-m", "http.server", "8080"],
                    "env": [
                        {
                            "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
                            "value": "http://jaeger-legacy:14268",
                        }
                    ],
                    "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "100m", "memory": "128Mi"}},
                }
            ],
        ),
        make_sample_deployment(
            "recommendation",
            OTEL_NS,
            lang_label="python",
            pod_annotations={"instrumentation.opentelemetry.io/inject-python": "otel-demo-instrumentation"},
        ),
        # Privileged eBPF OBI DaemonSet fixture in otel-demo (for security posture audit)
        {
            "apiVersion": "apps/v1",
            "kind": "DaemonSet",
            "metadata": {
                "name": "obi-ebpf",
                "namespace": OTEL_NS,
                "labels": {"app.kubernetes.io/name": "obi"},
            },
            "spec": {
                "selector": {"matchLabels": {"app.kubernetes.io/name": "obi"}},
                "template": {
                    "metadata": {"labels": {"app.kubernetes.io/name": "obi"}},
                    "spec": {
                        "hostPID": True,
                        "containers": [
                            {
                                "name": "obi",
                                "image": "python:3.12-alpine",
                                "command": ["python3", "-c", "import time; time.sleep(86400)"],
                                "securityContext": {"privileged": True},
                                "resources": {
                                    "requests": {"cpu": "5m", "memory": "16Mi"},
                                    "limits": {"cpu": "50m", "memory": "64Mi"},
                                },
                            }
                        ],
                    },
                },
            },
        },
        # Live OTLP telemetry generator sending real traces, metrics, and logs through opentelemetry-otel-collector -> Tempo, Prometheus, Loki!
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "otel-live-traffic-script", "namespace": OTEL_NS},
            "data": {"emitter.py": LIVE_OTLP_EMITTER_PY},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "otel-live-traffic", "namespace": OTEL_NS},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "otel-live-traffic"}},
                "template": {
                    "metadata": {"labels": {"app": "otel-live-traffic"}},
                    "spec": {
                        "containers": [
                            {
                                "name": "emitter",
                                "image": "python:3.12-alpine",
                                "command": ["python3", "/app/emitter.py"],
                                "volumeMounts": [{"name": "script", "mountPath": "/app"}],
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "32Mi"},
                                    "limits": {"cpu": "100m", "memory": "128Mi"},
                                },
                            }
                        ],
                        "volumes": [
                            {"name": "script", "configMap": {"name": "otel-live-traffic-script"}},
                        ],
                    },
                },
            },
        },
    ]
    apply_manifests(workload_docs)

    # Wait 3 seconds so load-generator pod creationTimestamp strictly predates Instrumentation CR!
    time.sleep(3)

    # Create Instrumentation CRs (note python intentionally mispointed to :4317 when troubleshooting skill runs!)
    py_ep = (
        "http://opentelemetry-otel-collector.otel-demo.svc.cluster.local:4317"
        if skill_filter == "troubleshooting-telemetry-pipelines"
        else "http://opentelemetry-otel-collector.otel-demo.svc.cluster.local:4318"
    )
    instr_docs: list[dict[str, Any]] = [
        {
            "apiVersion": "opentelemetry.io/v1alpha1",
            "kind": "Instrumentation",
            "metadata": {"name": "otel-demo-instrumentation", "namespace": OTEL_NS},
            "spec": {
                "exporter": {
                    "endpoint": "http://opentelemetry-otel-collector.otel-demo.svc.cluster.local:4317"
                },
                "propagators": ["tracecontext", "baggage"],
                "sampler": {"type": "parentbased_traceidratio", "argument": "0.25"},
                "python": {
                    "env": [
                        {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": py_ep},
                    ]
                },
            },
        },
    ]
    # Add duplicate legacy-jaeger-inst when testing instrumenting-kubernetes-workloads (or default all)
    if skill_filter in (None, "instrumenting-kubernetes-workloads"):
        instr_docs.append(
            {
                "apiVersion": "opentelemetry.io/v1alpha1",
                "kind": "Instrumentation",
                "metadata": {"name": "legacy-jaeger-inst", "namespace": OTEL_NS},
                "spec": {
                    "exporter": {"endpoint": "http://jaeger-legacy.otel-demo.svc:4317"},
                    "propagators": ["tracecontext"],
                },
            }
        )
    apply_manifests(instr_docs)

    if skill_filter == "troubleshooting-telemetry-pipelines":
        # Restart recommendation AFTER Instrumentation CR exists so its initContainer injects with :4317 mismatch!
        kubectl(["rollout", "restart", "deploy/recommendation", "-n", OTEL_NS], check=False)

    # Wait for primary collector pod readiness
    for wait_target in [
        ("deploy/opentelemetry-otel-collector-collector", OTEL_NS),
        ("ds/otel-agent-collector", OBS_NS),
        ("deploy/otel-gateway-collector", OBS_NS),
        ("deploy/otel-prod-us-collector-collector", COMPLIANT_NS),
    ]:
        for _ in range(25):
            chk = run_cmd(
                ["kubectl", "--context", KUBE_CONTEXT, "rollout", "status", wait_target[0], "-n", wait_target[1], "--timeout=10s"],
                check=False,
            )
            if chk.returncode == 0:
                break
            time.sleep(2)

    print("[stage_d10] Battleground reset complete.")


def verify_end_to_end_telemetry() -> None:
    print("[stage_d10] Verifying end-to-end OTLP flow -> Collector -> Prometheus, Loki, and Tempo...")
    time.sleep(8)
    # 1. Collector internal :8888 metrics via K8s Service proxy
    out = kubectl(
        [
            "get",
            "--raw",
            f"/api/v1/namespaces/{OTEL_NS}/services/opentelemetry-otel-collector:8888/proxy/metrics",
        ],
        check=False,
    )
    sent_lines = [
        ln
        for ln in out.splitlines()
        if ln.startswith(("otelcol_exporter_sent_", "otelcol_receiver_accepted_"))
    ]
    print("[stage_d10] Collector :8888/metrics counters:")
    for ln in sent_lines[:12]:
        print(f"  {ln}")

    # 2. Prometheus query for collector-forwarded metric
    prom_out = kubectl(
        [
            "get",
            "--raw",
            f"/api/v1/namespaces/{OBS_NS}/services/prometheus-d6:29090/proxy/api/v1/query?query=app_checkout_orders_processed_total",
        ],
        check=False,
    )
    print(f"[stage_d10] Prometheus query result: {prom_out[:240]}")

    # 3. Tempo distributor search
    tempo_out = kubectl(
        [
            "get",
            "--raw",
            f"/api/v1/namespaces/{OBS_NS}/services/tempo-distributor:3200/proxy/api/search?limit=3",
        ],
        check=False,
    )
    print(f"[stage_d10] Tempo search result: {tempo_out[:240]}")

    # 4. Loki gateway query
    loki_out = kubectl(
        [
            "get",
            "--raw",
            f"/api/v1/namespaces/{OBS_NS}/services/loki-gateway:80/proxy/loki/api/v1/labels",
        ],
        check=False,
    )
    print(f"[stage_d10] Loki labels result: {loki_out[:240]}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "deploy"
    skill_arg = sys.argv[2] if len(sys.argv) > 2 else None

    write_env_file()
    ensure_namespaces()
    if cmd == "deploy":
        install_otel_operator()
        deploy_observability_gateways()
        reset_battleground(skill_arg)
        verify_end_to_end_telemetry()
    elif cmd == "reset":
        reset_battleground(skill_arg)
    elif cmd == "verify":
        verify_end_to_end_telemetry()
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
