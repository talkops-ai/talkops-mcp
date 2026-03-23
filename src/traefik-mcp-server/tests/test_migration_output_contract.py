"""Contract tests for the migration output responses.

Validates that:
- analysis_report_to_dict shape (breakingAnnotations, etc.)
- migrate() internal merge still includes analysis at root for generators
- MCP tool uses slim_migrate_tool_payload (no analysis keys inline)
- analyze resource wrapper schema
- Truncated migrate bundles nest file payload under migration; note is honest
"""

import json
from typing import List

from traefik_mcp_server.migration_nginx.scanner import (
    ScanResult,
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ServiceRef,
    scan_result_to_dict,
    scan_result_to_compact_dict,
)
from traefik_mcp_server.migration_nginx.analyzer import (
    NginxMigrationAnalyzer,
    AnalysisReport,
    analysis_report_to_dict,
)
from traefik_mcp_server.migration_nginx.migrator_traefik import (
    TraefikMigrator,
    GeneratedFile,
)
from traefik_mcp_server.migration_nginx.generator import (
    bundle_migration_output,
)
from traefik_mcp_server.resources.migration_resources import (
    _nginx_analyze_resource_body,
    _nginx_scan_agent_digest,
)
from traefik_mcp_server.services.nginx_migration_service import slim_migrate_tool_payload


def _make_scan_result(n_ingresses: int = 2) -> ScanResult:
    """Build a minimal ScanResult with n Ingress objects."""
    ingresses = []
    for i in range(n_ingresses):
        ing = IngressInfo(
            namespace="default",
            name=f"test-ingress-{i}",
            ingress_class="nginx",
            hosts=[f"test-{i}.example.com"],
            paths=[
                PathInfo(
                    host=f"test-{i}.example.com",
                    path="/",
                    path_type="Prefix",
                    service_name=f"svc-{i}",
                    service_port=80,
                )
            ],
            tls_enabled=i % 2 == 0,
            tls_secrets=["tls-secret"] if i % 2 == 0 else [],
            annotations={
                "nginx.ingress.kubernetes.io/force-ssl-redirect": "true",
            },
            nginx_annotations={
                "force-ssl-redirect": "true",
            },
            services=[
                ServiceRef(namespace="default", name=f"svc-{i}", port=80)
            ],
            complexity="simple",
        )
        ingresses.append(ing)
    return ScanResult(
        cluster_name="test-cluster",
        controller=ControllerInfo(
            detected=True,
            type="traefik",
            version="v3.6.10",
            namespace="traefik",
            pod_name="traefik-test",
        ),
        ingresses=ingresses,
        namespaces=["default"],
    )


def _analyze(scan_result: ScanResult) -> AnalysisReport:
    analyzer = NginxMigrationAnalyzer(target="traefik")
    return analyzer.analyze(scan_result)


def _migrate(scan_result: ScanResult, analysis: AnalysisReport) -> List[GeneratedFile]:
    migrator = TraefikMigrator()
    return migrator.migrate(scan_result, analysis)


