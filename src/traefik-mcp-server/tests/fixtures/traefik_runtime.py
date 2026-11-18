"""Sample Traefik /api/* runtime snapshots for testing."""

import copy
from typing import Any, Dict


DEFAULT_RUNTIME_FIXTURE: Dict[str, Any] = {
    "version": {"Version": "3.6.1", "Codename": "ramon"},
    "overview": {
        "http": {
            "routers": {"total": 2, "warnings": 0, "errors": 0},
            "services": {"total": 3, "warnings": 0, "errors": 0},
            "middlewares": {"total": 1, "warnings": 0, "errors": 0},
        },
        "tcp": {
            "routers": {"total": 0, "warnings": 0, "errors": 0},
            "services": {"total": 0, "warnings": 0, "errors": 0},
            "middlewares": {"total": 0, "warnings": 0, "errors": 0},
        },
        "udp": {
            "routers": {"total": 0, "warnings": 0, "errors": 0},
            "services": {"total": 0, "warnings": 0, "errors": 0},
        },
    },
    "entrypoints": [
        {"name": "web", "address": ":80", "transport": {"respondingTimeouts": {"readTimeout": "60s"}}},
        {"name": "websecure", "address": ":443", "http": {"tls": {}}},
        {"name": "tcp", "address": ":9000"},
        {"name": "udp", "address": ":53/udp"},
    ],
    "http": {
        "routers": [
            {
                "name": "default-payments-route-0@kubernetescrd",
                "rule": "Host(`api.example.com`) && PathPrefix(`/payments`)",
                "priority": 120,
                "entryPoints": ["websecure"],
                "middlewares": ["default-api-ratelimit@kubernetescrd"],
                "service": "default-payments-wrr@kubernetescrd",
                "status": "enabled",
                "provider": "kubernetescrd",
                "tls": {"options": "default-modern-tls@kubernetescrd"},
            },
            {
                "name": "default-payments-catchall-0@kubernetescrd",
                "rule": "Host(`api.example.com`)",
                "priority": 21,
                "entryPoints": ["websecure"],
                "middlewares": [],
                "service": "default-orders-svc-8080@kubernetescrd",
                "status": "enabled",
                "provider": "kubernetescrd",
            },
        ],
        "services": [
            {
                "name": "default-payments-stable-80@kubernetescrd",
                "status": "enabled",
                "serverStatus": {"http://10.244.0.10:8080": "UP", "http://10.244.0.11:8080": "UP"},
            },
            {
                "name": "default-payments-canary-80@kubernetescrd",
                "status": "enabled",
                "serverStatus": {"http://10.244.0.12:8080": "UP"},
            },
            {
                "name": "default-payments-wrr@kubernetescrd",
                "status": "enabled",
                "weighted": {
                    "services": [
                        {"name": "default-payments-stable-80@kubernetescrd", "weight": 90},
                        {"name": "default-payments-canary-80@kubernetescrd", "weight": 10},
                    ]
                },
            },
        ],
        "middlewares": [
            {
                "name": "default-api-ratelimit@kubernetescrd",
                "type": "ratelimiter",
                "status": "enabled",
                "rateLimit": {"average": 100, "burst": 200, "period": "1s"},
            }
        ],
    },
    "tcp": {"routers": [], "services": [], "middlewares": []},
    "udp": {"routers": [], "services": []},
}


def get_runtime_fixture() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_RUNTIME_FIXTURE)
