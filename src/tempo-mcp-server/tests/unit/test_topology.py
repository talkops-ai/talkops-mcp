"""Unit tests for topology / service dependency derivation.

Covers §3 (derived dependency logic): graph derivation from metrics.
"""

import pytest

from tempo_mcp_server.models.topology import ServiceNode, ServiceEdge


class TestServiceGraphModels:
    """Verify topology model construction."""

    def test_node_creation(self):
        node = ServiceNode(service="api-gateway")
        assert node.service == "api-gateway"

    def test_edge_creation(self):
        edge = ServiceEdge(client="frontend", server="api-gateway", request_rate=100.5, error_rate=2.1)
        assert edge.client == "frontend"
        assert edge.server == "api-gateway"
        assert edge.request_rate == 100.5
        assert edge.error_rate == 2.1

    def test_edge_defaults(self):
        edge = ServiceEdge(client="a", server="b")
        assert edge.request_rate is None
        assert edge.error_rate is None
        assert edge.source_metric == "traces_service_graph_request_total"
