"""Response size enforcement utility.

Enforces soft size limits on structured MCP tool responses by truncating
arrays while preserving the response structure. Accounts for FastMCP's
wire overhead: each Dict result gets serialized as both TextContent (JSON
string) and structured_content (dict), roughly doubling the wire payload.
"""

from typing import Any, Dict, Optional
import pydantic_core

# FastMCP serializes tool results twice:
#   1. TextContent (JSON string in content[])
#   2. structured_content (dict for outputSchema validation)
# Plus JSON envelope overhead. Empirically ~2.2x the raw dict size.
WIRE_OVERHEAD_FACTOR = 2.2


def enforce_structured_size_limit(
    result: Dict[str, Any],
    *,
    truncatable_key: str,
    max_bytes: int = 40_000,
    serializer: Any = pydantic_core.to_json,
    query_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Enforce a soft size limit on structured responses by truncating an array.

    This performs a binary search to find the maximum number of elements in the
    truncatable array that fit within the effective byte budget (max_bytes
    adjusted for FastMCP wire overhead).

    Args:
        result: The structured dict to enforce size limit on.
        truncatable_key: Key in the dict containing the list to truncate.
        max_bytes: Maximum size in bytes for the raw dict payload.
        serializer: Function to serialize the dict to bytes.
        query_hint: Optional LogQL query string for generating refinement advice.

    Returns:
        The potentially truncated structured dict with truncation metadata.
    """
    if truncatable_key not in result:
        return result

    arr = result[truncatable_key]
    if not isinstance(arr, list) or not arr:
        return result

    # Check if the whole thing fits
    try:
        raw_size = len(serializer(result))
        if raw_size <= max_bytes:
            return result
    except Exception:
        # If serialization fails, just return it and let MCP/middleware handle it
        return result

    # It's too big, we need to truncate.
    # Binary search for the largest array length that fits within budget.
    # We include ALL metadata fields during measurement so the final
    # serialized result actually fits within max_bytes.
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
        result["_truncation_advice"] = _build_truncation_advice(
            total_count, mid, query_hint
        )

        try:
            size = len(serializer(result))
            if size <= max_bytes:
                best_len = mid
                low = mid + 1
            else:
                high = mid - 1
        except Exception:
            break

    # Apply the best length with final metadata
    result[truncatable_key] = original_arr[:best_len]
    result["truncated"] = True
    result["truncated_at"] = best_len
    result["total_count"] = total_count
    result["_truncation_advice"] = _build_truncation_advice(
        total_count, best_len, query_hint
    )

    return result


def _build_truncation_advice(
    total: int, returned: int, query_hint: Optional[str] = None
) -> str:
    """Build actionable advice for the agent when results are truncated."""
    parts = [
        f"Response truncated: showing {returned} of {total} results.",
        "To get more precise results, refine your LogQL query:",
    ]

    suggestions = [
        "- Add label filters: {app=\"x\", namespace=\"y\"}",
        "- Use line filters: |= \"error\" or |~ \"regex\"",
        "- Narrow the time range with start/end parameters",
        "- Reduce max_log_lines for stream queries",
    ]

    if query_hint and "rate(" in query_hint.lower():
        suggestions.insert(
            0,
            "- Use sum() or topk() to aggregate high-cardinality metric results",
        )

    parts.extend(suggestions)
    return " ".join(parts)
