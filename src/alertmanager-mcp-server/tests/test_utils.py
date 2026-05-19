"""Tests for utility functions."""
import pytest
from datetime import datetime, timezone
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.utils import (
    all_matchers_match, compute_silence_window, derive_matchers_from_labels, matches_alert,
)


class TestMatchesAlert:
    def test_exact_match(self):
        assert matches_alert({"alertname": "HighCPU"}, AlertMatcher(name="alertname", value="HighCPU", isRegex=False, isEqual=True)) is True

    def test_exact_no_match(self):
        assert matches_alert({"alertname": "HighCPU"}, AlertMatcher(name="alertname", value="LowCPU", isRegex=False, isEqual=True)) is False

    def test_regex_match(self):
        assert matches_alert({"alertname": "HighCPU"}, AlertMatcher(name="alertname", value="High.*", isRegex=True, isEqual=True)) is True

    def test_negative_match(self):
        assert matches_alert({"alertname": "HighCPU"}, AlertMatcher(name="alertname", value="LowCPU", isRegex=False, isEqual=False)) is True

    def test_missing_label(self):
        assert matches_alert({}, AlertMatcher(name="alertname", value="HighCPU", isRegex=False, isEqual=True)) is False

    def test_all_matchers_match_true(self):
        labels = {"alertname": "HighCPU", "service": "api"}
        matchers = [AlertMatcher(name="alertname", value="HighCPU", isRegex=False, isEqual=True), AlertMatcher(name="service", value="api", isRegex=False, isEqual=True)]
        assert all_matchers_match(labels, matchers) is True

    def test_all_matchers_match_false(self):
        labels = {"alertname": "HighCPU", "service": "db"}
        matchers = [AlertMatcher(name="alertname", value="HighCPU", isRegex=False, isEqual=True), AlertMatcher(name="service", value="api", isRegex=False, isEqual=True)]
        assert all_matchers_match(labels, matchers) is False


class TestComputeSilenceWindow:
    def test_duration_minutes(self):
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        start, end = compute_silence_window(60, None, None, now)
        assert start == now
        assert (end - start).total_seconds() == 3600

    def test_explicit_window(self):
        sa = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        ea = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        start, end = compute_silence_window(None, sa, ea)
        assert start == sa and end == ea

    def test_missing_both_raises(self):
        with pytest.raises(ValueError):
            compute_silence_window(None, None, None)


class TestDeriveMatchers:
    def test_priority_keys(self):
        labels = {"alertname": "HighCPU", "service": "api", "env": "prod", "instance": "host:8080"}
        matchers = derive_matchers_from_labels(labels)
        names = [m.name for m in matchers]
        assert "alertname" in names
        assert "service" in names
        assert "env" in names
        assert "instance" not in names

    def test_fallback_all_labels(self):
        labels = {"custom_key": "custom_val"}
        matchers = derive_matchers_from_labels(labels)
        assert len(matchers) == 1
        assert matchers[0].name == "custom_key"

    def test_empty_labels_raises(self):
        with pytest.raises(ValueError):
            derive_matchers_from_labels({})