class TestAnalyzeContract:
    """Analysis dict matches service.analyze / resource body (no scan_result)."""

    def test_analyze_shape_is_flat_analysis_report(self):
        scan_result = _make_scan_result(n_ingresses=2)
        analysis = _analyze(scan_result)
        result = analysis_report_to_dict(analysis)

        assert "scan_result" not in result
        assert "target" in result
        assert result["target"] == "traefik"
        assert "ingressReports" in result
        assert "summary" in result
        summary = result["summary"]
        assert summary["total"] == 2
        assert "fullyCompatible" in summary
        assert "needsWorkaround" in summary
        assert "hasUnsupported" in summary

    def test_analysis_report_is_json_serializable(self):
        scan_result = _make_scan_result(n_ingresses=3)
        analysis = _analyze(scan_result)
        report = analysis_report_to_dict(analysis)

        serialized = json.dumps(report, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["target"] == "traefik"
        assert deserialized["summary"]["total"] == 3


class TestBreakingAnnotations:
    """Breaking ingress reports surface breakingAnnotations."""

    def test_breaking_lists_unsupported_mappings(self):
        ing = IngressInfo(
            namespace="prod",
            name="risky",
            ingress_class="nginx",
            hosts=["app.example.com"],
            paths=[
                PathInfo(
                    host="app.example.com",
                    path="/api",
                    path_type="Prefix",
                    service_name="api",
                    service_port=8080,
                )
            ],
            nginx_annotations={
                "auth-url": "https://oauth.example.com/auth",
                "totally-unknown-annotation": "yes",
            },
            services=[ServiceRef(namespace="prod", name="api", port=8080)],
            complexity="complex",
        )
        scan = ScanResult(
            cluster_name="c",
            controller=ControllerInfo(detected=True, type="nginx"),
            ingresses=[ing],
            namespaces=["prod"],
        )
        analysis = _analyze(scan)
        report = analysis_report_to_dict(analysis)
        ir = report["ingressReports"][0]
        assert ir["overallStatus"] == "breaking"
        assert "breakingAnnotations" in ir
        bad = [b["originalKey"] for b in ir["breakingAnnotations"]]
        assert "totally-unknown-annotation" in bad
        assert all(b["status"] == "unsupported" for b in ir["breakingAnnotations"])

    def test_ready_ingress_omits_breaking_annotations_key_or_empty(self):
        scan_result = _make_scan_result(n_ingresses=1)
        analysis = _analyze(scan_result)
        report = analysis_report_to_dict(analysis)
        ir = report["ingressReports"][0]
        assert ir["overallStatus"] == "ready"
        assert "breakingAnnotations" not in ir


class TestMigrateBundleContract:
    """bundle_migration_output returns runbook string; no files dict."""

    def test_bundle_contains_runbook_string(self):
        scan_result = _make_scan_result(n_ingresses=1)
        analysis = _analyze(scan_result)
        files = _migrate(scan_result, analysis)

        bundle = bundle_migration_output(files, scan_result, analysis)

        assert "migration" in bundle
        assert "runbook" in bundle["migration"]
        assert isinstance(bundle["migration"]["runbook"], str)
        assert "bundleSummary" in bundle["migration"]
        assert "files" not in bundle["migration"]
        assert "analysis_report" not in bundle

    def test_runbook_contains_phased_sections(self):
        scan_result = _make_scan_result(n_ingresses=1)
        analysis = _analyze(scan_result)
        files = _migrate(scan_result, analysis)

        bundle = bundle_migration_output(files, scan_result, analysis)
        runbook = bundle["migration"]["runbook"]

        assert "# NGINX → Traefik Migration Runbook" in runbook
        assert "## Compatibility Summary" in runbook
        assert "## Phase 1 — Prerequisites" in runbook
        assert "## Phase 2 — Apply Migration" in runbook
        assert "## Phase 3 — Validate" in runbook
        assert "## Phase 4 — Cutover / Switch" in runbook
        assert "## Phase 5 — Post-Migration" in runbook
        assert "action: revert" in runbook

    def test_runbook_inlines_middleware_yaml(self):
        scan_result = _make_scan_result(n_ingresses=1)
        analysis = _analyze(scan_result)
        files = _migrate(scan_result, analysis)

        bundle = bundle_migration_output(files, scan_result, analysis)
        runbook = bundle["migration"]["runbook"]

        assert "Apply Middleware CRDs" in runbook
        assert "redirectScheme" in runbook  # actual YAML is inlined

    def test_merged_migrate_matches_analyze_root_keys(self):
        scan_result = _make_scan_result(n_ingresses=2)
        analysis = _analyze(scan_result)
        files = _migrate(scan_result, analysis)
        bundle = bundle_migration_output(files, scan_result, analysis)
        analysis_dict = analysis_report_to_dict(analysis)
        merged = {**analysis_dict, **bundle}

        for key in ("target", "ingressReports", "summary"):
            assert merged[key] == analysis_dict[key]

    def test_bundle_is_json_serializable(self):
        scan_result = _make_scan_result(n_ingresses=2)
        analysis = _analyze(scan_result)
        files = _migrate(scan_result, analysis)
        bundle = bundle_migration_output(files, scan_result, analysis)
        analysis_dict = analysis_report_to_dict(analysis)
        merged = {**analysis_dict, **bundle}

        serialized = json.dumps(merged, default=str)
        deserialized = json.loads(serialized)
        assert isinstance(deserialized["migration"]["runbook"], str)

    def test_migration_plan_overrides_in_runbook(self):
        scan_result = _make_scan_result(n_ingresses=1)
        analysis = _analyze(scan_result)
        files = _migrate(scan_result, analysis)
        plan = {"test-ingress-0": {"ignore_annotations": ["force-ssl-redirect"]}}

        bundle = bundle_migration_output(files, scan_result, analysis, migration_plan=plan)
        runbook = bundle["migration"]["runbook"]

        assert "Agent Intelligence" in runbook
        assert "`force-ssl-redirect`" in runbook


class TestScanResourceDigest:
    """nginx-ingress-scan resource digest includes paths and nginxAnnotations."""

    def test_digest_paths_and_nginx_values(self):
        scan = {
            "clusterName": "c",
            "controller": {},
            "namespaces": ["ns1"],
            "ingresses": [
                {
                    "namespace": "ns1",
                    "name": "ing1",
                    "ingressClass": "nginx",
                    "hosts": ["h1.com"],
                    "paths": [
                        {
                            "host": "h1.com",
                            "path": "/shop",
                            "pathType": "Prefix",
                            "serviceName": "shop",
                            "servicePort": 80,
                        }
                    ],
                    "tlsEnabled": False,
                    "nginxAnnotations": {"affinity": "cookie", "limit-rps": "100"},
                    "complexity": "complex",
                    "services": [{"namespace": "ns1", "name": "shop", "port": 80}],
                }
            ],
        }
        d = _nginx_scan_agent_digest(scan, None)
        assert d["schema"] == "traefik.mcp/nginx-ingress-scan/2"
        ing = d["ingresses"][0]
        assert ing["paths"][0]["serviceName"] == "shop"
        assert ing["paths"][0]["path"] == "/shop"
        assert ing["nginxAnnotations"] == {"affinity": "cookie", "limit-rps": "100"}
        assert ing["pathCount"] == 1


class TestScanResultNoisy:
    """scan_result_to_dict must strip internal Kubernetes bookkeeping annotations."""

    def test_last_applied_configuration_stripped(self):
        scan_result = _make_scan_result(n_ingresses=1)
        scan_result.ingresses[0].annotations[
            "kubectl.kubernetes.io/last-applied-configuration"
        ] = '{"apiVersion":"networking.k8s.io/v1","kind":"Ingress",' + '"x":"' + "y" * 500 + '"}'

        result_dict = scan_result_to_dict(scan_result)
        ing = result_dict["ingresses"][0]

        assert "kubectl.kubernetes.io/last-applied-configuration" not in ing["annotations"]
        assert "nginx.ingress.kubernetes.io/force-ssl-redirect" in ing["annotations"]

    def test_nginx_annotations_preserved(self):
        scan_result = _make_scan_result(n_ingresses=1)
        scan_result.ingresses[0].annotations[
            "kubectl.kubernetes.io/last-applied-configuration"
        ] = '{"huge": "payload"}'

        result_dict = scan_result_to_dict(scan_result)
        ing = result_dict["ingresses"][0]

        assert ing["nginxAnnotations"] == {"force-ssl-redirect": "true"}


class TestCompactScanResult:
    """scan_result_to_compact_dict remains available for other callers."""

    def test_compact_omits_paths_and_annotations(self):
        scan_result = _make_scan_result(n_ingresses=2)
        compact = scan_result_to_compact_dict(scan_result)

        for ing in compact["ingresses"]:
            assert "paths" not in ing
            assert "services" not in ing
            assert "annotations" not in ing
            assert "nginxAnnotations" in ing

    def test_compact_is_smaller_than_full(self):
        scan_result = _make_scan_result(n_ingresses=5)
        full_size = len(json.dumps(scan_result_to_dict(scan_result)))
        compact_size = len(json.dumps(scan_result_to_compact_dict(scan_result)))

        assert compact_size < full_size


class TestAnalyzeResourceWrapper:
    """MCP analyze resource wraps payload with schema + scope."""

    def test_wrap_includes_schema_and_merges_analysis(self):
        analysis = {
            "target": "traefik",
            "ingressReports": [],
            "summary": {"total": 0, "fullyCompatible": 0, "needsWorkaround": 0, "hasUnsupported": 0},
        }
        body = _nginx_analyze_resource_body(analysis, "prod")
        assert body["schema"] == "traefik.mcp/nginx-ingress-analyze/1"
        assert body["scope"] == {"namespace": "prod"}
        assert body["target"] == "traefik"
        assert "fetchedAt" in body


class TestMigrateToolSlimPayload:
    """Tool response drops bulky analysis; points at resource URIs."""

    def test_slim_removes_analysis_root_keys(self):
        full = {
            "target": "traefik",
            "ingressReports": [{"x": 1}],
            "summary": {"total": 1},
            "status": "success",
            "migration": {"runbook": "# Runbook", "bundleSummary": {"total_files": 1}},
        }
        slim = slim_migrate_tool_payload(full, "production")
        assert "target" not in slim
        assert "ingressReports" not in slim
        assert "summary" not in slim
        assert slim["status"] == "success"
        assert "migration" in slim
        cr = slim["compatibilityReport"]
        assert cr["readResourceClusterUri"] == "traefik://migration/nginx-ingress-analyze"
        assert cr["readResourceNamespaceUri"] == (
            "traefik://migration/nginx-ingress-analyze/production"
        )
