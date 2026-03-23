"""Tests for shadow mode integration in both migrators."""

import yaml as pyyaml

from traefik_mcp_server.migration_nginx.migrator_traefik import TraefikMigrator
from traefik_mcp_server.migration_nginx.migrator_gateway_api import GatewayAPIMigrator
from traefik_mcp_server.migration_nginx.migration_plan import (
    IngressMigrationPlanEntry,
    parse_migration_plan,
)
from traefik_mcp_server.migration_nginx.scanner import (
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ScanResult,
    ServiceRef,
)


def _ing(name="app", ns="default"):
    return IngressInfo(
        namespace=ns,
        name=name,
        ingress_class="nginx",
        hosts=["app.example.com"],
        paths=[
            PathInfo(
                host="app.example.com",
                path="/",
                path_type="Prefix",
                service_name="api-svc",
                service_port=80,
            )
        ],
        annotations={},
        nginx_annotations={},
        services=[ServiceRef(namespace=ns, name="api-svc", port=80)],
        complexity="simple",
    )


def _scan(*ingresses):
    return ScanResult(
        cluster_name="test",
        controller=ControllerInfo(
            detected=True, type="ingress-nginx", version="1",
            namespace="ing", pod_name="p",
        ),
        ingresses=list(ingresses),
        namespaces=[i.namespace for i in ingresses],
    )


class TestShadowModeModel:
    def test_default_shadow_mode_is_false(self):
        entry = IngressMigrationPlanEntry()
        assert entry.shadow_mode is False
        assert entry.shadow_mirror_percent == 20

    def test_shadow_mode_accepts_true(self):
        entry = IngressMigrationPlanEntry(shadow_mode=True, shadow_mirror_percent=50)
        assert entry.shadow_mode is True
        assert entry.shadow_mirror_percent == 50

    def test_parse_migration_plan_with_shadow_mode(self):
        raw = {"app": {"shadow_mode": True, "shadow_mirror_percent": 30}}
        plan = parse_migration_plan(raw)
        assert "app" in plan
        assert plan["app"].shadow_mode is True
        assert plan["app"].shadow_mirror_percent == 30


class TestShadowModeTraefikMigrator:
    def test_no_shadow_files_without_plan(self):
        scan = _scan(_ing())
        files = TraefikMigrator().migrate(scan)
        shadow_files = [f for f in files if f.category == "shadow"]
        assert len(shadow_files) == 0

    def test_shadow_mode_generates_traefik_service_mirror(self):
        scan = _scan(_ing("webapp", "prod"))
        plan = {"webapp": {"shadow_mode": True, "shadow_mirror_percent": 25}}
        files = TraefikMigrator().migrate(scan, migration_plan=plan)

        shadow_files = [f for f in files if f.category == "shadow"]
        assert len(shadow_files) == 1

        sf = shadow_files[0]
        assert "07-shadow/" in sf.rel_path
        assert "-mirror.yaml" in sf.rel_path

        # Parse YAML (skip comment lines)
        yaml_lines = [l for l in sf.content.split("\n") if not l.startswith("#")]
        doc = pyyaml.safe_load("\n".join(yaml_lines))
        assert doc["kind"] == "TraefikService"
        assert doc["spec"]["mirroring"]["name"] == "api-svc"
        assert doc["spec"]["mirroring"]["mirrors"][0]["name"] == "api-svc-shadow"
        assert doc["spec"]["mirroring"]["mirrors"][0]["percent"] == 25

    def test_shadow_mode_only_for_enabled_ingresses(self):
        ing1 = _ing("a", "ns1")
        ing2 = _ing("b", "ns1")
        scan = _scan(ing1, ing2)
        plan = {"a": {"shadow_mode": True}}
        files = TraefikMigrator().migrate(scan, migration_plan=plan)
        shadow_files = [f for f in files if f.category == "shadow"]
        assert len(shadow_files) == 1
        assert "ns1-a" in shadow_files[0].rel_path

    def test_wildcard_shadow_mode_applies_to_all_ingresses(self):
        """P1.6: cluster-level shadow via '*' wildcard key."""
        ing1 = _ing("x", "ns1")
        ing2 = _ing("y", "ns2")
        scan = _scan(ing1, ing2)
        plan = {"*": {"shadow_mode": True, "shadow_mirror_percent": 10}}
        files = TraefikMigrator().migrate(scan, migration_plan=plan)
        shadow_files = [f for f in files if f.category == "shadow"]
        assert len(shadow_files) == 2

    def test_per_ingress_overrides_wildcard(self):
        """Per-Ingress entry takes priority over wildcard."""
        ing1 = _ing("a", "ns1")
        ing2 = _ing("b", "ns1")
        scan = _scan(ing1, ing2)
        plan = {
            "*": {"shadow_mode": True},
            "b": {"shadow_mode": False},  # override wildcard for 'b'
        }
        files = TraefikMigrator().migrate(scan, migration_plan=plan)
        shadow_files = [f for f in files if f.category == "shadow"]
        assert len(shadow_files) == 1
        assert "ns1-a" in shadow_files[0].rel_path


class TestShadowModeGatewayAPIMigrator:
    def test_shadow_mode_generates_mirror_in_gateway_api(self):
        scan = _scan(_ing("gw-app", "staging"))
        plan = {"gw-app": {"shadow_mode": True, "shadow_mirror_percent": 15}}
        files = GatewayAPIMigrator().migrate(scan, migration_plan=plan)

        shadow_files = [f for f in files if f.category == "shadow"]
        assert len(shadow_files) == 1

        yaml_lines = [l for l in shadow_files[0].content.split("\n") if not l.startswith("#")]
        doc = pyyaml.safe_load("\n".join(yaml_lines))
        assert doc["kind"] == "TraefikService"
        assert doc["spec"]["mirroring"]["mirrors"][0]["percent"] == 15
