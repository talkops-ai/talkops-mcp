#!/usr/bin/env python3
"""Domain 9 (Grafana Tempo 2.x/3.x) Live Kubernetes Battleground Deployer & Idempotent Stager.

Deploys Grafana Tempo 2.7.1 in namespace `observability` on `docker-desktop` exposed via
`Service/tempo` (:3200, :4317, :4318, :9095 in-cluster) and `Service/tempo-lb`
(`http://localhost:13200` HTTP API + `:14317`/`:14318` OTLP + companion diagnostic ports
`:13201`..`:13204`), installs `tempo.grafana.com/v1alpha1` CRDs (`TempoStack`, `TempoMonolithic`),
enables live OTLP trace export on `OTEL-APP` workloads in `otel-demo`, writes
`evals/workspaces/.tempo.env`, and idempotently stages multi-tenant OTLP traces, discarded-span
counters, runtime `/api/overrides`, and Kubernetes Tempo Operator CRs.

Usage:
  python3 scripts/stage_d9_tempo.py deploy
  python3 scripts/stage_d9_tempo.py reset [skill-name]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

KUBE_CONTEXT = "docker-desktop"
NAMESPACE = "observability"
OTEL_NAMESPACE = "otel-demo"
TEMPO_IMAGE = "grafana/tempo:2.7.1"
TEMPO_LOCAL_URL = "http://localhost:13200"
TEMPO_OTLP_HTTP_URL = "http://localhost:14318"

DEVOPS_PLUGINS_ROOT = Path(os.environ.get("DEVOPS_PLUGINS_ROOT", Path(__file__).resolve().parents[4] / "devops-plugins"))
WORKSPACES_DIR = DEVOPS_PLUGINS_ROOT / "evals" / "workspaces"
TEMPO_ENV_FILE = WORKSPACES_DIR / ".tempo.env"

TEMPO_CONFIG_YAML = """stream_over_http_enabled: true
multitenancy_enabled: true
target: all

server:
  http_listen_port: 3200
  grpc_listen_port: 9095
  log_level: warn

query_frontend:
  search:
    default_result_limit: 20
    max_result_limit: 100
  metrics:
    max_duration: 3h

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  max_block_duration: 3h
  trace_idle_period: 3h
  flush_check_period: 10s

compactor:
  compaction:
    block_retention: 336h
    compaction_cycle: 5s

metrics_generator:
  ring:
    kvstore:
      store: inmemory
  registry:
    external_labels:
      source: tempo
      cluster: docker-desktop
  storage:
    path: /var/tempo/generator/wal
    remote_write:
      - url: http://prometheus-d6.observability.svc.cluster.local:9090/api/v1/write
        send_exemplars: true
  traces_storage:
    path: /var/tempo/generator/traces
  processor:
    service_graphs:
      wait: 2s
      dimensions: [service.namespace]
      peer_attributes: [peer.service, db.system, db.name, server.address, net.peer.name, messaging.system]
    span_metrics:
      dimensions: [service.namespace, k8s.pod.name, service.version, http.route]
      enable_target_info: true
    local_blocks:
      flush_to_storage: true
      filter_server_spans: false
      trace_idle_period: 2s
      flush_check_period: 2s
      complete_block_timeout: 3h
      max_block_duration: 5s

storage:
  trace:
    backend: local
    blocklist_poll: 2s
    block:
      version: vParquet4
    wal:
      path: /var/tempo/wal
    local:
      path: /var/tempo/blocks

overrides:
  defaults:
    ingestion:
      rate_limit_bytes: 52428800
      burst_size_bytes: 78643200
      max_traces_per_user: 50000
    global:
      max_bytes_per_trace: 10485760
    metrics_generator:
      processors: [service-graphs, span-metrics, local-blocks]
      generate_native_histograms: both
      ingestion_time_range_slack: 3h
  per_tenant_override_config: /var/tempo/runtime-overrides.yaml
  per_tenant_override_period: 2s
  user_configurable_overrides:
    enabled: true
    poll_interval: 2s
    client:
      backend: local
      confirm_versioning: false
      local:
        path: /var/tempo/uco
"""

TEMPO_STATIC_OVERRIDES_YAML = """overrides:
  otel-flood-drop:
    ingestion:
      rate_limit_bytes: 128
      burst_size_bytes: 128
      max_traces_per_user: 1
    global:
      max_bytes_per_trace: 256
"""

COMPANION_PROFILES_PY = r"""import copy, http.server, json, os, socketserver, threading, urllib.error, urllib.request

TEMPO_UPSTREAM = "http://127.0.0.1:3200"
UCO_STATE_FILE = "/var/tempo/uco_gateway_state.json"
RUNTIME_OVERRIDES_YAML = "/var/tempo/runtime-overrides.yaml"
_UCO_LOCK = threading.Lock()

def _load_uco_state():
    if os.path.exists(UCO_STATE_FILE):
        try:
            with open(UCO_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"tenants": {}}

def _write_runtime_overrides_yaml(state):
    lines = [
        "overrides:",
        "  otel-flood-drop:",
        "    ingestion:",
        "      rate_limit_bytes: 128",
        "      burst_size_bytes: 128",
        "      max_traces_per_user: 1",
        "    global:",
        "      max_bytes_per_trace: 256",
    ]
    for tenant_id, entry in sorted(state.get("tenants", {}).items()):
        if tenant_id == "otel-flood-drop":
            continue
        doc = entry.get("overrides") or {}
        if not doc:
            continue
        lines.append(f"  {tenant_id}:")
        ing = {}
        if "ingestion_rate_limit_bytes" in doc:
            ing["rate_limit_bytes"] = int(doc["ingestion_rate_limit_bytes"])
        if "ingestion_burst_size_bytes" in doc:
            ing["burst_size_bytes"] = int(doc["ingestion_burst_size_bytes"])
        if "max_traces_per_user" in doc:
            ing["max_traces_per_user"] = int(doc["max_traces_per_user"])
        if isinstance(doc.get("ingestion"), dict):
            ing.update(doc["ingestion"])
        if ing:
            lines.append("    ingestion:")
            for k, v in ing.items():
                lines.append(f"      {k}: {v}")
        glob = {}
        if "max_bytes_per_trace" in doc:
            glob["max_bytes_per_trace"] = int(doc["max_bytes_per_trace"])
        if isinstance(doc.get("global"), dict):
            glob.update(doc["global"])
        if glob:
            lines.append("    global:")
            for k, v in glob.items():
                lines.append(f"      {k}: {v}")
        mg = doc.get("metrics_generator")
        if isinstance(mg, dict) and isinstance(mg.get("processors"), list):
            procs_str = ", ".join(str(p) for p in mg["processors"])
            lines.append("    metrics_generator:")
            lines.append(f"      processors: [{procs_str}]")
    tmp = RUNTIME_OVERRIDES_YAML + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, RUNTIME_OVERRIDES_YAML)

def _rfc7386_merge(target, patch):
    res = copy.deepcopy(target) if isinstance(target, dict) else {}
    for k, v in patch.items():
        if v is None:
            res.pop(k, None)
        elif isinstance(v, dict):
            res[k] = _rfc7386_merge(res.get(k, {}), v)
        else:
            res[k] = copy.deepcopy(v)
    return res

