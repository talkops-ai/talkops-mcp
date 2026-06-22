"""Cursor-based pagination utilities."""

import base64
import binascii
from typing import List, Optional, Tuple, TypeVar

T = TypeVar("T")


def paginate(
    items: List[T],
    page_size: int = 50,
    cursor: Optional[str] = None,
) -> Tuple[List[T], Optional[str]]:
    """Apply cursor-based pagination to a list of items.

    The cursor is a base64-encoded integer offset. This provides a simple,
    deterministic pagination scheme suitable for in-memory lists.

    Args:
        items: Full list of items to paginate.
        page_size: Maximum items per page (default 50, max 200).
        cursor: Opaque cursor from a previous response (or None for first page).

    Returns:
        Tuple of (page_items, next_cursor). next_cursor is None if this
        is the last page.
    """
    # Clamp page_size to reasonable bounds
    page_size = max(1, min(page_size, 200))

    # Decode cursor to offset
    offset = 0
    if cursor:
        try:
            offset = int(base64.b64decode(cursor).decode("utf-8"))
        except (ValueError, binascii.Error):
            offset = 0

    # Clamp offset
    offset = max(0, min(offset, len(items)))

    # Extract page
    page_items = items[offset : offset + page_size]

    # Compute next cursor
    next_offset = offset + page_size
    next_cursor: Optional[str] = None
    if next_offset < len(items):
        next_cursor = base64.b64encode(
            str(next_offset).encode("utf-8")
        ).decode("utf-8")

    return page_items, next_cursor


def encode_cursor(offset: int) -> str:
    """Encode an integer offset as a cursor string.

    Args:
        offset: Integer offset to encode.

    Returns:
        Base64-encoded cursor string.
    """
    return base64.b64encode(str(offset).encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str) -> int:
    """Decode a cursor string to an integer offset.

    Args:
        cursor: Base64-encoded cursor string.

    Returns:
        Integer offset, or 0 if invalid.
    """
    try:
        return int(base64.b64decode(cursor).decode("utf-8"))
    except (ValueError, binascii.Error):
        return 0
