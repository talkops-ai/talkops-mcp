"""Test cursor-based pagination utilities."""

from opentelemetry_mcp_server.utils.pagination import (
    decode_cursor,
    encode_cursor,
    paginate,
)


class TestPagination:
    """Test cursor-based pagination."""

    def test_first_page(self) -> None:
        items = list(range(100))
        page, cursor = paginate(items, page_size=10)
        assert len(page) == 10
        assert page == list(range(10))
        assert cursor is not None

    def test_second_page(self) -> None:
        items = list(range(100))
        _, first_cursor = paginate(items, page_size=10)
        page, cursor = paginate(items, page_size=10, cursor=first_cursor)
        assert len(page) == 10
        assert page == list(range(10, 20))

    def test_last_page(self) -> None:
        items = list(range(5))
        page, cursor = paginate(items, page_size=10)
        assert len(page) == 5
        assert cursor is None

    def test_invalid_cursor(self) -> None:
        items = list(range(10))
        page, cursor = paginate(items, page_size=5, cursor="invalid")
        assert len(page) == 5  # Falls back to offset 0

    def test_encode_decode_cursor(self) -> None:
        encoded = encode_cursor(42)
        assert decode_cursor(encoded) == 42

    def test_clamp_page_size(self) -> None:
        items = list(range(10))
        page, _ = paginate(items, page_size=500)  # Clamped to 200
        assert len(page) == 10  # Only 10 items total
