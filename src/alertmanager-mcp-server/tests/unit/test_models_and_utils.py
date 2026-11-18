"""Unit tests for Pydantic models, audit log persistence, and utility functions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alertmanager_mcp_server.models.alert import (
    AlertGroup,
    AlertMatcher,
    GettableAlert,
)
from alertmanager_mcp_server.models.silence import PostableSilence
from alertmanager_mcp_server.utils import (
    all_matchers_match,
    compute_silence_window,
    derive_matchers_from_labels,
    matches_alert,
)
from alertmanager_mcp_server.utils.audit import (
    add_audit_entry,
    clear_audit_log,
    get_audit_entries,
)


class TestModelsAndAudit:
    def test_postable_silence_serializes_rfc3339_utc_with_optional_id(self) -> None:
        start = datetime(2026, 3, 29, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        ps = PostableSilence(
            id="sil-123",
            matchers=[AlertMatcher(name="service", value="checkout")],
            startsAt=start,
            endsAt=end,
            createdBy="sre@example.com",
            comment="CHG-101: test",
        )
        payload = ps.to_api_payload()
        assert payload["id"] == "sil-123"
        assert payload["startsAt"] == "2026-03-29T10:00:00Z"
        assert payload["endsAt"] == "2026-03-29T12:00:00Z"

    def test_alert_and_group_receiver_properties(self) -> None:
        alert = GettableAlert(
            fingerprint="fp1",
            labels={"alertname": "Test"},
            startsAt=datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc),
            receivers=[{"name": "slack-sre"}, "pagerduty"],
        )
        assert alert.receiver_names == ["slack-sre", "pagerduty"]

        grp = AlertGroup(
            labels={"alertname": "Test"},
            receiver={"name": "slack-sre"},
            alerts=[alert],
        )
        assert grp.receiver_name == "slack-sre"

    def test_audit_log_jsonl_file_sink(self, tmp_path: Path) -> None:
        sink = tmp_path / "audit.jsonl"
        add_audit_entry(
            backend_id="test-am",
            operation="create_silence",
            principal="sre@example.com",
            summary="id=sil-1",
            outcome="succeeded",
            details={"silence_id": "sil-1"},
            audit_log_path=str(sink),
        )
        entries = get_audit_entries()
        assert len(entries) == 1
        assert sink.exists()
        lines = sink.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"operation":"create_silence"' in lines[0]

        # Clear in-memory log and verify disk JSONL is still loaded by get_audit_entries
        clear_audit_log()
        reloaded = get_audit_entries(audit_log_path=str(sink))
        assert len(reloaded) == 1
        assert reloaded[0].operation == "create_silence"
        assert reloaded[0].principal == "sre@example.com"

    def test_utils_helpers(self) -> None:
        m = AlertMatcher(name="service", value="api|web", isRegex=True, isEqual=True)
        assert matches_alert({"service": "api"}, m) is True
        assert all_matchers_match({"service": "web"}, [m]) is True

        derived = derive_matchers_from_labels(
            {"alertname": "HighCPU", "service": "api", "env": "prod", "instance": "i-1"}
        )
        assert [d.name for d in derived] == ["alertname", "service", "env"]

        now = datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc)
        s, e = compute_silence_window(60, None, None, now=now)
        assert (e - s).total_seconds() == 3600
