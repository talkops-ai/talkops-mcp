#!/usr/bin/env python3
"""Domain 8 (Grafana Loki 3.x) Live Kubernetes Battleground Deployer & Idempotent Stager.

Deploys Grafana Loki 3.3.2 SingleBinary in namespace `observability` on `docker-desktop`
exposed via `Service/loki` (:3100 in-cluster) and `Service/loki-lb` (`http://localhost:13100`,
avoiding `:3100` Argo Rollouts Dashboard), installs `loki.grafana.com` (`v1` & `v1beta1`)
CRDs (`LokiStack`, `AlertingRule`, `RecordingRule`, `RulerConfig`), enables live OTLP log
export on `OTEL-APP` deployments in `otel-demo`, writes `evals/workspaces/.loki.env`, and
idempotently stages multi-tenant logs, structured metadata, discarded-sample counters,
Ruler rule groups, Compactor delete requests, and Loki Operator CRs.

Usage:
  python3 scripts/stage_d8_loki.py deploy
  python3 scripts/stage_d8_loki.py reset [skill-name]
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
LOKI_IMAGE = "grafana/loki:3.3.2"
LOKI_LOCAL_URL = "http://localhost:13100"

DEVOPS_PLUGINS_ROOT = Path(os.environ.get("DEVOPS_PLUGINS_ROOT", Path(__file__).resolve().parents[4] / "devops-plugins"))
WORKSPACES_DIR = DEVOPS_PLUGINS_ROOT / "evals" / "workspaces"
LOKI_ENV_FILE = WORKSPACES_DIR / ".loki.env"

LOKI_CONFIG_YAML = """auth_enabled: true

server:
  http_listen_port: 3100
  grpc_listen_port: 9095
  log_level: warn

common:
  instance_addr: 127.0.0.1
  path_prefix: /var/loki
  storage:
    filesystem:
      chunks_directory: /var/loki/chunks
      rules_directory: /var/loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2024-04-01"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /var/loki/tsdb-index
    cache_location: /var/loki/tsdb-cache
  filesystem:
    directory: /var/loki/chunks

ingester:
  chunk_encoding: snappy
  chunk_target_size: 1572864
  chunk_idle_period: 30m
  max_chunk_age: 2h
  wal:
    enabled: true
    dir: /var/loki/wal

pattern_ingester:
  enabled: true

limits_config:
  allow_structured_metadata: true
  discover_log_levels: true
  volume_enabled: true
  unordered_writes: true
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  creation_grace_period: 30m
  retention_period: 720h
  ingestion_rate_mb: 64
  ingestion_burst_size_mb: 128
  per_stream_rate_limit: 10MB
  per_stream_rate_limit_burst: 20MB
  max_global_streams_per_user: 50000
  max_line_size: 256KB
  max_line_size_truncate: false

runtime_config:
  file: /etc/loki/overrides.yaml
  period: 5s

compactor:
  working_directory: /var/loki/compactor
  compaction_interval: 5m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 50
  delete_request_store: filesystem

ruler:
  storage:
    type: s3
    s3:
      endpoint: 127.0.0.1:9000
      bucketnames: loki-ruler
      access_key_id: loki
      secret_access_key: lokistore
      s3forcepathstyle: true
      insecure: true
  rule_path: /var/loki/rules-temp
  alertmanager_url: http://alertmanager.observability.svc.cluster.local:9093
  ring:
    kvstore:
      store: inmemory
  enable_api: true
"""

MINIS3_SERVER_PY = r"""import hashlib, http.server, os, socketserver, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path("/var/s3")
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "loki-ruler").mkdir(parents=True, exist_ok=True)

class S3Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _parts(self):
        parsed = urllib.parse.urlparse(self.path)
        rel = urllib.parse.unquote(parsed.path).lstrip("/")
        qs = urllib.parse.parse_qs(parsed.query)
        if "/" in rel:
            bkt, key = rel.split("/", 1)
        else:
            bkt, key = rel, ""
        return bkt, key, qs

    def _send(self, code, body=b"", ctype="application/xml", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def do_HEAD(self):
        bkt, key, _ = self._parts()
        bdir = ROOT / bkt
        if not key:
            return self._send(200 if bdir.exists() else 404)
        fp = bdir / key
        if not fp.is_file():
            return self._send(404)
        data = fp.read_bytes()
        etag = '"' + hashlib.md5(data).hexdigest() + '"'
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", "Mon, 16 Nov 2026 00:00:00 GMT")
        self.end_headers()

    def do_GET(self):
        bkt, key, qs = self._parts()
        bdir = ROOT / bkt
        bdir.mkdir(parents=True, exist_ok=True)
        if not key:
            prefix = qs.get("prefix", [""])[0]
            delim = qs.get("delimiter", [""])[0]
            contents = []
            common_prefixes = set()
            for p in sorted(bdir.rglob("*")):
                if not p.is_file():
                    continue
                rel_k = p.relative_to(bdir).as_posix()
                if prefix and not rel_k.startswith(prefix):
                    continue
                if delim:
                    rem = rel_k[len(prefix):]
                    if delim in rem:
                        cp = prefix + rem.split(delim, 1)[0] + delim
                        common_prefixes.add(cp)
                        continue
                data = p.read_bytes()
                etag = '"' + hashlib.md5(data).hexdigest() + '"'
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                contents.append(
                    f"<Contents><Key>{escape(rel_k)}</Key><LastModified>{ts}</LastModified>"
                    f"<ETag>{escape(etag)}</ETag><Size>{len(data)}</Size><StorageClass>STANDARD</StorageClass></Contents>"
                )
            cp_xml = "".join(f"<CommonPrefixes><Prefix>{escape(cp)}</Prefix></CommonPrefixes>" for cp in sorted(common_prefixes))
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                f"<Name>{escape(bkt)}</Name><Prefix>{escape(prefix)}</Prefix>"
                f"<KeyCount>{len(contents) + len(common_prefixes)}</KeyCount><MaxKeys>1000</MaxKeys>"
                f"<IsTruncated>false</IsTruncated>{''.join(contents)}{cp_xml}</ListBucketResult>"
            )
            return self._send(200, xml)
        fp = bdir / key
        if not fp.is_file():
            err = '<?xml version="1.0" encoding="UTF-8"?><Error><Code>NoSuchKey</Code><Message>Not found</Message></Error>'
            return self._send(404, err)
        data = fp.read_bytes()
        etag = '"' + hashlib.md5(data).hexdigest() + '"'
        return self._send(200, data, ctype="application/octet-stream", extra={"ETag": etag})

    def do_PUT(self):
        bkt, key, _ = self._parts()
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""
        bdir = ROOT / bkt
        bdir.mkdir(parents=True, exist_ok=True)
        if not key:
            return self._send(200, b"")
        fp = bdir / key
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(body)
        etag = '"' + hashlib.md5(body).hexdigest() + '"'
        return self._send(200, b"", extra={"ETag": etag})

    def do_DELETE(self):
        bkt, key, _ = self._parts()
        if key:
            fp = ROOT / bkt / key
            if fp.is_file():
                fp.unlink()
        return self._send(204, b"")

    def do_POST(self):
        bkt, _, qs = self._parts()
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="ignore") if length > 0 else ""
        if "delete" in qs or "<Delete" in raw:
            import re as _re
            for k in _re.findall(r"<Key>(.*?)</Key>", raw):
                fp = ROOT / bkt / k
                if fp.is_file():
                    fp.unlink()
            return self._send(200, '<?xml version="1.0" encoding="UTF-8"?><DeleteResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"></DeleteResult>')
        return self._send(200, b"")

