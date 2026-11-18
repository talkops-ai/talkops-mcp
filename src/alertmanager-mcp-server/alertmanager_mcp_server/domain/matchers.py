"""Alertmanager matcher grammar parser, RE2-compatible compiler, and evaluator.

Implements Alertmanager / Prometheus label matching semantics (`pkg/labels`):
- Operators: `=`, `!=`, `=~`, `!~`
- Missing labels evaluate against the empty string `""`
- Regular expressions are implicitly anchored across the full value (`^(?:pattern)$`)
- Rejects PCRE-only constructs unsupported by Go RE2 (lookaround, backreferences)
- Parses single matcher expressions (`env="prod"`), braced matcher sets
  (`{env="prod", service=~"api|web"}`), API matcher dicts, and legacy route
  `match` / `match_re` blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

MatcherOperator = Literal["=", "!=", "=~", "!~"]

LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Reject PCRE-only constructs that Go's RE2 engine in Alertmanager rejects:
# lookahead (?=...), (?!...), lookbehind (?<=...), (?<!...), backreferences \1..\9,
# conditional patterns (?(...)), atomic groups (?>...).
_UNSUPPORTED_RE2_CONSTRUCTS = re.compile(
    r"\(\?(?:=|!|<=|<!|>|\()|\\[1-9]"
)

_SINGLE_MATCHER_RE = re.compile(
    r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*(.*?)\s*$',
    re.DOTALL,
)


class MatcherValidationError(ValueError):
    """Raised when a matcher expression or regex is syntactically invalid."""


def validate_re2_regex(pattern: str) -> re.Pattern[str]:
    """Validate that a regex is compatible with Go RE2 and compile it anchored."""
    if _UNSUPPORTED_RE2_CONSTRUCTS.search(pattern):
        raise MatcherValidationError(
            f"Regex '{pattern}' uses PCRE constructs (lookaround or backreferences) "
            "that are unsupported by Alertmanager's Go RE2 engine."
        )
    try:
        return re.compile(f"^(?:{pattern})$", re.DOTALL)
    except re.error as exc:
        raise MatcherValidationError(
            f"Invalid regular expression '{pattern}': {exc}"
        ) from exc


def escape_filter_value(value: str) -> str:
    """Escape backslashes and double quotes for Alertmanager filter strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def unescape_filter_value(raw: str) -> str:
    """Unescape a quoted or unquoted matcher value from a filter string."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        inner = text[1:-1]
        out: list[str] = []
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                if nxt == "n":
                    out.append("\n")
                elif nxt == "t":
                    out.append("\t")
                elif nxt in ('"', "\\"):
                    out.append(nxt)
                else:
                    # Preserve regex escapes like \d, \w, \.
                    out.append("\\" + nxt)
                i += 2
            else:
                out.append(ch)
                i += 1
        return "".join(out)
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


def format_filter_param(
    name: str,
    value: str,
    operator: MatcherOperator = "=",
) -> str:
    """Format a single Alertmanager API `filter` query parameter cleanly."""
    if not LABEL_NAME_RE.match(name):
        raise MatcherValidationError(
            f"Invalid Alertmanager label name '{name}'. Must match [a-zA-Z_][a-zA-Z0-9_]*."
        )
    if operator not in ("=", "!=", "=~", "!~"):
        raise MatcherValidationError(f"Unsupported matcher operator '{operator}'.")
    if operator in ("=~", "!~"):
        validate_re2_regex(value)
    return f'{name}{operator}"{escape_filter_value(value)}"'


@dataclass(frozen=True)
class CompiledMatcher:
    """Immutable, pre-compiled Alertmanager label matcher."""

    name: str
    value: str
    is_regex: bool = False
    is_equal: bool = True
    _compiled_re: re.Pattern[str] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not LABEL_NAME_RE.match(self.name):
            raise MatcherValidationError(
                f"Invalid label name '{self.name}'. Label names must match "
                "^[a-zA-Z_][a-zA-Z0-9_]*$."
            )
        if self.is_regex:
            compiled = validate_re2_regex(self.value)
            object.__setattr__(self, "_compiled_re", compiled)

    @property
    def operator(self) -> MatcherOperator:
        if self.is_regex:
            return "=~" if self.is_equal else "!~"
        return "=" if self.is_equal else "!="

    def matches_value(self, candidate: str) -> bool:
        """Evaluate this matcher against a single label value (or '' if absent)."""
        if self.is_regex:
            assert self._compiled_re is not None
            matched = bool(self._compiled_re.match(candidate))
            return matched if self.is_equal else not matched
        matched = candidate == self.value
        return matched if self.is_equal else not matched

    def matches(self, labels: Mapping[str, str]) -> bool:
        """Evaluate this matcher against an alert's label set.

        Follows Alertmanager `pkg/labels`: missing labels are treated as `""`.
        """
        candidate = str(labels.get(self.name, ""))
        return self.matches_value(candidate)

    def matches_empty(self) -> bool:
        """Return True if this matcher matches an empty label value (`""`)."""
        return self.matches_value("")

    def is_wildcard_regex(self) -> bool:
        """Return True if this matcher is a positive regex matching any value (e.g. `.*`, `.+`)."""
        if not self.is_regex or not self.is_equal:
            return False
        stripped = self.value.strip()
        return stripped in (".*", ".+", "^.*$", "^.+$", "(.*)", "(.+)")

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize to Alertmanager v2 OpenAPI `Matcher` object."""
        return {
            "name": self.name,
            "value": self.value,
            "isRegex": self.is_regex,
            "isEqual": self.is_equal,
        }

    def to_filter_string(self) -> str:
        """Serialize to canonical Alertmanager matcher syntax (`name="value"`)."""
        return format_filter_param(self.name, self.value, self.operator)


