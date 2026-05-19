"""Static documentation resources."""

from pathlib import Path
from prometheus_mcp_server.resources.base import BaseResource


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
            "prom://best-practices",
            name="prom_best_practices",
            description="Prometheus best practices for monitoring, querying, and FinOps",
            mime_type="text/markdown"
        )
        async def prom_best_practices() -> str:
            return _load_static_file('PROMETHEUS_BEST_PRACTICES.md')

        @mcp_instance.resource(
            "prom://onboarding-guide",
            name="prom_onboarding_guide",
            description="Step-by-step guide for onboarding applications to Prometheus monitoring",
            mime_type="text/markdown"
        )
        async def prom_onboarding_guide() -> str:
            return _load_static_file('PROMETHEUS_ONBOARDING_GUIDE.md')
