"""Tests for migration gap fixes: ServersTransport CRD + Service sticky session patches.

Validates that the migrator generates:
  - ServersTransport CRDs for timeout/backend-protocol annotations
  - Service annotation patches for sticky sessions
  - Strips consumed annotations from updated Ingress manifests
  - Includes new categories in runbook output
"""

import yaml as pyyaml

from traefik_mcp_server.migration_nginx.analyzer import NginxMigrationAnalyzer
from traefik_mcp_server.migration_nginx.migrator_traefik import (
    TraefikMigrator,
    generate_servers_transports,
    generate_service_patches,
    _parse_nginx_timeout,
)
from traefik_mcp_server.migration_nginx.generator import (
    generate_migration_report,
    bundle_migration_output,
)
from traefik_mcp_server.migration_nginx.scanner import (
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ScanResult,
    ServiceRef,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _scan_with_ingress(ing: IngressInfo) -> ScanResult:
    return ScanResult(
        cluster_name="test-cluster",
        controller=ControllerInfo(
            detected=True, type="ingress-nginx", version="1.9", namespace="ingress-nginx", pod_name="p"
        ),
        ingresses=[ing],
        namespaces=[ing.namespace],
    )


def _make_ingress(**nginx_ann) -> IngressInfo:
    """Create a simple IngressInfo with the given nginx annotations."""
    return IngressInfo(
        namespace="prod",
        name="my-app",
        ingress_class="nginx",
        hosts=["app.example.com"],
        paths=[
            PathInfo(
                host="app.example.com",
                path="/",
                path_type="Prefix",
                service_name="my-app-svc",
                service_port=80,
            )
        ],
        annotations={
            f"nginx.ingress.kubernetes.io/{k}": v for k, v in nginx_ann.items()
        },
        nginx_annotations=nginx_ann,
        services=[ServiceRef(namespace="prod", name="my-app-svc", port=80)],
    )


# ── ServersTransport: _parse_nginx_timeout ─────────────────────────────────────

class TestParseNginxTimeout:
    def test_bare_number_seconds(self):
        assert _parse_nginx_timeout("60") == "60s"

    def test_already_has_suffix(self):
        assert _parse_nginx_timeout("30s") == "30s"
        assert _parse_nginx_timeout("1m") == "1m"
        assert _parse_nginx_timeout("2h") == "2h"

    def test_empty_returns_default(self):
        assert _parse_nginx_timeout("") == "30s"

    def test_whitespace_stripped(self):
        assert _parse_nginx_timeout("  120  ") == "120s"

    def test_invalid_returns_default(self):
        assert _parse_nginx_timeout("abc") == "30s"


# ── ServersTransport CRD generation ────────────────────────────────────────────

class TestServersTransportGeneration:
    def test_generated_for_read_timeout(self):
        """proxy-read-timeout alone should produce a ServersTransport."""
        ing = _make_ingress(**{"proxy-read-timeout": "60"})
        files = generate_servers_transports(ing)
        assert len(files) == 1
        f = files[0]
        assert f.category == "serverstransport"
        assert "ServersTransport" in f.content
        # Parse YAML (strip comments)
        yaml_lines = [l for l in f.content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["kind"] == "ServersTransport"
        assert obj["spec"]["forwardingTimeouts"]["responseHeaderTimeout"] == "60s"

    def test_generated_for_connect_timeout(self):
        """proxy-connect-timeout maps to dialTimeout."""
        ing = _make_ingress(**{"proxy-connect-timeout": "10"})
        files = generate_servers_transports(ing)
        assert len(files) == 1
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["spec"]["forwardingTimeouts"]["dialTimeout"] == "10s"

    def test_connect_preferred_over_send_for_dial(self):
        """When both connect and send are present, connect wins for dialTimeout."""
        ing = _make_ingress(**{
            "proxy-connect-timeout": "5",
            "proxy-send-timeout": "30",
        })
        files = generate_servers_transports(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["spec"]["forwardingTimeouts"]["dialTimeout"] == "5s"

    def test_send_timeout_fallback_for_dial(self):
        """proxy-send-timeout used for dialTimeout when no connect-timeout."""
        ing = _make_ingress(**{"proxy-send-timeout": "45"})
        files = generate_servers_transports(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["spec"]["forwardingTimeouts"]["dialTimeout"] == "45s"

    def test_backend_protocol_https(self):
        """backend-protocol: HTTPS → insecureSkipVerify."""
        ing = _make_ingress(**{"backend-protocol": "HTTPS"})
        files = generate_servers_transports(ing)
        assert len(files) == 1
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["spec"]["insecureSkipVerify"] is True
        assert "serversscheme: https" in files[0].content

    def test_combined_timeouts_and_https(self):
        """Both timeouts and HTTPS → single ServersTransport with both."""
        ing = _make_ingress(**{
            "proxy-read-timeout": "120",
            "proxy-connect-timeout": "10",
            "backend-protocol": "HTTPS",
        })
        files = generate_servers_transports(ing)
        assert len(files) == 1
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["spec"]["forwardingTimeouts"]["responseHeaderTimeout"] == "120s"
        assert obj["spec"]["insecureSkipVerify"] is True

    def test_no_serverstransport_without_annotations(self):
        """No timeout/backend annotations → no ServersTransport generated."""
        ing = _make_ingress(**{"ssl-redirect": "true"})
        files = generate_servers_transports(ing)
        assert files == []

    def test_backend_protocol_http_ignored(self):
        """backend-protocol: HTTP (not HTTPS) → no ServersTransport."""
        ing = _make_ingress(**{"backend-protocol": "HTTP"})
        files = generate_servers_transports(ing)
        assert files == []

    def test_migration_label_set(self):
        """ServersTransport should have migration.source label."""
        ing = _make_ingress(**{"proxy-read-timeout": "60"})
        files = generate_servers_transports(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["metadata"]["labels"]["migration.source"] == "my-app"


# ── Service sticky session patch generation ────────────────────────────────────

class TestServicePatchGeneration:
    def test_generated_for_cookie_affinity(self):
        """affinity: cookie → Service patch with sticky annotations."""
        ing = _make_ingress(**{
            "affinity": "cookie",
            "session-cookie-name": "SERVERID",
        })
        files = generate_service_patches(ing)
        assert len(files) == 1
        f = files[0]
        assert f.category == "service_patch"
        yaml_lines = [l for l in f.content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["kind"] == "Service"
        ann = obj["metadata"]["annotations"]
        assert ann["traefik.ingress.kubernetes.io/service.sticky.cookie"] == "true"
        assert ann["traefik.ingress.kubernetes.io/service.sticky.cookie.name"] == "SERVERID"

    def test_maxage_from_max_age(self):
        """session-cookie-max-age maps to sticky.cookie.maxage."""
        ing = _make_ingress(**{
            "affinity": "cookie",
            "session-cookie-max-age": "3600",
        })
        files = generate_service_patches(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        ann = obj["metadata"]["annotations"]
        assert ann["traefik.ingress.kubernetes.io/service.sticky.cookie.maxage"] == "3600"

    def test_maxage_from_expires_fallback(self):
        """session-cookie-expires is used if session-cookie-max-age is absent."""
        ing = _make_ingress(**{
            "affinity": "cookie",
            "session-cookie-expires": "7200",
        })
        files = generate_service_patches(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        ann = obj["metadata"]["annotations"]
        assert ann["traefik.ingress.kubernetes.io/service.sticky.cookie.maxage"] == "7200"

    def test_samesite_and_secure(self):
        """session-cookie-samesite/secure map to respective Traefik annotations."""
        ing = _make_ingress(**{
            "affinity": "cookie",
            "session-cookie-samesite": "Lax",
            "session-cookie-secure": "true",
        })
        files = generate_service_patches(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        ann = obj["metadata"]["annotations"]
        assert ann["traefik.ingress.kubernetes.io/service.sticky.cookie.samesite"] == "Lax"
        assert ann["traefik.ingress.kubernetes.io/service.sticky.cookie.secure"] == "true"

    def test_no_patch_without_affinity(self):
        """No affinity annotation → no Service patch."""
        ing = _make_ingress(**{"ssl-redirect": "true"})
        files = generate_service_patches(ing)
        assert files == []

    def test_no_patch_for_non_cookie_affinity(self):
        """affinity: ip-hash → not supported, no patch."""
        ing = _make_ingress(**{"affinity": "ip-hash"})
        files = generate_service_patches(ing)
        assert files == []

    def test_patch_targets_correct_service(self):
        """Patch references the backend service name/namespace from the Ingress."""
        ing = _make_ingress(**{"affinity": "cookie"})
        files = generate_service_patches(ing)
        yaml_lines = [l for l in files[0].content.split("\n") if not l.strip().startswith("#")]
        obj = pyyaml.safe_load("\n".join(yaml_lines))
        assert obj["metadata"]["name"] == "my-app-svc"
        assert obj["metadata"]["namespace"] == "prod"


# ── Integration: TraefikMigrator.migrate() ─────────────────────────────────────

class TestMigrateIntegration:
    def _run_migrate(self, **nginx_ann):
        ing = _make_ingress(**nginx_ann)
        scan = _scan_with_ingress(ing)
        analyzer = NginxMigrationAnalyzer(target="traefik")
        analysis = analyzer.analyze(scan)
        migrator = TraefikMigrator()
        return migrator.migrate(scan, analysis)

    def test_migrate_emits_serverstransport(self):
        files = self._run_migrate(**{"proxy-read-timeout": "60"})
        st_files = [f for f in files if f.category == "serverstransport"]
        assert len(st_files) >= 1

    def test_migrate_emits_service_patch(self):
        files = self._run_migrate(**{"affinity": "cookie", "session-cookie-name": "SID"})
        sp_files = [f for f in files if f.category == "service_patch"]
        assert len(sp_files) >= 1

    def test_timeout_annotations_stripped_from_ingress(self):
        files = self._run_migrate(**{"proxy-read-timeout": "60", "proxy-connect-timeout": "5"})
        ingress_files = [f for f in files if f.category == "ingress"]
        assert len(ingress_files) == 1
        assert "proxy-read-timeout" not in ingress_files[0].content
        assert "proxy-connect-timeout" not in ingress_files[0].content

    def test_affinity_annotations_stripped_from_ingress(self):
        files = self._run_migrate(**{
            "affinity": "cookie",
            "session-cookie-name": "SID",
            "session-cookie-max-age": "3600",
        })
        ingress_files = [f for f in files if f.category == "ingress"]
        assert len(ingress_files) == 1
        content = ingress_files[0].content
        assert "affinity" not in content or "traefik" in content.split("affinity")[0][-50:]
        assert "session-cookie-name" not in content
        assert "session-cookie-max-age" not in content

    def test_migrate_with_no_special_annotations(self):
        """Ingress with only ssl-redirect should not produce ST or SP files."""
        files = self._run_migrate(**{"ssl-redirect": "true"})
        st_files = [f for f in files if f.category == "serverstransport"]
        sp_files = [f for f in files if f.category == "service_patch"]
        assert len(st_files) == 0
        assert len(sp_files) == 0


# ── Runbook output ─────────────────────────────────────────────────────────────

class TestRunbookOutput:
    def _get_runbook(self, **nginx_ann):
        ing = _make_ingress(**nginx_ann)
        scan = _scan_with_ingress(ing)
        analyzer = NginxMigrationAnalyzer(target="traefik")
        analysis = analyzer.analyze(scan)
        migrator = TraefikMigrator()
        files = migrator.migrate(scan, analysis)
        return generate_migration_report(scan, analysis, files=files)

    def test_runbook_includes_serverstransport(self):
        report = self._get_runbook(**{"proxy-read-timeout": "60"})
        assert "ServersTransport" in report
        assert "backend timeouts/TLS" in report

    def test_runbook_includes_service_patch(self):
        report = self._get_runbook(**{"affinity": "cookie", "session-cookie-name": "SID"})
        assert "sticky session" in report.lower()
        assert "service.sticky.cookie" in report

    def test_bundle_includes_new_categories(self):
        ing = _make_ingress(**{
            "proxy-read-timeout": "60",
            "affinity": "cookie",
            "session-cookie-name": "SID",
        })
        scan = _scan_with_ingress(ing)
        analyzer = NginxMigrationAnalyzer(target="traefik")
        analysis = analyzer.analyze(scan)
        migrator = TraefikMigrator()
        files = migrator.migrate(scan, analysis)
        bundle = bundle_migration_output(files, scan, analysis)
        categories = bundle["migration"]["bundleSummary"]["categories"]
        assert "serverstransport" in categories
        assert "service_patch" in categories
