"""Unit tests for pagination utilities."""

import pytest

from loki_mcp_server.utils.pagination import (
    decode_cursor,
    encode_cursor,
    paginate,
)


class TestCursorEncoding:
    def test_encode_decode_roundtrip(self):
        for offset in [0, 10, 100, 999]:
            cursor = encode_cursor(offset)
            assert decode_cursor(cursor) == offset

    def test_decode_none(self):
        assert decode_cursor(None) == 0

    def test_decode_invalid(self):
        assert decode_cursor("invalid-cursor") == 0

    def test_decode_empty(self):
        assert decode_cursor("") == 0


class TestPaginate:
    def test_first_page(self):
        items = list(range(100))
        page, next_cursor, total = paginate(items, page_size=10)
        assert len(page) == 10
        assert page == list(range(10))
        assert next_cursor is not None
        assert total == 100

    def test_last_page(self):
        items = list(range(25))
        cursor = encode_cursor(20)
        page, next_cursor, total = paginate(items, page_size=10, cursor=cursor)
        assert len(page) == 5
        assert page == list(range(20, 25))
        assert next_cursor is None

    def test_empty_list(self):
        page, next_cursor, total = paginate([], page_size=10)
        assert page == []
        assert next_cursor is None
        assert total == 0

    def test_exact_page_size(self):
        items = list(range(10))
        page, next_cursor, total = paginate(items, page_size=10)
        assert len(page) == 10
        assert next_cursor is None

    def test_cursor_continuation(self):
        items = list(range(30))
        page1, cursor1, _ = paginate(items, page_size=10)
        page2, cursor2, _ = paginate(items, page_size=10, cursor=cursor1)
        page3, cursor3, _ = paginate(items, page_size=10, cursor=cursor2)
        assert page1 == list(range(0, 10))
        assert page2 == list(range(10, 20))
        assert page3 == list(range(20, 30))
        assert cursor3 is None
