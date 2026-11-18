"""Unit tests for `alertmanager_mcp_server.domain.silence_policy` (`SP001`–`SP010`)."""

from __future__ import annotations

from datetime import datetime, timezone

from alertmanager_mcp_server.domain.silence_policy import SilencePolicy

_REF_NOW = datetime(2026, 3, 29, 10, 0, 0, tzinfo=timezone.utc)


class TestSilencePolicyRules:
    def test_valid_scoped_silence_passes_all_rules(self) -> None:
        policy = SilencePolicy(max_duration_minutes=1440, confirm_threshold=50)
        res = policy.evaluate(
            matchers=['alertname="HighLatency"', 'service="checkout"', 'env="prod"'],
            duration_minutes=120,
            created_by="sre@example.com",
            comment="CHG-1042: Planned DB index rebuild",
            matched_alert_count=5,
            matched_critical_count=1,
            now=_REF_NOW,
        )
        assert res.valid is True
        assert res.requires_confirmation is False
        assert res.violations == []
        assert res.warnings == []
        assert res.starts_at_utc == "2026-03-29T10:00:00Z"
        assert res.ends_at_utc == "2026-03-29T12:00:00Z"

    def test_sp001_rejects_empty_matchers_or_invalid_regex(self) -> None:
        policy = SilencePolicy()
        res_empty = policy.evaluate(
            matchers=[],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res_empty.valid is False
        assert any(v.rule_id == "SP001" for v in res_empty.violations)

        res_bad_re = policy.evaluate(
            matchers=['service=~"(?=lookahead)api"'],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res_bad_re.valid is False
        assert any(v.rule_id == "SP001" for v in res_bad_re.violations)

    def test_sp002_and_sp003_reject_wildcard_and_negative_only_matchers(self) -> None:
        policy = SilencePolicy()
        # Wildcard regex `.*` fails both SP003 (wildcard) and SP002 (matches empty string)
        res_wc = policy.evaluate(
            matchers=[{"name": "alertname", "value": ".*", "isRegex": True, "isEqual": True}],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res_wc.valid is False
        rule_ids = {v.rule_id for v in res_wc.violations}
        assert "SP002" in rule_ids
        assert "SP003" in rule_ids

        # Negative-only matcher matches empty string -> fails SP002
        res_neg = policy.evaluate(
            matchers=['env!="dev"'],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res_neg.valid is False
        assert any(v.rule_id == "SP002" for v in res_neg.violations)

    def test_sp004_rejects_sole_broad_labels(self) -> None:
        policy = SilencePolicy()
        res = policy.evaluate(
            matchers=['env="prod"', 'severity="critical"'],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res.valid is False
        assert any(v.rule_id == "SP004" for v in res.violations)

    def test_sp005_rejects_watchdog_heartbeat_silence(self) -> None:
        policy = SilencePolicy()
        res = policy.evaluate(
            matchers=['alertname="Watchdog"', 'service="monitoring"'],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res.valid is False
        assert any(v.rule_id == "SP005" for v in res.violations)

    def test_sp006_and_sp007_enforce_rfc3339_offset_and_duration_cap(self) -> None:
        policy = SilencePolicy(max_duration_minutes=1440)
        # Naive timestamp without 'Z' or offset -> SP006
        res_naive = policy.evaluate(
            matchers=['alertname="HighCPU"', 'service="api"'],
            starts_at="2026-03-29T10:00:00",
            ends_at="2026-03-29T12:00:00",
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res_naive.valid is False
        assert any(v.rule_id == "SP006" for v in res_naive.violations)

        # Explicit ends_at 30 days in future -> SP007 (fixes P9!)
        res_long = policy.evaluate(
            matchers=['alertname="HighCPU"', 'service="api"'],
            starts_at="2026-03-29T10:00:00Z",
            ends_at="2026-04-28T10:00:00Z",
            created_by="sre@example.com",
            comment="CHG-1: test",
            now=_REF_NOW,
        )
        assert res_long.valid is False
        assert any(v.rule_id == "SP007" for v in res_long.violations)

    def test_sp008_and_sp009_enforce_author_and_comment(self) -> None:
        policy = SilencePolicy(comment_pattern=r"^CHG-\d+:")
        res = policy.evaluate(
            matchers=['alertname="HighCPU"', 'service="api"'],
            duration_minutes=60,
            created_by="mcp",
            comment="no ticket prefix",
            now=_REF_NOW,
        )
        assert res.valid is False
        rule_ids = {v.rule_id for v in res.violations}
        assert "SP008" in rule_ids
        assert "SP009" in rule_ids

    def test_sp010_flags_high_blast_radius_and_unscoped_critical(self) -> None:
        policy = SilencePolicy(confirm_threshold=50)
        res = policy.evaluate(
            matchers=['service="checkout"'],
            duration_minutes=60,
            created_by="sre@example.com",
            comment="CHG-100: maintenance",
            matched_alert_count=55,
            matched_critical_count=2,
            now=_REF_NOW,
        )
        assert res.valid is True
        assert res.requires_confirmation is True
        assert len(res.confirmation_reasons) == 2
        assert any(w.rule_id == "SP010" for w in res.warnings)
