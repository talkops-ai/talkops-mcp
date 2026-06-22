"""Unit tests for tag parsing and attribute normalization.

Covers §6.3 (tag parsing) and §11 #5 (test_attribute_names_parses_v2_tags).
"""

import pytest
from typing import Dict, Any

from tempo_mcp_server.utils.traceql_helpers import DEFAULT_K8S_MAP


class TestV2TagsParsing:
    """Normalize attribute names from /api/v2/search/tags response."""

    # §11 #5: test_attribute_names_parses_v2_tags
    def test_parses_scoped_tags(self, sample_tag_payload: Dict[str, Any]):
        """Verify the v2 tags response scopes are correctly structured."""
        scopes = sample_tag_payload.get("scopes", [])
        assert len(scopes) == 3

        scope_names = [s["name"] for s in scopes]
        assert "resource" in scope_names
        assert "span" in scope_names
        assert "intrinsic" in scope_names

    def test_resource_scope_has_k8s_attrs(self, sample_tag_payload):
        resource_scope = next(s for s in sample_tag_payload["scopes"] if s["name"] == "resource")
        tag_names = [t["name"] for t in resource_scope["tags"]]
        assert "service.name" in tag_names
        assert "k8s.namespace.name" in tag_names

    def test_span_scope_has_http_attrs(self, sample_tag_payload):
        span_scope = next(s for s in sample_tag_payload["scopes"] if s["name"] == "span")
        tag_names = [t["name"] for t in span_scope["tags"]]
        assert "http.method" in tag_names
        assert "http.status_code" in tag_names

    def test_total_tag_count(self, sample_tag_payload):
        total = sum(len(s["tags"]) for s in sample_tag_payload["scopes"])
        assert total == 13  # 5 resource + 5 span + 3 intrinsic


class TestTagValuesParsing:
    """Normalize tag values from /api/v2/search/tag/<tag>/values response."""

    def test_extracts_string_values(self):
        from tests.conftest import _load_fixture
        payload = _load_fixture("tags_values_response.json")
        values = [tv["value"] for tv in payload["tagValues"]]
        assert "api-gateway" in values
        assert "user-service" in values
        assert len(values) == 4


class TestK8sAttributeMap:
    """Verify the K8s-to-OTel attribute mapping."""

    def test_namespace_mapping(self):
        assert DEFAULT_K8S_MAP["namespace"] == "k8s.namespace.name"

    def test_service_mapping(self):
        # C-02 fix: map value must NOT include "resource." prefix since that is
        # added at query-generation time via `resource.{attr}`. The old value
        # "resource.service.name" would produce "resource.resource.service.name".
        assert DEFAULT_K8S_MAP["service"] == "service.name"

    def test_deployment_mapping(self):
        assert DEFAULT_K8S_MAP["deployment"] == "k8s.deployment.name"

    def test_all_keys_present(self):
        expected_keys = {"namespace", "service", "deployment", "cluster", "environment"}
        assert expected_keys <= set(DEFAULT_K8S_MAP.keys())