def split_matcher_expressions(text: str) -> list[str]:
    """Split a braced or comma-separated matcher expression string safely.

    Respects double-quoted and single-quoted substrings and backslash escapes so
    commas inside regexes (`service=~"api,v2"`) are not split.
    """
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    if not s:
        return []

    parts: list[str] = []
    buf: list[str] = []
    in_quote: str | None = None
    escaped = False

    for ch in s:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            buf.append(ch)
            escaped = True
            continue
        if in_quote is not None:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ('"', "'"):
            in_quote = ch
            buf.append(ch)
            continue
        if ch == ",":
            token = "".join(buf).strip()
            if token:
                parts.append(token)
            buf = []
            continue
        buf.append(ch)

    if in_quote is not None:
        raise MatcherValidationError(
            f"Unterminated quote in matcher expression '{text}'."
        )

    trailing = "".join(buf).strip()
    if trailing:
        parts.append(trailing)
    return parts


def parse_matcher(item: Any) -> CompiledMatcher:
    """Parse a single matcher from a string, dict, or Pydantic Matcher model."""
    if isinstance(item, CompiledMatcher):
        return item

    # Support Pydantic Matcher model or similar object with attributes
    if hasattr(item, "model_dump"):
        item = getattr(item, "model_dump")(by_alias=True)

    if isinstance(item, Mapping):
        name = str(item.get("name", "")).strip()
        if not name:
            raise MatcherValidationError("Matcher object is missing 'name'.")
        if "value" not in item or item.get("value") is None:
            raise MatcherValidationError(f"Matcher '{name}' is missing 'value'.")
        value = str(item["value"])
        is_regex = bool(item.get("isRegex", item.get("is_regex", False)))
        is_equal_raw = item.get("isEqual", item.get("is_equal", True))
        is_equal = True if is_equal_raw is None else bool(is_equal_raw)
        return CompiledMatcher(
            name=name,
            value=value,
            is_regex=is_regex,
            is_equal=is_equal,
        )

    if isinstance(item, str):
        raw = item.strip()
        if raw.startswith("{") and raw.endswith("}"):
            inner = split_matcher_expressions(raw)
            if len(inner) != 1:
                raise MatcherValidationError(
                    f"Expected a single matcher, got {len(inner)} in '{item}'."
                )
            raw = inner[0]

        m = _SINGLE_MATCHER_RE.match(raw)
        if not m:
            raise MatcherValidationError(
                f"Invalid matcher syntax '{item}'. Expected format like "
                'env="prod", service=~"api|web", or instance!="localhost:9090".'
            )
        name, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
        # If unquoted, ensure there are no stray unescaped quotes or spaces
        if not (
            (len(raw_val) >= 2 and raw_val[0] == '"' and raw_val[-1] == '"')
            or (len(raw_val) >= 2 and raw_val[0] == "'" and raw_val[-1] == "'")
        ):
            if any(c in raw_val for c in ('"', "'", "{", "}", ",")):
                raise MatcherValidationError(
                    f"Invalid unquoted matcher value '{raw_val}' in '{item}'."
                )
        value = unescape_filter_value(raw_val)
        is_regex = op in ("=~", "!~")
        is_equal = op in ("=", "=~")
        return CompiledMatcher(
            name=name,
            value=value,
            is_regex=is_regex,
            is_equal=is_equal,
        )

    raise MatcherValidationError(
        f"Unsupported matcher representation of type {type(item).__name__}."
    )


