#!/usr/bin/env python3
"""Domain 7 (Alertmanager) Live Kubernetes Battleground Deployer & Idempotent Stager.

Deploys and stages 4 real `prom/alertmanager:v0.28.1` instances + `alert-sink` in
namespace `observability` on `docker-desktop`, wires `prometheus-d6` (`v3.2.1`) and
`ServiceMonitor/alertmanager-monitor` end-to-end, writes `evals/workspaces/.alertmanager.env`,
and stages deterministic live alerts, silences, failed config reloads, and audit logs.

Usage:
  python3 scripts/stage_d7_alertmanager.py deploy
  python3 scripts/stage_d7_alertmanager.py reset [skill-name]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

KUBE_CONTEXT = "docker-desktop"
NAMESPACE = "observability"
ALERTMANAGER_IMAGE = "prom/alertmanager:v0.28.1"

DEVOPS_PLUGINS_ROOT = Path(os.environ.get("DEVOPS_PLUGINS_ROOT", Path(__file__).resolve().parents[4] / "devops-plugins"))
WORKSPACES_DIR = DEVOPS_PLUGINS_ROOT / "evals" / "workspaces"
ALERTMANAGER_ENV_FILE = WORKSPACES_DIR / ".alertmanager.env"
SEED_AUDIT_FILE = WORKSPACES_DIR / ".alertmanager-seed-audit.jsonl"

URLS = {
    "default": "http://localhost:19093",
    "staging": "http://localhost:19094",
    "otel-dr": "http://localhost:19095",
    "global-am": "http://localhost:19096",
}

ALERT_SINK_SERVER_PY = r"""
import http.server
import json
import socketserver
import threading
from collections import Counter

COUNTS = Counter()

class SinkHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _respond(self, code: int, payload: dict | str, content_type: str = "application/json"):
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 0:
            _ = self.rfile.read(length)
        path = self.path.split("?", 1)[0]
        COUNTS[path] += 1

        if path == "/healthz":
            return self._respond(200, {"status": "ok"})
        if path == "/received":
            return self._respond(200, {"counts": dict(COUNTS)})
        if path.startswith("/slack/ok"):
            return self._respond(200, "ok", "text/plain")
        if path.startswith("/pagerduty/ok"):
            return self._respond(202, {"status": "success", "message": "Event processed", "dedup_key": "d7-ok"})
        if path.startswith("/opsgenie/ok"):
            return self._respond(202, {"result": "Request will be processed", "took": 0.01, "requestId": "og-ok"})
        if path.startswith("/deadmanssnitch") or path.startswith("/webhook/ok"):
            return self._respond(200, {"status": "ok", "path": path})

        # Intentional failure endpoints to drive real alertmanager_notifications_failed_total metrics
        if path.startswith("/slack/fail"):
            return self._respond(403, "invalid_auth", "text/plain")
        if path.startswith("/pagerduty/fail"):
            return self._respond(500, {"status": "internal error", "message": "pagerduty upstream 500"})
        if path.startswith("/opsgenie/fail"):
            return self._respond(401, {"message": "Could not authenticate"})
        if path.startswith("/webhook/fail"):
            return self._respond(500, {"error": "webhook_endpoint_500"})

        return self._respond(200, {"status": "default_ok", "path": path})

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    srv = ThreadedHTTPServer(("0.0.0.0", 8080), SinkHandler)
    srv.serve_forever()
"""

AM_DEFAULT_CONFIG = """global:
  resolve_timeout: 5m

time_intervals:
  - name: business-hours
    time_intervals:
      - weekdays: ['monday:friday']
        times:
          - start_time: '08:00'
            end_time: '20:00'
        location: 'UTC'
  - name: offhours-weekends
    time_intervals:
      - weekdays: ['saturday', 'sunday']
        location: 'UTC'

route:
  receiver: default-catchall
  group_by: ['alertname', 'cluster', 'namespace', 'service']
  group_wait: 1s
  group_interval: 5s
  repeat_interval: 4h
  routes:
    - matchers:
        - 'alertname="Watchdog"'
      receiver: deadmanssnitch
      group_wait: 0s
      group_interval: 10s
      repeat_interval: 1m
      continue: false

    - matchers:
        - 'team="checkout"'
      receiver: otel-checkout-email
      repeat_interval: 1h
      routes:
        - matchers:
            - 'severity="critical"'
          receiver: otel-checkout-slack
          continue: true
        - matchers:
            - 'severity="critical"'
          receiver: otel-checkout-pagerduty
          continue: false

    - matchers:
        - 'team="platform"'
      receiver: otel-platform-email
      routes:
        - matchers:
            - 'severity="critical"'
          receiver: otel-platform-pagerduty
          continue: false

    - matchers:
        - 'team="storefront"'
        - 'severity="warning"'
      receiver: otel-storefront-slack
      active_time_intervals: ['business-hours']
      mute_time_intervals: ['offhours-weekends']

    - matchers:
        - 'service=~"cart|cart-service|valkey-cart"'
      receiver: otel-cart-slack

    - matchers:
        - 'alertname="OtelFlagdConfigReloaded"'
        - 'severity="info"'
      receiver: otel-sre-pagerduty

    - matchers:
        - 'team="ops-integrations"'
      receiver: broken-multi-sink

inhibit_rules:
  - source_matchers:
      - 'alertname="OtelValkeyCartDown"'
      - 'severity="critical"'
    target_matchers:
      - 'alertname=~"OtelCartServiceErrors|OtelCheckoutDegraded|CartHighLatency"'
      - 'severity="warning"'
    equal: ['env', 'cluster', 'namespace']

  - source_matchers:
      - 'alertname=~"OtelPostgresqlDown|OtelPostgresqlOOMKilled"'
      - 'severity="critical"'
    target_matchers:
      - 'alertname=~"OtelProductCatalogLatencyHigh|OtelRecommendationGrpcErrors|OtelAccountingDbLag"'
      - 'severity="warning"'
    equal: ['env', 'cluster', 'namespace']

