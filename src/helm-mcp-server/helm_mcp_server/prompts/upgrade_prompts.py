"""Upgrade-related prompts."""

from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


class UpgradePrompts(BasePrompt):
    """Upgrade prompts."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        def helm_upgrade_guide(chart_name: str) -> Prompt:
            """Guide for upgrading existing Helm releases.
            
            Arguments:
                chart_name: Name of the Helm chart to upgrade
            """
            return Prompt(
                name="helm-upgrade-guide",
                description=f"Guide for upgrading Helm chart: {chart_name}",
                arguments=[
                    PromptArgument(
                        name="chart_name",
                        description="Name of the Helm chart to upgrade",
                        required=True
                    )
                ],
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""# Helm Upgrade Guide: {chart_name}

## Pre-Upgrade Checklist

### Preparation
- [ ] Review release notes and changelog for {chart_name}
- [ ] Check breaking changes between versions
- [ ] Backup current release configuration
- [ ] Test upgrade in non-production environment
- [ ] Review current values and configuration
- [ ] Check for deprecated values or parameters
- [ ] Verify cluster has sufficient resources

### Current State Assessment
- [ ] Document current release version
- [ ] Export current values: `helm get values <release-name>`
- [ ] Check current release status: `helm status <release-name>`
- [ ] Review running pods and services
- [ ] Verify data persistence (if applicable)
- [ ] Check for custom resources or configurations

## Upgrade Process

### Step 1: Fetch Updated Chart
```bash
helm repo update
helm search repo {chart_name} --versions
```

### Step 2: Review Changes
- Compare current and new chart versions
- Review values schema changes
- Check for new required values
- Identify deprecated parameters
- Review resource changes

### Step 3: Prepare Values
- Update values file with new parameters
- Remove deprecated values
- Add new required values
- Test values validation: `helm template <chart> --values <values-file>`

### Step 4: Dry-Run Upgrade
```bash
helm upgrade <release-name> <chart> \\
  --values <values-file> \\
  --dry-run \\
  --debug
```

### Step 5: Perform Upgrade
```bash
helm upgrade <release-name> <chart> \\
  --values <values-file> \\
  --namespace <namespace> \\
  --wait \\
  --timeout 10m
```

## Post-Upgrade Verification

### Immediate Checks
- [ ] Verify all pods are running: `kubectl get pods`
- [ ] Check release status: `helm status <release-name>`
- [ ] Review pod logs for errors
- [ ] Verify services are accessible
- [ ] Check for any error events

### Functional Testing
- [ ] Test application functionality
- [ ] Verify data integrity (if applicable)
- [ ] Check service endpoints
- [ ] Test critical workflows
- [ ] Monitor application metrics

### Monitoring
- [ ] Watch pod status for first 15-30 minutes
- [ ] Monitor resource usage
- [ ] Check application logs
- [ ] Review metrics and alerts
- [ ] Verify health checks are passing

## Rollback Plan

### If Upgrade Fails
1. Stop the upgrade process immediately
2. Review error messages and logs
3. Identify the cause of failure
4. Fix issues if possible
5. Rollback if necessary: `helm rollback <release-name>`

### Rollback Command
```bash
helm rollback <release-name> [revision-number]
helm status <release-name>  # Verify rollback
```

## Best Practices

### Version Management
- ✅ Pin specific chart versions
- ✅ Test upgrades incrementally
- ✅ Keep upgrade path documented
- ✅ Maintain upgrade history

### Risk Mitigation
- ✅ Always backup before upgrading
- ✅ Test in staging first
- ✅ Have rollback plan ready
- ✅ Upgrade during maintenance windows
- ✅ Monitor closely after upgrade

### Common Pitfalls
- ❌ Skipping dry-run testing
- ❌ Not reviewing breaking changes
- ❌ Ignoring deprecated values warnings
- ❌ Upgrading without backups
- ❌ Not testing in non-production first
- ❌ Upgrading multiple components simultaneously

## Troubleshooting

If you encounter issues during upgrade:
1. Check Helm release history: `helm history <release-name>`
2. Review upgrade logs and events
3. Compare old and new manifests
4. Check for resource conflicts
5. Verify values compatibility
6. Consult chart documentation"""
                        )
                    )
                ]
            )

