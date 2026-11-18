"""Unit tests for Kubernetes manifest sanitization and secret redaction."""

from __future__ import annotations

from kargo_mcp_server.utils import (
    REDACTED_PLACEHOLDER,
    redact_credentials_dict,
    sanitize_manifest,
)


def test_sanitize_manifest_strips_noise_and_redacts_secrets() -> None:
    secret_manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "repo-cred",
            "namespace": "guestbook",
            "managedFields": [{"manager": "kargo"}],
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": '{"secret":"leak"}',
                "kargo.akuity.io/description": "git credentials",
            },
        },
        "data": {"password": "c2VjcmV0", "username": "YWRtaW4="},
        "stringData": {"token": "ghp_supersecret123"},
    }

    cleaned = sanitize_manifest(secret_manifest)
    assert "managedFields" not in cleaned["metadata"]
    assert (
        "kubectl.kubernetes.io/last-applied-configuration"
        not in cleaned["metadata"]["annotations"]
    )
    assert cleaned["metadata"]["annotations"]["kargo.akuity.io/description"] == "git credentials"
    assert cleaned["data"]["password"] == REDACTED_PLACEHOLDER
    assert cleaned["data"]["username"] == REDACTED_PLACEHOLDER
    assert cleaned["stringData"]["token"] == REDACTED_PLACEHOLDER


def test_sanitize_manifest_redacts_literal_container_env_values_only() -> None:
    pod_like = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "analysis-pod"},
        "spec": {
            "containers": [
                {
                    "name": "runner",
                    "env": [
                        {"name": "API_TOKEN", "value": "plain-secret"},
                        {
                            "name": "FROM_SECRET",
                            "valueFrom": {"secretKeyRef": {"name": "my-sec", "key": "k"}},
                        },
                    ],
                }
            ]
        },
    }
    cleaned = sanitize_manifest(pod_like)
    env_list = cleaned["spec"]["containers"][0]["env"]
    assert env_list[0]["value"] == REDACTED_PLACEHOLDER
    assert "valueFrom" in env_list[1]


def test_redact_credentials_dict_redacts_sensitive_keys() -> None:
    raw = {
        "metadata": {"name": "my-cred"},
        "stringData": {
            "repoURL": "https://github.com/org/repo.git",
            "username": "octocat",
            "password": "my-password",
            "sshPrivateKey": "-----BEGIN OPENSSH PRIVATE KEY-----",
        },
    }
    redacted = redact_credentials_dict(raw)
    assert redacted["stringData"]["repoURL"] == "https://github.com/org/repo.git"
    assert redacted["stringData"]["username"] == "octocat"
    assert redacted["stringData"]["password"] == REDACTED_PLACEHOLDER
    assert redacted["stringData"]["sshPrivateKey"] == REDACTED_PLACEHOLDER
