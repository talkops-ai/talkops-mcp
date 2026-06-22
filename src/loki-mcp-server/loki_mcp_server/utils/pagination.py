"""Cursor-based pagination utilities.

Mirrors the OTel reference pattern for consistent pagination
across all TalkOps MCP servers.
"""

import base64
from typing import List, Optional, Tuple, TypeVar

T = TypeVar("T")


def encode_cursor(offset: int) -> str:
    """Encode a numeric offset into an opaque cursor string.

    Args:
        offset: The numeric offset to encode.

    Returns:
        Base64-encoded cursor string.
    """
    return base64.b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: Optional[str]) -> int:
    """Decode an opaque cursor string back to a numeric offset.

    Args:
        cursor: Base64-encoded cursor, or None for the first page.

    Returns:
        Decoded offset integer. Returns 0 for None/invalid cursors.
    """
    if not cursor:
        return 0
    try:
        return int(base64.b64decode(cursor.encode()).decode())
    except (ValueError, Exception):
        return 0


def paginate(
    items: List[T],
    page_size: int = 50,
    cursor: Optional[str] = None,
) -> Tuple[List[T], Optional[str], int]:
    """Paginate a list with cursor-based navigation.

    Args:
        items: Complete list of items to paginate.
        page_size: Number of items per page (default: 50).
        cursor: Opaque cursor for the next page, or None for first page.

    Returns:
        Tuple of (page_items, next_cursor_or_none, total_count).
    """
    total = len(items)
    offset = decode_cursor(cursor)

    # Clamp offset
    offset = max(0, min(offset, total))

    page = items[offset : offset + page_size]

    next_offset = offset + page_size
    next_cursor = encode_cursor(next_offset) if next_offset < total else None

    return page, next_cursor, total