def _proxy_upstream(handler, override_tenant=None):
    url = f"{TEMPO_UPSTREAM}{handler.path}"
    clen = int(handler.headers.get("Content-Length", "0") or "0")
    req_body = handler.rfile.read(clen) if clen > 0 else None
    headers = {k: v for k, v in handler.headers.items() if k.lower() not in ("host", "connection", "content-length")}
    if override_tenant and "x-scope-orgid" not in {k.lower() for k in headers}:
        headers["X-Scope-OrgID"] = override_tenant
    req = urllib.request.Request(url, data=req_body, headers=headers, method=handler.command)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
            handler.send_response(resp.status)
            for hk, hv in resp.headers.items():
                if hk.lower() not in ("transfer-encoding", "connection", "content-length"):
                    handler.send_header(hk, hv)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            if handler.command != "HEAD":
                handler.wfile.write(body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        handler.send_response(exc.code)
        handler.send_header("Content-Type", exc.headers.get("Content-Type", "text/plain"))
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

def _send_json(handler, status, obj, extra_headers=None):
    raw = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    if extra_headers:
        for k, v in extra_headers.items():
            handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def _send_text(handler, status, text, ctype="text/plain; charset=utf-8"):
    raw = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

class PrimaryGatewayHandler(http.server.BaseHTTPRequestHandler):
    # Port 3210: Transparent proxy to real Tempo 127.0.0.1:3200 + ETag-versioned /api/overrides synced to runtime-overrides.yaml & Tempo UCO.
    def log_message(self, fmt, *args): pass
    def _tenant(self):
        for hk, hv in self.headers.items():
            if hk.lower() == "x-scope-orgid" and hv.strip():
                return hv.strip()
        return "single-tenant"
    def _if_match(self):
        for hk, hv in self.headers.items():
            if hk.lower() == "if-match":
                return hv.strip()
        return None
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/api/overrides":
            tenant = self._tenant()
            with _UCO_LOCK:
                state = _load_uco_state()
                entry = state.get("tenants", {}).get(tenant)
                if not entry:
                    entry = {
                        "version": 1,
                        "etag": f'"etag-{tenant}-v1"',
                        "overrides": {
                            "ingestion_rate_limit_bytes": 52428800,
                            "ingestion_burst_size_bytes": 78643200,
                            "max_bytes_per_trace": 10485760,
                            "max_traces_per_user": 50000,
                            "block_retention": "336h",
                            "metrics_generator": {"processors": ["service-graphs", "span-metrics", "local-blocks"]},
                        },
                    }
                return _send_json(self, 200, entry["overrides"], extra_headers={"ETag": entry["etag"]})
        return _proxy_upstream(self)
    def _mutate_overrides(self, replace_full=False):
        tenant = self._tenant()
        clen = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(clen).decode("utf-8") if clen > 0 else "{}"
        try:
            payload = json.loads(raw)
        except Exception as exc:
            return _send_text(self, 400, f"invalid JSON: {exc}")
        if_match = self._if_match()
        with _UCO_LOCK:
            state = _load_uco_state()
            tenants = state.setdefault("tenants", {})
            cur = tenants.get(tenant)
            cur_etag = cur["etag"] if cur else f'"etag-{tenant}-v1"'
            if if_match and if_match not in ("*", '""') and if_match != cur_etag:
                return _send_text(self, 412, f"Precondition Failed: expected {cur_etag}, got {if_match}")
            base_doc = {} if (replace_full or not cur) else cur.get("overrides", {})
            merged = _rfc7386_merge(base_doc, payload) if not replace_full else copy.deepcopy(payload)
            next_ver = 1 if (replace_full and if_match == "*") else ((cur["version"] + 1) if cur else 2)
            new_etag = f'"etag-{tenant}-v{next_ver}"'
            tenants[tenant] = {"version": next_ver, "etag": new_etag, "overrides": merged}
            with open(UCO_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            _write_runtime_overrides_yaml(state)
            # Also sync metrics_generator/cost_attribution/forwarders to real Tempo 127.0.0.1:3200/api/overrides
            uco_sub = {k: v for k, v in merged.items() if k in ("metrics_generator", "cost_attribution", "forwarders")}
            if uco_sub:
                try:
                    ureq = urllib.request.Request(
                        f"{TEMPO_UPSTREAM}/api/overrides",
                        data=json.dumps(uco_sub).encode("utf-8"),
                        headers={"Content-Type": "application/json", "X-Scope-OrgID": tenant, "If-Match": "0"},
                        method="POST",
                    )
                    urllib.request.urlopen(ureq, timeout=5).read()
                except Exception:
                    pass
            return _send_json(self, 200, merged, extra_headers={"ETag": new_etag})
    def do_PATCH(self):
        if self.path.split("?", 1)[0] == "/api/overrides":
            return self._mutate_overrides(replace_full=False)
        return _proxy_upstream(self)
    def do_POST(self):
        if self.path.split("?", 1)[0] == "/api/overrides":
            return self._mutate_overrides(replace_full=True)
        return _proxy_upstream(self)

class NoLocalBlocksHandler(http.server.BaseHTTPRequestHandler):
    # Port 3201: Real Tempo search/trace proxy, but metrics_generator processors & overrides API disabled.
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/status/config":
            return _send_json(self, 200, {
                "multitenancy_enabled": True,
                "metrics_generator": {"processor": {}},
                "overrides": {
                    "defaults": {"metrics_generator": {"processors": []}},
                    "user_configurable_overrides": {"enabled": False},
                },
                "storage": {"trace": {"backend": "local", "block": {"version": "vParquet3"}}},
            })
        if p.startswith("/api/metrics/"):
            return _send_text(self, 400, "metrics-generator local-blocks processor is not enabled on this Tempo instance")
        if p == "/api/overrides":
            return _send_text(self, 404, "404 page not found: user_configurable_overrides disabled")
        return _proxy_upstream(self, override_tenant="otel-demo")

class OtelUsNoMetricsHandler(http.server.BaseHTTPRequestHandler):
    # Port 3202: Reachable Tempo query path, /metrics unreachable (404) -> INGESTION_METRICS_UNREACHABLE.
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/metrics":
            return _send_text(self, 404, "404 /metrics not exposed on query-frontend gateway")
        return _proxy_upstream(self, override_tenant="otel-demo")

class Tempo2xDegradedRingHandler(http.server.BaseHTTPRequestHandler):
    # Port 3203: Tempo 2.6.1 microservices with UNHEALTHY ingester ring & failed gossip 7946 compactor ring.
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/ready":
            return _send_text(self, 200, "ready")
        if p == "/api/status/buildinfo":
            return _send_json(self, 200, {"version": "2.6.1", "branch": "HEAD", "goVersion": "go1.23.2"})
        if p == "/status/services":
            return _send_json(self, 200, {
                "distributor": "Running",
                "ingester": "Stopping",
                "querier": "Running",
                "query-frontend": "Running",
                "compactor": "Starting",
            })
        if p == "/status/config":
            return _send_json(self, 200, {
                "multitenancy_enabled": False,
                "overrides": {
                    "defaults": {"metrics_generator": {"processors": ["service-graphs", "span-metrics", "local-blocks"]}},
                    "user_configurable_overrides": {"enabled": True},
                },
                "storage": {"trace": {"backend": "s3", "block": {"version": "vParquet3"}}},
            })
        if p == "/distributor/ring":
            return _send_text(self, 200, "<html><body><table><tr><td>tempo-distributor-0</td><td>ACTIVE</td></tr><tr><td>tempo-distributor-1</td><td>ACTIVE</td></tr></table></body></html>", "text/html")
        if p == "/ingester/ring":
            return _send_text(self, 200, "<html><body><table><tr><td>tempo-ingester-0</td><td>ACTIVE</td></tr><tr><td>tempo-ingester-1</td><td>LEAVING</td></tr><tr><td>tempo-ingester-2</td><td>UNHEALTHY</td></tr></table></body></html>", "text/html")
        if p == "/compactor/ring":
            return _send_text(self, 503, "memberlist gossip port 7946 connection refused on headless service")
        if p == "/metrics":
            return _send_text(self, 200, 'tempo_distributor_spans_received_total 18420\n')
        return _proxy_upstream(self, override_tenant="otel-demo")

class Tempo3xDistributedHandler(http.server.BaseHTTPRequestHandler):
    # Port 3204: Tempo 3.0.1 distributed architecture (ingest -> Kafka -> block-builder -> vParquet4) + partition lag.
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/ready":
            return _send_text(self, 200, "ready")
        if p == "/api/status/buildinfo":
            return _send_json(self, 200, {"version": "3.0.1", "branch": "release-3.0", "goVersion": "go1.24.0"})
        if p == "/status/services":
            return _send_json(self, 200, {
                "distributor": "Running",
                "ingest": "Running",
                "live-store": "Running",
                "block-builder": "Running",
                "querier": "Running",
                "query-frontend": "Running",
                "compactor": "Running",
            })
        if p == "/status/config":
            return _send_json(self, 200, {
                "multitenancy_enabled": True,
                "ingest": {"kafka": {"brokers": ["tempo-kafka:9092"]}},
                "block_builder": {"consume_concurrency": 2},
                "live_store": {"enabled": True},
                "overrides": {
                    "defaults": {"metrics_generator": {"processors": ["service-graphs", "span-metrics", "local-blocks"]}},
                    "user_configurable_overrides": {"enabled": True},
                },
                "storage": {"trace": {"backend": "s3", "block": {"version": "vParquet4"}}},
            })
        if p in ("/live-store/ring", "/partition-ring"):
            return _send_text(self, 200, "<html><body><table><tr><td>tempo-3x-0</td><td>ACTIVE</td></tr><tr><td>tempo-3x-1</td><td>ACTIVE</td></tr></table></body></html>", "text/html")
        if p == "/metrics":
            prom = (
                'tempo_distributor_spans_received_total{tenant="otel-demo"} 94500\n'
                'tempo_ingest_group_partition_lag_seconds{group="block-builder",partition="0"} 238.4\n'
                'tempo_ingest_group_partition_lag_seconds{group="block-builder",partition="1"} 194.2\n'
                'tempo_block_builder_owned_partitions 2\n'
            )
            return _send_text(self, 200, prom)
        org = None
        for hk, hv in self.headers.items():
            if hk.lower() == "x-scope-orgid":
                org = hv
                break
        if not org:
            return _send_text(self, 401, "no org id: X-Scope-OrgID header required when multitenancy_enabled=true")
        return _proxy_upstream(self, override_tenant=org)

class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    if not os.path.exists(RUNTIME_OVERRIDES_YAML):
        _write_runtime_overrides_yaml(_load_uco_state())
    servers = [
        ThreadedServer(("0.0.0.0", 3210), PrimaryGatewayHandler),
        ThreadedServer(("0.0.0.0", 3201), NoLocalBlocksHandler),
        ThreadedServer(("0.0.0.0", 3202), OtelUsNoMetricsHandler),
        ThreadedServer(("0.0.0.0", 3203), Tempo2xDegradedRingHandler),
        ThreadedServer(("0.0.0.0", 3204), Tempo3xDistributedHandler),
    ]
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Event().wait()
"""


def _build_tempo_crd_manifest(kind: str, plural: str, singular: str, spec_props: dict[str, Any]) -> dict[str, Any]:
    open_schema = {
        "type": "object",
        "properties": {
            "spec": {
                "type": "object",
                "properties": spec_props,
                "x-kubernetes-preserve-unknown-fields": True,
            },
            "status": {
                "type": "object",
                "x-kubernetes-preserve-unknown-fields": True,
            },
        },
        "x-kubernetes-preserve-unknown-fields": True,
    }
    return {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": f"{plural}.tempo.grafana.com"},
        "spec": {
            "group": "tempo.grafana.com",
            "names": {
                "kind": kind,
                "listKind": f"{kind}List",
                "plural": plural,
                "singular": singular,
            },
            "scope": "Namespaced",
            "versions": [
                {
                    "name": "v1alpha1",
                    "served": True,
                    "storage": True,
                    "schema": {"openAPIV3Schema": open_schema},
                    "subresources": {"status": {}},
                }
            ],
        },
    }


def _kubectl(*args: str, stdin_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl", "--context", KUBE_CONTEXT, *args]
    return subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        check=check,
    )


def _http_req(
    base_url: str,
    method: str,
    path: str,
    *,
    org_id: str | None = "otel-demo",
    body: bytes | str | None = None,
    content_type: str = "application/json",
    extra_headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: int = 15,
) -> tuple[int, str, dict[str, str]]:
    url = f"{base_url}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = body.encode("utf-8") if isinstance(body, str) else body
    headers: dict[str, str] = {}
    if org_id:
        headers["X-Scope-OrgID"] = org_id
    if data is not None:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()}
            return resp.status, resp.read().decode("utf-8", errors="replace"), resp_headers
    except urllib.error.HTTPError as exc:
        resp_headers = {k: v for k, v in exc.headers.items()} if exc.headers else {}
        return exc.code, exc.read().decode("utf-8", errors="replace"), resp_headers


def wait_for_tempo_ready(max_wait_sec: int = 90) -> None:
    deadline = time.time() + max_wait_sec
    last_err = ""
    while time.time() < deadline:
        try:
            code, txt, _ = _http_req(TEMPO_LOCAL_URL, "GET", "/ready", org_id=None, timeout=3)
            c2, _, _ = _http_req("http://localhost:13201", "GET", "/ready", org_id=None, timeout=3)
            if code == 200 and c2 == 200:
                print(f"[OK] Tempo ready at {TEMPO_LOCAL_URL} ({txt.strip()}) + companion ports :13201..:13204")
                return
            last_err = f"HTTP {code}: {txt.strip()}"
        except Exception as exc:
            last_err = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for Tempo at {TEMPO_LOCAL_URL}: {last_err}")


def install_tempo_crds_and_workload() -> None:
    print("[1/5] Installing tempo.grafana.com/v1alpha1 CRDs (TempoStack, TempoMonolithic)...")
    tempostack_props = {
        k: {"type": "object", "x-kubernetes-preserve-unknown-fields": True}
        for k in ("storage", "retention", "resources", "search", "tenants", "template", "observability", "extraConfig")
    }
    tempostack_props["storageSize"] = {"type": "string"}
    tempostack_props["replicationFactor"] = {"type": "integer"}
    tempomono_props = {
        k: {"type": "object", "x-kubernetes-preserve-unknown-fields": True}
        for k in ("storage", "resources", "multitenancy", "jaegerui", "observability", "extraConfig")
    }
    crds = [
        _build_tempo_crd_manifest("TempoStack", "tempostacks", "tempostack", tempostack_props),
        _build_tempo_crd_manifest("TempoMonolithic", "tempomonolithics", "tempomonolithic", tempomono_props),
    ]
    crd_yaml = "\n---\n".join(yaml.safe_dump(c, sort_keys=False) for c in crds)
    _kubectl("apply", "-f", "-", stdin_text=crd_yaml)

    print(f"[2/5] Deploying {TEMPO_IMAGE} + companion diagnostic endpoints + Service/tempo + Service/tempo-lb (:13200)...")
    manifests = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "tempo-d9-config", "namespace": NAMESPACE},
            "data": {
                "tempo.yaml": TEMPO_CONFIG_YAML,
                "overrides.yaml": TEMPO_STATIC_OVERRIDES_YAML,
                "companion_profiles.py": COMPANION_PROFILES_PY,
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "tempo",
                "namespace": NAMESPACE,
                "labels": {"app": "tempo", "app.kubernetes.io/name": "tempo", "domain": "d9-tempo"},
            },
            "spec": {
                "replicas": 1,
                "strategy": {"type": "Recreate"},
                "selector": {"matchLabels": {"app": "tempo"}},
                "template": {
                    "metadata": {"labels": {"app": "tempo", "app.kubernetes.io/name": "tempo", "domain": "d9-tempo"}},
                    "spec": {
                        "securityContext": {"fsGroup": 10001, "runAsUser": 10001, "runAsGroup": 10001},
                        "initContainers": [
                            {
                                "name": "init-dirs",
                                "image": "busybox:1.36",
                                "command": [
                                    "sh",
                                    "-c",
                                    "mkdir -p /var/tempo/wal /var/tempo/blocks /var/tempo/uco /var/tempo/generator/wal /var/tempo/generator/traces && cp /etc/tempo/overrides.yaml /var/tempo/runtime-overrides.yaml",
                                ],
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/etc/tempo"},
                                    {"name": "data", "mountPath": "/var/tempo"},
                                ],
                            }
                        ],
                        "containers": [
                            {
                                "name": "tempo",
                                "image": TEMPO_IMAGE,
                                "args": ["-config.file=/etc/tempo/tempo.yaml"],
                                "ports": [
                                    {"name": "http", "containerPort": 3200},
                                    {"name": "grpc", "containerPort": 9095},
                                    {"name": "otlp-grpc", "containerPort": 4317},
                                    {"name": "otlp-http", "containerPort": 4318},
                                ],
                                "readinessProbe": {
                                    "httpGet": {"path": "/ready", "port": 3200},
                                    "initialDelaySeconds": 4,
                                    "periodSeconds": 4,
                                },
                                "resources": {
                                    "requests": {"cpu": "250m", "memory": "512Mi"},
                                    "limits": {"cpu": "3000m", "memory": "2Gi"},
                                },
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/etc/tempo"},
                                    {"name": "data", "mountPath": "/var/tempo"},
                                ],
                            },
                            {
                                "name": "tempo-profiles",
                                "image": "python:3.12-alpine",
                                "command": ["python3", "/etc/tempo/companion_profiles.py"],
                                "ports": [
                                    {"name": "gw", "containerPort": 3210},
                                    {"name": "no-lb", "containerPort": 3201},
                                    {"name": "otel-us", "containerPort": 3202},
                                    {"name": "ring-deg", "containerPort": 3203},
                                    {"name": "tempo-3x", "containerPort": 3204},
                                ],
                                "resources": {
                                    "requests": {"cpu": "20m", "memory": "32Mi"},
                                    "limits": {"cpu": "200m", "memory": "128Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/etc/tempo"},
                                    {"name": "data", "mountPath": "/var/tempo"},
                                ],
                            },
                        ],
                        "volumes": [
                            {"name": "config", "configMap": {"name": "tempo-d9-config"}},
                            {"name": "data", "emptyDir": {}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "tempo",
                "namespace": NAMESPACE,
                "labels": {"app": "tempo", "app.kubernetes.io/name": "tempo"},
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "tempo"},
                "ports": [
                    {"name": "http", "port": 3200, "targetPort": 3200},
                    {"name": "grpc", "port": 9095, "targetPort": 9095},
                    {"name": "otlp-grpc", "port": 4317, "targetPort": 4317},
                    {"name": "otlp-http", "port": 4318, "targetPort": 4318},
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "tempo-lb", "namespace": NAMESPACE},
            "spec": {
                "type": "LoadBalancer",
                "selector": {"app": "tempo"},
                "ports": [
                    {"name": "http", "port": 13200, "targetPort": 3210},
                    {"name": "no-local-blocks", "port": 13201, "targetPort": 3201},
                    {"name": "otel-us", "port": 13202, "targetPort": 3202},
                    {"name": "ring-degraded", "port": 13203, "targetPort": 3203},
                    {"name": "tempo-3x", "port": 13204, "targetPort": 3204},
                    {"name": "otlp-grpc", "port": 14317, "targetPort": 4317},
                    {"name": "otlp-http", "port": 14318, "targetPort": 4318},
                ],
            },
        },
    ]
    bundle_yaml = "\n---\n".join(yaml.safe_dump(m, sort_keys=False) for m in manifests)
    _kubectl("apply", "-f", "-", stdin_text=bundle_yaml)
    _kubectl("rollout", "status", "deploy/tempo", "-n", NAMESPACE, "--timeout=120s")


def wire_otel_app_deployments() -> None:
    """Wire live OTEL-APP deployments in otel-demo to export OTLP traces to Tempo."""
    print("[3/5] Wiring OTEL-APP deployments in otel-demo to export live OTLP traces -> Tempo :4318...")
    services_to_wire = ["checkout", "currency", "frontend", "payment", "shipping"]
    for svc in services_to_wire:
        chk = _kubectl("get", f"deploy/{svc}", "-n", OTEL_NAMESPACE, check=False)
        if chk.returncode != 0:
            continue
        _kubectl(
            "set",
            "env",
            f"deploy/{svc}",
            "-n",
            OTEL_NAMESPACE,
            "OTEL_TRACES_EXPORTER=otlp",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://tempo.observability.svc.cluster.local:4318/v1/traces",
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf",
            "OTEL_EXPORTER_OTLP_HEADERS=X-Scope-OrgID=otel-demo",
            check=False,
        )


def write_tempo_env() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    backends = [
        {
            "id": "default",
            "base_url": "http://localhost:13200",
            "type": "tempo",
            "display_name": "Primary Observability Tempo 2.7 (Monolithic + Metrics Generator)",
            "deployment_mode": "monolithic",
            "multi_tenant": True,
            "default_tenant": "otel-demo",
            "llm_format_supported": False,
            "prometheus_url": "http://localhost:29090",
        },
        {
            "id": "tempo-no-local-blocks",
            "base_url": "http://localhost:13201",
            "type": "tempo",
            "display_name": "Tempo Without local-blocks / Overrides API",
            "deployment_mode": "monolithic",
            "multi_tenant": True,
            "default_tenant": "otel-demo",
            "llm_format_supported": False,
        },
        {
            "id": "otel-us",
            "base_url": "http://localhost:13202",
            "type": "tempo-gateway",
            "display_name": "Regional US Tempo Gateway (No /metrics scrape)",
            "deployment_mode": "microservices",
            "multi_tenant": True,
            "default_tenant": "otel-demo",
            "llm_format_supported": False,
        },
        {
            "id": "otel-eu",
            "base_url": "http://localhost:13299",
            "type": "tempo-gateway",
            "display_name": "Regional EU Tempo Gateway (Unreachable)",
            "deployment_mode": "microservices",
            "multi_tenant": True,
            "default_tenant": "otel-demo",
            "timeout": 2,
            "llm_format_supported": False,
        },
        {
            "id": "tempo-2x-degraded-ring",
            "base_url": "http://localhost:13203",
            "type": "tempo",
            "display_name": "Tempo 2.6 Distributed (Degraded Ingester Ring)",
            "deployment_mode": "microservices",
            "multi_tenant": False,
            "llm_format_supported": False,
        },
        {
            "id": "tempo-3x-distributed",
            "base_url": "http://localhost:13204",
            "type": "tempo",
            "display_name": "Tempo 3.0 Distributed (Kafka + vParquet4)",
            "deployment_mode": "microservices",
            "multi_tenant": True,
            "default_tenant": None,
            "llm_format_supported": False,
        },
    ]
    env_content = (
        f"TEMPO_BASE_URL={TEMPO_LOCAL_URL}\n"
        f"TEMPO_URL={TEMPO_LOCAL_URL}\n"
        "TEMPO_BACKEND_ID=default\n"
        "TEMPO_TYPE=tempo\n"
        "TEMPO_DEPLOYMENT_MODE=monolithic\n"
        "TEMPO_MULTI_TENANT=true\n"
        "TEMPO_DEFAULT_TENANT=otel-demo\n"
        f"TEMPO_BACKENDS='{json.dumps(backends, separators=(',', ':'))}'\n"
        "K8S_ENABLED=true\n"
        f"K8S_CONTEXT={KUBE_CONTEXT}\n"
        "MCP_ALLOW_WRITE=true\n"
        "MCP_TOOLSETS=all\n"
    )
    TEMPO_ENV_FILE.write_text(env_content, encoding="utf-8")
    TEMPO_ENV_FILE.chmod(0o600)
    print(f"[OK] Wrote {TEMPO_ENV_FILE}")


def _ns(dt: datetime) -> str:
    return str(int(dt.timestamp() * 1_000_000_000))


def _otlp_kv(k: str, v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"key": k, "value": {"boolValue": v}}
    if isinstance(v, int):
        return {"key": k, "value": {"intValue": str(v)}}
    if isinstance(v, float):
        return {"key": k, "value": {"doubleValue": v}}
    return {"key": k, "value": {"stringValue": str(v)}}


def _make_rs(
    service_name: str,
    spans: list[dict[str, Any]],
    *,
    namespace: str = "otel-demo",
    version: str = "2.2.0",
    pod: str | None = None,
    node: str = "docker-desktop",
    scope_name: str = "io.opentelemetry.auto",
) -> dict[str, Any]:
    res_attrs = [
        _otlp_kv("service.name", service_name),
        _otlp_kv("service.namespace", namespace),
        _otlp_kv("service.version", version),
        _otlp_kv("k8s.namespace.name", namespace),
        _otlp_kv("k8s.pod.name", pod or f"{service_name}-84c9c9-5hxhp"),
        _otlp_kv("k8s.node.name", node),
        _otlp_kv("k8s.deployment.name", service_name),
        _otlp_kv("deployment.environment.name", "prod" if namespace == "otel-demo" else "staging"),
    ]
    return {
        "resource": {"attributes": res_attrs},
        "scopeSpans": [{"scope": {"name": scope_name, "version": "1.26.0"}, "spans": spans}],
    }


def _span(
    trace_id: str,
    span_id: str,
    name: str,
    start_dt: datetime,
    dur_ms: float,
    *,
    parent_id: str = "",
    kind: int = 2,  # 1=INTERNAL, 2=SERVER, 3=CLIENT, 4=PRODUCER, 5=CONSUMER
    error: bool = False,
    status_msg: str = "",
    attrs: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    end_dt = start_dt + timedelta(milliseconds=dur_ms)
    sp: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": _ns(start_dt),
        "endTimeUnixNano": _ns(end_dt),
        "attributes": [_otlp_kv(k, v) for k, v in (attrs or {}).items()],
        "status": {"code": 2 if error else 1, "message": status_msg},
    }
    if parent_id:
        sp["parentSpanId"] = parent_id
    if events:
        sp["events"] = events
    if links:
        sp["links"] = links
    return sp


def _exc_event(ts: datetime, exc_type: str, exc_msg: str, stacktrace: str) -> dict[str, Any]:
    return {
        "timeUnixNano": _ns(ts),
        "name": "exception",
        "attributes": [
            _otlp_kv("exception.type", exc_type),
            _otlp_kv("exception.message", exc_msg),
            _otlp_kv("exception.stacktrace", stacktrace),
        ],
    }


def _send_otlp(resource_spans: list[dict[str, Any]], org_id: str = "otel-demo") -> None:
    # Batch in chunks of 30 resourceSpans so payloads stay small and fast
    for idx in range(0, len(resource_spans), 30):
        batch = {"resourceSpans": resource_spans[idx : idx + 30]}
        code, resp, _ = _http_req(
            TEMPO_OTLP_HTTP_URL,
            "POST",
            "/v1/traces",
            org_id=org_id,
            body=json.dumps(batch),
        )
        if code not in (200, 202, 204):
            raise RuntimeError(f"OTLP trace push failed ({code}) for tenant {org_id}: {resp}")


def trigger_discarded_spans() -> None:
    """Trigger real rate_limited and trace_too_large discarded spans on tenant otel-demo (and otel-flood-drop)."""
    now = datetime.now(timezone.utc)
    # 1. Briefly tighten otel-demo runtime overrides so real Tempo increments rate_limited & trace_too_large on otel-demo!
    _http_req(
        TEMPO_LOCAL_URL,
        "POST",
        "/api/overrides",
        org_id="otel-demo",
        body=json.dumps({
            "ingestion_rate_limit_bytes": 128,
            "ingestion_burst_size_bytes": 128,
            "max_bytes_per_trace": 512,
            "max_traces_per_user": 50000,
        }),
        extra_headers={"If-Match": "*"},
    )
    time.sleep(2.5)
    big_attr = "X" * 4096
    for target_org in ("otel-demo", "otel-flood-drop"):
        for i in range(6):
            tid = f"deadbeefdeadbeefdeadbeef0000{i:04x}"
            rs = [
                _make_rs(
                    "load-generator",
                    [
                        _span(
                            tid,
                            f"f00d00000000{i:04x}",
                            "GET /",
                            now - timedelta(seconds=5 - min(i, 4)),
                            50.0,
                            attrs={"http.route": "/", "flood.payload": big_attr if i >= 3 else "flood"},
                        )
                    ],
                    namespace="otel-demo",
                )
            ]
            try:
                _http_req(
                    TEMPO_OTLP_HTTP_URL,
                    "POST",
                    "/v1/traces",
                    org_id=target_org,
                    body=json.dumps({"resourceSpans": rs}),
                )
            except Exception:
                pass
    # Immediately restore healthy otel-demo runtime overrides so normal ingestion continues unimpeded
    _http_req(
        TEMPO_LOCAL_URL,
        "POST",
        "/api/overrides",
        org_id="otel-demo",
        body=json.dumps({
            "ingestion_rate_limit_bytes": 26214400,
            "ingestion_burst_size_bytes": 39321600,
            "max_bytes_per_trace": 5242880,
            "max_traces_per_user": 25000,
            "block_retention": "336h",
            "metrics_generator": {"processors": ["service-graphs", "span-metrics", "local-blocks"]},
        }),
        extra_headers={"If-Match": "*"},
    )
    time.sleep(2.2)


def seed_otel_traces() -> None:
    """Seed deterministic multi-window, multi-tenant OTEL-APP traces into Tempo 2.7."""
    now = datetime.now(timezone.utc)
    rs_demo: list[dict[str, Any]] = []

    # ── A. Canonical Named Traces (exact trace IDs referenced in incident scenarios) ──

    # 1. 4bf92f3577b34da6a3ce929d0e0e4736: PlaceOrder failing downstream in payment (Charge) AND email (/send_order_confirmation without exception event)
    t_4bf = now - timedelta(minutes=6)
    tid_4bf = "4bf92f3577b34da6a3ce929d0e0e4736"
    rs_demo.extend([
        _make_rs("frontend-proxy", [
            _span(tid_4bf, "00f067aa0ba902b7", "POST /api/checkout", t_4bf, 840.0, kind=2, error=True, status_msg="HTTP 500",
                  attrs={"http.request.method": "POST", "http.response.status_code": 500, "http.route": "/api/checkout", "url.path": "/api/checkout"}),
            _span(tid_4bf, "00f067aa0ba902b8", "POST frontend:8080/api/checkout", t_4bf + timedelta(milliseconds=3), 832.0, parent_id="00f067aa0ba902b7", kind=3, error=True,
                  attrs={"peer.service": "frontend", "server.address": "frontend"}),
        ], pod="frontend-proxy-envoy-d9d495cbc-hj9fk"),
        _make_rs("frontend", [
            _span(tid_4bf, "1111000000000001", "POST /api/checkout", t_4bf + timedelta(milliseconds=5), 825.0, parent_id="00f067aa0ba902b8", kind=2, error=True,
                  attrs={"http.request.method": "POST", "http.response.status_code": 500, "http.route": "/api/checkout"}),
            _span(tid_4bf, "1111000000000002", "oteldemo.CheckoutService/PlaceOrder", t_4bf + timedelta(milliseconds=10), 810.0, parent_id="1111000000000001", kind=3, error=True,
                  attrs={"rpc.system": "grpc", "peer.service": "checkout-service"}),
        ], pod="frontend-6fbbcb4878-jch42"),
        _make_rs("checkout-service", [
            _span(tid_4bf, "2222000000000001", "oteldemo.CheckoutService/PlaceOrder", t_4bf + timedelta(milliseconds=12), 802.0, parent_id="1111000000000002", kind=2, error=True, status_msg="PlaceOrder failed",
                  attrs={"rpc.system": "grpc", "rpc.method": "PlaceOrder", "app.order.id": "ord_4bf92f"}),
            _span(tid_4bf, "2222000000000002", "oteldemo.PaymentService/Charge", t_4bf + timedelta(milliseconds=25), 420.0, parent_id="2222000000000001", kind=3, error=True,
                  attrs={"rpc.system": "grpc", "peer.service": "payment"}),
            _span(tid_4bf, "2222000000000003", "POST /shiporder", t_4bf + timedelta(milliseconds=450), 95.0, parent_id="2222000000000001", kind=3, error=False,
                  attrs={"http.request.method": "POST", "peer.service": "shipping-service"}),
            _span(tid_4bf, "2222000000000004", "POST /send_order_confirmation", t_4bf + timedelta(milliseconds=550), 245.0, parent_id="2222000000000001", kind=3, error=True,
                  attrs={"http.method": "POST", "http.status_code": 500, "peer.service": "email"}),
        ], pod="checkout-84c9c9c9c4-5hxhp"),
        _make_rs("payment", [
            _span(tid_4bf, "3333000000000001", "oteldemo.PaymentService/Charge", t_4bf + timedelta(milliseconds=28), 410.0, parent_id="2222000000000002", kind=2, error=True, status_msg="PaymentFailure: card declined (flagd paymentFailure=25%)",
                  attrs={"rpc.system": "grpc", "rpc.method": "Charge", "app.payment.card_type": "visa", "flagd.variant": "25%"},
                  events=[_exc_event(t_4bf + timedelta(milliseconds=430), "PaymentDeclinedException", "PaymentService Charge failed under paymentFailure=25%", "at ChargeService.charge (payment/index.js:88:15)")]),
        ], pod="payment-789f78d97c-qhr9t"),
        _make_rs("shipping-service", [
            _span(tid_4bf, "4444000000000001", "POST /shiporder", t_4bf + timedelta(milliseconds=452), 90.0, parent_id="2222000000000003", kind=2, error=False,
                  attrs={"http.request.method": "POST", "http.response.status_code": 200, "http.route": "/shiporder"}),
        ], pod="shipping-5c4b69567b-gxhk4"),
        # Note: email span intentionally has status=error WITHOUT exception stacktrace event (for eval-08 Loki correlation!)
        _make_rs("email", [
            _span(tid_4bf, "5555000000000001", "POST /send_order_confirmation", t_4bf + timedelta(milliseconds=553), 238.0, parent_id="2222000000000004", kind=2, error=True, status_msg="Internal Server Error (worker memory pressure)",
                  attrs={"http.method": "POST", "http.status_code": 500, "http.route": "/send_order_confirmation"}),
        ], pod="email-5d9c8b-k2m9q"),
    ])

    # 2. 8899aabbccddeeff0011223344556677: frontend-proxy 502 -> frontend 500 -> recommendation -> product-catalog-service L9ECAV7KIM error
    t_889 = now - timedelta(minutes=7)
    tid_889 = "8899aabbccddeeff0011223344556677"
    rs_demo.extend([
        _make_rs("frontend-proxy", [
            _span(tid_889, "8899000000000001", "GET /api/recommendations", t_889, 145.0, kind=2, error=True, status_msg="HTTP 502 Bad Gateway",
                  attrs={"http.request.method": "GET", "http.response.status_code": 502, "http.route": "/api/recommendations"}),
            _span(tid_889, "8899000000000002", "GET frontend/api/recommendations", t_889 + timedelta(milliseconds=2), 140.0, parent_id="8899000000000001", kind=3, error=True,
                  attrs={"peer.service": "frontend"}),
        ], pod="frontend-proxy-envoy-d9d495cbc-hj9fk"),
        _make_rs("frontend", [
            _span(tid_889, "8899000000000003", "GET /api/recommendations", t_889 + timedelta(milliseconds=4), 135.0, parent_id="8899000000000002", kind=2, error=True,
                  attrs={"http.request.method": "GET", "http.response.status_code": 500, "http.route": "/api/recommendations"}),
            _span(tid_889, "8899000000000004", "oteldemo.RecommendationService/ListRecommendations", t_889 + timedelta(milliseconds=8), 125.0, parent_id="8899000000000003", kind=3, error=True,
                  attrs={"peer.service": "recommendation"}),
        ], pod="frontend-6fbbcb4878-jch42"),
        _make_rs("recommendation", [
            _span(tid_889, "8899000000000005", "oteldemo.RecommendationService/ListRecommendations", t_889 + timedelta(milliseconds=10), 120.0, parent_id="8899000000000004", kind=2, error=True, status_msg="gRPC INTERNAL",
                  attrs={"rpc.system": "grpc", "rpc.method": "ListRecommendations"}),
            _span(tid_889, "8899000000000006", "oteldemo.ProductCatalogService/GetProduct", t_889 + timedelta(milliseconds=15), 108.0, parent_id="8899000000000005", kind=3, error=True,
                  attrs={"peer.service": "product-catalog-service", "app.product.id": "L9ECAV7KIM"}),
        ], pod="recommendation-6b9d8c-p4k2m"),
        _make_rs("product-catalog-service", [
            _span(tid_889, "8899000000000007", "oteldemo.ProductCatalogService/GetProduct", t_889 + timedelta(milliseconds=17), 102.0, parent_id="8899000000000006", kind=2, error=True, status_msg="ProductCatalogFailureError: productCatalogFailure enabled for L9ECAV7KIM",
                  attrs={"rpc.system": "grpc", "rpc.method": "GetProduct", "app.product.id": "L9ECAV7KIM", "flagd.variant": "on"},
                  events=[_exc_event(t_889 + timedelta(milliseconds=115), "ProductCatalogFailureError", "Error: ProductCatalogService fail feature flag enabled for product L9ECAV7KIM", "main.go:214 (*productCatalog).GetProduct()")]),
            _span(tid_889, "8899000000000008", "SELECT * FROM catalog.products", t_889 + timedelta(milliseconds=22), 45.0, parent_id="8899000000000007", kind=3, error=True, status_msg="query aborted on L9ECAV7KIM",
                  attrs={"db.system": "postgresql", "db.system.name": "postgresql", "server.address": "postgresql", "server.port": 5432, "app.product.id": "L9ECAV7KIM"}),
        ], pod="product-catalog-7d9f4b-m2n8q"),
    ])

    # 3. Log-bundle trace IDs: abcdef0123456789abcdef0123456789 & 11223344556677889900aabbccddeeff
    t_log1 = now - timedelta(minutes=8)
    tid_log1 = "abcdef0123456789abcdef0123456789"
    rs_demo.extend([
        _make_rs("recommendation", [
            _span(tid_log1, "abcd000000000001", "oteldemo.RecommendationService/ListRecommendations", t_log1, 95.0, kind=2, error=True, status_msg="GetProduct L9ECAV7KIM failed"),
            _span(tid_log1, "abcd000000000002", "oteldemo.ProductCatalogService/GetProduct", t_log1 + timedelta(milliseconds=5), 85.0, parent_id="abcd000000000001", kind=3, error=True, attrs={"peer.service": "product-catalog-service", "app.product.id": "L9ECAV7KIM"}),
        ]),
        _make_rs("product-catalog-service", [
            _span(tid_log1, "abcd000000000003", "oteldemo.ProductCatalogService/GetProduct", t_log1 + timedelta(milliseconds=7), 80.0, parent_id="abcd000000000002", kind=2, error=True, status_msg="L9ECAV7KIM failure",
                  attrs={"app.product.id": "L9ECAV7KIM"},
                  events=[_exc_event(t_log1 + timedelta(milliseconds=82), "ProductCatalogFailureError", "Product L9ECAV7KIM unavailable", "catalog.go:199")]),
        ]),
    ])
    t_log2 = now - timedelta(minutes=8, seconds=10)
    tid_log2 = "11223344556677889900aabbccddeeff"
    rs_demo.extend([
        _make_rs("checkout-service", [
            _span(tid_log2, "1122000000000001", "oteldemo.CheckoutService/PlaceOrder", t_log2, 310.0, kind=2, error=True, status_msg="PaymentService/Charge unavailable"),
            _span(tid_log2, "1122000000000002", "oteldemo.PaymentService/Charge", t_log2 + timedelta(milliseconds=10), 290.0, parent_id="1122000000000001", kind=3, error=True, attrs={"peer.service": "payment"}),
        ]),
        _make_rs("payment", [
            _span(tid_log2, "1122000000000003", "oteldemo.PaymentService/Charge", t_log2 + timedelta(milliseconds=12), 282.0, parent_id="1122000000000002", kind=2, error=True, status_msg="Unavailable: paymentUnreachable=on",
                  events=[_exc_event(t_log2 + timedelta(milliseconds=290), "GrpcUnavailableError", "Payment gateway unreachable", "payment.js:52")]),
        ]),
    ])

    # 4. N+1 Fan-out traces: 11112222333344445555666677778888 (baseline 140ms, 2 calls) vs 9999aaaabbbbccccddddeeeeffff0000 (1850ms, 40 calls)
    t_n1 = now - timedelta(minutes=9)
    tid_n1_base = "11112222333344445555666677778888"
    rs_demo.extend([
        _make_rs("recommendation", [
            _span(tid_n1_base, "n1ba000000000001".replace("n", "a"), "oteldemo.RecommendationService/ListRecommendations", t_n1, 140.0, kind=2,
                  attrs={"flagd.recommendationCacheFailure": "off"}),
            _span(tid_n1_base, "a1ba000000000002", "oteldemo.ProductCatalogService/GetProduct", t_n1 + timedelta(milliseconds=10), 6.0, parent_id="a1ba000000000001", kind=3, attrs={"peer.service": "product-catalog-service"}),
            _span(tid_n1_base, "a1ba000000000003", "oteldemo.ProductCatalogService/GetProduct", t_n1 + timedelta(milliseconds=20), 6.0, parent_id="a1ba000000000001", kind=3, attrs={"peer.service": "product-catalog-service"}),
        ]),
        _make_rs("product-catalog-service", [
            _span(tid_n1_base, "a1ba000000000004", "SELECT * FROM catalog.products", t_n1 + timedelta(milliseconds=11), 4.0, parent_id="a1ba000000000002", kind=3, attrs={"db.system": "postgresql", "peer.service": "postgresql"}),
            _span(tid_n1_base, "a1ba000000000005", "SELECT * FROM catalog.products", t_n1 + timedelta(milliseconds=21), 4.0, parent_id="a1ba000000000003", kind=3, attrs={"db.system": "postgresql", "peer.service": "postgresql"}),
        ]),
    ])
    tid_n1_deg = "9999aaaabbbbccccddddeeeeffff0000"
    rec_deg_spans = [
        _span(tid_n1_deg, "b1de000000000000", "oteldemo.RecommendationService/ListRecommendations", t_n1 + timedelta(seconds=2), 1850.0, kind=2,
              attrs={"flagd.recommendationCacheFailure": "on"}),
    ]
    cat_deg_spans = []
    for k in range(1, 36):
        c_sid = f"b1de00000000{k:04x}"
        db_sid = f"b1df00000000{k:04x}"
        off_ms = 15 + (k * 48)
        rec_deg_spans.append(
            _span(tid_n1_deg, c_sid, "oteldemo.ProductCatalogService/GetProduct", t_n1 + timedelta(seconds=2, milliseconds=off_ms), 6.2, parent_id="b1de000000000000", kind=3,
                  attrs={"peer.service": "product-catalog-service", "app.product.id": f"PROD_{k:02d}"})
        )
        cat_deg_spans.append(
            _span(tid_n1_deg, db_sid, "SELECT * FROM catalog.products", t_n1 + timedelta(seconds=2, milliseconds=off_ms + 1), 4.2, parent_id=c_sid, kind=3,
                  attrs={"db.system": "postgresql", "db.system.name": "postgresql", "peer.service": "postgresql"})
        )
    rs_demo.append(_make_rs("recommendation", rec_deg_spans))
    rs_demo.append(_make_rs("product-catalog-service", cat_deg_spans))

    # 5. Single-Operation GC Slowdown: aaaa1111bbbb2222cccc3333dddd4444 (220ms) vs eeee5555ffff66660000777788889999 (1620ms)
    t_gc = now - timedelta(minutes=10)
    tid_gc_fast = "aaaa1111bbbb2222cccc3333dddd4444"
    tid_gc_slow = "eeee5555ffff66660000777788889999"
    for tid_cur, total_d, ad_d, gc_flag in [
        (tid_gc_fast, 220.0, 45.0, "off"),
        (tid_gc_slow, 1620.0, 1450.0, "on"),
    ]:
        rs_demo.extend([
            _make_rs("frontend-proxy", [
                _span(tid_cur, "c001000000000001", "GET /", t_gc, total_d, kind=2, attrs={"http.route": "/"}),
                _span(tid_cur, "c001000000000002", "GET frontend/", t_gc + timedelta(milliseconds=3), total_d - 6, parent_id="c001000000000001", kind=3, attrs={"peer.service": "frontend"}),
            ]),
            _make_rs("frontend", [
                _span(tid_cur, "c001000000000003", "GET /", t_gc + timedelta(milliseconds=5), total_d - 12, parent_id="c001000000000002", kind=2, attrs={"http.route": "/"}),
                _span(tid_cur, "c001000000000004", "oteldemo.ProductCatalogService/ListProducts", t_gc + timedelta(milliseconds=12), 55.0, parent_id="c001000000000003", kind=3, attrs={"peer.service": "product-catalog-service"}),
                _span(tid_cur, "c001000000000005", "oteldemo.CartService/GetCart", t_gc + timedelta(milliseconds=70), 35.0, parent_id="c001000000000003", kind=3, attrs={"peer.service": "cart-service"}),
                _span(tid_cur, "c001000000000006", "oteldemo.AdService/GetAds", t_gc + timedelta(milliseconds=110), ad_d + 10, parent_id="c001000000000003", kind=3, attrs={"peer.service": "ad"}),
            ]),
            _make_rs("product-catalog-service", [
                _span(tid_cur, "c001000000000007", "oteldemo.ProductCatalogService/ListProducts", t_gc + timedelta(milliseconds=14), 50.0, parent_id="c001000000000004", kind=2),
            ]),
            _make_rs("cart-service", [
                _span(tid_cur, "c001000000000008", "oteldemo.CartService/GetCart", t_gc + timedelta(milliseconds=72), 30.0, parent_id="c001000000000005", kind=2),
            ]),
            _make_rs("ad", [
                _span(tid_cur, "c001000000000009", "oteldemo.AdService/GetAds", t_gc + timedelta(milliseconds=115), ad_d, parent_id="c001000000000006", kind=2,
                      attrs={"flagd.adManualGc": gc_flag, "flagd.adHighCpu": gc_flag, "app.ads.contextKeys": "binoculars"}),
            ]),
        ])

    # 6. New Sync Dependency & Retry Amplification: abcd0001... vs abcd0002...
    t_up = now - timedelta(minutes=11)
    tid_up_a = "abcd0001abcd0001abcd0001abcd0001"
    rs_demo.extend([
        _make_rs("checkout-service", [
            _span(tid_up_a, "d001000000000001", "oteldemo.CheckoutService/PlaceOrder", t_up, 180.0, kind=2),
            _span(tid_up_a, "d001000000000002", "oteldemo.PaymentService/Charge", t_up + timedelta(milliseconds=15), 95.0, parent_id="d001000000000001", kind=3, attrs={"peer.service": "payment"}),
            _span(tid_up_a, "d001000000000003", "POST /shiporder", t_up + timedelta(milliseconds=115), 55.0, parent_id="d001000000000001", kind=3, attrs={"peer.service": "shipping-service"}),
        ], version="2.2.0"),
        _make_rs("payment", [
            _span(tid_up_a, "d001000000000004", "oteldemo.PaymentService/Charge", t_up + timedelta(milliseconds=17), 90.0, parent_id="d001000000000002", kind=2),
        ]),
    ])
    tid_up_b = "abcd0002abcd0002abcd0002abcd0002"
    rs_demo.extend([
        _make_rs("checkout-service", [
            _span(tid_up_b, "d002000000000001", "oteldemo.CheckoutService/PlaceOrder", t_up + timedelta(seconds=3), 460.0, kind=2),
            _span(tid_up_b, "d002000000000002", "flagd.evaluation.v1.Service/ResolveBoolean", t_up + timedelta(seconds=3, milliseconds=10), 85.0, parent_id="d002000000000001", kind=3, attrs={"peer.service": "flagd"}),
            _span(tid_up_b, "d002000000000003", "oteldemo.PaymentService/Charge", t_up + timedelta(seconds=3, milliseconds=100), 95.0, parent_id="d002000000000001", kind=3, error=True, status_msg="transient timeout retry 1", attrs={"peer.service": "payment", "retry.attempt": 1}),
            _span(tid_up_b, "d002000000000004", "oteldemo.PaymentService/Charge", t_up + timedelta(seconds=3, milliseconds=210), 95.0, parent_id="d002000000000001", kind=3, error=True, status_msg="transient timeout retry 2", attrs={"peer.service": "payment", "retry.attempt": 2}),
            _span(tid_up_b, "d002000000000005", "oteldemo.PaymentService/Charge", t_up + timedelta(seconds=3, milliseconds=320), 80.0, parent_id="d002000000000001", kind=3, error=False, attrs={"peer.service": "payment", "retry.attempt": 3}),
            _span(tid_up_b, "d002000000000006", "POST /shiporder", t_up + timedelta(seconds=3, milliseconds=402), 52.0, parent_id="d002000000000001", kind=3, attrs={"peer.service": "shipping-service"}),
        ], version="2.3.0-checkout"),
        _make_rs("flagd", [
            _span(tid_up_b, "d002000000000007", "flagd.evaluation.v1.Service/ResolveBoolean", t_up + timedelta(seconds=3, milliseconds=12), 80.0, parent_id="d002000000000002", kind=2),
        ]),
        _make_rs("payment", [
            _span(tid_up_b, "d002000000000008", "oteldemo.PaymentService/Charge", t_up + timedelta(seconds=3, milliseconds=102), 90.0, parent_id="d002000000000003", kind=2, error=True, status_msg="Charge timeout"),
            _span(tid_up_b, "d002000000000009", "oteldemo.PaymentService/Charge", t_up + timedelta(seconds=3, milliseconds=212), 90.0, parent_id="d002000000000004", kind=2, error=True, status_msg="Charge timeout"),
            _span(tid_up_b, "d00200000000000a", "oteldemo.PaymentService/Charge", t_up + timedelta(seconds=3, milliseconds=322), 75.0, parent_id="d002000000000005", kind=2, error=False),
        ]),
    ])

    # 7. Async Kafka Producer -> Linked Consumer Trace (1234567890abcdef1234567890abcdef -> fedc0001fedc0001fedc0001fedc0001)
    t_kf = now - timedelta(minutes=12)
    tid_prod = "1234567890abcdef1234567890abcdef"
    tid_cons = "fedc0001fedc0001fedc0001fedc0001"
    rs_demo.extend([
        _make_rs("checkout-service", [
            _span(tid_prod, "e001000000000001", "oteldemo.CheckoutService/PlaceOrder", t_kf, 90.0, kind=2, attrs={"app.order.id": "ord_kafka_01"}),
            _span(tid_prod, "e001000000000002", "orders publish", t_kf + timedelta(milliseconds=65), 18.0, parent_id="e001000000000001", kind=4,
                  attrs={"messaging.system": "kafka", "messaging.destination.name": "orders", "peer.service": "kafka"}),
        ]),
        _make_rs("accounting", [
            _span(tid_cons, "e002000000000001", "orders process", t_kf + timedelta(seconds=18), 340.0, kind=5, error=True, status_msg="kafkaQueueProblems consumer lag 18.0s",
                  attrs={"messaging.system": "kafka", "messaging.destination.name": "orders", "messaging.kafka.consumer.lag_ms": 18000, "app.order.id": "ord_kafka_01", "flagd.kafkaQueueProblems": "on"},
                  events=[_exc_event(t_kf + timedelta(seconds=18, milliseconds=120), "KafkaConsumerLagWarning", "Order message dwelled 18.0s in orders partition before consumption", "consumer.go:142")],
                  links=[{"traceId": tid_prod, "spanId": "e001000000000002"}]),
            _span(tid_cons, "e002000000000002", "INSERT INTO accounting.order", t_kf + timedelta(seconds=18, milliseconds=280), 42.0, parent_id="e002000000000001", kind=3,
                  attrs={"db.system": "postgresql", "db.system.name": "postgresql", "peer.service": "postgresql"}),
        ], pod="accounting-5f7d9c-q8w2k"),
    ])

    # 8. Downstream Wait trace: fedcba9876543210fedcba9876543210 (frontend-proxy 5100ms, 18ms self-time -> image-provider 5040ms)
    t_img = now - timedelta(minutes=5)
    tid_img = "fedcba9876543210fedcba9876543210"
    rs_demo.extend([
        _make_rs("frontend-proxy", [
            _span(tid_img, "f001000000000001", "GET /images/LensCleaningKit.jpg", t_img, 5100.0, kind=2,
                  attrs={"http.request.method": "GET", "http.response.status_code": 200, "url.path": "/images/LensCleaningKit.jpg"}),
            _span(tid_img, "f001000000000002", "GET image-provider:8081/images/LensCleaningKit.jpg", t_img + timedelta(milliseconds=10), 5082.0, parent_id="f001000000000001", kind=3,
                  attrs={"peer.service": "image-provider"}),
        ]),
        _make_rs("image-provider", [
            _span(tid_img, "f001000000000003", "GET /images/LensCleaningKit.jpg", t_img + timedelta(milliseconds=25), 5040.0, parent_id="f001000000000002", kind=2,
                  attrs={"http.request.method": "GET", "http.response.status_code": 200, "url.path": "/images/LensCleaningKit.jpg", "flagd.variant": "5sec", "flagd.imageSlowLoad": "5sec"}),
        ], pod="image-provider-85df4c8c8-d94bv"),
    ])

    # 9. Uninstrumented Time-Gap traces:
    # - 33333333333333333333333333333333: 3.4s parent checkout-service span with only 180ms of child spans
    # - 00112233445566778899aabbccddeeff: 3.2s wall-clock recommendation trace with 620ms critical path
    # - 9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d: 4.8s wall-clock PlaceOrder trace with 900ms visible spans
    t_gap = now - timedelta(minutes=8)
    tid_gap_33 = "33333333333333333333333333333333"
    rs_demo.extend([
        _make_rs("checkout-service", [
            _span(tid_gap_33, "3300000000000001", "oteldemo.CheckoutService/PlaceOrder", t_gap, 3400.0, kind=2),
            _span(tid_gap_33, "3300000000000002", "oteldemo.PaymentService/Charge", t_gap + timedelta(milliseconds=3150), 70.0, parent_id="3300000000000001", kind=3, attrs={"peer.service": "payment"}),
            _span(tid_gap_33, "3300000000000003", "POST /shiporder", t_gap + timedelta(milliseconds=3225), 60.0, parent_id="3300000000000001", kind=3, attrs={"peer.service": "shipping-service"}),
            _span(tid_gap_33, "3300000000000004", "oteldemo.CartService/GetCart", t_gap + timedelta(milliseconds=3290), 50.0, parent_id="3300000000000001", kind=3, attrs={"peer.service": "cart-service"}),
        ]),
    ])
    tid_gap_00 = "00112233445566778899aabbccddeeff"
    rs_demo.extend([
        _make_rs("recommendation", [
            _span(tid_gap_00, "0011000000000001", "oteldemo.RecommendationService/ListRecommendations", t_gap, 600.0, kind=2),
        ]),
        _make_rs("product-catalog-service", [
            _span(tid_gap_00, "0011000000000002", "oteldemo.ProductCatalogService/GetProduct", t_gap + timedelta(milliseconds=3180), 20.0, kind=2),
        ]),
    ])
    tid_gap_9a = "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d"
    rs_demo.extend([
        _make_rs("frontend-proxy", [
            _span(tid_gap_9a, "9a8b000000000001", "POST /api/checkout", t_gap, 520.0, kind=2, attrs={"http.route": "/api/checkout"}),
            _span(tid_gap_9a, "9a8b000000000002", "oteldemo.CheckoutService/PlaceOrder", t_gap + timedelta(milliseconds=10), 350.0, parent_id="9a8b000000000001", kind=3, attrs={"peer.service": "checkout-service"}),
        ]),
        _make_rs("shipping-service", [
            _span(tid_gap_9a, "9a8b000000000003", "POST /shiporder", t_gap + timedelta(milliseconds=4770), 30.0, kind=2, attrs={"http.route": "/shiporder"}),
        ]),
    ])

    # ── B. Multi-Window & Cohort Skew Batches (for live TraceQL Metrics, RED, compare(), Pagination & Service Graphs) ──

    # 1. Baseline healthy window (68m..50m ago) for checkout-service, frontend, product-catalog-service (~80ms p50, ~210ms p99)
    pc_ops = [
        "oteldemo.ProductCatalogService/GetProduct",
        "oteldemo.ProductCatalogService/ListProducts",
        "oteldemo.ProductCatalogService/SearchProducts",
    ]
    for i in range(15):
        ts_b = now - timedelta(minutes=68 - i)
        tid_b = f"ba5e111122223333444455556666{i:04x}"
        pc_op_b = pc_ops[i % 3]
        pc_dur_b = 210.0 if i == 14 else 80.0
        rs_demo.extend([
            _make_rs("frontend", [
                _span(tid_b, f"ba5000000001{i:04x}", "GET /api/products", ts_b, 145.0, kind=2,
                      attrs={"http.request.method": "GET", "http.response.status_code": 200, "http.route": "/api/products"}),
                _span(tid_b, f"ba5000000002{i:04x}", "oteldemo.CheckoutService/PlaceOrder", ts_b + timedelta(milliseconds=10), 120.0, parent_id=f"ba5000000001{i:04x}", kind=3,
                      attrs={"peer.service": "checkout-service"}),
            ]),
            _make_rs("checkout-service", [
                _span(tid_b, f"ba5000000003{i:04x}", "oteldemo.CheckoutService/PlaceOrder", ts_b + timedelta(milliseconds=12), 115.0, parent_id=f"ba5000000002{i:04x}", kind=2,
                      attrs={"rpc.method": "PlaceOrder"}),
                _span(tid_b, f"ba5000000004{i:04x}", pc_op_b, ts_b + timedelta(milliseconds=20), pc_dur_b + 5.0, parent_id=f"ba5000000003{i:04x}", kind=3,
                      attrs={"peer.service": "product-catalog-service"}),
            ]),
            _make_rs("product-catalog-service", [
                _span(tid_b, f"ba5000000005{i:04x}", pc_op_b, ts_b + timedelta(milliseconds=22), pc_dur_b, parent_id=f"ba5000000004{i:04x}", kind=2,
                      attrs={"rpc.method": pc_op_b.split("/")[-1]}),
                _span(tid_b, f"ba5000000006{i:04x}", "SELECT * FROM catalog.products", ts_b + timedelta(milliseconds=25), 14.0, parent_id=f"ba5000000005{i:04x}", kind=3,
                      attrs={"db.system": "postgresql", "db.system.name": "postgresql", "server.address": "postgresql", "server.port": 5432, "db.pool.wait_ms": 2}),
            ], pod="product-catalog-7d9f4b-m2n8q"),
        ])

    # 1b. Uniform latency shift on product-catalog-service over last 18m (~195ms p50, ~490ms p99 across GetProduct, ListProducts, SearchProducts with postgresql:5432 DB pool saturation)
    for i in range(18):
        ts_u = now - timedelta(minutes=17) + timedelta(seconds=i * 45)
        tid_u = f"c47a106011112222333344445555{i:04x}"
        pc_op_u = pc_ops[i % 3]
        pc_dur_u = 490.0 if i % 6 == 0 else 195.0
        pool_wait = 390 if i % 6 == 0 else 145
        rs_demo.append(
            _make_rs("product-catalog-service", [
                _span(tid_u, f"c47a00000001{i:04x}", pc_op_u, ts_u, pc_dur_u, kind=2,
                      attrs={"rpc.system": "grpc", "rpc.method": pc_op_u.split("/")[-1], "gomemlimit": "160MiB"}),
                _span(tid_u, f"c47a00000002{i:04x}", "SELECT * FROM catalog.products", ts_u + timedelta(milliseconds=6), pc_dur_u - 15.0, parent_id=f"c47a00000001{i:04x}", kind=3,
                      attrs={"db.system": "postgresql", "db.system.name": "postgresql", "peer.service": "postgresql", "server.address": "postgresql", "server.port": 5432, "db.pool.wait_ms": pool_wait, "db.pool.active_connections": 50, "db.pool.max_connections": 50}),
            ], pod="product-catalog-7d9f4b-m2n8q" if i % 2 == 0 else "product-catalog-7d9f4b-w9x4v")
        )

    # 2. Recent checkout-service + payment + shipping-service + email traffic (28 payment Charge errors for pagination + sibling spans + !> aborted spans)
    for i in range(28):
        ts_p = now - timedelta(minutes=25) + timedelta(seconds=i * 35)
        tid_p = f"ca11f00d11112222333344445555{i:04x}"
        is_err = i < 24  # 24 failing payment Charge traces across 25m -> >20 for pagination!
        chk_spans = [
            _span(tid_p, f"ca1000000001{i:04x}", "oteldemo.CheckoutService/PlaceOrder", ts_p, 1650.0 if is_err else 190.0, kind=2, error=is_err,
                  attrs={"rpc.system": "grpc", "rpc.method": "PlaceOrder"}),
            _span(tid_p, f"ca1000000002{i:04x}", "oteldemo.PaymentService/Charge", ts_p + timedelta(milliseconds=15), 1520.0 if is_err else 65.0, parent_id=f"ca1000000001{i:04x}", kind=3, error=is_err,
                  attrs={"peer.service": "payment", "rpc.method": "Charge"}),
            _span(tid_p, f"ca1000000003{i:04x}", "POST /shiporder", ts_p + timedelta(milliseconds=20), 85.0, parent_id=f"ca1000000001{i:04x}", kind=3,
                  attrs={"peer.service": "shipping-service", "http.route": "/shiporder"}),
            _span(tid_p, f"ca1000000007{i:04x}", "oteldemo.ProductCatalogService/GetProduct", ts_p + timedelta(milliseconds=25), 45.0, parent_id=f"ca1000000001{i:04x}", kind=3,
                  attrs={"peer.service": "product-catalog-service"}),
        ]
        if not is_err:
            chk_spans.append(
                _span(tid_p, f"ca1000000004{i:04x}", "POST /send_order_confirmation", ts_p + timedelta(milliseconds=110), 40.0, parent_id=f"ca1000000001{i:04x}", kind=3,
                      attrs={"peer.service": "email", "http.method": "POST", "http.status_code": 200})
            )
        rs_demo.append(_make_rs("checkout-service", chk_spans))
        rs_demo.append(_make_rs("payment", [
            _span(tid_p, f"ca1000000005{i:04x}", "oteldemo.PaymentService/Charge", ts_p + timedelta(milliseconds=18), 1500.0 if is_err else 60.0, parent_id=f"ca1000000002{i:04x}", kind=2, error=is_err,
                  status_msg="Card charge declined (paymentFailure)" if is_err else "",
                  attrs={"rpc.system": "grpc", "rpc.method": "Charge", "flagd.variant": "25%" if is_err else "off"},
                  events=[_exc_event(ts_p + timedelta(milliseconds=1500), "PaymentDeclinedException", "Card declined", "payment/charge.js:88")] if is_err else None),
        ]))
        rs_demo.append(_make_rs("shipping-service", [
            _span(tid_p, f"ca1000000006{i:04x}", "POST /shiporder", ts_p + timedelta(milliseconds=22), 80.0 + (i * 4), parent_id=f"ca1000000003{i:04x}", kind=2,
                  attrs={"http.request.method": "POST", "http.response.status_code": 200, "http.route": "/shiporder"}),
        ]))
        rs_demo.append(_make_rs("product-catalog-service", [
            _span(tid_p, f"ca1000000008{i:04x}", "oteldemo.ProductCatalogService/GetProduct", ts_p + timedelta(milliseconds=27), 210.0, parent_id=f"ca1000000007{i:04x}", kind=2,
                  attrs={"rpc.method": "GetProduct"}),
        ]))

    # 3. shipping-service -> quote HTTP 5xx traces (with dual OTel v1.20 http.status_code on quote & v1.24 http.response.status_code on shipping-service)
    for i in range(10):
        ts_q = now - timedelta(minutes=14) + timedelta(seconds=i * 40)
        tid_q = f"5b19917611112222333344445555{i:04x}"
        q_err = i < 6
        rs_demo.extend([
            _make_rs("shipping-service", [
                _span(tid_q, f"5b1000000001{i:04x}", "POST /getquote", ts_q, 320.0 if q_err else 95.0, kind=2, error=q_err, status_msg="quote 500" if q_err else "",
                      attrs={"http.request.method": "POST", "http.response.status_code": 502 if q_err else 200, "http.route": "/getquote"}),
                _span(tid_q, f"5b1000000002{i:04x}", "POST quote:8080/getquote", ts_q + timedelta(milliseconds=8), 300.0 if q_err else 80.0, parent_id=f"5b1000000001{i:04x}", kind=3, error=q_err,
                      attrs={"peer.service": "quote", "server.address": "quote"}),
            ]),
            _make_rs("quote", [
                _span(tid_q, f"5b1000000003{i:04x}", "POST /getquote", ts_q + timedelta(milliseconds=10), 290.0 if q_err else 75.0, parent_id=f"5b1000000002{i:04x}", kind=2, error=q_err,
                      status_msg="DivisionByZeroError in calculateQuote" if q_err else "",
                      attrs={"http.method": "POST", "http.status_code": 500 if q_err else 200, "http.route": "/getquote"},
                      events=[_exc_event(ts_q + timedelta(milliseconds=295), "DivisionByZeroError", "Uncaught DivisionByZeroError in app/routes.php:47", "app/routes.php:47")] if q_err else None),
            ], pod="quote-74c49cd84f-7h89x"),
        ])

    # 4. Canary version skew on `ad` (2.3.0-rc1 >= 88% of errors vs 2.2.0 healthy fleet)
    for i in range(18):
        ts_ad = now - timedelta(minutes=16) + timedelta(seconds=i * 30)
        tid_ad = f"ad00ca4a11112222333344445555{i:04x}"
        if i < 14:
            # Healthy 2.2.0 baseline
            rs_demo.append(_make_rs("ad", [
                _span(tid_ad, f"ad0000000001{i:04x}", "oteldemo.AdService/GetAds", ts_ad, 38.0, kind=2, error=False,
                      attrs={"rpc.system": "grpc", "rpc.method": "GetAds", "app.ads.contextKeys": "astronomy"}),
            ], version="2.2.0", pod="ad-6c8f7d-stable1"))
        else:
            # Healthy 2.3.0-rc1 (only 2 spans) vs 1 error on 2.2.0
            ver = "2.3.0-rc1" if i < 16 else "2.2.0"
            err_flag = i >= 16 and i == 16
            rs_demo.append(_make_rs("ad", [
                _span(tid_ad, f"ad0000000001{i:04x}", "oteldemo.AdService/GetAds", ts_ad, 42.0, kind=2, error=err_flag,
                      attrs={"rpc.system": "grpc", "rpc.method": "GetAds"}),
            ], version=ver, pod="ad-7f9b2c-canary" if ver == "2.3.0-rc1" else "ad-6c8f7d-stable2"))

    for i in range(15):
        ts_adc = now - timedelta(minutes=15) + timedelta(seconds=i * 30)
        tid_adc = f"ad00badc11112222333344445555{i:04x}"
        rs_demo.append(_make_rs("ad", [
            _span(tid_adc, f"adbad0000001{i:04x}", "oteldemo.AdService/GetAds", ts_adc, 110.0, kind=2, error=True,
                  status_msg="NullPointerException in AdRepository.findByCategory",
                  attrs={"rpc.system": "grpc", "rpc.method": "GetAds", "app.ads.contextKeys": "telescopes"},
                  events=[_exc_event(ts_adc + timedelta(milliseconds=105), "java.lang.NullPointerException", "Cannot invoke Category.getId() because category is null", "oteldemo.AdService.getAds(AdService.java:132)")]),
        ], version="2.3.0-rc1", pod="ad-7f9b2c-canary"))

    # 5. Single-pod defect skew on `cart-service` (`cart-6d8f9b-x7k2p` has 9/11 = 81.8% >= 60% of errors, <15% of healthy)
    healthy_cart_pods = ["cart-6d8f9b-good1", "cart-6d8f9b-good2", "cart-6d8f9b-good3", "cart-6d8f9b-x7k2p"]
    for i in range(28):
        ts_ct = now - timedelta(minutes=18) + timedelta(seconds=i * 25)
        tid_ct = f"ca47000011112222333344445555{i:04x}"
        pod_c = healthy_cart_pods[0 if i % 4 == 3 else (i % 3)]  # keep x7k2p rare in healthy baseline!
        rs_demo.append(_make_rs("cart-service", [
            _span(tid_ct, f"c47000000001{i:04x}", "oteldemo.CartService/GetCart", ts_ct, 22.0, kind=2, error=False,
                  attrs={"rpc.system": "grpc", "rpc.method": "GetCart"}),
            _span(tid_ct, f"c47000000002{i:04x}", "HMGET cart", ts_ct + timedelta(milliseconds=3), 8.0, parent_id=f"c47000000001{i:04x}", kind=3,
                  attrs={"db.system": "redis", "peer.service": "valkey-cart", "server.address": "valkey-cart", "server.port": 6379}),
        ], pod=pod_c))
    for i in range(11):
        ts_cte = now - timedelta(minutes=14) + timedelta(seconds=i * 35)
        tid_cte = f"ca47bad011112222333344445555{i:04x}"
        bad_pod = "cart-6d8f9b-x7k2p" if i < 9 else "cart-6d8f9b-good1"
        rs_demo.append(_make_rs("cart-service", [
            _span(tid_cte, f"c47e00000001{i:04x}", "oteldemo.CartService/AddItem", ts_cte, 510.0, kind=2, error=True,
                  status_msg="RedisConnectionException: socket closed on valkey-cart:6379",
                  attrs={"rpc.system": "grpc", "rpc.method": "AddItem"},
                  events=[_exc_event(ts_cte + timedelta(milliseconds=505), "StackExchange.Redis.RedisConnectionException", "SocketClosed on valkey-cart:6379", "CartStore.AddItemAsync() in ValkeyCartStore.cs:94")]),
        ], pod=bad_pod))

    # 6. Bimodal storefront + image-provider traffic (fast 150ms cohort + >4s imageSlowLoad="5sec" tail cohort + frontend 5xx spans)
    for i in range(24):
        ts_fe = now - timedelta(minutes=17) + timedelta(seconds=i * 30)
        tid_fe = f"f4077e7d11112222333344445555{i:04x}"
        is_slow = i < 5
        is_5xx = 5 <= i < 9
        dur_fe = 5250.0 if is_slow else (310.0 if is_5xx else 165.0)
        rs_demo.extend([
            _make_rs("frontend", [
                _span(tid_fe, f"fe0000000001{i:04x}", "POST /api/checkout" if is_5xx else "GET /images/product.jpg", ts_fe, dur_fe, kind=2, error=is_5xx,
                      attrs={
                          "http.request.method": "POST" if is_5xx else "GET",
                          "http.response.status_code": 500 if is_5xx else 200,
                          "http.route": "/api/checkout" if is_5xx else "/images/product.jpg",
                          "url.path": "/api/checkout" if is_5xx else ("/images/LensCleaningKit.jpg" if is_slow else "/images/NationalPark.jpg"),
                          "flagd.variant": "5sec" if is_slow else "off",
                      }),
                _span(tid_fe, f"fe0000000002{i:04x}", "GET image-provider", ts_fe + timedelta(milliseconds=8), dur_fe - 20, parent_id=f"fe0000000001{i:04x}", kind=3,
                      attrs={"peer.service": "image-provider"}),
                _span(tid_fe, f"fe0000000004{i:04x}", "oteldemo.ProductCatalogService/ListProducts", ts_fe + timedelta(milliseconds=10), 195.0, parent_id=f"fe0000000001{i:04x}", kind=3,
                      attrs={"peer.service": "product-catalog-service"}),
            ]),
            _make_rs("image-provider", [
                _span(tid_fe, f"fe0000000003{i:04x}", "GET /images/asset", ts_fe + timedelta(milliseconds=12), 5120.0 if is_slow else 45.0, parent_id=f"fe0000000002{i:04x}", kind=2,
                      attrs={
                          "http.request.method": "GET",
                          "http.response.status_code": 200,
                          "url.path": "/images/LensCleaningKit.jpg" if is_slow else "/images/NationalPark.jpg",
                          "flagd.variant": "5sec" if is_slow else "off",
                          "app.ads.contextKeys": "photography" if is_slow else "general",
                      }),
            ]),
            _make_rs("product-catalog-service", [
                _span(tid_fe, f"fe0000000005{i:04x}", "oteldemo.ProductCatalogService/ListProducts", ts_fe + timedelta(milliseconds=12), 190.0, parent_id=f"fe0000000004{i:04x}", kind=2,
                      attrs={"rpc.method": "ListProducts"}),
                _span(tid_fe, f"fe0000000006{i:04x}", "flagd.evaluation.v1.Service/ResolveBoolean", ts_fe + timedelta(milliseconds=20), 15.0, parent_id=f"fe0000000005{i:04x}", kind=3,
                      attrs={"peer.service": "flagd"}),
            ]),
            _make_rs("flagd", [
                _span(tid_fe, f"fe0000000007{i:04x}", "flagd.evaluation.v1.Service/ResolveBoolean", ts_fe + timedelta(milliseconds=21), 12.0, parent_id=f"fe0000000006{i:04x}", kind=2),
            ]),
        ])

    # 7. High-QPS multi-caller product-catalog-service + L9ECAV7KIM errors (for exemplar pivot & high-coupling >=3 callers at >=10 rps)
    for i in range(16):
        ts_pc = now - timedelta(minutes=10) + timedelta(seconds=i * 20)
        tid_pc = f"9c0019ec11112222333344445555{i:04x}"
        is_l9 = i < 8
        rs_demo.extend([
            _make_rs("recommendation", [
                _span(tid_pc, f"9c0000000001{i:04x}", "oteldemo.RecommendationService/ListRecommendations", ts_pc, 240.0, kind=2, error=is_l9),
                _span(tid_pc, f"9c0000000002{i:04x}", "oteldemo.ProductCatalogService/GetProduct", ts_pc + timedelta(milliseconds=5), 225.0, parent_id=f"9c0000000001{i:04x}", kind=3, error=is_l9,
                      attrs={"peer.service": "product-catalog-service", "app.product.id": "L9ECAV7KIM" if is_l9 else "OLJCESPC7Z"}),
            ]),
            _make_rs("product-catalog-service", [
                _span(tid_pc, f"9c0000000003{i:04x}", "oteldemo.ProductCatalogService/GetProduct" if is_l9 else "oteldemo.ProductCatalogService/SearchProducts", ts_pc + timedelta(milliseconds=7), 220.0, parent_id=f"9c0000000002{i:04x}", kind=2, error=is_l9,
                      status_msg="ProductCatalogFailureError: L9ECAV7KIM" if is_l9 else "",
                      attrs={"rpc.system": "grpc", "rpc.method": "GetProduct" if is_l9 else "SearchProducts", "app.product.id": "L9ECAV7KIM" if is_l9 else "OLJCESPC7Z"},
                      events=[_exc_event(ts_pc + timedelta(milliseconds=220), "ProductCatalogFailureError", "Feature flag productCatalogFailure triggered on product ID L9ECAV7KIM", "main.go:214 (*productCatalog).GetProduct()")] if is_l9 else None),
            ]),
        ])

    # 8. Live-timestamp wave (`now - 2s`) so Tempo metrics_generator remote-writes fresh span-metrics
    # (`traces_spanmetrics_calls_total{service="checkout-service", span_kind="SPAN_KIND_SERVER", ...}` &
    # `traces_spanmetrics_latency_bucket`) within prometheus-d6's active TSDB head window!
    for i in range(4):
        ts_live = now - timedelta(seconds=3 - min(i, 2))
        tid_live = f"11fe000011112222333344445555{i:04x}"
        live_err = i < 1
        rs_demo.extend([
            _make_rs("checkout-service", [
                _span(tid_live, f"11fe00000001{i:04x}", "oteldemo.CheckoutService/PlaceOrder", ts_live, 1250.0 if live_err else 195.0, kind=2, error=live_err,
                      attrs={"rpc.system": "grpc", "rpc.method": "PlaceOrder", "http.route": "/PlaceOrder"}),
                _span(tid_live, f"11fe00000002{i:04x}", "oteldemo.PaymentService/Charge", ts_live + timedelta(milliseconds=10), 1100.0 if live_err else 80.0, parent_id=f"11fe00000001{i:04x}", kind=3, error=live_err,
                      attrs={"peer.service": "payment"}),
            ]),
            _make_rs("payment", [
                _span(tid_live, f"11fe00000003{i:04x}", "oteldemo.PaymentService/Charge", ts_live + timedelta(milliseconds=12), 1080.0 if live_err else 75.0, parent_id=f"11fe00000002{i:04x}", kind=2, error=live_err),
            ]),
        ])

    _send_otlp(rs_demo, org_id="otel-demo")

    # ── C. Tenant 2: otel-staging (isolated chaos traces so multi-tenant isolation is testable!) ──
    rs_staging = [
        _make_rs("chaos-injector", [
            _span("57a61760000000000000000000000001", "57a6000000000001", "POST /chaos/burn", now - timedelta(minutes=5), 420.0, kind=2, error=True,
                  attrs={"http.route": "/chaos/burn"}),
            _span("57a61760000000000000000000000001", "57a6000000000002", "POST staging-payment", now - timedelta(minutes=5, milliseconds=-5), 400.0, parent_id="57a6000000000001", kind=3, error=True,
                  attrs={"peer.service": "staging-only-payment"}),
        ], namespace="otel-staging"),
        _make_rs("staging-only-payment", [
            _span("57a61760000000000000000000000001", "57a6000000000003", "ChargeSandbox", now - timedelta(minutes=5, milliseconds=-10), 390.0, parent_id="57a6000000000002", kind=2, error=True),
        ], namespace="otel-staging"),
    ]
    _send_otlp(rs_staging, org_id="otel-staging")


def seed_prometheus_service_graph_metrics() -> None:
    """Flush Tempo local-blocks/service-graphs, push correlated Loki logs, and ensure Prometheus service-graph counters."""
    now = datetime.now(timezone.utc)

    # 1. Push correlated Ruby email NoMemoryError log for trace 4bf92f3577b34da6a3ce929d0e0e4736 to live Loki (:13100)
    loki_ts_ns = str(int((now - timedelta(minutes=6) + timedelta(milliseconds=555)).timestamp() * 1_000_000_000))
    loki_payload = {
        "streams": [
            {
                "stream": {
                    "namespace": "otel-demo",
                    "service_name": "email",
                    "app": "email",
                    "pod": "email-5d9c8b-k2m9q",
                    "level": "error",
                },
                "values": [
                    [
                        loki_ts_ns,
                        'level=error service=email pod=email-5d9c8b-k2m9q trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=5555000000000001 '
                        'error="NoMemoryError: failed to allocate memory in Sinatra POST /send_order_confirmation while emailMemoryLeak=10x active" '
                        'file="email_server.rb:74"',
                    ]
                ],
            }
        ]
    }
    for loki_org in (None, "otel-demo"):
        try:
            _http_req("http://localhost:13100", "POST", "/loki/api/v1/push", org_id=loki_org, body=json.dumps(loki_payload), timeout=5)
        except Exception:
            pass

    # 2. Push monotonic OTLP service-graph counters to prometheus-d6 (:29090/api/v1/otlp/v1/metrics) across a 3m window
    # so high-coupling callers (>=3 callers at >=10 req/s on product-catalog-service) & failing edges are immediately queryable.
    edges_spec = [
        ("frontend", "product-catalog-service", 18.5, 0.2),
        ("checkout-service", "product-catalog-service", 14.2, 0.1),
        ("recommendation", "product-catalog-service", 12.8, 1.9),
        ("product-catalog-service", "postgresql", 19.4, 0.9),
        ("product-catalog-service", "flagd", 14.0, 0.0),
        ("frontend-proxy", "frontend", 32.0, 1.4),
        ("frontend", "checkout-service", 11.6, 2.5),
        ("checkout-service", "payment", 11.4, 2.6),
        ("checkout-service", "shipping-service", 11.2, 0.4),
        ("shipping-service", "quote", 6.5, 1.3),
        ("frontend", "ad", 15.0, 1.2),
        ("checkout-service", "cart-service", 11.4, 0.5),
    ]
    t0_ns = str(int((now - timedelta(seconds=10)).timestamp() * 1_000_000_000))
    t1_ns = str(int((now - timedelta(seconds=4)).timestamp() * 1_000_000_000))
    t2_ns = str(int(now.timestamp() * 1_000_000_000))

    req_dps = []
    fail_dps = []
    for client_svc, server_svc, rps, err_rps in edges_spec:
        attrs = [
            _otlp_kv("client", client_svc),
            _otlp_kv("server", server_svc),
            _otlp_kv("client_service_namespace", "otel-demo"),
            _otlp_kv("server_service_namespace", "otel-demo"),
        ]
        for ts_cur, scale_s in ((t1_ns, 0.0), (t2_ns, 1800.0)):
            req_dps.append({
                "attributes": attrs,
                "startTimeUnixNano": t0_ns,
                "timeUnixNano": ts_cur,
                "asDouble": round(rps * scale_s, 2),
            })
            fail_dps.append({
                "attributes": attrs,
                "startTimeUnixNano": t0_ns,
                "timeUnixNano": ts_cur,
                "asDouble": round(err_rps * scale_s, 2),
            })

    otlp_metrics = {
        "resourceMetrics": [
            {
                "resource": {"attributes": [_otlp_kv("service.name", "tempo-metrics-generator"), _otlp_kv("service.namespace", "otel-demo")]},
                "scopeMetrics": [
                    {
                        "scope": {"name": "tempo.service_graphs"},
                        "metrics": [
                            {
                                "name": "traces_service_graph_request",
                                "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": req_dps},
                            },
                            {
                                "name": "traces_service_graph_request_failed",
                                "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": fail_dps},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    try:
        _http_req("http://localhost:29090", "POST", "/api/v1/otlp/v1/metrics", org_id=None, body=json.dumps(otlp_metrics), timeout=5)
    except Exception:
        pass

    # 3. Wait 6s for Tempo's 5s local_blocks max_block_duration so TraceQL Metrics & live ingester traces are immediately queryable.
    time.sleep(6)


def reset_overrides_and_operator_crs() -> None:
    """Idempotently reset Tempo /api/overrides for otel-demo & otel-staging and Kubernetes Operator CRs."""
    # 1. Reset /api/overrides for otel-demo and otel-staging (with peer SRE's max_traces_per_user: 42000 on otel-staging)
    for tenant_id, desired_doc in [
        (
            "otel-demo",
            {
                "ingestion_rate_limit_bytes": 26214400,
                "ingestion_burst_size_bytes": 39321600,
                "max_bytes_per_trace": 5242880,
                "max_traces_per_user": 25000,
                "block_retention": "336h",
                "metrics_generator": {"processors": ["service-graphs", "span-metrics", "local-blocks"]},
            },
        ),
        (
            "otel-staging",
            {
                "ingestion_rate_limit_bytes": 10485760,
                "ingestion_burst_size_bytes": 15728640,
                "max_traces_per_user": 42000,
                "block_retention": "72h",
            },
        ),
    ]:
        _http_req(
            TEMPO_LOCAL_URL,
            "POST",
            "/api/overrides",
            org_id=tenant_id,
            body=json.dumps(desired_doc),
            extra_headers={"If-Match": "*"},
        )

    # 2. Clean disposable Tempo Operator CRs in observability
    for plural, name in [
        ("tempostacks.tempo.grafana.com", "tempo-otel-prod"),
        ("tempostacks.tempo.grafana.com", "tempo-otel-azure"),
        ("tempostacks.tempo.grafana.com", "tempo-otel-ephemeral"),
        ("tempomonolithics.tempo.grafana.com", "tempo-otel-staging"),
        ("tempomonolithics.tempo.grafana.com", "otel-staging"),
    ]:
        _kubectl("delete", plural, name, "-n", NAMESPACE, "--ignore-not-found", check=False)

    # 3. Stage baseline Secrets + TempoStack/tempo-otel (Ready=True, 168h) + TempoStack/tempo-otel-degraded (Ready=False)
    k8s_objs = [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "tempo-otel-s3-credentials", "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {
                "endpoint": "https://s3.us-east-1.amazonaws.com",
                "bucket": "talkops-otel-tempo-traces",
                "region": "us-east-1",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "tempo-otel-gcs-creds", "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {"bucketname": "talkops-otel-tempo-gcs"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "tempo-otel-azure-blob", "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {"container": "talkops-otel-tempo-azure"},
        },
        {
            "apiVersion": "tempo.grafana.com/v1alpha1",
            "kind": "TempoStack",
            "metadata": {
                "name": "tempo-otel",
                "namespace": NAMESPACE,
                "labels": {"app.kubernetes.io/part-of": "otel-observability"},
            },
            "spec": {
                "storage": {"secret": {"name": "tempo-otel-s3-credentials", "type": "s3"}},
                "storageSize": "50Gi",
                "replicationFactor": 2,
                "retention": {"global": {"traces": "168h"}},
                "resources": {"total": {"limits": {"cpu": "6000m", "memory": "12Gi"}}},
                "template": {
                    "distributor": {"replicas": 2},
                    "ingester": {"replicas": 3},
                    "querier": {"replicas": 2},
                    "queryFrontend": {"replicas": 2},
                    "compactor": {"replicas": 1},
                    "metricsGenerator": {"enabled": True},
                },
            },
        },
        {
            "apiVersion": "tempo.grafana.com/v1alpha1",
            "kind": "TempoStack",
            "metadata": {
                "name": "tempo-otel-degraded",
                "namespace": NAMESPACE,
                "labels": {"app.kubernetes.io/part-of": "otel-observability"},
            },
            "spec": {
                "storage": {"secret": {"name": "tempo-otel-missing-s3-secret", "type": "s3"}},
                "storageSize": "50Gi",
                "replicationFactor": 2,
                "retention": {"global": {"traces": "168h"}},
            },
        },
    ]
    k8s_yaml = "\n---\n".join(yaml.safe_dump(o, sort_keys=False) for o in k8s_objs)
    _kubectl(
        "apply",
        "--server-side",
        "--field-manager=talkops-tempo-mcp",
        "--force-conflicts",
        "-f",
        "-",
        stdin_text=k8s_yaml,
    )

    # Patch status subresources on TempoStack/tempo-otel (Ready=True) and TempoStack/tempo-otel-degraded (Ready=False)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _kubectl(
        "patch",
        "tempostacks.tempo.grafana.com",
        "tempo-otel",
        "-n",
        NAMESPACE,
        "--subresource=status",
        "--type=merge",
        "-p",
        json.dumps(
            {
                "status": {
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "True",
                            "reason": "Reconciled",
                            "message": "All TempoStack components are ready",
                            "lastTransitionTime": now_iso,
                        }
                    ]
                }
            }
        ),
    )
    _kubectl(
        "patch",
        "tempostacks.tempo.grafana.com",
        "tempo-otel-degraded",
        "-n",
        NAMESPACE,
        "--subresource=status",
        "--type=merge",
        "-p",
        json.dumps(
            {
                "status": {
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "False",
                            "reason": "StorageSecretNotFound",
                            "message": 'Secret "tempo-otel-missing-s3-secret" not found in namespace "observability"',
                            "lastTransitionTime": now_iso,
                        }
                    ]
                }
            }
        ),
    )


def deploy_all() -> None:
    install_tempo_crds_and_workload()
    wire_otel_app_deployments()
    write_tempo_env()
    wait_for_tempo_ready()
    print("[4/5] Seeding multi-tenant OTEL-APP traces & triggering discarded-span counters...")
    seed_otel_traces()
    trigger_discarded_spans()
    seed_prometheus_service_graph_metrics()
    print("[5/5] Staging Tempo /api/overrides and Kubernetes TempoStack CRs...")
    reset_overrides_and_operator_crs()
    print("[DONE] Domain 9 (Grafana Tempo 2.7.1) battleground is 100% live and staged!")


def reset_state(skill_name: str | None = None) -> None:
    write_tempo_env()
    # Rollout-restart deploy/tempo so emptyDir WAL & local-blocks start 100% clean with zero duplicate blocks or stale gRPC pools
    _kubectl("rollout", "restart", "deploy/tempo", "-n", NAMESPACE)
    _kubectl("rollout", "status", "deploy/tempo", "-n", NAMESPACE, "--timeout=60s")
    wait_for_tempo_ready(max_wait_sec=45)
    seed_otel_traces()
    trigger_discarded_spans()
    seed_prometheus_service_graph_metrics()
    reset_overrides_and_operator_crs()
    print(f"[RESET OK] Clean Domain 9 Tempo state staged{f' for {skill_name}' if skill_name else ''}.")


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "deploy"
    skill_arg = sys.argv[2] if len(sys.argv) > 2 else None
    if action == "deploy":
        deploy_all()
    elif action == "reset":
        reset_state(skill_arg)
    else:
        print(f"Unknown action '{action}'. Use 'deploy' or 'reset'.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
