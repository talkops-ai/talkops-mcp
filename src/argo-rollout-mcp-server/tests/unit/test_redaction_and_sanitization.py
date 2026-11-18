"""Unit tests for Kubernetes manifest redaction and metadata sanitization (T-U4)."""

from argo_rollout_mcp_server.utils.redaction import REDACTED_PLACEHOLDER, sanitize_manifest


def test_strips_managed_fields_and_last_applied_configuration():
    raw = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Rollout",
        "metadata": {
            "name": "payments-api",
            "namespace": "default",
            "managedFields": [{"manager": "kubectl"}],
            "managed_fields": [{"manager": "argocd"}],
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": '{"secret":"leak"}',
                "argocd.argoproj.io/tracking-id": "payments:argoproj.io/Rollout:default/payments-api",
            },
        },
        "spec": {},
    }

    cleaned = sanitize_manifest(raw)
    meta = cleaned["metadata"]
    assert "managedFields" not in meta
    assert "managed_fields" not in meta
    assert "kubectl.kubernetes.io/last-applied-configuration" not in meta.get("annotations", {})
    assert "argocd.argoproj.io/tracking-id" in meta["annotations"]


def test_redacts_literal_env_values_and_preserves_value_from():
    raw = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Rollout",
        "metadata": {"name": "payments-api"},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "env": [
                                {"name": "API_KEY", "value": "sk-live-12345"},
                                {
                                    "name": "DB_PASS",
                                    "valueFrom": {
                                        "secretKeyRef": {"name": "db-sec", "key": "password"}
                                    },
                                },
                            ],
                        }
                    ],
                    "initContainers": [
                        {
                            "name": "init",
                            "env": [{"name": "INIT_TOKEN", "value": "init-secret"}],
                        }
                    ],
                }
            }
        },
    }

    cleaned = sanitize_manifest(raw)
    pod_spec = cleaned["spec"]["template"]["spec"]
    app_env = pod_spec["containers"][0]["env"]
    assert app_env[0]["value"] == REDACTED_PLACEHOLDER
    assert "value" not in app_env[1]
    assert app_env[1]["valueFrom"]["secretKeyRef"]["name"] == "db-sec"

    init_env = pod_spec["initContainers"][0]["env"]
    assert init_env[0]["value"] == REDACTED_PLACEHOLDER


def test_redacts_secret_data_and_string_data():
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "my-secret"},
        "data": {"tls.key": "base64data"},
        "stringData": {"password": "plain-password"},
    }
    cleaned = sanitize_manifest(secret)
    assert cleaned["data"]["tls.key"] == REDACTED_PLACEHOLDER
    assert cleaned["stringData"]["password"] == REDACTED_PLACEHOLDER
