"""Tests for Gateway API migrator (HTTPRoute + Gateway generation)."""

from dataclasses import replace

import yaml as pyyaml

from traefik_mcp_server.migration_nginx.migrator_gateway_api import (
    GatewayAPIMigrator,
    GATEWAY_NAMESPACE,
    generate_httproute,
)
from traefik_mcp_server.migration_nginx.scanner import (
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ScanResult,
    ServiceRef,
)

from typing import Dict, List, Optional


def _basic_ingress(
    namespace: str = "default",
    name: str = "webapp",
    ingress_class: str = "nginx",
    hosts: Optional[List[str]] = None,
    paths: Optional[List[PathInfo]] = None,
    annotations: Optional[Dict[str, str]] = None,
    nginx_annotations: Optional[Dict[str, str]] = None,
    services: Optional[List[ServiceRef]] = None,
    complexity: str = "simple",
) -> IngressInfo:
    return IngressInfo(
        namespace=namespace,
        name=name,
        ingress_class=ingress_class,
        hosts=hosts if hosts is not None else ["app.example.com"],
        paths=paths if paths is not None else [
            PathInfo(
                host="app.example.com",
                path="/",
                path_type="Prefix",
                service_name="webapp-svc",
                service_port=80,
            )
        ],
        annotations=annotations if annotations is not None else {},
        nginx_annotations=nginx_annotations if nginx_annotations is not None else {},
        services=services if services is not None else [
            ServiceRef(namespace="default", name="webapp-svc", port=80)
        ],
        complexity=complexity,
    )


def _scan_with(*ingresses) -> ScanResult:
    return ScanResult(
        cluster_name="test",
        controller=ControllerInfo(
            detected=True, type="ingress-nginx", version="1", namespace="ing", pod_name="p"
        ),
        ingresses=list(ingresses),
        namespaces=[i.namespace for i in ingresses],
    )


class TestGenerateHTTPRoute:
    def test_basic_httproute_structure(self):
        ing = _basic_ingress()
        gf = generate_httproute(ing)
        assert gf.category == "httproute"
        assert "02-httproutes/" in gf.rel_path
        doc = pyyaml.safe_load(gf.content)
        assert doc["apiVersion"] == "gateway.networking.k8s.io/v1"
        assert doc["kind"] == "HTTPRoute"
        assert doc["metadata"]["name"] == "webapp"
        assert doc["metadata"]["namespace"] == "default"
        assert doc["spec"]["hostnames"] == ["app.example.com"]
        assert len(doc["spec"]["rules"]) == 1
        rule = doc["spec"]["rules"][0]
        assert rule["backendRefs"][0]["name"] == "webapp-svc"
        assert rule["backendRefs"][0]["port"] == 80
        # parentRefs should reference the shared Gateway namespace
        parent = doc["spec"]["parentRefs"][0]
        assert parent["name"] == "traefik-gateway"
        assert parent["namespace"] == GATEWAY_NAMESPACE

    def test_ssl_redirect_generates_filter(self):
        ing = _basic_ingress(
            nginx_annotations={"ssl-redirect": "true"},
            annotations={"nginx.ingress.kubernetes.io/ssl-redirect": "true"},
        )
        gf = generate_httproute(ing)
        doc = pyyaml.safe_load(gf.content)
        filters = doc["spec"]["rules"][0].get("filters", [])
        assert any(f["type"] == "RequestRedirect" for f in filters)
        redirect = next(f for f in filters if f["type"] == "RequestRedirect")
        assert redirect["requestRedirect"]["scheme"] == "https"

    def test_rewrite_target_generates_url_rewrite_filter(self):
        ing = _basic_ingress(
            nginx_annotations={"rewrite-target": "/api/$1"},
            annotations={"nginx.ingress.kubernetes.io/rewrite-target": "/api/$1"},
        )
        gf = generate_httproute(ing)
        doc = pyyaml.safe_load(gf.content)
        filters = doc["spec"]["rules"][0].get("filters", [])
        assert any(f["type"] == "URLRewrite" for f in filters)
        rewrite = next(f for f in filters if f["type"] == "URLRewrite")
        assert rewrite["urlRewrite"]["path"]["replacePrefixMatch"] == "/api/$1"

    def test_cors_generates_response_header_modifier(self):
        ing = _basic_ingress(
            nginx_annotations={
                "enable-cors": "true",
                "cors-allow-origin": "*",
                "cors-allow-methods": "GET,POST",
            },
        )
        gf = generate_httproute(ing)
        doc = pyyaml.safe_load(gf.content)
        filters = doc["spec"]["rules"][0].get("filters", [])
        resp_filter = [f for f in filters if f["type"] == "ResponseHeaderModifier"]
        assert len(resp_filter) == 1
        headers = resp_filter[0]["responseHeaderModifier"]["set"]
        names = [h["name"] for h in headers]
        assert "Access-Control-Allow-Origin" in names
        assert "Access-Control-Allow-Methods" in names

    def test_canary_weight_in_backend_refs(self):
        ing = _basic_ingress(
            nginx_annotations={"canary": "true", "canary-weight": "30"},
        )
        gf = generate_httproute(ing)
        doc = pyyaml.safe_load(gf.content)
        refs = doc["spec"]["rules"][0]["backendRefs"]
        assert refs[0]["weight"] == 30

    def test_no_hosts_omits_hostnames(self):
        ing = _basic_ingress(hosts=[])
        gf = generate_httproute(ing)
        doc = pyyaml.safe_load(gf.content)
        assert "hostnames" not in doc["spec"]


