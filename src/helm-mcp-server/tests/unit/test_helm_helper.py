"""Unit tests for helm_helper utilities (secret redaction, semver comparison, manifest diffing)."""

from __future__ import annotations

import yaml

from helm_mcp_server.utils.helm_helper import (
    REDACTED_PLACEHOLDER,
    compare_k8s_versions,
    compute_manifest_diff,
    parse_semver,
    redact_secrets_in_manifests,
    redact_sensitive_values,
)


def test_redact_sensitive_values_masks_secrets_and_preserves_secret_refs() -> None:
    """Sensitive keys like password/token should be redacted while existingSecret is preserved."""
    raw = {
        "auth": {
            "postgresPassword": "super-secret-password",
            "password": "user-secret",
            "existingSecret": "my-vault-secret",
            "secretKeys": {"adminPasswordKey": "postgres-password"},
            "apiToken": "tok_live_12345",
        },
        "primary": {
            "resources": {"requests": {"cpu": "250m"}},
        },
        "env": [
            {"name": "DB_PASSWORD", "value": "inline-secret"},
            {"name": "LOG_LEVEL", "value": "info"},
        ],
    }

    redacted = redact_sensitive_values(raw)

    assert redacted["auth"]["postgresPassword"] == REDACTED_PLACEHOLDER
    assert redacted["auth"]["password"] == REDACTED_PLACEHOLDER
    assert redacted["auth"]["apiToken"] == REDACTED_PLACEHOLDER
    # Secret reference names and key pointers must remain visible
    assert redacted["auth"]["existingSecret"] == "my-vault-secret"
    assert redacted["auth"]["secretKeys"]["adminPasswordKey"] == "postgres-password"
    assert redacted["primary"]["resources"]["requests"]["cpu"] == "250m"
    assert redacted["env"][0]["value"] == REDACTED_PLACEHOLDER
    assert redacted["env"][1]["value"] == "info"


def test_redact_secrets_in_manifests_masks_secret_data_and_sensitive_env() -> None:
    """Kubernetes Secret.data / stringData and sensitive container env values must be redacted."""
    manifest = """---
apiVersion: v1
kind: Secret
metadata:
  name: my-postgres
  namespace: prod
type: Opaque
data:
  postgres-password: c3VwZXItc2VjcmV0LXBhc3N3b3Jk
stringData:
  replication-password: plain-text-password
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: prod
spec:
  template:
    spec:
      containers:
        - name: app
          image: nginx:1.27.0
          env:
            - name: POSTGRES_PASSWORD
              value: exposed-password
            - name: APP_MODE
              value: production
"""
    sanitized = redact_secrets_in_manifests(manifest)
    docs = [d for d in yaml.safe_load_all(sanitized) if isinstance(d, dict)]

    secret_doc = docs[0]
    assert secret_doc["data"]["postgres-password"] == REDACTED_PLACEHOLDER
    assert secret_doc["stringData"]["replication-password"] == REDACTED_PLACEHOLDER

    dep_doc = docs[1]
    env_list = dep_doc["spec"]["template"]["spec"]["containers"][0]["env"]
    assert env_list[0]["value"] == REDACTED_PLACEHOLDER
    assert env_list[1]["value"] == "production"


def test_parse_semver_and_compare_k8s_versions() -> None:
    """Semver comparison must handle v-prefixes, EKS/GKE suffixes, and multi-digit minor versions."""
    assert parse_semver("v1.29.2-eks-1234") == (1, 29, 2)
    assert parse_semver(">=1.25.0-0") == (1, 25, 0)
    assert parse_semver("1.9") == (1, 9, 0)

    # Numeric semver check where lexicographical string comparison would fail ("1.9.0" vs "1.28.0")
    assert compare_k8s_versions("v1.9.0", "v1.28.0") is False
    assert compare_k8s_versions("v1.28.4-eks-abcdef", "1.28.0") is True
    assert compare_k8s_versions("v1.30.1", "v1.29.0") is True


def test_compute_manifest_diff_detects_added_removed_modified_images_and_replicas() -> None:
    """compute_manifest_diff should report added/removed/modified resources, image changes, and replica changes."""
    current_manifest = """---
apiVersion: v1
kind: Service
metadata:
  name: my-app
  namespace: prod
spec:
  ports:
    - port: 80
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: prod
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: app
          image: myorg/app:1.0.0
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: old-config
  namespace: prod
data:
  key: val
"""

    proposed_manifest = """---
apiVersion: v1
kind: Service
metadata:
  name: my-app
  namespace: prod
spec:
  ports:
    - port: 80
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: prod
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: app
          image: myorg/app:2.0.0
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ing
  namespace: prod
spec: {}
"""

    diff = compute_manifest_diff(current_manifest, proposed_manifest, default_namespace="prod")

    assert diff["has_changes"] is True
    assert diff["added_resources"] == [{"kind": "Ingress", "namespace": "prod", "name": "my-app-ing"}]
    assert diff["removed_resources"] == [{"kind": "ConfigMap", "namespace": "prod", "name": "old-config"}]
    assert diff["modified_resources"] == [
        {
            "kind": "Deployment",
            "namespace": "prod",
            "name": "my-app",
            "changed_fields": ["spec"],
        }
    ]
    assert diff["unchanged_count"] == 1
    assert diff["image_changes"] == [
        {
            "resource": "Deployment/my-app",
            "container": "app",
            "from": "myorg/app:1.0.0",
            "to": "myorg/app:2.0.0",
        }
    ]
    assert diff["replica_changes"] == [
        {
            "resource": "Deployment/my-app",
            "from": 1,
            "to": 3,
        }
    ]