def parse_matcher_set(
    source: str | Sequence[Any] | Mapping[str, Any] | None,
) -> list[CompiledMatcher]:
    """Parse any matcher input (string, braced set, list of strings/dicts, or label dict)."""
    if source is None:
        return []

    if isinstance(source, str):
        tokens = split_matcher_expressions(source)
        return [parse_matcher(tok) for tok in tokens]

    if isinstance(source, Mapping):
        # Could be a single API matcher dict {"name": ..., "value": ...}
        if "name" in source and "value" in source and len(source) <= 4:
            maybe_keys = set(source.keys())
            if maybe_keys.issubset({"name", "value", "isRegex", "is_regex", "isEqual", "is_equal"}):
                return [parse_matcher(source)]
        # Otherwise treat as exact-match label dictionary {"env": "prod", "severity": "critical"}
        result: list[CompiledMatcher] = []
        for k, v in source.items():
            key_str = str(k).strip()
            val_str = str(v)
            # Also support operator embedded in value or key if someone passed {"service": "=~web.*"}
            if val_str.startswith(("=~", "!~", "!=")):
                op = val_str[:2]
                actual = unescape_filter_value(val_str[2:].strip())
                result.append(
                    CompiledMatcher(
                        name=key_str,
                        value=actual,
                        is_regex=op in ("=~", "!~"),
                        is_equal=op in ("=", "=~"),
                    )
                )
            else:
                result.append(
                    CompiledMatcher(name=key_str, value=val_str, is_regex=False, is_equal=True)
                )
        return result

    if isinstance(source, Sequence):
        compiled: list[CompiledMatcher] = []
        for entry in source:
            if isinstance(entry, str) and (
                entry.strip().startswith("{") or "," in entry
            ):
                for tok in split_matcher_expressions(entry):
                    compiled.append(parse_matcher(tok))
            else:
                compiled.append(parse_matcher(entry))
        return compiled

    raise MatcherValidationError(
        f"Cannot parse matcher set from type {type(source).__name__}."
    )


def parse_route_matchers(
    block: Mapping[str, Any],
    *,
    match_key: str = "match",
    match_re_key: str = "match_re",
    matchers_key: str = "matchers",
) -> list[CompiledMatcher]:
    """Extract and compile all matchers from an Alertmanager route or inhibit rule block.

    Supports simultaneously:
    - `match`: `dict[str, str]` (deprecated exact matchers)
    - `match_re`: `dict[str, str]` (deprecated regex matchers)
    - `matchers`: `list[str]` (modern matcher expressions, including `{a="b", c=~"d"}`)
    """
    compiled: list[CompiledMatcher] = []

    raw_match = block.get(match_key)
    if isinstance(raw_match, Mapping):
        for k, v in raw_match.items():
            compiled.append(
                CompiledMatcher(
                    name=str(k),
                    value=str(v),
                    is_regex=False,
                    is_equal=True,
                )
            )

    raw_match_re = block.get(match_re_key)
    if isinstance(raw_match_re, Mapping):
        for k, v in raw_match_re.items():
            compiled.append(
                CompiledMatcher(
                    name=str(k),
                    value=str(v),
                    is_regex=True,
                    is_equal=True,
                )
            )

    raw_matchers = block.get(matchers_key)
    if isinstance(raw_matchers, Sequence) and not isinstance(raw_matchers, (str, bytes)):
        for expr in raw_matchers:
            if isinstance(expr, str):
                for tok in split_matcher_expressions(expr):
                    compiled.append(parse_matcher(tok))
            elif isinstance(expr, Mapping):
                compiled.append(parse_matcher(expr))

    return compiled


def match_all(
    matchers: Sequence[CompiledMatcher],
    labels: Mapping[str, str],
) -> bool:
    """Return True if every matcher in `matchers` matches `labels`."""
    return all(m.matches(labels) for m in matchers)