class TestGatewayAPIMigrator:
    def test_migrator_produces_httproute_and_gateway(self):
        scan = _scan_with(_basic_ingress())
        migrator = GatewayAPIMigrator()
        files = migrator.migrate(scan)
        categories = {f.category for f in files}
        assert "httproute" in categories
        assert "gateway" in categories
        assert "verify" in categories

    def test_gateway_has_http_and_https_listeners(self):
        scan = _scan_with(_basic_ingress())
        files = GatewayAPIMigrator().migrate(scan)
        gw_file = next(f for f in files if f.category == "gateway")
        # Skip comment lines
        yaml_lines = [
            l for l in gw_file.content.split("\n") if not l.startswith("#")
        ]
        doc = pyyaml.safe_load("\n".join(yaml_lines))
        listeners = doc["spec"]["listeners"]
        names = [l["name"] for l in listeners]
        assert "http" in names
        assert "https" in names

    def test_migration_plan_ignores_annotations(self):
        ing = _basic_ingress(
            nginx_annotations={"ssl-redirect": "true"},
            annotations={"nginx.ingress.kubernetes.io/ssl-redirect": "true"},
        )
        scan = _scan_with(ing)
        plan = {"webapp": {"ignore_annotations": ["ssl-redirect"]}}
        files = GatewayAPIMigrator().migrate(scan, migration_plan=plan)
        httproute_file = next(f for f in files if f.category == "httproute")
        doc = pyyaml.safe_load(httproute_file.content)
        filters = doc["spec"]["rules"][0].get("filters", [])
        # ssl-redirect filter should NOT be present
        assert not any(f.get("type") == "RequestRedirect" for f in filters)

    def test_gateway_has_namespace(self):
        scan = _scan_with(_basic_ingress())
        files = GatewayAPIMigrator().migrate(scan)
        gw_file = next(f for f in files if f.category == "gateway")
        yaml_lines = [
            l for l in gw_file.content.split("\n") if not l.startswith("#")
        ]
        doc = pyyaml.safe_load("\n".join(yaml_lines))
        assert doc["metadata"]["namespace"] == GATEWAY_NAMESPACE

    def test_parentrefs_resolve_to_gateway_namespace(self):
        """P0.1: parentRefs in HTTPRoute match the Gateway namespace."""
        ing = _basic_ingress(namespace="production")
        scan = _scan_with(ing)
        files = GatewayAPIMigrator().migrate(scan)
        httproute_file = next(f for f in files if f.category == "httproute")
        gw_file = next(f for f in files if f.category == "gateway")

        route_doc = pyyaml.safe_load(httproute_file.content)
        gw_doc = pyyaml.safe_load(
            "\n".join(l for l in gw_file.content.split("\n") if not l.startswith("#"))
        )

        parent_ns = route_doc["spec"]["parentRefs"][0]["namespace"]
        gw_ns = gw_doc["metadata"]["namespace"]
        assert parent_ns == gw_ns == GATEWAY_NAMESPACE

    def test_tls_certificate_refs_keep_same_secret_name_across_namespaces(self):
        """P0.3: dedupe by (namespace, secret), not secret name alone."""
        ing_a = replace(
            _basic_ingress(namespace="ns-a", name="ing-a"),
            tls_enabled=True,
            tls_secrets=["wildcard-tls"],
        )
        ing_b = replace(
            _basic_ingress(namespace="ns-b", name="ing-b"),
            tls_enabled=True,
            tls_secrets=["wildcard-tls"],
        )
        scan = _scan_with(ing_a, ing_b)
        files = GatewayAPIMigrator().migrate(scan)
        gw_file = next(f for f in files if f.category == "gateway")
        gw_doc = pyyaml.safe_load(
            "\n".join(l for l in gw_file.content.split("\n") if not l.startswith("#"))
        )
        https = next(l for l in gw_doc["spec"]["listeners"] if l["name"] == "https")
        cert_refs = https["tls"]["certificateRefs"]
        assert len(cert_refs) == 2
        pairs = {(r["namespace"], r["name"]) for r in cert_refs}
        assert pairs == {("ns-a", "wildcard-tls"), ("ns-b", "wildcard-tls")}

    def test_tls_certificate_refs_dedupe_same_namespace_and_secret(self):
        ing_a = replace(
            _basic_ingress(namespace="shared", name="ing-a"),
            tls_enabled=True,
            tls_secrets=["tls"],
        )
        ing_b = replace(
            _basic_ingress(namespace="shared", name="ing-b"),
            tls_enabled=True,
            tls_secrets=["tls"],
        )
        scan = _scan_with(ing_a, ing_b)
        files = GatewayAPIMigrator().migrate(scan)
        gw_file = next(f for f in files if f.category == "gateway")
        gw_doc = pyyaml.safe_load(
            "\n".join(l for l in gw_file.content.split("\n") if not l.startswith("#"))
        )
        https = next(l for l in gw_doc["spec"]["listeners"] if l["name"] == "https")
        cert_refs = https["tls"]["certificateRefs"]
        assert len(cert_refs) == 1
        assert cert_refs[0] == {"kind": "Secret", "name": "tls", "namespace": "shared"}
