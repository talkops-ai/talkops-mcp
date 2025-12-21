"""Installation-related prompts."""

from mcp.types import Prompt, PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


class InstallationPrompts(BasePrompt):
    """Installation prompts."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        def helm_installation_guidelines() -> Prompt:
            """Helm installation guidelines and best practices.
            
            This prompt provides guidelines for safe Helm chart installation.
            """
            return Prompt(
                name="helm-installation-guidelines",
                description="Best practices for Helm chart installation",
                arguments=[],  # No arguments required
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text="""# Helm Installation Best Practices

## Pre-Installation Checklist
- [ ] Verify cluster connectivity and permissions
- [ ] Review chart documentation and release notes
- [ ] Validate all required configuration values
- [ ] Check resource availability (CPU, memory, storage)
- [ ] Plan for rollback if needed
- [ ] Verify namespace exists or will be created
- [ ] Check for conflicting releases or resources

## Installation Steps
1. **Fetch chart metadata** - Get chart info and schema
2. **Validate configuration** - Check values against schema
3. **Render manifests** - Preview what will be deployed
4. **Dry-run** - Test installation without deploying
5. **Review output** - Check for any warnings or errors
6. **Get approval** - Ensure stakeholder sign-off
7. **Install** - Deploy to cluster
8. **Monitor** - Watch pods and services
9. **Verify** - Run health checks
10. **Document** - Record configuration and access info

## Common Mistakes to Avoid
- ❌ Not testing with --dry-run first
- ❌ Using 'latest' version (pin specific versions)
- ❌ Ignoring resource limits
- ❌ Not backing up before upgrades
- ❌ Installing to production without testing first
- ❌ Forgetting about persistent volumes
- ❌ Not setting up monitoring/alerting

## Post-Installation
- Verify all pods are running
- Check service endpoints are accessible
- Review logs for any errors
- Set up monitoring and alerts
- Document the installation
- Create runbook for maintenance"""
                        )
                    )
                ]
            )

