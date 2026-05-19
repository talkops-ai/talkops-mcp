"""Upgrade-related prompts."""

from typing import List
from mcp.types import PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


class UpgradePrompts(BasePrompt):
    """Upgrade prompts."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt(
            name="helm-upgrade-guide",
            description="Guide for upgrading Helm charts",
        )
        def helm_upgrade_guide(chart_name: str) -> List[PromptMessage]:
            """Guide for upgrading existing Helm releases."""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"# Helm Upgrade Guide: {chart_name}\n\n"
                            "## Pre-Upgrade Checklist\n\n"
                            f"- [ ] Review release notes for {chart_name}\n"
                            "- [ ] Check breaking changes between versions\n"
                            "- [ ] Backup current release configuration\n"
                            "- [ ] Test upgrade in non-production environment\n"
                            "- [ ] Verify cluster has sufficient resources\n\n"
                            "## Upgrade Process\n\n"
                            "### Step 1: Fetch Updated Chart\n"
                            "```bash\nhelm repo update\n"
                            f"helm search repo {chart_name} --versions\n```\n\n"
                            "### Step 2: Dry-Run Upgrade\n"
                            "```bash\nhelm upgrade <release> <chart> --values <values-file> --dry-run --debug\n```\n\n"
                            "### Step 3: Perform Upgrade\n"
                            "```bash\nhelm upgrade <release> <chart> --values <values-file> --namespace <ns> --wait --timeout 10m\n```\n\n"
                            "## Post-Upgrade Verification\n"
                            "- [ ] Verify all pods are running\n"
                            "- [ ] Check release status: `helm status <release-name>`\n"
                            "- [ ] Review pod logs for errors\n"
                            "- [ ] Monitor for 15-30 minutes\n\n"
                            "## Rollback Plan\n"
                            "```bash\nhelm rollback <release-name> [revision-number]\n```\n\n"
                            "## Best Practices\n"
                            "- ✅ Pin specific chart versions\n"
                            "- ✅ Always backup before upgrading\n"
                            "- ✅ Test in staging first\n"
                            "- ✅ Have rollback plan ready\n"
                            "- ❌ Skipping dry-run testing\n"
                            "- ❌ Upgrading without backups\n"
                        )
                    )
                )
            ]
