"""Unit tests for JSON & CLF access log and controller log parser with secret redaction."""

from traefik_mcp_server.services.log_parser import (
    analyze_log_lines,
    parse_access_log_line,
    parse_controller_log_line,
)
from tests.fixtures.sample_logs import SAMPLE_ACCESS_LOG_LINES, SAMPLE_CONTROLLER_LOG_LINES


def test_parse_json_and_clf_access_log_lines_with_redaction():
    rec_json = parse_access_log_line(SAMPLE_ACCESS_LOG_LINES[0])
    assert rec_json is not None
    assert rec_json["status"] == 200
    assert "[REDACTED]" in rec_json["path"]
    assert "topsecret123" not in rec_json["path"]
    assert "jwt-secret-val" not in str(rec_json["raw"])

    rec_clf = parse_access_log_line(SAMPLE_ACCESS_LOG_LINES[3])
    assert rec_clf is not None
    assert rec_clf["status"] == 200
    assert "[REDACTED]" in rec_clf["path"]
    assert "abc999" not in rec_clf["path"]


def test_analyze_access_logs_filters_and_grouping():
    summary = analyze_log_lines(
        SAMPLE_ACCESS_LOG_LINES,
        source="access",
        filters={"status_range": "5xx"},
        group_by="status",
        limit_samples=5,
    )
    assert summary["total_lines_scanned"] == 4
    assert summary["matched_lines"] == 1
    assert summary["groups"] == [{"key": "502", "count": 1}]


def test_parse_and_analyze_controller_logs():
    rec = parse_controller_log_line(SAMPLE_CONTROLLER_LOG_LINES[0])
    assert rec is not None
    assert rec["level"] == "error"

    summary = analyze_log_lines(
        SAMPLE_CONTROLLER_LOG_LINES,
        source="controller",
        filters={"level": "error"},
        group_by="error_code",
    )
    assert summary["matched_lines"] == 1
