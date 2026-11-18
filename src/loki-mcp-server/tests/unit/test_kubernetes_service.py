"""Unit tests for KubernetesService (LokiStack, RulerConfig, AlertingRule, RecordingRule CRDs)."""

from __future__ import annotations

import pytest

from loki_mcp_server.config import KubernetesConfig, LokiOperatorConfig
from loki_mcp_server.exceptions import LokiValidationError
from loki_mcp_server.services.kubernetes_service import KubernetesService

VALID_LOKISTACK_YAML = """
apiVersion: loki.grafana.com/v1
kind: LokiStack
metadata:
  name: loki-prod
  namespace: logging
spec:
  size: 1x.small
  storage:
    schemas:
      - version: v13
        effectiveDate: "2024-04-01"
    secret:
      name: loki-s3-creds
      type: s3
      access_key_secret: should-be-redacted
"""

VALID_ALERTING_RULE_YAML = """
apiVersion: loki.grafana.com/v1beta1
kind: AlertingRule
metadata:
  name: checkout-alerts
  namespace: prod
spec:
  tenantID: application
  groups:
    - name: checkout-slo
      interval: 1m
      rules:
        - alert: CheckoutHighErrorRate
          expr: rate({service_name="checkout"} |= "error" [5m]) > 1
          for: 5m
"""


class TestKubernetesService:
    """Comprehensive unit tests for KubernetesService CRD validation, diffing, and state."""

    def setup_method(self) -> None:
        self.svc = KubernetesService(
            KubernetesConfig(enabled=True),
            operator_config=LokiOperatorConfig(),
            field_manager="talkops-loki-mcp",
        )

    def test_resolve_crd_kind_supported_and_unsupported(self) -> None:
        assert self.svc.resolve_crd_kind("lokistack") == ("LokiStack", "lokistacks", "v1")
        assert self.svc.resolve_crd_kind("AlertingRule") == (
            "AlertingRule",
            "alertingrules",
            "v1beta1",
        )
        assert self.svc.resolve_crd_kind("RecordingRule") == (
            "RecordingRule",
            "recordingrules",
            "v1beta1",
        )
        assert self.svc.resolve_crd_kind("RulerConfig") == (
            "RulerConfig",
            "rulerconfigs",
            "v1beta1",
        )
        with pytest.raises(LokiValidationError, match="Unsupported Loki Operator CRD kind"):
            self.svc.resolve_crd_kind("Deployment")

    def test_validate_operator_manifest_rejects_invalid_inputs(self) -> None:
        with pytest.raises(LokiValidationError, match="must not be empty"):
            self.svc.validate_operator_manifest("")

        with pytest.raises(LokiValidationError, match="missing required 'kind'"):
            self.svc.validate_operator_manifest("metadata:\n  name: test\n")

        with pytest.raises(LokiValidationError, match="Invalid apiVersion"):
            self.svc.validate_operator_manifest(
                "apiVersion: apps/v1\nkind: LokiStack\nmetadata:\n  name: x\nspec:\n  size: 1x.small\n"
            )

        with pytest.raises(LokiValidationError, match="spec.size is required"):
            self.svc.validate_operator_manifest(
                "apiVersion: loki.grafana.com/v1\nkind: LokiStack\nmetadata:\n  name: x\nspec:\n  storage: {}\n"
            )

        with pytest.raises(LokiValidationError, match="spec.storage.secret is required"):
            self.svc.validate_operator_manifest(
                "apiVersion: loki.grafana.com/v1\nkind: LokiStack\nmetadata:\n  name: x\nspec:\n  size: 1x.small\n"
            )

    @pytest.mark.asyncio
    async def test_apply_dry_run_and_live_lifecycle_with_redaction(self) -> None:
        # 1. Dry-run preview does not persist to store
        preview = await self.svc.apply_loki_operator_cr(
            manifest_yaml=VALID_LOKISTACK_YAML,
            namespace="logging",
            dry_run=True,
        )
        assert preview["status"] == "dry_run_preview"
        assert preview["dry_run"] is True
        assert preview["kind"] == "LokiStack"
        assert "+  size: 1x.small" in preview["diff"]
        assert (
            preview["manifest"]["spec"]["storage"]["secret"]["access_key_secret"]
            == "***REDACTED***"
        )
        assert await self.svc.list_loki_operator_crs(namespace="logging") == []

        # 2. Live apply persists sanitized CR
        applied = await self.svc.apply_loki_operator_cr(
            manifest_yaml=VALID_LOKISTACK_YAML,
            namespace="logging",
            dry_run=False,
        )
        assert applied["status"] == "applied"
        assert applied["dry_run"] is False

        # 3. Add an AlertingRule in 'prod' namespace
        await self.svc.apply_loki_operator_cr(
            manifest_yaml=VALID_ALERTING_RULE_YAML,
            namespace="prod",
            dry_run=False,
        )

        logging_crs = await self.svc.list_loki_operator_crs(namespace="logging")
        assert len(logging_crs) == 1
        assert logging_crs[0]["metadata"]["name"] == "loki-prod"

        all_crs = await self.svc.list_loki_operator_crs(namespace="_all")
        assert len(all_crs) == 2

        fetched = await self.svc.get_loki_operator_cr("LokiStack", "logging", "loki-prod")
        assert fetched["spec"]["size"] == "1x.small"

        missing = await self.svc.get_loki_operator_cr("LokiStack", "logging", "nonexistent")
        assert missing["status"]["phase"] == "NotFound"
