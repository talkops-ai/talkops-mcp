"""JSON coercion helpers for MCP tool parameters.

When LLM clients send tool arguments over JSON-RPC, complex types (dicts, lists)
sometimes arrive as stringified JSON rather than parsed native objects.  Pydantic
strict validation rejects these, causing confusing errors for the agent.

This module provides lightweight ``BeforeValidator`` functions that transparently
handle both native *and* string-encoded JSON, keeping the tool parameter
declarations clean.

Usage in a tool function signature::

    from typing import Annotated
    from pydantic import BeforeValidator
    from prometheus_mcp_server.utils.json_coerce import coerce_dict, coerce_list

    filter_labels: Annotated[Optional[Dict[str, str]], BeforeValidator(coerce_dict)] = None
    targets:       Annotated[Optional[List[str]],      BeforeValidator(coerce_list)] = None
"""

import json
from typing import Any


def coerce_dict(v: Any) -> Any:
    """Accept a dict *or* a JSON-encoded string and return a dict."""
    if v is None:
        return v
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        raise ValueError(
            f"Expected a JSON object (dict), got string that could not be parsed: {v!r}"
        )
    return v


def coerce_list(v: Any) -> Any:
    """Accept a list *or* a JSON-encoded string and return a list."""
    if v is None:
        return v
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        raise ValueError(
            f"Expected a JSON array (list), got string that could not be parsed: {v!r}"
        )
    return v