receivers:
  - name: default-catchall
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/webhook/ok'
        send_resolved: true
  - name: deadmanssnitch
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/deadmanssnitch'
        send_resolved: false
  - name: otel-checkout-email
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/webhook/ok'
  - name: otel-checkout-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-checkout-alerts'
        send_resolved: true
  - name: otel-checkout-pagerduty
    pagerduty_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/pagerduty/fail-500'
        routing_key: 'pd-sim-checkout-key-0001'
        send_resolved: true
  - name: otel-platform-email
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/webhook/ok'
  - name: otel-platform-pagerduty
    pagerduty_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/pagerduty/ok'
        routing_key: 'pd-sim-platform-key-0002'
  - name: otel-storefront-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-storefront-slack'
  - name: otel-cart-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-cart-alerts'
  - name: otel-sre-pagerduty
    pagerduty_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/pagerduty/ok'
        routing_key: 'pd-sim-sre-key-0003'
  - name: broken-multi-sink
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/fail-403'
        channel: '#otel-broken-alerts'
    opsgenie_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/opsgenie/fail-401/'
        api_key: 'og-sim-broken-key-0004'
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/webhook/fail-500'
"""

AM_STAGING_CONFIG = """global:
  resolve_timeout: 5m

time_intervals:
  - name: offhours-weekends
    time_intervals:
      - weekdays: ['saturday', 'sunday']
        location: 'UTC'

route:
  receiver: staging-default-slack
  group_by: ['alertname', 'cluster', 'namespace', 'service']
  group_wait: 1s
  group_interval: 5s
  repeat_interval: 4h
  routes:
    - matchers:
        - 'alertname="Watchdog"'
      receiver: deadmanssnitch
      group_wait: 0s
      repeat_interval: 1m
      continue: false
    - matchers:
        - 'team="fulfillment"'
      receiver: otel-fulfillment-slack
    - matchers:
        - 'team="checkout"'
      receiver: otel-checkout-slack
    - matchers:
        - 'team="catalog"'
      receiver: otel-catalog-slack
    - matchers:
        - 'team="storefront"'
      receiver: otel-storefront-slack

inhibit_rules:
  - source_matchers:
      - 'alertname="OtelValkeyCartDown"'
      - 'severity="critical"'
    target_matchers:
      - 'severity="warning"'
    equal: ['env', 'cluster', 'namespace']

receivers:
  - name: staging-default-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-staging-default'
  - name: deadmanssnitch
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/deadmanssnitch'
  - name: otel-fulfillment-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-fulfillment-slack'
  - name: otel-checkout-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-checkout-staging'
  - name: otel-catalog-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-catalog-slack'
  - name: otel-storefront-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-storefront-slack'
"""

AM_DR_VALID_BOOT_CONFIG = """global:
  resolve_timeout: 5m

route:
  receiver: otel-dr-pagerduty
  group_by: ['alertname', 'namespace', 'service']
  group_wait: 1s
  group_interval: 5s
  repeat_interval: 1h

receivers:
  - name: otel-dr-pagerduty
    pagerduty_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/pagerduty/fail-500'
        routing_key: 'pd-sim-dr-key-0009'
"""

AM_GLOBAL_CONFIG = """global:
  resolve_timeout: 5m

route:
  receiver: global-sre-slack
  group_by: ['alertname', 'namespace', 'service']
  group_wait: 2s
  group_interval: 30s
  repeat_interval: 4h
  routes:
    - matchers:
        - 'alertname="Watchdog"'
      receiver: deadmanssnitch
      continue: false

receivers:
  - name: global-sre-slack
    slack_configs:
      - api_url: 'http://alert-sink.observability.svc.cluster.local:8080/slack/ok'
        channel: '#otel-global-alerts'
  - name: deadmanssnitch
    webhook_configs:
      - url: 'http://alert-sink.observability.svc.cluster.local:8080/deadmanssnitch'
