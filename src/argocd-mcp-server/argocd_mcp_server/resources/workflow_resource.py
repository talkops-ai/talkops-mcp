"""Static workflow documentation resource."""

from pathlib import Path
from argocd_mcp_server.resources.base import BaseResource


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


class WorkflowResource(BaseResource):
    """Workflow documentation resources."""
    
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP."""
        
        @mcp_instance.resource(
            "argocd://workflow-architecture",
            name="argocd_workflow_architecture",
            description="Complete ArgoCD MCP Server Workflow Architecture and Guidelines",
            mime_type="text/markdown"
        )
        async def argocd_workflow_architecture() -> str:
            """Provides the ArgoCD MCP Server Workflow Architecture.
            
            This resource contains comprehensive documentation on:
            - The 3-Layer Architecture (Tools, Prompts, Resources)
            - Detailed capabilities of all 18 Tools
            - Workflows for the 3 Prompts
            - Description of the 5 Real-time Resources
            - Architectural Diagram
            
            Use this resource to understand how to orchestrate the server capabilities.
            
            Returns:
                Workflow Architecture documentation as markdown
            """
            return _load_static_file('ARGOCD_WORKFLOW.md')
