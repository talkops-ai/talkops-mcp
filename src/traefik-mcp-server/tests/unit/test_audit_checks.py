"""Unit tests for all 20 deterministic security, TLS, reliability, hygiene, v3_migration, and gateway_api audit checks."""

from traefik_mcp_server.services.audit_checks import (
    ALL_AUDIT_CHECK_IDS,
    run_configuration_audit,
)


def test_all_20_audit_check_ids_triggered_on_synthetic_misconfigured_state():
    static_config = {
        "api": {"insecure": True, "dashboard": True},
        "entryPoints": {
            "web": {"address": ":80", "forwardedHeaders": {"insecure": True}},
        },
        "providers": {
            "kubernetesCRD": {
                "allowCrossNamespace": True,
                "allowExternalNameServices": True,
            }
        },
    }
    routes = [
        {
            "kind": "IngressRoute",
            "name": "legacy-route-1",
            "namespace": "default",
            "api_version": "traefik.containo.us/v1alpha1",
            "entry_points": ["web"],
            "tls": None,
            "rules": [
                {
                    "match": "Headers(`X-Legacy`, `1`)",
                    "priority": None,
                    "middlewares": [],
                    "services": [{"name": "missing-k8s-svc", "port": 80}],
                }
            ],
        },
        {
            "kind": "IngressRoute",
            "name": "dup-route-a",
            "namespace": "default",
            "api_version": "traefik.io/v1alpha1",
            "entry_points": ["web"],
            "tls": None,
            "rules": [{"match": "Host(`dup.example.com`)", "priority": None, "middlewares": [], "services": []}],
        },
        {
            "kind": "IngressRoute",
            "name": "dup-route-b",
            "namespace": "default",
            "api_version": "traefik.io/v1alpha1",
            "entry_points": ["web"],
            "tls": None,
            "rules": [{"match": "Host(`dup.example.com`)", "priority": None, "middlewares": [], "services": []}],
        },
        {
            "kind": "TraefikService",
            "name": "orphan-wrr",
            "namespace": "default",
            "referenced_by_count": 0,
            "spec": {
                "weighted": {
                    "services": [
                        {"name": "svc-a", "port": 80, "weight": 50},
                        {"name": "svc-b", "port": 80, "weight": 50},
                    ]
                }
            },
        },
    ]
    policies = [
        {
            "kind": "Middleware",
            "name": "wildcard-cors",
            "namespace": "default",
            "referenced_by_count": 0,
            "spec": {
                "headers": {
                    "accessControlAllowOriginList": ["*"],
                    "accessControlAllowCredentials": True,
                }
            },
        },
        {
            "kind": "Middleware",
            "name": "excessive-retry",
            "namespace": "default",
            "referenced_by_count": 1,
            "spec": {"retry": {"attempts": 8}},
        },
        {
            "kind": "TLSOption",
            "name": "weak-tls-opt",
            "namespace": "default",
            "referenced_by_count": 0,
            "spec": {
                "minVersion": "VersionTLS10",
                "cipherSuites": ["TLS_RSA_WITH_AES_128_CBC_SHA"],
            },
        },
        {
            "kind": "ServersTransport",
            "name": "insecure-transport",
            "namespace": "default",
            "referenced_by_count": 1,
            "spec": {"insecureSkipVerify": True},
        },
    ]
    certificates = [
        {
            "name": "expired-default-cert",
            "namespace": "default",
            "expired": True,
            "days_remaining": -5,
            "is_traefik_default_cert": True,
        }
    ]
    gateways = [
        {
            "kind": "HTTPRoute",
            "name": "rejected-httproute",
            "namespace": "default",
            "accepted": False,
            "resolved_refs": False,
        }
    ]

    report = run_configuration_audit(
        static_config=static_config,
        routes=routes,
        policies=policies,
        certificates=certificates,
        gateways=gateways,
        existing_services=set(),
        has_legacy_containo_crds=True,
        max_findings=100,
    )
    triggered_ids = {f["check_id"] for f in report["findings"]}
    assert set(ALL_AUDIT_CHECK_IDS) == triggered_ids