class ThreadedS3(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    ThreadedS3(("127.0.0.1", 9000), S3Handler).serve_forever()
"""

LOKI_OVERRIDES_YAML = """overrides:
  otel-drop-rate:
    ingestion_rate_mb: 0.0001
    ingestion_burst_size_mb: 0.0001
  otel-drop-stream-rate:
    per_stream_rate_limit: 64B
    per_stream_rate_limit_burst: 64B
  otel-drop-max-streams:
    max_global_streams_per_user: 1
  otel-drop-line-len:
    max_line_size: 256B
    max_line_size_truncate: false
  otel-loadtest:
    retention_period: 72h
"""


def _build_crd_manifest(kind: str, plural: str, singular: str) -> dict[str, Any]:
    open_schema = {
        "type": "object",
        "properties": {
            "spec": {"type": "object", "x-kubernetes-preserve-unknown-fields": True},
            "status": {"type": "object", "x-kubernetes-preserve-unknown-fields": True},
        },
        "x-kubernetes-preserve-unknown-fields": True,
    }
    return {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": f"{plural}.loki.grafana.com"},
        "spec": {
            "group": "loki.grafana.com",
            "names": {
                "kind": kind,
                "listKind": f"{kind}List",
                "plural": plural,
                "singular": singular,
            },
            "scope": "Namespaced",
            "versions": [
                {
                    "name": "v1",
                    "served": True,
                    "storage": True,
                    "schema": {"openAPIV3Schema": open_schema},
                    "subresources": {"status": {}},
                },
                {
                    "name": "v1beta1",
                    "served": True,
                    "storage": False,
                    "schema": {"openAPIV3Schema": open_schema},
                    "subresources": {"status": {}},
                },
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
    method: str,
    path: str,
    *,
    org_id: str = "otel-demo",
    body: bytes | str | None = None,
    content_type: str = "application/json",
    params: dict[str, str] | None = None,
    timeout: int = 15,
) -> tuple[int, str]:
    url = f"{LOKI_LOCAL_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = body.encode("utf-8") if isinstance(body, str) else body
    headers = {"X-Scope-OrgID": org_id}
    if data is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def wait_for_loki_ready(max_wait_sec: int = 90) -> None:
    deadline = time.time() + max_wait_sec
    last_err = ""
    while time.time() < deadline:
        try:
            code, txt = _http_req("GET", "/ready", timeout=3)
            if code == 200:
                print(f"[OK] Loki ready at {LOKI_LOCAL_URL} ({txt.strip()})")
                return
            last_err = f"HTTP {code}: {txt.strip()}"
        except Exception as exc:
            last_err = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for Loki at {LOKI_LOCAL_URL}: {last_err}")


def install_loki_crds_and_workload() -> None:
    print("[1/5] Installing loki.grafana.com CRDs (LokiStack, AlertingRule, RecordingRule, RulerConfig)...")
    crds = [
        _build_crd_manifest("LokiStack", "lokistacks", "lokistack"),
        _build_crd_manifest("AlertingRule", "alertingrules", "alertingrule"),
        _build_crd_manifest("RecordingRule", "recordingrules", "recordingrule"),
        _build_crd_manifest("RulerConfig", "rulerconfigs", "rulerconfig"),
    ]
    crd_yaml = "\n---\n".join(yaml.safe_dump(c, sort_keys=False) for c in crds)
    _kubectl("apply", "-f", "-", stdin_text=crd_yaml)

    print(f"[2/5] Deploying {LOKI_IMAGE} SingleBinary + Service/loki + Service/loki-lb (:13100) in {NAMESPACE}...")
    manifests = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "loki-d8-config", "namespace": NAMESPACE},
            "data": {
                "loki.yaml": LOKI_CONFIG_YAML,
                "overrides.yaml": LOKI_OVERRIDES_YAML,
                "minis3.py": MINIS3_SERVER_PY,
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "loki",
                "namespace": NAMESPACE,
                "labels": {"app": "loki", "domain": "d8-loki"},
            },
            "spec": {
                "replicas": 1,
                "strategy": {"type": "Recreate"},
                "selector": {"matchLabels": {"app": "loki"}},
                "template": {
                    "metadata": {"labels": {"app": "loki", "domain": "d8-loki"}},
                    "spec": {
                        "securityContext": {"fsGroup": 10001, "runAsUser": 10001, "runAsGroup": 10001},
                        "initContainers": [
                            {
                                "name": "init-dirs",
                                "image": "busybox:1.36",
                                "command": [
                                    "sh",
                                    "-c",
                                    "mkdir -p /var/loki/chunks /var/loki/rules /var/loki/rules-temp "
                                    "/var/loki/tsdb-index /var/loki/tsdb-cache /var/loki/wal /var/loki/compactor /var/s3/loki-ruler",
                                ],
                                "volumeMounts": [
                                    {"name": "data", "mountPath": "/var/loki"},
                                    {"name": "s3data", "mountPath": "/var/s3"},
                                ],
                            }
                        ],
                        "containers": [
                            {
                                "name": "s3-ruler-store",
                                "image": "python:3.12-alpine",
                                "command": ["python3", "/etc/loki/minis3.py"],
                                "resources": {
                                    "requests": {"cpu": "20m", "memory": "32Mi"},
                                    "limits": {"cpu": "200m", "memory": "128Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/etc/loki"},
                                    {"name": "s3data", "mountPath": "/var/s3"},
                                ],
                            },
                            {
                                "name": "loki",
                                "image": LOKI_IMAGE,
                                "args": ["-config.file=/etc/loki/loki.yaml", "-target=all"],
                                "ports": [
                                    {"name": "http", "containerPort": 3100},
                                    {"name": "grpc", "containerPort": 9095},
                                ],
                                "readinessProbe": {
                                    "httpGet": {"path": "/ready", "port": 3100},
                                    "initialDelaySeconds": 5,
                                    "periodSeconds": 5,
                                },
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "256Mi"},
                                    "limits": {"cpu": "1000m", "memory": "1Gi"},
                                },
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/etc/loki"},
                                    {"name": "data", "mountPath": "/var/loki"},
                                ],
                            },
                        ],
                        "volumes": [
                            {"name": "config", "configMap": {"name": "loki-d8-config"}},
                            {"name": "data", "emptyDir": {}},
                            {"name": "s3data", "emptyDir": {}},
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "loki", "namespace": NAMESPACE},
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "loki"},
                "ports": [
                    {"name": "http", "port": 3100, "targetPort": 3100},
                    {"name": "grpc", "port": 9095, "targetPort": 9095},
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "loki-lb", "namespace": NAMESPACE},
            "spec": {
                "type": "LoadBalancer",
                "selector": {"app": "loki"},
                "ports": [
                    {"name": "http", "port": 13100, "targetPort": 3100},
                ],
            },
        },
    ]
    bundle_yaml = "\n---\n".join(yaml.safe_dump(m, sort_keys=False) for m in manifests)
    _kubectl("apply", "-f", "-", stdin_text=bundle_yaml)
    _kubectl("rollout", "status", "deploy/loki", "-n", NAMESPACE, "--timeout=120s")


def wire_otel_app_deployments() -> None:
    """Enable live OTLP log shipping on OTEL-APP deployments in otel-demo (keeping quote un-instrumented for eval-09)."""
    print("[3/5] Enabling OTEL_EXPORTER_OTLP_LOGS_ENDPOINT -> Loki 3.x /otlp/v1/logs on otel-demo workloads...")
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
            "OTEL_LOGS_EXPORTER=otlp",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://loki.observability.svc.cluster.local:3100/otlp/v1/logs",
            "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/protobuf",
            "OTEL_EXPORTER_OTLP_HEADERS=X-Scope-OrgID=otel-demo",
            f"OTEL_RESOURCE_ATTRIBUTES=service.namespace=otel-demo,k8s.namespace.name=otel-demo,service.name={svc}-service",
            check=False,
        )


def write_loki_env() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    env_content = (
        f"LOKI_URL={LOKI_LOCAL_URL}\n"
        "LOKI_TIMEOUT=30\n"
        "LOKI_ORG_ID=otel-demo\n"
        "K8S_ENABLED=true\n"
        f"K8S_CONTEXT={KUBE_CONTEXT}\n"
        "MCP_ALLOW_WRITE=true\n"
        "LOKI_TOOLSETS=all\n"
    )
    LOKI_ENV_FILE.write_text(env_content, encoding="utf-8")
    LOKI_ENV_FILE.chmod(0o600)
    print(f"[OK] Wrote {LOKI_ENV_FILE}")


def _ns(dt: datetime) -> str:
    return str(int(dt.timestamp() * 1_000_000_000))


def _push_streams(streams: list[dict[str, Any]], org_id: str = "otel-demo") -> tuple[int, str]:
    payload = json.dumps({"streams": streams})
    return _http_req("POST", "/loki/api/v1/push", org_id=org_id, body=payload)


def trigger_real_discarded_samples() -> None:
    """Trigger genuine loki_discarded_samples_total counters across all key drop reasons."""
    now = datetime.now(timezone.utc)
    # 1. greater_than_max_sample_age (10 days old > 168h reject_old_samples_max_age)
    old_ts = _ns(now - timedelta(days=10))
    _push_streams(
        [
            {
                "stream": {"namespace": "otel-demo", "service_name": "shipping"},
                "values": [[old_ts, "INFO backfilled archival order event from 10d ago"]],
            }
        ],
        org_id="otel-demo",
    )
    # 2. rate_limited
    big_chunk = "X" * 4096
    for i in range(4):
        _push_streams(
            [
                {
                    "stream": {"namespace": "otel-demo", "service_name": "frontend-proxy"},
                    "values": [[_ns(now - timedelta(seconds=10 - i)), f"INFO flood {big_chunk}"]],
                }
            ],
            org_id="otel-drop-rate",
        )
    # 3. per_stream_rate_limit
    for i in range(4):
        _push_streams(
            [
                {
                    "stream": {"namespace": "otel-demo", "service_name": "frontend-proxy"},
                    "values": [[_ns(now - timedelta(seconds=10 - i)), f"INFO stream burst {big_chunk}"]],
                }
            ],
            org_id="otel-drop-stream-rate",
        )
    # 4. max_global_streams_per_user / stream_limit
    _push_streams(
        [
            {
                "stream": {"namespace": "otel-demo", "service_name": "frontend-proxy", "req": "1"},
                "values": [[_ns(now - timedelta(seconds=5)), "stream 1"]],
            },
            {
                "stream": {"namespace": "otel-demo", "service_name": "frontend-proxy", "req": "2"},
                "values": [[_ns(now - timedelta(seconds=4)), "stream 2"]],
            },
            {
                "stream": {"namespace": "otel-demo", "service_name": "frontend-proxy", "req": "3"},
                "values": [[_ns(now - timedelta(seconds=3)), "stream 3"]],
            },
        ],
        org_id="otel-drop-max-streams",
    )
    # 5. line_too_long
    _push_streams(
        [
            {
                "stream": {"namespace": "otel-demo", "service_name": "ad"},
                "values": [[_ns(now - timedelta(seconds=2)), "ERROR Java stacktrace " + ("A" * 1024)]],
            }
        ],
        org_id="otel-drop-line-len",
    )


def seed_otel_logs() -> None:
    """Seed deterministic multi-window, multi-tenant OTEL-APP logs into Loki 3.x."""
    now = datetime.now(timezone.utc)
    otel_demo_streams: list[dict[str, Any]] = []

    # 1. checkout-service: healthy baseline (85m..45m ago) + active paymentUnreachable/paymentFailure spike (14m..1m ago)
    checkout_vals: list[list[Any]] = []
    for i in range(25):
        ts = now - timedelta(minutes=85 - i)
        checkout_vals.append(
            [
                _ns(ts),
                json.dumps(
                    {
                        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "level": "info",
                        "status": 200,
                        "method": "POST",
                        "route": "/oteldemo.CheckoutService/PlaceOrder",
                        "duration_ms": 38 + (i % 9),
                        "order_id": f"ord_base_{i:04d}",
                        "msg": "PlaceOrder completed via PaymentService/Charge",
                    }
                ),
                {
                    "trace_id": f"00112233445566778899aabbccdd{i:04x}",
                    "span_id": f"a1b2c3d4e5f6{i:04x}",
                    "k8s.pod.name": "checkout-84c9c9c9c4-5hxhp",
                    "k8s_pod_name": "checkout-84c9c9c9c4-5hxhp",
                    "severity_text": "INFO",
                },
            ]
        )
    # Current window: healthy + 35 error lines with new PaymentService/Charge Unavailable signature
    spike_trace = "99887766554433221100aabbccddeeff"
    for i in range(20):
        ts = now - timedelta(minutes=14, seconds=30 - i)
        checkout_vals.append(
            [
                _ns(ts),
                json.dumps(
                    {
                        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "level": "info",
                        "status": 200,
                        "method": "POST",
                        "route": "/oteldemo.CheckoutService/PlaceOrder",
                        "duration_ms": 1350 + (i * 15),
                        "order_id": f"ord_curr_{i:04d}",
                        "msg": "PlaceOrder retrying kafka publish (kafkaQueueProblems=on)",
                    }
                ),
                {
                    "trace_id": f"2233445566778899aabbccddeeff{i:04x}",
                    "span_id": f"b1c2d3e4f5a6{i:04x}",
                    "k8s.pod.name": "checkout-84c9c9c9c4-5hxhp",
                    "k8s_pod_name": "checkout-84c9c9c9c4-5hxhp",
                    "severity_text": "WARN",
                },
            ]
        )
    for i in range(32):
        ts = now - timedelta(minutes=13) + timedelta(seconds=i * 20)
        tid = spike_trace if i == 0 else f"5566778899aabbccddeeff001122{i:04x}"
        checkout_vals.append(
            [
                _ns(ts),
                json.dumps(
                    {
                        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "level": "error",
                        "status": 503,
                        "method": "POST",
                        "route": "/oteldemo.CheckoutService/PlaceOrder",
                        "duration_ms": 1510 + i,
                        "order_id": f"ord_fail_{i:04d}",
                        "trace_id": tid,
                        "flag": "paymentUnreachable",
                        "msg": "PlaceOrder failed: could not charge the card: PaymentService/Charge rpc error: code = Unavailable desc = upstream payment connection refused",
                    }
                ),
                {
                    "trace_id": tid,
                    "span_id": f"c1d2e3f4a5b6{i:04x}",
                    "k8s.pod.name": "checkout-84c9c9c9c4-5hxhp",
                    "k8s_pod_name": "checkout-84c9c9c9c4-5hxhp",
                    "severity_text": "ERROR",
                },
            ]
        )
    checkout_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "checkout-service",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": checkout_vals,
        }
    )

    # 2. payment: root-cause Charge error 5ms BEFORE checkout-service on spike_trace + synthetic PII lines
    t_pay_root = now - timedelta(minutes=13) - timedelta(milliseconds=15)
    payment_vals: list[list[Any]] = [
        [
            _ns(now - timedelta(minutes=75)),
            '{"level":"info","service":"payment","rpc":"oteldemo.PaymentService/Charge","status":200,"msg":"Card charged"}',
            {"severity_text": "INFO", "k8s.pod.name": "payment-c98fddbc4-pcmbd"},
        ],
        [
            _ns(t_pay_root),
            json.dumps(
                {
                    "level": "error",
                    "service": "payment",
                    "rpc": "oteldemo.PaymentService/Charge",
                    "status": 503,
                    "trace_id": spike_trace,
                    "flag": "paymentUnreachable",
                    "msg": "FATAL PaymentService/Charge failed: payment gateway unreachable (flagd paymentUnreachable=on)",
                }
            ),
            {
                "trace_id": spike_trace,
                "span_id": "0000111122223333",
                "severity_text": "ERROR",
                "k8s.pod.name": "payment-c98fddbc4-pcmbd",
            },
        ],
    ]
    for i in range(12):
        ts_p = now - timedelta(minutes=12) + timedelta(seconds=i * 30)
        payment_vals.append(
            [
                _ns(ts_p),
                json.dumps(
                    {
                        "level": "error",
                        "service": "payment",
                        "rpc": "oteldemo.PaymentService/Charge",
                        "status": 503,
                        "msg": "PaymentService/Charge declined: flagd paymentFailure active",
                    }
                ),
                {"severity_text": "ERROR", "k8s.pod.name": "payment-c98fddbc4-pcmbd"},
            ]
        )
    for i in range(3):
        ts_pii = now - timedelta(minutes=40 - i * 5)
        payment_vals.append(
            [
                _ns(ts_pii),
                f'WARN oteldemo.PaymentService/Charge debug payload credit_card_number=4111-2222-3333-000{i} order_id=ord_pii_{i}',
                {"severity_text": "WARN", "k8s.pod.name": "payment-c98fddbc4-pcmbd"},
            ]
        )
    payment_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "payment",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": payment_vals,
        }
    )

    # 3. Cross-service trace 4bf92f3577b34da6a3ce929d0e0e4736 (postgresql -> product-catalog-service -> recommendation -> frontend-proxy)
    # Placed at now - 28m so recommendation is active at that moment and goes silent 25m ago!
    t_chain = now - timedelta(minutes=28)
    corr_trace = "4bf92f3577b34da6a3ce929d0e0e4736"

    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "postgresql",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": [
                [
                    _ns(t_chain),
                    f"FATAL: remaining connection slots are reserved for superuser (db=otel, max_connections=100) trace_id={corr_trace}",
                    {"trace_id": corr_trace, "severity_text": "FATAL", "k8s.pod.name": "postgresql-db-6fffbdd97d-zkmnz"},
                ]
            ],
        }
    )

    # 4. product-catalog-service (stable 2.2.0 + canary 2.3.0-canary + L9ECAV7KIM errors + corr_trace)
    pc_stable_vals: list[list[Any]] = [
        [
            _ns(t_chain + timedelta(milliseconds=3)),
            json.dumps(
                {
                    "ts": (t_chain + timedelta(milliseconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "level": "error",
                    "product.id": "L9ECAV7KIM",
                    "trace_id": corr_trace,
                    "msg": "GetProduct failed for L9ECAV7KIM: pq: sorry, too many clients already",
                }
            ),
            {"trace_id": corr_trace, "severity_text": "ERROR", "k8s.pod.name": "product-catalog-stable-1"},
        ]
    ]
    for i in range(10):
        ts_pc = now - timedelta(minutes=18 - i)
        pc_stable_vals.append(
            [
                _ns(ts_pc),
                json.dumps(
                    {
                        "ts": ts_pc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "level": "info",
                        "product.id": "OLJCESPC7Z",
                        "msg": "GetProduct succeeded",
                    }
                ),
                {"severity_text": "INFO", "k8s.pod.name": "product-catalog-stable-1"},
            ]
        )
    pc_stable_vals.append(
        [
            _ns(now - timedelta(minutes=6)),
            json.dumps(
                {
                    "ts": (now - timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "level": "error",
                    "product.id": "L9ECAV7KIM",
                    "msg": "panic: ProductCatalogFailure enabled for L9ECAV7KIM",
                }
            ),
            {"severity_text": "ERROR", "k8s.pod.name": "product-catalog-stable-1"},
        ]
    )
    pc_stable_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "product-catalog-service",
                "version": "2.2.0",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": pc_stable_vals,
        }
    )

    pc_canary_vals: list[list[Any]] = []
    for i in range(14):
        ts_can = now - timedelta(minutes=16 - i)
        pc_canary_vals.append(
            [
                _ns(ts_can),
                json.dumps(
                    {
                        "ts": ts_can.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "level": "error",
                        "product.id": "L9ECAV7KIM",
                        "version": "2.3.0-canary",
                        "msg": "ERROR canary proto v2 schema deserialization panic: nil priceMicros on L9ECAV7KIM",
                    }
                ),
                {"severity_text": "ERROR", "k8s.pod.name": "product-catalog-canary-7b9d"},
            ]
        )
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "product-catalog-service",
                "version": "2.3.0-canary",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": pc_canary_vals,
        }
    )

    # 5. recommendation: active 90m..26m ago, silent for last 25m (eval-06), with OTLP structured metadata (eval-02)
    rec_vals: list[list[Any]] = []
    for i in range(12):
        ts_r = now - timedelta(minutes=60 - i * 2)
        rec_vals.append(
            [
                _ns(ts_r),
                f"INFO ListRecommendations served 5 items for product=OLJCESPC7Z",
                {
                    "k8s.pod.name": "recommendation-6b7f",
                    "k8s_pod_name": "recommendation-6b7f",
                    "k8s.container.name": "recommendation",
                    "trace_id": f"77889900aabbccddeeff11223344{i:04x}",
                    "span_id": f"112233445566{i:04x}",
                    "severity_text": "INFO",
                },
            ]
        )
    rec_vals.append(
        [
            _ns(t_chain + timedelta(milliseconds=6)),
            f"ERROR gRPC ListRecommendations failed: upstream product-catalog-service Unavailable trace_id={corr_trace}",
            {
                "k8s.pod.name": "recommendation-6b7f",
                "k8s_pod_name": "recommendation-6b7f",
                "k8s.container.name": "recommendation",
                "trace_id": corr_trace,
                "span_id": "5566778899aabbcc",
                "severity_text": "ERROR",
            },
        ]
    )
    rec_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "recommendation",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": rec_vals,
        }
    )

    # 6. frontend-proxy: Envoy access patterns + JSON 200/503 + logfmt external 403 + corr_trace + unpropagated trace
    unprop_trace = "abcdef1234567890abcdef1234567890"
    t_unprop = now - timedelta(minutes=11)
    fp_vals: list[list[Any]] = [
        [
            _ns(t_chain + timedelta(milliseconds=9)),
            f'[{(t_chain + timedelta(milliseconds=9)).strftime("%Y-%m-%dT%H:%M:%S.121Z")}] "GET /api/recommendations HTTP/2" 503 UF 0 94 185 184 "10.42.0.9" "Mozilla/5.0" "{corr_trace}" "frontend-proxy:8090" "10.96.174.254:8080" trace_id={corr_trace}',
            {"trace_id": corr_trace, "severity_text": "ERROR"},
        ],
        [
            _ns(t_unprop),
            f'[{t_unprop.strftime("%Y-%m-%dT%H:%M:%S.010Z")}] "POST /api/checkout HTTP/2" 503 UF 512 128 940 938 "10.42.0.12" "Mozilla/5.0" "{unprop_trace}" "frontend-proxy:8090" "10.96.214.116:8080" trace_id={unprop_trace}',
            {"trace_id": unprop_trace, "severity_text": "ERROR"},
        ],
    ]
    for i in range(40):
        ts_e = now - timedelta(minutes=45) + timedelta(seconds=i * 55)
        status_code = 503 if i % 8 == 0 else 200
        dur = 890 if status_code == 503 else (22 + (i % 15))
        route = "/oteldemo.CheckoutService/PlaceOrder" if i % 3 == 0 else "/api/products"
        fp_vals.append(
            [
                _ns(ts_e),
                f'[{ts_e.strftime("%Y-%m-%dT%H:%M:%S.123Z")}] "POST {route} HTTP/2" {status_code} - 512 1024 {dur} {dur - 2} "-" "grpc-node-js/1.10"',
                {"severity_text": "ERROR" if status_code >= 500 else "INFO"},
            ]
        )
    # JSON status lines for eval-09 & RecordingRule backtest (eval-03)
    for i in range(20):
        ts_j = now - timedelta(minutes=25) + timedelta(seconds=i * 60)
        st = 502 if i % 5 == 0 else 200
        fp_vals.append(
            [
                _ns(ts_j + timedelta(milliseconds=200)),
                json.dumps(
                    {
                        "status": st,
                        "route": "/api/checkout" if st >= 500 else "/api/products",
                        "duration_ms": 640 if st >= 500 else 19,
                        "msg": "envoy_upstream_response",
                    }
                ),
                {"severity_text": "ERROR" if st >= 500 else "INFO"},
            ]
        )
    # logfmt 403 external vs internal CIDR (eval-07)
    for i in range(5):
        ts_c = now - timedelta(minutes=20 - i * 3)
        fp_vals.append(
            [
                _ns(ts_c + timedelta(milliseconds=350)),
                f'ts={ts_c.strftime("%Y-%m-%dT%H:%M:%SZ")} level=warn status=403 client_ip=203.0.113.{40 + i} method=GET route=/admin msg="waf_forbidden_external"',
                {"severity_text": "WARN"},
            ]
        )
        fp_vals.append(
            [
                _ns(ts_c + timedelta(milliseconds=400)),
                f'ts={ts_c.strftime("%Y-%m-%dT%H:%M:%SZ")} level=warn status=403 client_ip=10.42.1.{10 + i} method=GET route=/metrics msg="internal_rbac_denied"',
                {"severity_text": "WARN"},
            ]
        )
    fp_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "frontend-proxy",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": fp_vals,
        }
    )

    # High-cardinality client_ip/session_id streams on frontend-proxy for FinOps audit (eval-01/03)
    for idx_hc in range(12):
        ts_hc = now - timedelta(minutes=30 - idx_hc)
        otel_demo_streams.append(
            {
                "stream": {
                    "namespace": "otel-demo",
                    "service_namespace": "otel-demo",
                    "service_name": "frontend-proxy",
                    "pod": f"frontend-proxy-7d9f-{idx_hc:02d}",
                    "client_ip": f"198.51.100.{idx_hc + 10}",
                    "session_id": f"sess-flood-{idx_hc:04d}",
                    "trace_id": f"eeff00112233445566778899aabb{idx_hc:04x}",
                },
                "values": [
                    [
                        _ns(ts_hc),
                        'GET /healthz HTTP/1.1 200 kube-probe/1.31 level=debug msg="homepage flood probe ok"',
                    ]
                ],
            }
        )

    # 7. frontend: JSON route duration_ms + malformed line to test | unwrap duration_ms | __error__=""
    routes = ["/api/checkout", "/api/products", "/api/recommendations", "/api/cart", "/api/currency", "/api/shipping"]
    base_durs = {"/api/checkout": 840, "/api/recommendations": 510, "/api/products": 190, "/api/shipping": 140, "/api/cart": 85, "/api/currency": 35}
    fe_vals: list[list[Any]] = []
    for m in range(55):
        ts_fe = now - timedelta(minutes=56 - m)
        rt = routes[m % len(routes)]
        fe_vals.append(
            [
                _ns(ts_fe),
                json.dumps(
                    {
                        "level": "info",
                        "route": rt,
                        "status": 200,
                        "duration_ms": base_durs[rt] + (m % 25),
                        "msg": "SSR request handled",
                    }
                ),
            ]
        )
    fe_vals.append(
        [
            _ns(now - timedelta(minutes=2, seconds=15)),
            '{"level":"warn","route":"/api/checkout","duration_ms":"N/A","msg":"aborted client stream"}',
        ]
    )
    fe_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "frontend",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": fe_vals,
        }
    )

    # 8. cart-service: OTLP structured metadata k8s.pod.name="cart-7f9d8c-2x9lm" + severity_text="ERROR" (eval-10)
    cart_vals: list[list[Any]] = []
    for i in range(15):
        ts_c = now - timedelta(minutes=22 - i)
        cart_vals.append(
            [
                _ns(ts_c),
                f"valkey-cart:6379 timeout on GetCart for user_cart_{i} (failedReadinessProbe)",
                {
                    "k8s.pod.name": "cart-7f9d8c-2x9lm",
                    "k8s_pod_name": "cart-7f9d8c-2x9lm",
                    "severity_text": "ERROR",
                    "trace_id": f"aabbccddeeff0011223344556677{i:04x}",
                    "span_id": f"998877665544{i:04x}",
                },
            ]
        )
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "cart-service",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": cart_vals,
        }
    )

    # 9. shipping-service + quote: duplicate "service_name":"quote" key (eval-08), unpropagated trace (eval-09), & accidental_purge_marker (eval-03)
    ship_vals: list[list[Any]] = [
        [
            _ns(t_unprop + timedelta(milliseconds=120)),
            json.dumps(
                {
                    "level": "error",
                    "service_name": "quote",
                    "endpoint": "http://quote:8080/getquote",
                    "status": 500,
                    "trace_id": unprop_trace,
                    "msg": "downstream quote /getquote returned HTTP 500 for 0-item shipment",
                }
            ),
            {"trace_id": unprop_trace, "severity_text": "ERROR"},
        ],
        [
            _ns(now - timedelta(minutes=15)),
            json.dumps(
                {
                    "level": "info",
                    "service_name": "quote",
                    "status": 200,
                    "duration_ms": 28,
                    "msg": "quote calculated",
                }
            ),
            {"severity_text": "INFO"},
        ],
        [
            _ns(now - timedelta(minutes=9)),
            '{"level":"warn","service_name":"quote","msg":"accidental_purge_marker test record"}',
            {"severity_text": "WARN"},
        ],
    ]
    ship_vals.sort(key=lambda x: int(x[0]))
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "shipping-service",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": ship_vals,
        }
    )

    # PHP quote without trace_id at t_unprop + 200ms (within +-5s fallback window for eval-09!)
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "quote",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": [
                [
                    _ns(now - timedelta(minutes=50)),
                    "INFO [php-fpm] POST /getquote items=3 quote_usd=8.95 status=200",
                ],
                [
                    _ns(t_unprop + timedelta(milliseconds=210)),
                    "ERROR [php-fpm] POST /getquote DivisionByZeroError: item_count=0 cannot compute shipping cost status=500",
                ],
            ],
        }
    )

    # 10. email: pod email-5d9c8b-k2m9q startup + NoMemoryError OOM death rattle + synthetic PII email line
    t_em_boot = now - timedelta(minutes=10)
    otel_demo_streams.append(
        {
            "stream": {
                "namespace": "otel-demo",
                "service_namespace": "otel-demo",
                "service_name": "email",
                "pod": "email-5d9c8b-k2m9q",
                "cluster": "docker-desktop",
                "env": "prod",
            },
            "values": [
                [
                    _ns(now - timedelta(minutes=70)),
                    "INFO Sinatra email server healthy rss=42MiB",
                    {"k8s.pod.name": "email-5d9c8b-k2m9q", "severity_text": "INFO"},
                ],
                [
                    _ns(now - timedelta(minutes=35)),
                    "INFO /send_order_confirmation sent receipt to customer_email=alice.pii-test@example.com order_id=ord_991",
                    {"k8s.pod.name": "email-5d9c8b-k2m9q", "severity_text": "INFO"},
                ],
                [
                    _ns(t_em_boot),
                    "INFO Starting Ruby Sinatra email-service on 0.0.0.0:8080 FLAGD_HOST=flagd:8013 memory_limit=100Mi emailMemoryLeak=10000x",
                    {"k8s.pod.name": "email-5d9c8b-k2m9q", "severity_text": "INFO"},
                ],
                [
                    _ns(t_em_boot + timedelta(seconds=3)),
                    "WARN Connected to flagd:8013; variant emailMemoryLeak=10000x active on /send_order_confirmation",
                    {"k8s.pod.name": "email-5d9c8b-k2m9q", "severity_text": "WARN"},
                ],
                [
                    _ns(t_em_boot + timedelta(seconds=18)),
                    "FATAL email NoMemoryError: failed to allocate 104857600 bytes in /send_order_confirmation (container RSS 100Mi/100Mi OOMKilled)",
                    {"k8s.pod.name": "email-5d9c8b-k2m9q", "severity_text": "FATAL"},
                ],
            ],
        }
    )

    # 11. ad, kafka, image-provider, currency-service, flagd, valkey-cart, load-generator
    otel_demo_streams.extend(
        [
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "ad", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [_ns(now - timedelta(minutes=19)), "WARN AdService - ManualGC #1 triggered for contextKey astronomy after 1180ms"],
                    [_ns(now - timedelta(minutes=14)), "WARN AdService - ManualGC #2 triggered for contextKey telescope after 1420ms"],
                    [_ns(now - timedelta(minutes=8)), "ERROR AdService - java.lang.OutOfMemoryError: Java heap space during GetAds"],
                ],
            },
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "kafka", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [_ns(now - timedelta(minutes=17)), 'WARN [KafkaRaft] consumer_group=checkout-orders lag=4820 retrying fetch (kafkaQueueProblems=on) duration_ms=1640'],
                    [_ns(now - timedelta(minutes=9)), 'WARN [KafkaRaft] producer queue saturation deadline exceeded retrying partition=0 duration_ms=1890'],
                ],
            },
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "image-provider", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [
                        _ns(now - timedelta(minutes=4, seconds=i * 15)),
                        f'10.2.3.{i + 1} - - [{(now - timedelta(minutes=4, seconds=i * 15)).strftime("%d/%b/%Y:%H:%M:%S +0000")}] '
                        f'"GET /images/LensCleaningKit.jpg HTTP/1.1" {502 if i % 4 == 0 else 200} 154',
                    ]
                    for i in range(12)
                ][::-1],
            },
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "currency-service", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [_ns(now - timedelta(minutes=12)), "ts=2026-11-16T14:00:00Z level=info service=currency-service from=USD to=EUR rate=0.92 duration_ms=4"],
                    [_ns(now - timedelta(minutes=5)), "ts=2026-11-16T14:07:00Z level=info service=currency-service from=USD to=JPY rate=153.4 duration_ms=3"],
                ],
            },
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "flagd", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [_ns(now - timedelta(minutes=15)), "ts=2026-11-16T14:00:00Z level=warn service=flagd port=8013 flag=paymentUnreachable variant=on"],
                    [_ns(now - timedelta(minutes=4)), "ts=2026-11-16T14:11:00Z level=info service=flagd port=8013 flag=loadGeneratorFloodHomepage variant=on"],
                ],
            },
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "valkey-cart", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [_ns(now - timedelta(minutes=11)), "1:M 16 Nov 2026 14:00:00.000 * Background saving terminated with success"],
                ],
            },
            {
                "stream": {"namespace": "otel-demo", "service_namespace": "otel-demo", "service_name": "load-generator", "cluster": "docker-desktop", "env": "prod"},
                "values": [
                    [
                        _ns(now - timedelta(minutes=30) + timedelta(seconds=i * 20)),
                        f'DEBUG locust.user GET /healthz 200 OK kube-probe/1.31 flood_iteration={i} payload={"Z" * 300}',
                    ]
                    for i in range(45)
                ],
            },
        ]
    )

    code, resp = _push_streams(otel_demo_streams, org_id="otel-demo")
    if code not in (200, 204):
        raise RuntimeError(f"Failed seeding otel-demo logs ({code}): {resp}")

    # Tenant 2: otel-staging (legacy Promtail _entry packed logs + app/job labels without service_name + order_id correlation)
    t_ord = now - timedelta(minutes=20)
    ord_id = "ord_01J9Z8K7M6N5P4Q3R2"
    otel_staging_streams = [
        {
            "stream": {"job": "legacy-promtail", "app": "postgresql", "namespace": "otel-staging"},
            "values": [
                [
                    _ns(now - timedelta(minutes=25)),
                    json.dumps({"_entry": "level=error msg=connection_reset db=otel", "pod": "postgresql-0"}),
                ],
                [
                    _ns(now - timedelta(minutes=18)),
                    json.dumps({"_entry": "level=warn msg=checkpoint_too_frequent db=otel", "pod": "postgresql-0"}),
                ],
            ],
        },
        {
            "stream": {"job": "legacy-promtail", "app": "valkey-cart", "namespace": "otel-staging"},
            "values": [
                [
                    _ns(now - timedelta(minutes=21)),
                    json.dumps({"_entry": "level=info msg=aof_rewrite_done db=cart", "pod": "valkey-cart-0"}),
                ],
            ],
        },
        {
            "stream": {"namespace": "otel-staging", "service_name": "checkout-service"},
            "values": [
                [_ns(t_ord), f'INFO PlaceOrder started order_id="{ord_id}" user_id=usr_42'],
                [_ns(t_ord + timedelta(milliseconds=45)), f'ERROR PlaceOrder fulfillment failed upstream shipping 502 order_id="{ord_id}"'],
            ],
        },
        {
            "stream": {"namespace": "otel-staging", "service_name": "shipping-service"},
            "values": [
                [_ns(t_ord + timedelta(milliseconds=12)), f'INFO Dispatching quote request order_id="{ord_id}"'],
                [_ns(t_ord + timedelta(milliseconds=35)), f'ERROR Quote calculation failed HTTP 500 from quote:8080 order_id="{ord_id}"'],
            ],
        },
        {
            "stream": {"namespace": "otel-staging", "service_name": "quote"},
            "values": [
                [_ns(t_ord + timedelta(milliseconds=20)), f'FATAL PHP uncaught exception invalid weight_kg=-1 for order_id="{ord_id}"'],
            ],
        },
        {
            "stream": {"namespace": "otel-staging", "service_name": "email"},
            "values": [
                [_ns(t_ord + timedelta(milliseconds=55)), f'WARN Order failure notification queued order_id="{ord_id}"'],
            ],
        },
    ]
    code_s, resp_s = _push_streams(otel_staging_streams, org_id="otel-staging")
    if code_s not in (200, 204):
        raise RuntimeError(f"Failed seeding otel-staging logs ({code_s}): {resp_s}")

    # Tenant 3: otel-loadtest (noisy neighbor chaos flood streams for eval-08 FinOps)
    otel_loadtest_streams = [
        {
            "stream": {"namespace": "otel-loadtest", "service_name": "load-generator", "vu": f"vu-{i}"},
            "values": [
                [_ns(now - timedelta(minutes=15 - (i % 10))), f"INFO flood homepage locust_users=200 batch={i} " + ("L" * 512)]
            ],
        }
        for i in range(20)
    ]
    _push_streams(otel_loadtest_streams, org_id="otel-loadtest")
    # Flush ingester chunks to TSDB v13 store so /loki/api/v1/index/stats immediately reports non-zero bytes/chunks/streams
    _http_req("POST", "/flush", org_id="otel-demo")


def reset_ruler_compactor_and_crds() -> None:
    """Idempotently reset Loki Ruler rule groups, Compactor delete requests, and Kubernetes Loki CRs."""
    # 1. Clean test Ruler groups in otel-demo & otel-staging, then stage baseline groups
    for ns, grp in [
        ("otel-demo", "otel-checkout-log-alerts"),
        ("otel-demo", "otel-payment-charge-alerts"),
        ("otel-demo", "shipping-service-log-alerts"),
    ]:
        _http_req("DELETE", f"/loki/api/v1/rules/{ns}/{grp}", org_id="otel-demo")

    kafka_lag_group = """name: otel-kafka-lag-alerts
interval: 15s
rules:
  - alert: OtelKafkaConsumerLagLogsHigh
    expr: sum by (namespace, service_name, consumer_id) (count_over_time({service_name="kafka", namespace="otel-demo"} |= "lag=" [30m])) > 10
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "Kafka consumer lag logs elevated in otel-demo"
"""
    email_pod_group = """name: otel-email-pod-alerts
interval: 1m
rules:
  - alert: OtelEmailPodOOMKilled
    expr: sum by (namespace, service_name, pod) (count_over_time({service_name="email", namespace="otel-demo", pod=~"email-.*"} |= "NoMemoryError" [5m])) > 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Ruby email pod OOM NoMemoryError detected"
"""
    _http_req("POST", "/loki/api/v1/rules/otel-demo", org_id="otel-demo", body=kafka_lag_group, content_type="application/yaml")
    _http_req("POST", "/loki/api/v1/rules/otel-demo", org_id="otel-demo", body=email_pod_group, content_type="application/yaml")

    legacy_jaeger_group = """name: legacy-jaeger-log-alerts
interval: 1m
rules:
  - alert: LegacyJaegerCollectorDroppedSpans
    expr: count_over_time({namespace="otel-staging"} |= "jaeger" [5m]) > 50
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Deprecated Jaeger log alert (migrated to Tempo)"
"""
    _http_req("POST", "/loki/api/v1/rules/otel-staging", org_id="otel-staging", body=legacy_jaeger_group, content_type="application/yaml")

    # 2. Reset Compactor delete requests on otel-demo: cancel existing received requests, then stage 1 accidental shipping-service request
    code_d, body_d = _http_req("GET", "/loki/api/v1/delete", org_id="otel-demo")
    if code_d == 200 and body_d.strip():
        try:
            reqs = json.loads(body_d)
            if isinstance(reqs, list):
                for r in reqs:
                    rid = r.get("request_id")
                    if rid and r.get("status") == "received":
                        _http_req(
                            "DELETE",
                            "/loki/api/v1/delete",
                            org_id="otel-demo",
                            params={"request_id": str(rid), "force": "true"},
                        )
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    _http_req(
        "POST",
        "/loki/api/v1/delete",
        org_id="otel-demo",
        params={
            "query": '{service_name="shipping-service", namespace="otel-demo"} |= "accidental_purge_marker"',
            "start": str(int((now - timedelta(hours=1)).timestamp())),
            "end": str(int(now.timestamp())),
        },
    )

    # 3. Reset Kubernetes Loki Operator CRs in observability
    for kind_plural, name in [
        ("lokistacks.loki.grafana.com", "loki-otel-prod"),
        ("alertingrules.loki.grafana.com", "otel-catalog-panic-alerts"),
        ("recordingrules.loki.grafana.com", "otel-proxy-latency-recordings"),
    ]:
        _kubectl("delete", kind_plural, name, "-n", NAMESPACE, "--ignore-not-found", check=False)

    staged_k8s_objects = [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "loki-otel-s3-secret", "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {
                "endpoint": "https://s3.us-east-1.amazonaws.com",
                "bucketnames": "talkops-otel-loki-chunks",
                "region": "us-east-1",
            },
        },
        {
            "apiVersion": "loki.grafana.com/v1",
            "kind": "LokiStack",
            "metadata": {
                "name": "loki-otel",
                "namespace": NAMESPACE,
                "labels": {"app.kubernetes.io/part-of": "otel-observability"},
            },
            "spec": {
                "size": "1x.extra-small",
                "storage": {
                    "schemas": [
                        {"version": "v12", "effectiveDate": "2023-10-01"},
                        {"version": "v13", "effectiveDate": "2024-04-01"},
                    ],
                    "secret": {"name": "loki-otel-s3-secret", "type": "s3"},
                },
                "storageClassName": "gp3",
                "tenants": {"mode": "openshift-logging"},
                "limits": {"global": {"retention": {"days": 14}}},
                "rules": {
                    "enabled": True,
                    "selector": {"matchLabels": {"loki.grafana.com/rules": "true"}},
                },
            },
        },
        {
            "apiVersion": "loki.grafana.com/v1",
            "kind": "AlertingRule",
            "metadata": {
                "name": "otel-frontend-proxy-5xx-alerts",
                "namespace": NAMESPACE,
                "labels": {
                    "loki.grafana.com/rules": "true",
                    "app.kubernetes.io/part-of": "otel-demo",
                },
            },
            "spec": {
                "tenantID": "otel-demo",
                "groups": [
                    {
                        "name": "frontend-proxy-envoy-slo",
                        "interval": "1m",
                        "rules": [
                            {
                                "alert": "OtelFrontendProxyHigh5xxRatio",
                                "expr": (
                                    '(sum by (namespace, service_name) (rate({service_name="frontend-proxy", namespace="otel-demo"} |= "50" | json status="status" | status >= 500 | __error__="" [5m])) '
                                    '/ (sum by (namespace, service_name) (rate({service_name="frontend-proxy", namespace="otel-demo"} | json status="status" | __error__="" [5m])) > 0)) > 0.02'
                                ),
                                "for": "5m",
                                "labels": {"severity": "critical", "service_name": "frontend-proxy", "team": "edge"},
                                "annotations": {
                                    "summary": "Envoy 5xx error ratio above threshold on frontend-proxy",
                                    "description": "5xx log ratio exceeded threshold for 5m in otel-demo.",
                                    "runbook_url": "https://runbooks.talkops.internal/otel-frontend-proxy-5xx",
                                },
                            },
                            {
                                "alert": "OtelFrontendProxyLogsAbsent",
                                "expr": 'absent_over_time({service_name="frontend-proxy", namespace="otel-demo"}[15m]) == 1',
                                "for": "5m",
                                "labels": {"severity": "warning", "service_name": "frontend-proxy"},
                                "annotations": {
                                    "summary": "No Envoy access logs received from frontend-proxy for 15m",
                                },
                            },
                        ],
                    }
                ],
            },
        },
    ]
    k8s_yaml = "\n---\n".join(yaml.safe_dump(o, sort_keys=False) for o in staged_k8s_objects)
    _kubectl(
        "apply",
        "--server-side",
        "--field-manager=talkops-loki-mcp",
        "--force-conflicts",
        "-f",
        "-",
        stdin_text=k8s_yaml,
    )


def deploy_all() -> None:
    install_loki_crds_and_workload()
    wire_otel_app_deployments()
    write_loki_env()
    wait_for_loki_ready()
    print("[4/5] Seeding multi-tenant OTEL-APP logs & triggering discarded-sample diagnostics...")
    seed_otel_logs()
    trigger_real_discarded_samples()
    print("[5/5] Staging Loki Ruler groups, Compactor delete requests, and Loki Operator CRs...")
    reset_ruler_compactor_and_crds()
    print("[DONE] Domain 8 (Grafana Loki 3.3.2) battleground is 100% live and staged!")


def reset_state(skill_name: str | None = None) -> None:
    write_loki_env()
    wait_for_loki_ready(max_wait_sec=30)
    seed_otel_logs()
    trigger_real_discarded_samples()
    reset_ruler_compactor_and_crds()
    print(f"[RESET OK] Clean Domain 8 Loki state staged{f' for {skill_name}' if skill_name else ''}.")


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
