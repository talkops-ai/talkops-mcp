"""Tests for Pydantic data models."""
import pytest
from datetime import datetime, timezone
from alertmanager_mcp_server.models import (
    AlertGroup, AlertMatcher, AlertmanagerConfigSnapshot, AuditLogEntry,
    BackendDescriptor, BackendsSummary, GettableAlert, GettableSilence,
    InhibitionRule, PostableSilence, ReceiverConfig, RoutingRoute,
    RoutingSimulationResult, SilenceEffectPreview, SilenceStatus,
)


class TestBackendModels:
    def test_backend_descriptor_defaults(self):
        bd = BackendDescriptor(id="test", base_url="http://localhost:9093")
        assert bd.health == "unknown"
        assert bd.labels == {}

    def test_backends_summary(self):
        summary = BackendsSummary(backends=[BackendDescriptor(id="a", base_url="http://a:9093")])
        assert len(summary.backends) == 1


class TestAlertModels:
    def test_alert_matcher(self):
        m = AlertMatcher(name="alertname", value="HighCPU", isRegex=False, isEqual=True)
        assert m.isRegex is False
        assert m.isEqual is True

    def test_gettable_alert(self):
        a = GettableAlert(fingerprint="abc", labels={"alertname": "Test"}, startsAt=datetime.now(timezone.utc))
        assert a.fingerprint == "abc"

    def test_alert_group(self):
        g = AlertGroup(labels={"alertname": "Test"})
        assert len(g.alerts) == 0


class TestSilenceModels:
    def test_silence_status(self):
        s = SilenceStatus(state="active")
        assert s.state == "active"

    def test_postable_silence(self):
        now = datetime.now(timezone.utc)
        ps = PostableSilence(matchers=[AlertMatcher(name="alertname", value="X", isRegex=False, isEqual=True)],
                             startsAt=now, endsAt=now, createdBy="test", comment="test")
        assert ps.createdBy == "test"

    def test_gettable_silence(self):
        now = datetime.now(timezone.utc)
        gs = GettableSilence(id="s1", matchers=[], startsAt=now, endsAt=now,
                             createdBy="test", comment="test", status=SilenceStatus(state="active"))
        assert gs.id == "s1"

    def test_silence_effect_preview(self):
        p = SilenceEffectPreview(affected_alert_count=10, warning_flag=False)
        assert p.affected_alert_count == 10


class TestConfigModels:
    def test_receiver_config(self):
        rc = ReceiverConfig(name="slack-sre", type="slack")
        assert rc.name == "slack-sre"

    def test_routing_route(self):
        r = RoutingRoute(receiver="default")
        assert r.receiver == "default"

    def test_inhibition_rule(self):
        ir = InhibitionRule(equal=["alertname"])
        assert ir.equal == ["alertname"]

    def test_config_snapshot(self):
        cs = AlertmanagerConfigSnapshot()
        assert cs.routes == []

    def test_routing_simulation(self):
        rs = RoutingSimulationResult(receivers=["slack"], route_path="root -> slack")
        assert "slack" in rs.receivers


class TestAuditModels:
    def test_audit_log_entry(self):
        entry = AuditLogEntry(timestamp=datetime.now(timezone.utc), backend_id="test",
                              operation="create_silence", principal="mcp", summary="Created silence")
        assert entry.operation == "create_silence"
