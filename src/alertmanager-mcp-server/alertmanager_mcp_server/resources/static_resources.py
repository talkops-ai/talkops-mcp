"""Static documentation resources."""
from pathlib import Path
from alertmanager_mcp_server.resources.base import BaseResource


def _load_static(filename: str) -> str:
    path = Path(__file__).parent.parent / 'static' / filename
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return f"# {filename}\n\nContent not found."


class StaticResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://best-practices", name="am_best_practices",
                               description="Alerting best practices", mime_type="text/markdown")
        async def best_practices() -> str:
            return _load_static('ALERTMANAGER_BEST_PRACTICES.md')

        @mcp_instance.resource("am://onboarding-guide", name="am_onboarding_guide",
                               description="Alert onboarding guide", mime_type="text/markdown")
        async def onboarding_guide() -> str:
            return _load_static('ALERTMANAGER_ONBOARDING_GUIDE.md')
