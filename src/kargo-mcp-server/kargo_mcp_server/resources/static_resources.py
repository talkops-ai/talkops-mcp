"""Static documentation resources."""

from pathlib import Path
from kargo_mcp_server.resources.base import BaseResource


def _load_static_file(filename: str) -> str:
    static_dir = Path(__file__).parent.parent / 'static'
    file_path = static_dir / filename
    try:
        return file_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return f"# {filename}\n\nContent not found."


class StaticResources(BaseResource):
    """Static documentation resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://best-practices",
            name="kargo_best_practices",
            description="Kargo best practices for promotion pipelines",
            mime_type="text/markdown"
        )
        async def kargo_best_practices() -> str:
            """Kargo best practices guide."""
            return _load_static_file('KARGO_BEST_PRACTICES.md')

        @mcp_instance.resource(
            "kargo://promotion-steps",
            name="kargo_promotion_steps",
            description="Built-in Kargo promotion step types catalogue",
            mime_type="text/markdown"
        )
        async def kargo_promotion_steps() -> str:
            """Kargo promotion steps catalogue."""
            return _load_static_file('KARGO_PROMOTION_STEPS.md')
