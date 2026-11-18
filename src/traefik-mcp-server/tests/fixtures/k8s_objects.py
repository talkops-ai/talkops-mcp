"""Sample Kubernetes, Traefik CRD, and Gateway API objects for unit and integration tests."""

import copy
from typing import Any, Dict, List
from tests.fixtures.sample_certs import VALID_WILDCARD_CERT_B64


def default_seed_objects() -> List[Dict[str, Any]]:
    """Return a realistic seed set of Traefik CRDs, K8s Services/Endpoints/Secrets, and Gateway API objects."""
    return copy.deepcopy([
        # Kubernetes Services
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "payments-stable", "namespace": "default", "resourceVersion": "1001"},
            "spec": {"type": "ClusterIP", "ports": [{"name": "http", "port": 80, "targetPort": 8080}]},
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "payments-canary", "namespace": "default", "resourceVersion": "1002"},
            "spec": {"type": "ClusterIP", "ports": [{"name": "http", "port": 80, "targetPort": 8080}]},
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "payments-empty", "namespace": "default", "resourceVersion": "1003"},
            "spec": {"type": "ClusterIP", "ports": [{"name": "http", "port": 80, "targetPort": 8080}]},
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "orders-svc", "namespace": "default", "resourceVersion": "1004"},
            "spec": {"type": "ClusterIP", "ports": [{"name": "http", "port": 8080}]},
        },
        # Endpoints
        {
            "apiVersion": "v1",
            "kind": "Endpoints",
            "metadata": {"name": "payments-stable", "namespace": "default"},
            "subsets": [{"addresses": [{"ip": "10.244.0.10"}, {"ip": "10.244.0.11"}]}],
        },
        {
            "apiVersion": "v1",
            "kind": "Endpoints",
            "metadata": {"name": "payments-canary", "namespace": "default"},
            "subsets": [{"addresses": [{"ip": "10.244.0.12"}]}],
        },
        {
            "apiVersion": "v1",
            "kind": "Endpoints",
            "metadata": {"name": "payments-empty", "namespace": "default"},
            "subsets": [{"addresses": [], "notReadyAddresses": [{"ip": "10.244.0.99"}]}],
        },
        {
            "apiVersion": "v1",
            "kind": "Endpoints",
            "metadata": {"name": "orders-svc", "namespace": "default"},
            "subsets": [{"addresses": [{"ip": "10.244.0.20"}]}],
        },
        # TLS Secret
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "prod-wildcard-tls", "namespace": "default", "resourceVersion": "2001"},
            "type": "kubernetes.io/tls",
            "data": {
                "tls.crt": VALID_WILDCARD_CERT_B64,
                "tls.key": "SUPER_SECRET_PRIVATE_KEY_BASE64",
            },
        },
        # cert-manager Certificate
        {
            "apiVersion": "cert-manager.io/v1",
            "kind": "Certificate",
            "metadata": {"name": "prod-wildcard-cert", "namespace": "default"},
            "spec": {"secretName": "prod-wildcard-tls", "issuerRef": {"name": "letsencrypt-prod", "kind": "ClusterIssuer"}},
            "status": {"conditions": [{"type": "Ready", "status": "True"}], "renewalTime": "2027-01-01T00:00:00Z"},
        },
        # Middleware
        {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "Middleware",
            "metadata": {
                "name": "api-ratelimit",
                "namespace": "default",
                "resourceVersion": "3001",
                "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
            },
            "spec": {"rateLimit": {"average": 100, "burst": 200, "period": "1s"}},
        },
        # TLSOption
        {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "TLSOption",
            "metadata": {
                "name": "modern-tls",
                "namespace": "default",
                "resourceVersion": "3002",
                "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
            },
            "spec": {"minVersion": "VersionTLS13", "sniStrict": True},
        },
        # Weighted TraefikService
        {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "TraefikService",
            "metadata": {
                "name": "payments-wrr",
                "namespace": "default",
                "resourceVersion": "4001",
                "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
            },
            "spec": {
                "weighted": {
                    "services": [
                        {"name": "payments-stable", "port": 80, "weight": 90},
                        {"name": "payments-canary", "port": 80, "weight": 10},
                    ]
                }
            },
        },
        # IngressRoute referencing payments-wrr & api-ratelimit & prod-wildcard-tls
        {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "IngressRoute",
            "metadata": {
                "name": "payments-route",
                "namespace": "default",
                "resourceVersion": "5001",
                "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
                "managedFields": [{"manager": "kubectl", "operation": "Update"}],
                "annotations": {
                    "kubectl.kubernetes.io/last-applied-configuration": '{"heavy":"bloat"}',
                },
            },
            "spec": {
                "entryPoints": ["websecure"],
                "routes": [
                    {
                        "kind": "Rule",
                        "match": "Host(`api.example.com`) && PathPrefix(`/payments`)",
                        "priority": 120,
                        "middlewares": [{"name": "api-ratelimit"}],
                        "services": [{"name": "payments-wrr", "kind": "TraefikService"}],
                    }
                ],
                "tls": {
                    "secretName": "prod-wildcard-tls",
                    "options": {"name": "modern-tls"},
                },
            },
        },
        # Standard Kubernetes Ingress with nginx.ingress.kubernetes.io/* annotations
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": "legacy-nginx-ingress",
                "namespace": "default",
                "resourceVersion": "5500",
                "annotations": {
                    "nginx.ingress.kubernetes.io/rewrite-target": "/$1",
                    "nginx.ingress.kubernetes.io/ssl-redirect": "true",
                },
            },
            "spec": {
                "ingressClassName": "nginx",
                "rules": [
                    {
                        "host": "legacy.example.com",
                        "http": {
                            "paths": [
                                {
                                    "path": "/orders",
                                    "pathType": "Prefix",
                                    "backend": {"service": {"name": "orders-svc", "port": {"number": 8080}}},
                                }
                            ]
                        },
                    }
                ],
            },
        },
        # Gateway API objects (read & diagnose only)
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "GatewayClass",
            "metadata": {"name": "traefik", "resourceVersion": "6001"},
            "spec": {"controllerName": "traefik.io/gateway-controller"},
            "status": {"conditions": [{"type": "Accepted", "status": "True", "reason": "Accepted"}]},
        },
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "Gateway",
            "metadata": {"name": "shared-gateway", "namespace": "default", "resourceVersion": "6002"},
            "spec": {
                "gatewayClassName": "traefik",
                "listeners": [
                    {"name": "websecure", "port": 443, "protocol": "HTTPS", "hostname": "*.example.com"}
                ],
            },
            "status": {"conditions": [{"type": "Programmed", "status": "True", "reason": "Programmed"}]},
        },
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {"name": "orders-httproute", "namespace": "default", "resourceVersion": "6003"},
            "spec": {
                "parentRefs": [{"name": "shared-gateway"}],
                "hostnames": ["orders.example.com"],
                "rules": [{"backendRefs": [{"name": "orders-svc", "port": 8080}]}],
            },
            "status": {
                "parents": [
                    {
                        "parentRef": {"name": "shared-gateway"},
                        "conditions": [
                            {"type": "Accepted", "status": "True", "reason": "Accepted"},
                            {"type": "ResolvedRefs", "status": "True", "reason": "ResolvedRefs"},
                        ],
                    }
                ]
            },
        },
    ])
