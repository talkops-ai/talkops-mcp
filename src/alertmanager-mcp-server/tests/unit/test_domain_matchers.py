"""Unit tests for `alertmanager_mcp_server.domain.matchers`."""

from __future__ import annotations

import pytest

from alertmanager_mcp_server.domain.matchers import (
    CompiledMatcher,
    MatcherValidationError,
    format_filter_param,
    match_all,
    parse_matcher,
    parse_matcher_set,
    parse_route_matchers,
    split_matcher_expressions,
)


class TestMatcherParsing:
    @pytest.mark.parametrize(
        "expr,expected",
        [
            ('env="prod"', ("env", "prod", False, True)),
            ('env!="dev"', ("env", "dev", False, False)),
            ('service=~"api|web"', ("service", "api|web", True, True)),
            ('instance!~"canary-.*"', ("instance", "canary-.*", True, False)),
            ("env=prod", ("env", "prod", False, True)),
            ('{env="prod"}', ("env", "prod", False, True)),
        ],
    )
    def test_parse_single_matcher(self, expr: str, expected: tuple) -> None:
        m = parse_matcher(expr)
        assert (m.name, m.value, m.is_regex, m.is_equal) == expected

    def test_parse_braced_matcher_set_with_commas_in_quotes(self) -> None:
        expr = '{env="prod", service=~"api,v2|web", instance!="db:5432"}'
        tokens = split_matcher_expressions(expr)
        assert len(tokens) == 3
        compiled = parse_matcher_set(expr)
        assert len(compiled) == 3
        assert compiled[1].name == "service"
        assert compiled[1].value == "api,v2|web"
        assert compiled[1].is_regex is True
        assert compiled[2].is_equal is False

    def test_parse_matcher_set_from_dict_and_list(self) -> None:
        from_dict = parse_matcher_set({"env": "prod", "service": "=~checkout|cart"})
        assert len(from_dict) == 2
        assert from_dict[0] == CompiledMatcher("env", "prod", False, True)
        assert from_dict[1] == CompiledMatcher("service", "checkout|cart", True, True)

        from_list = parse_matcher_set(
            [
                {"name": "alertname", "value": "HighCPU", "isRegex": False, "isEqual": True},
                'cluster!="staging"',
            ]
        )
        assert len(from_list) == 2
        assert from_list[1].operator == "!="

    def test_parse_route_matchers_combines_match_match_re_and_matchers(self) -> None:
        route_block = {
            "match": {"env": "prod"},
            "match_re": {"service": "api|web"},
            "matchers": ['{severity!="info", region=~"us-.*"}'],
        }
        compiled = parse_route_matchers(route_block)
        assert len(compiled) == 4
        assert match_all(
            compiled,
            {"env": "prod", "service": "api", "severity": "critical", "region": "us-east-1"},
        )
        assert not match_all(
            compiled,
            {"env": "prod", "service": "api", "severity": "info", "region": "us-east-1"},
        )


class TestMatcherEvaluationAndValidation:
    def test_missing_label_evaluates_against_empty_string(self) -> None:
        # In Alertmanager, missing label has value ""
        m_not_dev = parse_matcher('env!="dev"')
        assert m_not_dev.matches({}) is True
        assert m_not_dev.matches_empty() is True

        m_empty_eq = parse_matcher('env=""')
        assert m_empty_eq.matches({}) is True
        assert m_empty_eq.matches_empty() is True

        m_wildcard = parse_matcher('alertname=~".*"')
        assert m_wildcard.matches({}) is True
        assert m_wildcard.matches_empty() is True
        assert m_wildcard.is_wildcard_regex() is True

        m_specific = parse_matcher('alertname="HighLatency"')
        assert m_specific.matches({}) is False
        assert m_specific.matches_empty() is False

    def test_anchored_full_string_regex_matching(self) -> None:
        m = parse_matcher('service=~"api"')
        assert m.matches({"service": "api"}) is True
        # Partial match must NOT succeed because Alertmanager anchors regexes
        assert m.matches({"service": "api-v2"}) is False
        assert m.matches({"service": "my-api"}) is False

    @pytest.mark.parametrize(
        "bad_expr",
        [
            '123bad="val"',
            'service=~"(?=lookahead)api"',
            'service=~"(?!neg)api"',
            'service=~"(?<=behind)api"',
            r'service=~"(api)\1"',
            'service=~"[unclosed"',
            '{env="unterminated}',
        ],
    )
    def test_rejects_invalid_syntax_and_non_re2_regex(self, bad_expr: str) -> None:
        with pytest.raises(MatcherValidationError):
            parse_matcher_set(bad_expr)

    def test_filter_string_escaping_roundtrip(self) -> None:
        formatted = format_filter_param("summary", 'disk "root" \\ full', "=")
        assert formatted == r'summary="disk \"root\" \\ full"'
        reparsed = parse_matcher(formatted)
        assert reparsed.value == 'disk "root" \\ full'
