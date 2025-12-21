"""Static documentation resources."""

from pathlib import Path
from helm_mcp_server.resources.base import BaseResource


def _load_static_file(filename: str) -> str:
    """Load content from static directory.
    
    Args:
        filename: Name of the file in the static directory
    
    Returns:
        File content as string
    """
    static_dir = Path(__file__).parent.parent / 'static'
    file_path = static_dir / filename
    
    try:
        return file_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return f"# {filename}\n\nContent not found."


class StaticResources(BaseResource):
    """Static documentation resources including best practices."""
    
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP."""
        
        @mcp_instance.resource(
            "helm://best_practices",
            name="helm_best_practices",
            description="Helm Best Practices from the official Helm documentation",
            mime_type="text/markdown"
        )
        async def helm_best_practices() -> str:
            """Provides Helm Best Practices guidance.
            
            This resource contains comprehensive best practices for:
            - Chart development and structure
            - Values files and configuration
            - Templates and helpers
            - Dependencies management
            - Security considerations
            - Release management
            
            Returns:
                Helm Best Practices documentation as markdown
            """
            return _load_static_file('HELM_BEST_PRACTICES.md')


