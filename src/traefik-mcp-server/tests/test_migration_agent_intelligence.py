"""Tests for agent-supplied migration_plan (ignore_annotations, inject_middlewares)."""

import yaml as pyyaml

from traefik_mcp_server.migration_nginx.analyzer import NginxMigrationAnalyzer
from traefik_mcp_server.migration_nginx.migrator_traefik import TraefikMigrator
from traefik_mcp_server.migration_nginx.migration_plan import (
    apply_plan_to_analysis,
    filter_ingress_for_plan,
    parse_migration_plan,
)
from traefik_mcp_server.migration_nginx.scanner import (
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ScanResult,
    ServiceRef,
)


def _scan_with_ingress(ing: IngressInfo) -> ScanResult:
    return ScanResult(
        cluster_name="c1",
        controller=ControllerInfo(
            detected=True, type="ingress-nginx", version="1", namespace="ing", pod_name="p"
        ),
        ingresses=[ing],
        namespaces=[ing.namespace],
    )


def test_ignore_breaking_annotation_makes_ingress_ready_in_analysis():
    """Unsupported annotation alone yields breaking; ignoring it yields ready."""
    ing = IngressInfo(
        namespace="ecommerce",
        name="ecommerce-shop",
        ingress_class="nginx",
        hosts=["shop.example"],
        paths=[
            PathInfo(
                host="shop.example",
                path="/",
                path_type="Prefix",
                service_name="api",
                service_port=80,
            )
        ],
        annotations={
            "nginx.ingress.kubernetes.io/session-cookie-conditional-samesite-none": "true",
        },
        nginx_annotations={
            "session-cookie-conditional-samesite-none": "true",
        },
        services=[ServiceRef(namespace="ecommerce", name="api", port=80)],
        complexity="simple",
    )
    scan = _scan_with_ingress(ing)
    analyzer = NginxMigrationAnalyzer(target="traefik")
    report = analyzer.analyze(scan)
    assert report.ingress_reports[0].overall_status == "breaking"

    plan = parse_migration_plan(
        {
            "ecommerce-shop": {
                "ignore_annotations": ["session-cookie-conditional-samesite-none"],
            }
        }
    )
    adjusted = apply_plan_to_analysis(report, plan)
    assert adjusted.ingress_reports[0].overall_status == "ready"
    assert adjusted.summary.has_unsupported == 0
    assert adjusted.summary.fully_compatible == 1


def test_migrator_skips_middleware_for_ignored_annotation():
    """Ignored ssl-redirect must not emit ssl redirect middleware YAML."""
    ing = IngressInfo(
        namespace="ns1",
        name="ing-a",
        ingress_class="nginx",
        hosts=["h.test"],
        paths=[
            PathInfo(
                host="h.test", path="/", path_type="Prefix", service_name="s", service_port=80
            )
        ],
        annotations={
            "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        },
        nginx_annotations={"ssl-redirect": "true"},
        services=[ServiceRef(namespace="ns1", name="s", port=80)],
        complexity="simple",
    )
    scan = _scan_with_ingress(ing)
    m0 = TraefikMigrator().migrate(scan, migration_plan=None)
    mw_paths_0 = [f.rel_path for f in m0 if f.category == "middleware"]
    assert any("ing-a" in p for p in mw_paths_0)

    plan = {"ing-a": {"ignore_annotations": ["ssl-redirect"]}}
    m1 = TraefikMigrator().migrate(scan, migration_plan=plan)
    mw_paths_1 = [f.rel_path for f in m1 if f.category == "middleware"]
    assert not any("ing-a" in p for p in mw_paths_1)


def test_inject_middlewares_on_ingress_yaml():
    ing = IngressInfo(
        namespace="ns1",
        name="plain",
        ingress_class="nginx",
        hosts=["x.test"],
        paths=[
            PathInfo(
                host="x.test", path="/", path_type="Prefix", service_name="s", service_port=80
            )
        ],
        annotations={},
        nginx_annotations={},
        services=[ServiceRef(namespace="ns1", name="s", port=80)],
        complexity="simple",
    )
    scan = _scan_with_ingress(ing)
    plan = {"plain": {"inject_middlewares": ["custom-strict-samesite-mw"]}}
    files = TraefikMigrator().migrate(scan, migration_plan=plan)
    ing_file = next(f for f in files if f.rel_path.endswith("03-ingresses/ns1-plain.yaml"))
    doc = pyyaml.safe_load(ing_file.content)
    mw = doc["metadata"]["annotations"]["traefik.ingress.kubernetes.io/router.middlewares"]
    assert "ns1-custom-strict-samesite-mw@kubernetescrd" in mw


def test_filter_ingress_removes_short_and_full_keys():
    ing = IngressInfo(
        namespace="n",
        name="i",
        ingress_class="nginx",
        hosts=[],
        paths=[],
        annotations={
            "nginx.ingress.kubernetes.io/limit-rps": "5",
            "other/ann": "v",
        },
        nginx_annotations={"limit-rps": "5"},
        services=[],
        complexity="simple",
    )
    f = filter_ingress_for_plan(ing, ["limit-rps"])
    assert "limit-rps" not in f.nginx_annotations
    assert "nginx.ingress.kubernetes.io/limit-rps" not in f.annotations
    assert f.annotations.get("other/ann") == "v"


def test_parse_migration_plan_rejects_bad_values():
    assert parse_migration_plan(None) == {}
    assert parse_migration_plan({"x": "not-a-dict"}) == {}
    parsed = parse_migration_plan({"y": {"ignore_annotations": ["a"]}})
    assert "y" in parsed and parsed["y"].ignore_annotations == ["a"]
