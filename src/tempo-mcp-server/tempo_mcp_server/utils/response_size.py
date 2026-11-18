"""Response size enforcement utility.

Enforces soft size limits on structured MCP tool responses by truncating
arrays while preserving the response structure. Accounts for FastMCP's
wire overhead (~2.2x double-serialization).
"""

from typing import Any, Dict, Optional
import pydantic_core

WIRE_OVERHEAD_FACTOR = 2.2


def enforce_structured_size_limit(
    result: Dict[str, Any],
    *,
    truncatable_key: str,
    max_bytes: int = 40_000,
    serializer: Any = pydantic_core.to_json,
    query_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Enforce a soft size limit on structured responses by truncating an array."""
    if truncatable_key not in result:
        return result

    arr = result[truncatable_key]
    if not isinstance(arr, list) or not arr:
        return result

    try:
        raw_size = len(serializer(result))
        if raw_size <= max_bytes:
            return result
    except Exception:
        return result

    original_arr = arr
    total_count = len(original_arr)
    low = 0
    high = total_count
    best_len = 0

    while low <= high:
        mid = (low + high) // 2

        result[truncatable_key] = original_arr[:mid]
        result["truncated"] = True
        result["truncated_at"] = mid
        result["total_count"] = total_count

        try:
            size = len(serializer(result))
            if size <= max_bytes:
                best_len = mid
                low = mid + 1
            else:
                high = mid - 1
        except Exception:
            break

    result[truncatable_key] = original_arr[:best_len]
    result["truncated"] = True
    result["truncated_at"] = best_len
    result["total_count"] = total_count
    return result
