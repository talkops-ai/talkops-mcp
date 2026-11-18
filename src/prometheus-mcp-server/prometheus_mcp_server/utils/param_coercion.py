"""JSON-string coercion validators for MCP tool Dict/List parameters.

Some MCP client bridges (including lazy `call_mcp_tool` adapters) serialize nested
JSON objects and arrays as JSON strings (`str`) when forwarding tool arguments over
stdio/HTTP. Applying `BeforeValidator` lets FastMCP/Pydantic accept both native
dicts/lists and JSON-encoded strings transparently while preserving clean JSON Schema
types (`object` / `array`).
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Dict, List

from pydantic import BeforeValidator


def coerce_json_value(val: Any) -> Any:
    """Recursively parse JSON-encoded dict/list strings into Python dicts/lists."""
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith("{") and s.endswith("}")) or (
            s.startswith("[") and s.endswith("]")
        ):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, (dict, list)):
                    return coerce_json_value(parsed)
            except Exception:
                return val
        return val
    if isinstance(val, dict):
        cleaned: Dict[Any, Any] = {}
        for k, v in val.items():
            # Strip accidental outer quotes around keys like '"app.kubernetes.io/name"'
            ck = k[1:-1] if isinstance(k, str) and len(k) >= 2 and k[0] == '"' and k[-1] == '"' else k
            cleaned[ck] = coerce_json_value(v)
        return cleaned
    if isinstance(val, list):
        return [coerce_json_value(item) for item in val]
    return val


JsonDict = Annotated[Dict[str, Any], BeforeValidator(coerce_json_value)]
JsonStrDict = Annotated[Dict[str, str], BeforeValidator(coerce_json_value)]
JsonDictList = Annotated[List[Dict[str, Any]], BeforeValidator(coerce_json_value)]
JsonStrList = Annotated[List[str], BeforeValidator(coerce_json_value)]