"""


def kubectl(*args: str, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl", "--context", KUBE_CONTEXT, *args]
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def http_json(method: str, url: str, payload: Any = None, timeout: float = 8.0) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None


def wait_http_ok(url: str, timeout_sec: float = 90.0) -> None:
    deadline = time.time() + timeout_sec
    last_err = ""
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_err = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"Timed out waiting for {url}: {last_err}")


def build_k8s_manifests() -> str:
    docs: list[dict[str, Any]] = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "alert-sink-cm", "namespace": NAMESPACE},
            "data": {"server.py": ALERT_SINK_SERVER_PY},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "alert-sink", "namespace": NAMESPACE, "labels": {"app": "alert-sink"}},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "alert-sink"}},
                "template": {
                    "metadata": {"labels": {"app": "alert-sink"}},
                    "spec": {
                        "containers": [
                            {
                                "name": "sink",
                                "image": "python:3.12-alpine",
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["python3", "/app/server.py"],
                                "ports": [{"name": "http", "containerPort": 8080}],
                                "readinessProbe": {
                                    "httpGet": {"path": "/healthz", "port": 8080},
                                    "initialDelaySeconds": 1,
                                    "periodSeconds": 3,
                                },
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "24Mi"},
                                    "limits": {"cpu": "100m", "memory": "96Mi"},
                                },
                                "volumeMounts": [{"name": "script", "mountPath": "/app"}],
                            }
                        ],
                        "volumes": [{"name": "script", "configMap": {"name": "alert-sink-cm"}}],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "alert-sink", "namespace": NAMESPACE, "labels": {"app": "alert-sink"}},
            "spec": {
                "selector": {"app": "alert-sink"},
                "ports": [{"name": "http", "port": 8080, "targetPort": 8080}],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "alertmanager-d7-configs", "namespace": NAMESPACE},
            "data": {
                "alertmanager-default.yml": AM_DEFAULT_CONFIG,
                "alertmanager-staging.yml": AM_STAGING_CONFIG,
                "alertmanager-dr.yml": AM_DR_VALID_BOOT_CONFIG,
                "alertmanager-global.yml": AM_GLOBAL_CONFIG,
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "alertmanager",
                "namespace": NAMESPACE,
                "labels": {"app": "alertmanager"},
            },
            "spec": {
                "replicas": 1,
                "strategy": {"type": "Recreate"},
                "selector": {"matchLabels": {"app": "alertmanager"}},
                "template": {
                    "metadata": {"labels": {"app": "alertmanager"}},
                    "spec": {
                        "initContainers": [
                            {
                                "name": "init-dr-cfg",
                                "image": "busybox:latest",
                                "imagePullPolicy": "IfNotPresent",
                                "command": [
                                    "sh",
                                    "-c",
                                    "cp /cfg/alertmanager-dr.yml /dr-cfg/alertmanager.yml && chmod 0777 /dr-cfg && chmod 0666 /dr-cfg/alertmanager.yml",
                                ],
                                "volumeMounts": [
                                    {"name": "configs", "mountPath": "/cfg"},
                                    {"name": "dr-cfg", "mountPath": "/dr-cfg"},
                                ],
                            }
                        ],
                        "containers": [
                            {
                                "name": "am-default",
                                "image": ALERTMANAGER_IMAGE,
                                "imagePullPolicy": "IfNotPresent",
                                "args": [
                                    "--config.file=/etc/alertmanager/alertmanager-default.yml",
                                    "--storage.path=/data",
                                    "--web.listen-address=0.0.0.0:9093",
                                    "--cluster.listen-address=",
                                ],
                                "ports": [{"name": "http-metrics", "containerPort": 9093}],
                                "readinessProbe": {
                                    "httpGet": {"path": "/-/ready", "port": 9093},
                                    "initialDelaySeconds": 2,
                                    "periodSeconds": 3,
                                },
                                "resources": {
                                    "requests": {"cpu": "20m", "memory": "32Mi"},
                                    "limits": {"cpu": "200m", "memory": "128Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "configs", "mountPath": "/etc/alertmanager"},
                                    {"name": "data-default", "mountPath": "/data"},
                                ],
                            },
                            {
                                "name": "am-staging",
                                "image": ALERTMANAGER_IMAGE,
                                "imagePullPolicy": "IfNotPresent",
                                "args": [
                                    "--config.file=/etc/alertmanager/alertmanager-staging.yml",
                                    "--storage.path=/data",
                                    "--web.listen-address=0.0.0.0:9094",
                                    "--cluster.listen-address=",
                                ],
                                "ports": [{"name": "http-staging", "containerPort": 9094}],
                                "readinessProbe": {
                                    "httpGet": {"path": "/-/ready", "port": 9094},
                                    "initialDelaySeconds": 2,
                                    "periodSeconds": 3,
                                },
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "24Mi"},
                                    "limits": {"cpu": "150m", "memory": "96Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "configs", "mountPath": "/etc/alertmanager"},
                                    {"name": "data-staging", "mountPath": "/data"},
                                ],
                            },
                            {
                                "name": "am-dr",
                                "image": ALERTMANAGER_IMAGE,
                                "imagePullPolicy": "IfNotPresent",
                                "args": [
                                    "--config.file=/dr-cfg/alertmanager.yml",
                                    "--storage.path=/data",
                                    "--web.listen-address=0.0.0.0:9095",
                                    "--cluster.listen-address=",
                                ],
                                "ports": [{"name": "http-dr", "containerPort": 9095}],
                                "readinessProbe": {
                                    "httpGet": {"path": "/-/ready", "port": 9095},
                                    "initialDelaySeconds": 2,
                                    "periodSeconds": 3,
                                },
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "24Mi"},
                                    "limits": {"cpu": "150m", "memory": "96Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "dr-cfg", "mountPath": "/dr-cfg"},
                                    {"name": "data-dr", "mountPath": "/data"},
                                ],
                            },
                            {
                                "name": "am-global",
                                "image": ALERTMANAGER_IMAGE,
                                "imagePullPolicy": "IfNotPresent",
                                "args": [
                                    "--config.file=/etc/alertmanager/alertmanager-global.yml",
                                    "--storage.path=/data",
                                    "--web.listen-address=0.0.0.0:9096",
                                    "--cluster.listen-address=",
                                ],
                                "ports": [{"name": "http-global", "containerPort": 9096}],
                                "readinessProbe": {
                                    "httpGet": {"path": "/-/ready", "port": 9096},
                                    "initialDelaySeconds": 2,
                                    "periodSeconds": 3,
                                },
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "32Mi"},
                                    "limits": {"cpu": "150m", "memory": "128Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "configs", "mountPath": "/etc/alertmanager"},
                                    {"name": "data-global", "mountPath": "/data"},
                                ],
                            },
                        ],
                        "volumes": [
                            {"name": "configs", "configMap": {"name": "alertmanager-d7-configs"}},
                            {"name": "dr-cfg", "emptyDir": {}},
                            {"name": "data-default", "emptyDir": {}},
                            {"name": "data-staging", "emptyDir": {}},
                            {"name": "data-dr", "emptyDir": {}},
                            {"name": "data-global", "emptyDir": {}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "alertmanager",
                "namespace": NAMESPACE,
                "labels": {"app": "alertmanager", "release": "kube-prometheus-stack"},
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "alertmanager"},
                "ports": [{"name": "http-metrics", "port": 9093, "targetPort": 9093}],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "alertmanager-lb",
                "namespace": NAMESPACE,
                "labels": {"app": "alertmanager"},
            },
            "spec": {
                "type": "LoadBalancer",
                "selector": {"app": "alertmanager"},
                "ports": [
                    {"name": "am-default", "port": 19093, "targetPort": 9093},
                    {"name": "am-staging", "port": 19094, "targetPort": 9094},
                    {"name": "am-dr", "port": 19095, "targetPort": 9095},
                    {"name": "am-global", "port": 19096, "targetPort": 9096},
                ],
            },
        },
        {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "ServiceMonitor",
            "metadata": {
                "name": "alertmanager-monitor",
                "namespace": NAMESPACE,
                "labels": {"app": "alertmanager", "release": "kube-prometheus-stack"},
            },
            "spec": {
                "selector": {"matchLabels": {"app": "alertmanager"}},
                "namespaceSelector": {"matchNames": [NAMESPACE]},
                "endpoints": [{"port": "http-metrics", "path": "/metrics", "interval": "10s"}],
            },
        },
    ]
    return "\n---\n".join(yaml.safe_dump(d, sort_keys=False) for d in docs)


def wire_prometheus_d6() -> None:
    """Extend prometheus-d6 ConfigMaps to push firing alerts to Alertmanager & scrape its /metrics."""
    cm_cfg = json.loads(kubectl("-n", NAMESPACE, "get", "cm", "prometheus-d6-config", "-o", "json").stdout)
    prom_yml = yaml.safe_load(cm_cfg["data"]["prometheus.yml"])

    prom_yml["alerting"] = {
        "alertmanagers": [
            {
                "static_configs": [
                    {"targets": ["alertmanager.observability.svc.cluster.local:9093"]}
                ]
            }
        ]
    }
    for sc in prom_yml.get("scrape_configs", []):
        if sc.get("job_name") == "kubernetes-service-endpoints":
            for rc in sc.get("relabel_configs", []):
                if rc.get("source_labels") == ["__meta_kubernetes_service_name"] and rc.get("action") == "keep":
                    rc["regex"] = "(alertmanager|frontend-proxy|frontend-proxy-envoy|.*exporter.*)"
                if rc.get("target_label") == "__metrics_path__" and "alertmanager" in str(rc.get("regex", "")):
                    pass

    cm_cfg["data"]["prometheus.yml"] = yaml.safe_dump(prom_yml, sort_keys=False)
    for k in ("resourceVersion", "uid", "creationTimestamp", "managedFields"):
        cm_cfg["metadata"].pop(k, None)
    cm_cfg["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    kubectl("apply", "-f", "-", input_text=json.dumps(cm_cfg))

    cm_rules = json.loads(kubectl("-n", NAMESPACE, "get", "cm", "prometheus-d6-rules", "-o", "json").stdout)
    rules_key = next(iter(cm_rules["data"].keys()))
    rules_yml = yaml.safe_load(cm_rules["data"][rules_key])
    groups = rules_yml.get("groups", [])
    if not any(g.get("name") == "alertmanager-watchdog" for g in groups):
        groups.append(
            {
                "name": "alertmanager-watchdog",
                "interval": "10s",
                "rules": [
                    {
                        "alert": "Watchdog",
                        "expr": "vector(1)",
                        "labels": {
                            "severity": "info",
                            "env": "prod",
                            "cluster": "docker-desktop",
                            "namespace": "observability",
                            "service": "alertmanager",
                            "team": "sre",
                        },
                        "annotations": {
                            "summary": "Dead-man's-switch monitoring pipeline heartbeat",
                            "runbook_url": "https://runbooks.talkops.io/observability/watchdog",
                        },
                    }
                ],
            }
        )
    rules_yml["groups"] = groups
    cm_rules["data"][rules_key] = yaml.safe_dump(rules_yml, sort_keys=False)
    for k in ("resourceVersion", "uid", "creationTimestamp", "managedFields"):
        cm_rules["metadata"].pop(k, None)
    cm_rules["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    kubectl("apply", "-f", "-", input_text=json.dumps(cm_rules))

    # Wait briefly for kubelet ConfigMap projection or trigger hot reload on prometheus-d6
    try:
        req = urllib.request.Request("http://localhost:29090/-/reload", method="POST")
        urllib.request.urlopen(req, timeout=5.0).read()
    except Exception:
        pass


def write_alertmanager_env() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    backends = [
        {
            "id": "default",
            "base_url": "http://localhost:19093",
            "display_name": "OTEL-APP Primary Alertmanager (observability)",
            "labels": {"env": "prod", "cluster": "docker-desktop", "region": "us-east-1"},
            "is_default": True,
        },
        {
            "id": "prod",
            "base_url": "http://localhost:19093",
            "display_name": "OTEL-APP Production Alertmanager Alias",
            "labels": {"env": "prod", "cluster": "docker-desktop"},
            "is_default": False,
        },
        {
            "id": "staging",
            "base_url": "http://localhost:19094",
            "display_name": "OTEL-APP Staging Alertmanager",
            "labels": {"env": "staging", "cluster": "docker-desktop"},
            "is_default": False,
        },
        {
            "id": "otel-us",
            "base_url": "http://localhost:19093",
            "display_name": "OTEL-APP US-East Regional Alertmanager",
            "labels": {"env": "prod", "region": "us-east-1"},
            "is_default": False,
        },
        {
            "id": "otel-eu",
            "base_url": "http://localhost:19094",
            "display_name": "OTEL-APP EU-Central Regional Alertmanager",
            "labels": {"env": "prod", "region": "eu-central-1"},
            "is_default": False,
        },
        {
            "id": "otel-dr",
            "base_url": "http://localhost:19095",
            "display_name": "OTEL-APP DR Alertmanager (Degraded Reload & Missing Watchdog)",
            "labels": {"env": "dr", "region": "us-west-2"},
            "is_default": False,
        },
        {
            "id": "global-am",
            "base_url": "http://localhost:19096",
            "display_name": "OTEL-APP Global Benchmark Alertmanager",
            "labels": {"env": "benchmark", "tier": "global"},
            "is_default": False,
        },
    ]
    backends_json = json.dumps(backends, separators=(",", ":"))
    env_lines = [
        "ALERTMANAGER_BASE_URL=http://localhost:19093",
        "ALERTMANAGER_URL=http://localhost:19093",
        "ALERTMANAGER_BACKEND_ID=default",
        f"ALERTMANAGER_BACKENDS='{backends_json}'",
        "AM_MAX_SILENCE_MINUTES=1440",
        "AM_SILENCE_CONFIRM_THRESHOLD=50",
        "AM_SILENCE_WARNING_THRESHOLD=50",
        "AM_WATCHDOG_ALERTNAME=Watchdog",
        f"AM_SEED_AUDIT_LOG_PATH={SEED_AUDIT_FILE}",
        "MCP_TOOLSETS=all",
    ]
    ALERTMANAGER_ENV_FILE.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    ALERTMANAGER_ENV_FILE.chmod(0o600)


def clear_all_active_silences(base_url: str) -> None:
    silences = http_json("GET", f"{base_url}/api/v2/silences") or []
    for s in silences:
        st = (s.get("status") or {}).get("state")
        sid = s.get("id")
        if sid and st in ("active", "pending"):
            try:
                http_json("DELETE", f"{base_url}/api/v2/silence/{sid}")
            except Exception:
                pass


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stage_default_backend() -> dict[str, Any]:
    base_url = URLS["default"]
    clear_all_active_silences(base_url)

    now = datetime.now(timezone.utc)
    end_future = fmt_utc(now + timedelta(hours=6))

    # 1. Stage Silences FIRST so subsequently pushed matching alerts enter silenced state immediately
    sil_compliant = http_json(
        "POST",
        f"{base_url}/api/v2/silences",
        {
            "matchers": [
                {"name": "alertname", "value": "OtelLoadGenMaintenance", "isRegex": False, "isEqual": True},
                {"name": "service", "value": "load-generator", "isRegex": False, "isEqual": True},
                {"name": "namespace", "value": "otel-demo", "isRegex": False, "isEqual": True},
            ],
            "startsAt": fmt_utc(now),
            "endsAt": fmt_utc(now + timedelta(minutes=90)),
            "createdBy": "sre-alice@talkops.io",
            "comment": "CHG-4012: Planned load-generator traffic profile maintenance in otel-demo",
        },
    )

    sil_20h_email = http_json(
        "POST",
        f"{base_url}/api/v2/silences",
        {
            "matchers": [
                {"name": "alertname", "value": "OtelEmailMaintenanceMute", "isRegex": False, "isEqual": True},
                {"name": "service", "value": "email", "isRegex": False, "isEqual": True},
                {"name": "namespace", "value": "otel-demo", "isRegex": False, "isEqual": True},
            ],
            "startsAt": fmt_utc(now),
            "endsAt": fmt_utc(now + timedelta(hours=20)),
            "createdBy": "oncall-bob@talkops.io",
            "comment": "INC-2200: 20h window while investigating emailMemoryLeak OOMs on email",
        },
    )

    sil_expiring = http_json(
        "POST",
        f"{base_url}/api/v2/silences",
        {
            "matchers": [
                {"name": "alertname", "value": "OtelPostgresqlMaintenanceReplicaLag", "isRegex": False, "isEqual": True},
                {"name": "service", "value": "postgresql", "isRegex": False, "isEqual": True},
                {"name": "namespace", "value": "otel-demo", "isRegex": False, "isEqual": True},
            ],
            "startsAt": fmt_utc(now),
            "endsAt": fmt_utc(now + timedelta(minutes=26)),
            "createdBy": "dba-priya@talkops.io",
            "comment": "CHG-4099: PostgreSQL 17.6 init.sql index rebuild maintenance",
        },
    )

    sil_stale = http_json(
        "POST",
        f"{base_url}/api/v2/silences",
        {
            "matchers": [
                {"name": "service", "value": "product_catalog", "isRegex": False, "isEqual": True},
                {"name": "namespace", "value": "otel-demo", "isRegex": False, "isEqual": True},
            ],
            "startsAt": fmt_utc(now),
            "endsAt": fmt_utc(now + timedelta(minutes=180)),
            "createdBy": "sre-alice@talkops.io",
            "comment": "CHG-3901: Typoed product_catalog silence matching 0 alerts",
        },
    )

    sil_noncompliant = http_json(
        "POST",
        f"{base_url}/api/v2/silences",
        {
            "matchers": [
                {"name": "service", "value": "quote-legacy-unused", "isRegex": False, "isEqual": True},
            ],
            "startsAt": fmt_utc(now),
            "endsAt": fmt_utc(now + timedelta(hours=48)),
            "createdBy": "unknown",
            "comment": "quick mute",
        },
    )

    # 2. Build rich live alerts on default (:19093)
    alerts: list[dict[str, Any]] = [
        # Heartbeat Watchdog
        {
            "labels": {
                "alertname": "Watchdog",
                "severity": "info",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "observability",
                "service": "alertmanager",
                "team": "sre",
            },
            "annotations": {
                "summary": "Dead-man's-switch monitoring pipeline heartbeat",
                "runbook_url": "https://runbooks.talkops.io/observability/watchdog",
            },
            "startsAt": fmt_utc(now - timedelta(days=7)),
            "endsAt": end_future,
        },
        # Primary Valkey root-cause alert (inhibits OtelCartServiceErrors & OtelCheckoutDegraded)
        {
            "labels": {
                "alertname": "OtelValkeyCartDown",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "valkey-cart",
                "team": "storefront",
                "instance": "valkey-cart-0:6379",
            },
            "annotations": {
                "summary": "valkey-cart Redis/Valkey pod unreachable on :6379 in otel-demo",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/valkey-cart-down",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=28)),
            "endsAt": end_future,
        },
        # Downstream symptoms INHIBITED by OtelValkeyCartDown
        {
            "labels": {
                "alertname": "OtelCartServiceErrors",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "cart-service",
                "team": "storefront",
                "pod": "cart-service-6b9d8f-x1",
            },
            "annotations": {
                "summary": "cart-service GetCart/AddItem failing against valkey-cart:6379",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/cart-errors",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=26)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelCheckoutDegraded",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "checkout-service",
                "team": "checkout",
                "pod": "checkout-service-7c4d2a-k9",
            },
            "annotations": {
                "summary": "checkout-service cart lookup latency degraded",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/checkout-degraded",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=25)),
            "endsAt": end_future,
        },
        # PostgreSQL root cause + downstream cascade
        {
            "labels": {
                "alertname": "OtelPostgresqlOOMKilled",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "postgresql",
                "team": "platform",
                "pod": "postgresql-0",
            },
            "annotations": {
                "summary": "postgresql container OOMKilled at 100Mi memory limit in otel-demo",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/postgresql-oom",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=19)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelProductCatalogErrors",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "product-catalog-service",
                "team": "catalog",
                "pod": "product-catalog-7d9f1b-p2",
            },
            "annotations": {
                "summary": "product-catalog-service SQL connection refused to postgresql:5432",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/product-catalog-db",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=18, seconds=20)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelRecommendationGrpcErrors",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "recommendation",
                "team": "catalog",
                "pod": "recommendation-5c8a4e-r1",
            },
            "annotations": {
                "summary": "recommendation gRPC ListRecommendations failing upstream catalog fetch",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/recommendation-grpc",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=18)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelCheckoutPlaceOrderFailed",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "checkout-service",
                "team": "checkout",
                "pod": "checkout-service-7c4d2a-k9",
            },
            "annotations": {
                "summary": "checkout-service PlaceOrder failing during catalog & payment calls",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/checkout-placeorder",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=17, seconds=45)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelFrontend5xxSpike",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "frontend",
                "team": "storefront",
                "pod": "frontend-84f9b2-f1",
            },
            "annotations": {
                "summary": "Next.js frontend HTTP 5xx error spike on /api/checkout",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/frontend-5xx",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=17, seconds=30)),
            "endsAt": end_future,
        },
        # Checkout critical fast burn & Payment failures (hits otel-checkout-pagerduty -> fail-500!)
        {
            "labels": {
                "alertname": "OtelCheckoutErrorBudgetBurn",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "checkout-service",
                "team": "checkout",
                "instance": "checkout-service.otel-demo.svc:8080",
            },
            "annotations": {
                "summary": "checkout-service 99.9% SLO error budget burning at 16.2x",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/checkout-slo-burn",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=22)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelPaymentFailureHigh",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "payment",
                "team": "checkout",
                "instance": "payment.otel-demo.svc:8080",
            },
            "annotations": {
                "summary": "payment Charge RPC error rate > 45% (flagd paymentFailure active)",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=20)),
            "endsAt": end_future,
        },
        # Invalid severity taxonomy alert (severity="urgent" + missing runbook_url)
        {
            "labels": {
                "alertname": "OtelPaymentGatewayTimeout",
                "severity": "urgent",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "payment",
                "team": "checkout",
            },
            "annotations": {
                "summary": "Payment gateway outbound timeout spike",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=15)),
            "endsAt": end_future,
        },
        # Cart readiness probe alert for targeted single-fingerprint silencing
        {
            "labels": {
                "alertname": "OtelCartReadinessProbeFailed",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "cart-service",
                "team": "storefront",
                "pod": "cart-6b9d8f",
                "instance": "10.244.0.91:8080",
            },
            "annotations": {
                "summary": "cart-service pod cart-6b9d8f failing /readyz Valkey check",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/cart-readiness",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=14)),
            "endsAt": end_future,
        },
        # Kafka warning + Email OOM + Flagd info paging PagerDuty
        {
            "labels": {
                "alertname": "OtelKafkaConsumerLagHigh",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "kafka",
                "team": "platform",
            },
            "annotations": {
                "summary": "Kafka orders consumer group lag > 15,000 messages",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/kafka-lag",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=40)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelEmailPodOOMKilled",
                "severity": "critical",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "email",
                "team": "fulfillment",
                "pod": "email-7bc8f1-e1",
            },
            "annotations": {
                "summary": "email pod OOMKilled at 100Mi memory limit (emailMemoryLeak)",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/email-oom",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=35)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelFlagdConfigReloaded",
                "severity": "info",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "flagd",
                "team": "sre",
            },
            "annotations": {
                "summary": "flagd reloaded demo.flagd.json feature flag configuration",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/flagd-reload",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=12)),
            "endsAt": end_future,
        },
        # Chronic >48h alerts + unrouted fulfillment/catalog alerts missing runbook_url
        {
            "labels": {
                "alertname": "OtelRecommendationMemoryHigh",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "recommendation",
                "team": "catalog",
            },
            "annotations": {
                "summary": "recommendation pod memory usage > 88% of 500Mi limit (recommendationCacheFailure)",
            },
            "startsAt": fmt_utc(now - timedelta(hours=72)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelImageProviderSlowLoad",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "image-provider",
                "team": "fulfillment",
            },
            "annotations": {
                "summary": "image-provider static asset response latency > 5s (imageSlowLoad)",
            },
            "startsAt": fmt_utc(now - timedelta(hours=56)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelShippingDispatchBacklog",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "shipping-service",
                "team": "fulfillment",
            },
            "annotations": {},
            "startsAt": fmt_utc(now - timedelta(minutes=50)),
            "endsAt": end_future,
        },
        # Trigger broken Slack/OpsGenie/Webhook counters
        {
            "labels": {
                "alertname": "OtelIntegrationCanaryAlert",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "observability",
                "service": "otel-collector",
                "team": "ops-integrations",
            },
            "annotations": {
                "summary": "Collector export retry warning",
                "runbook_url": "https://runbooks.talkops.io/observability/collector-retries",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=10)),
            "endsAt": end_future,
        },
        # Alerts suppressed by our active silences (CHG-4012, INC-2200, CHG-4099)
        {
            "labels": {
                "alertname": "OtelLoadGenMaintenance",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "load-generator",
                "team": "sre",
            },
            "annotations": {
                "summary": "load-generator scheduled maintenance restart",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/loadgen",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=30)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelEmailMaintenanceMute",
                "severity": "warning",
                "env": "prod",
                "cluster": "docker-desktop",
                "namespace": "otel-demo",
                "service": "email",
                "team": "fulfillment",
            },
            "annotations": {
                "summary": "email worker heap pressure during leak investigation",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/email-oom",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=45)),
            "endsAt": end_future,
        },
    ]

    # Add 8 critical DB/catalog alerts suppressed by expiring-soon CHG-4099 silence
    for idx in range(1, 9):
        alerts.append(
            {
                "labels": {
                    "alertname": "OtelPostgresqlMaintenanceReplicaLag",
                    "severity": "critical",
                    "env": "prod",
                    "cluster": "docker-desktop",
                    "namespace": "otel-demo",
                    "service": "postgresql",
                    "team": "catalog",
                    "shard": f"pg-part-{idx:02d}",
                },
                "annotations": {
                    "summary": f"PostgreSQL partition {idx:02d} maintenance lag",
                    "runbook_url": "https://runbooks.talkops.io/otel-demo/pg-maint",
                },
                "startsAt": fmt_utc(now - timedelta(minutes=25)),
                "endsAt": end_future,
            }
        )

    # Add 40 per-pod storefront/checkout/catalog active alerts in otel-demo so:
    # - total active alerts on default >= 52 (triggers both >=20 alert-storm grouping AND >=50 SP010 blast-radius gate!)
    storm_specs = [
        ("OtelFrontendHighLatency", "frontend", "storefront", "warning", 10),
        ("OtelFrontendProxyEnvoy5xx", "frontend-proxy", "storefront", "warning", 10),
        ("OtelCheckoutGrpcTimeout", "checkout-service", "checkout", "warning", 10),
        ("OtelProductCatalogLatencyHigh", "product-catalog-service", "catalog", "warning", 10),
    ]
    for aname, svc, tm, sev, cnt in storm_specs:
        for i in range(1, cnt + 1):
            alerts.append(
                {
                    "labels": {
                        "alertname": aname,
                        "severity": sev,
                        "env": "prod",
                        "cluster": "docker-desktop",
                        "namespace": "otel-demo",
                        "service": svc,
                        "team": tm,
                        "pod": f"{svc}-pod-{i:02d}",
                    },
                    "annotations": {
                        "summary": f"{svc} pod {i:02d} elevated latency during dependency incident",
                        "runbook_url": f"https://runbooks.talkops.io/otel-demo/{svc}",
                    },
                    "startsAt": fmt_utc(now - timedelta(minutes=16)),
                    "endsAt": end_future,
                }
            )

    # Add 6 noisy staging alerts so triage eval-09 can distinguish staging noise from prod
    for i in range(1, 7):
        alerts.append(
            {
                "labels": {
                    "alertname": "OtelLoadGeneratorHighCPU",
                    "severity": "warning",
                    "env": "staging",
                    "cluster": "docker-desktop",
                    "namespace": "otel-staging",
                    "service": "load-generator",
                    "team": "sre",
                    "pod": f"load-generator-stg-{i:02d}",
                },
                "annotations": {
                    "summary": f"otel-staging load-generator pod {i:02d} CPU > 85%",
                    "runbook_url": "https://runbooks.talkops.io/otel-demo/loadgen-cpu",
                },
                "startsAt": fmt_utc(now - timedelta(minutes=30)),
                "endsAt": end_future,
            }
        )

    http_json("POST", f"{base_url}/api/v2/alerts", alerts)
    return {
        "silences": {
            "CHG-4012": sil_compliant,
            "INC-2200": sil_20h_email,
            "CHG-4099": sil_expiring,
            "CHG-3901": sil_stale,
            "noncompliant": sil_noncompliant,
        },
        "alerts_pushed": len(alerts),
    }


def stage_staging_backend() -> None:
    base_url = URLS["staging"]
    clear_all_active_silences(base_url)
    now = datetime.now(timezone.utc)
    end_future = fmt_utc(now + timedelta(hours=6))
    alerts = [
        {
            "labels": {
                "alertname": "Watchdog",
                "severity": "info",
                "env": "staging",
                "cluster": "docker-desktop",
                "namespace": "observability",
                "service": "alertmanager",
                "team": "sre",
            },
            "annotations": {
                "summary": "Dead-man's-switch heartbeat (staging / otel-eu)",
                "runbook_url": "https://runbooks.talkops.io/observability/watchdog",
            },
            "startsAt": fmt_utc(now - timedelta(days=5)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelCheckoutStagingLatency",
                "severity": "warning",
                "env": "staging",
                "cluster": "docker-desktop",
                "namespace": "otel-staging",
                "service": "checkout-service",
                "team": "checkout",
            },
            "annotations": {
                "summary": "Staging checkout p95 latency slightly elevated",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/checkout-latency",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=25)),
            "endsAt": end_future,
        },
    ]
    http_json("POST", f"{base_url}/api/v2/alerts", alerts)


def stage_dr_backend() -> None:
    """Stage otel-dr (:19095): NO Watchdog, 2 quiet warnings, failed config reload + failed PagerDuty."""
    base_url = URLS["otel-dr"]
    clear_all_active_silences(base_url)
    now = datetime.now(timezone.utc)
    end_future = fmt_utc(now + timedelta(hours=6))

    # Push ONLY 2 quiet non-Watchdog alerts (so watchdog_status == 'missing' AND OtelPostgresqlDown is absent!)
    alerts = [
        {
            "labels": {
                "alertname": "OtelCurrencyMinorCacheMiss",
                "severity": "warning",
                "env": "dr",
                "cluster": "otel-dr",
                "namespace": "otel-demo",
                "service": "currency",
                "team": "checkout",
            },
            "annotations": {
                "summary": "Minor currency conversion cache miss in DR",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/currency",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=12)),
            "endsAt": end_future,
        },
        {
            "labels": {
                "alertname": "OtelQuoteLatencyMinor",
                "severity": "warning",
                "env": "dr",
                "cluster": "otel-dr",
                "namespace": "otel-demo",
                "service": "quote",
                "team": "fulfillment",
            },
            "annotations": {
                "summary": "Minor shipping quote latency in DR",
                "runbook_url": "https://runbooks.talkops.io/otel-demo/quote",
            },
            "startsAt": fmt_utc(now - timedelta(minutes=10)),
            "endsAt": end_future,
        },
    ]
    http_json("POST", f"{base_url}/api/v2/alerts", alerts)

    # Write a broken YAML config into am-dr's writable /dr-cfg/alertmanager.yml and POST /-/reload
    # so Alertmanager keeps running in-memory but exposes alertmanager_config_last_reload_successful == 0!
    kubectl(
        "-n",
        NAMESPACE,
        "exec",
        "deploy/alertmanager",
        "-c",
        "am-dr",
        "--",
        "sh",
        "-c",
        "printf 'route:\\n  receiver: nonexistent-broken-receiver\\nreceivers: []\\n' > /dr-cfg/alertmanager.yml",
    )
    try:
        req = urllib.request.Request(f"{base_url}/-/reload", method="POST")
        urllib.request.urlopen(req, timeout=4.0).read()
    except urllib.error.HTTPError:
        # Expected HTTP 500 from invalid config reload!
        pass


def stage_global_backend() -> None:
    """Stage global-am (:19096) with Watchdog + 120 warning alerts across 12 namespaces."""
    base_url = URLS["global-am"]
    clear_all_active_silences(base_url)
    now = datetime.now(timezone.utc)
    end_future = fmt_utc(now + timedelta(hours=6))

    alerts: list[dict[str, Any]] = [
        {
            "labels": {
                "alertname": "Watchdog",
                "severity": "info",
                "env": "benchmark",
                "cluster": "otel-global",
                "namespace": "observability",
                "service": "alertmanager",
                "team": "sre",
            },
            "annotations": {
                "summary": "Dead-man's-switch heartbeat (global-am)",
                "runbook_url": "https://runbooks.talkops.io/observability/watchdog",
            },
            "startsAt": fmt_utc(now - timedelta(days=3)),
            "endsAt": end_future,
        }
    ]
    namespaces = ["otel-demo", "otel-staging"] + [f"otel-loadtest-{i:02d}" for i in range(1, 11)]
    services = ["frontend", "frontend-proxy", "checkout-service", "cart-service", "product-catalog-service"]
    for ns_idx, ns in enumerate(namespaces):
        for j in range(1, 11):
            svc = services[(ns_idx + j) % len(services)]
            alerts.append(
                {
                    "labels": {
                        "alertname": "OtelLoadTestHighLatency",
                        "severity": "warning",
                        "env": "benchmark",
                        "cluster": "otel-global",
                        "namespace": ns,
                        "service": svc,
                        "team": "storefront",
                        "pod": f"{svc}-{j:02d}",
                    },
                    "annotations": {
                        "summary": f"Load test p95 latency elevated on {ns}/{svc}-{j:02d}",
                        "runbook_url": "https://runbooks.talkops.io/otel-demo/loadtest-latency",
                    },
                    "startsAt": fmt_utc(now - timedelta(minutes=20)),
                    "endsAt": end_future,
                }
            )
    http_json("POST", f"{base_url}/api/v2/alerts", alerts)


def stage_seed_audit_log() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    entries = [
        {
            "timestamp": fmt_utc(now - timedelta(minutes=52)),
            "backend_id": "default",
            "operation": "create_silence",
            "principal": "anonymous",
            "summary": (
                "Policy violation: [SP003] Matcher 'service=~\"..*\"' uses an unanchored wildcard regex; "
                "[SP008] Silence requires explicit author attribution in 'created_by' (got 'anonymous'); "
                "[SP009] Silence requires a descriptive 'comment' (minimum 3 characters)."
            ),
            "outcome": "denied",
            "details": {"source": "load-generator-chaos-cronjob", "namespace": "otel-demo"},
        },
        {
            "timestamp": fmt_utc(now - timedelta(minutes=44)),
            "backend_id": "default",
            "operation": "create_silence",
            "principal": "chaos-runner",
            "summary": (
                "Policy violation: [SP004] Silence is scoped solely by broad organizational labels (['env']), "
                "which would mute an entire environment, cluster, or severity tier."
            ),
            "outcome": "denied",
            "details": {"matchers": [{"name": "env", "value": "prod", "isRegex": False, "isEqual": True}]},
        },
        {
            "timestamp": fmt_utc(now - timedelta(minutes=38)),
            "backend_id": "default",
            "operation": "create_silence",
            "principal": "chaos-runner",
            "summary": (
                "Policy violation: [SP005] Silencing heartbeat alert 'Watchdog' is prohibited "
                "because it masks dead-man's-switch pipeline failures."
            ),
            "outcome": "denied",
            "details": {"matchers": [{"name": "alertname", "value": "Watchdog", "isRegex": False, "isEqual": True}]},
        },
        {
            "timestamp": fmt_utc(now - timedelta(minutes=30)),
            "backend_id": "default",
            "operation": "create_silence",
            "principal": "sre-alice@talkops.io",
            "summary": "Created maintenance silence for CHG-4012 on load-generator in otel-demo",
            "outcome": "succeeded",
            "details": {"ticket": "CHG-4012"},
        },
    ]
    SEED_AUDIT_FILE.write_text(
        "\n".join(json.dumps(e, separators=(",", ":")) for e in entries) + "\n",
        encoding="utf-8",
    )


def reset_state() -> dict[str, Any]:
    write_alertmanager_env()
    for name, url in URLS.items():
        wait_http_ok(f"{url}/-/ready", timeout_sec=60.0)
    def_info = stage_default_backend()
    stage_staging_backend()
    stage_dr_backend()
    stage_global_backend()
    stage_seed_audit_log()
    # Give Alertmanager dispatch loops 2.5s to fire initial webhook/pagerduty/slack deliveries so /metrics counters populate!
    time.sleep(2.5)
    return def_info


def deploy_all() -> None:
    print("[d7] Applying Alertmanager v0.28.1 + alert-sink + ServiceMonitor manifests in observability...")
    manifests = build_k8s_manifests()
    kubectl("apply", "-f", "-", input_text=manifests)
    kubectl("-n", NAMESPACE, "rollout", "restart", "deploy/alert-sink")
    kubectl("-n", NAMESPACE, "rollout", "restart", "deploy/alertmanager")
    kubectl("-n", NAMESPACE, "rollout", "status", "deploy/alert-sink", "--timeout=120s")
    kubectl("-n", NAMESPACE, "rollout", "status", "deploy/alertmanager", "--timeout=180s")

    print("[d7] Wiring prometheus-d6 alerting & scrape config to alertmanager...")
    wire_prometheus_d6()

    print("[d7] Staging live multi-backend alerts, silences, failed reload, and seed audit log...")
    info = reset_state()
    print(json.dumps({"status": "ready", "urls": URLS, "staged": info}, indent=2))


def main(argv: list[str]) -> int:
    sub = argv[1] if len(argv) > 1 else "reset"
    if sub == "deploy":
        deploy_all()
    else:
        info = reset_state()
        print(json.dumps({"status": "reset_complete", "target": sub, "staged": info}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
