"""Unit tests for write-guard pipeline: namespace policy, ownership, schema gating, chain cycles, and weight safety."""

import pytest
from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.exceptions.custom import (
    KubernetesNamespaceError,
    TraefikEmptyBackendError,
    TraefikReferentialIntegrityError,
    TraefikSchemaGatingError,
    TraefikWeightError,
)
from traefik_mcp_server.services.guards import (
    check_crd_schema_gating,
    check_namespace_policy,
    check_ownership,
    check_traffic_weights_safety,
    compute_unified_diff,
    detect_middleware_chain_cycles,
    lint_middleware_ordering,
    stamp_managed_metadata,
)


def test_namespace_policy_blocks_protected_and_unallowed():
    cfg = ServerConfig(allow_write=True, allowed_namespaces=["default", "staging"])
    with pytest.raises(KubernetesNamespaceError, match="protected"):
        check_namespace_policy("kube-system", cfg)
    with pytest.raises(KubernetesNamespaceError, match="not in allowed_namespaces"):
        check_namespace_policy("untrusted", cfg)
    res = check_namespace_policy("default", cfg)
    assert res.passed is True


def test_ownership_blocks_argo_rollout_and_warns_gitops():
    rollout = {
        "metadata": {"name": "payments-rollout", "namespace": "default"},
        "spec": {"strategy": {"canary": {"trafficRouting": {"traefik": {"weightedTraefikServiceName": "payments-wrr"}}}}},
    }
    guard, owner = check_ownership("TraefikService", "payments-wrr", "default", existing_obj={}, argo_rollouts=[rollout])
    assert guard.passed is False
    assert owner == "argo_rollouts"

    gitops_obj = {"metadata": {"labels": {"argocd.argoproj.io/instance": "prod-app"}}}
    g2, owner2 = check_ownership("IngressRoute", "r1", "default", existing_obj=gitops_obj)
    assert g2.passed is True
    assert owner2 == "gitops"


def test_schema_gating_rejects_unsupported_ip_deny_list():
    with pytest.raises(TraefikSchemaGatingError, match="ipDenyList"):
        check_crd_schema_gating(
            kind="Middleware",
            spec={"ipDenyList": {"sourceRange": ["192.0.2.0/24"]}},
            installed_fields={"rateLimit", "ipAllowList", "headers"},
        )


def test_detect_middleware_chain_cycles():
    existing = {
        ("default", "chain-b"): {"spec": {"chain": {"middlewares": [{"name": "chain-a"}]}}},
    }
    with pytest.raises(TraefikReferentialIntegrityError, match="Circular"):
        detect_middleware_chain_cycles("chain-a", "default", [{"name": "chain-b"}], existing)


def test_check_traffic_weights_safety_blocks_zero_sum_and_empty_backend():
    with pytest.raises(TraefikWeightError, match="ALL_WEIGHTS_ZERO"):
        check_traffic_weights_safety({"a": 0, "b": 0}, {"a": 2, "b": 2})

    with pytest.raises(TraefikEmptyBackendError, match="WEIGHT_TO_EMPTY_BACKEND"):
        check_traffic_weights_safety({"a": 50, "empty-svc": 50}, {"a": 2, "empty-svc": 0})


def test_stamp_metadata_and_diff_and_ordering_lint():
    body = {"apiVersion": "traefik.io/v1alpha1", "kind": "Middleware", "metadata": {"name": "m1"}}
    stamped = stamp_managed_metadata(body)
    assert stamped["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "talkops-traefik-mcp"

    diff = compute_unified_diff(None, stamped, "Middleware/default/m1")
    assert "+kind: Middleware" in diff

    warnings = lint_middleware_ordering([("auth", "basicAuth"), ("rl", "rateLimit")])
    assert len(warnings) == 1
