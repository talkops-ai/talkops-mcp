"""Unit tests for trace ID format validation (H-01).

Covers _validate_trace_id(): valid hex acceptance, non-hex rejection,
boundary lengths (16, 32 chars), and mixed-case tolerance.
"""

import pytest

from tempo_mcp_server.tools.search.search_tools import _validate_trace_id
from tempo_mcp_server.exceptions import TempoValidationError


class TestValidateTraceId:
    """Verify _validate_trace_id() rejects non-hex and out-of-range IDs."""

    # ── Valid IDs ──────────────────────────────────────────────────────────

    def test_accepts_32_char_lowercase(self):
        """Standard 128-bit trace ID, lowercase hex."""
        _validate_trace_id("4bf92f3577b34da6a3ce929d0e0e4736")

    def test_accepts_32_char_uppercase(self):
        """Upper-case hex is valid — Tempo normalises case."""
        _validate_trace_id("4BF92F3577B34DA6A3CE929D0E0E4736")

    def test_accepts_32_char_mixed_case(self):
        _validate_trace_id("4Bf92F3577b34Da6A3ce929d0E0e4736")

    def test_accepts_16_char_minimum(self):
        """64-bit trace IDs (Zipkin B3 short form) are allowed."""
        _validate_trace_id("a3ce929d0e0e4736")

    def test_accepts_24_char_mid_length(self):
        _validate_trace_id("a3ce929d0e0e4736aabbcc00")

    # ── Invalid — wrong characters ─────────────────────────────────────────

    def test_rejects_non_hex_characters(self):
        """Underscores, letters beyond f, and similar are not hex."""
        with pytest.raises(TempoValidationError, match="hexadecimal"):
            _validate_trace_id("this_is_not_hex_")

    def test_rejects_uuid_with_hyphens(self):
        """UUIDs with hyphens are invalid trace IDs."""
        with pytest.raises(TempoValidationError):
            _validate_trace_id("4bf92f35-77b3-4da6-a3ce-929d0e0e4736")

    def test_rejects_g_character(self):
        """'g' is beyond the hex alphabet."""
        with pytest.raises(TempoValidationError):
            _validate_trace_id("gggggggggggggggg")

    def test_rejects_whitespace(self):
        with pytest.raises(TempoValidationError):
            _validate_trace_id("4bf92f3577b34d  ")

    # ── Invalid — wrong length ─────────────────────────────────────────────

    def test_rejects_15_char_too_short(self):
        """Below minimum 16 chars."""
        with pytest.raises(TempoValidationError):
            _validate_trace_id("a3ce929d0e0e473")

    def test_rejects_33_char_too_long(self):
        """Above maximum 32 chars."""
        with pytest.raises(TempoValidationError):
            _validate_trace_id("4bf92f3577b34da6a3ce929d0e0e47360")

    def test_rejects_empty_string(self):
        with pytest.raises(TempoValidationError):
            _validate_trace_id("")

    # ── Boundary precision ─────────────────────────────────────────────────

    def test_exact_16_chars_is_valid(self):
        _validate_trace_id("0" * 16)

    def test_exact_32_chars_is_valid(self):
        _validate_trace_id("f" * 32)

    def test_17_chars_is_valid(self):
        _validate_trace_id("a" * 17)

    def test_31_chars_is_valid(self):
        _validate_trace_id("b" * 31)
