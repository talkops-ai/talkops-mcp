"""Rollback-related prompts."""

from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


class RollbackPrompts(BasePrompt):
    """Rollback prompts."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        def helm_rollback_procedures(release_name: str) -> Prompt:
            """Step-by-step rollback procedures for Helm releases.
            
            Arguments:
                release_name: Name of the Helm release to rollback
            """
            return Prompt(
                name="helm-rollback-procedures",
                description=f"Step-by-step rollback procedures for release: {release_name}",
                arguments=[
                    PromptArgument(
                        name="release_name",
                        description="Name of the Helm release to rollback",
                        required=True
                    )
                ],
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""# Helm Rollback Procedures: {release_name}

## When to Rollback

Rollback should be considered when:
- Upgrade or installation fails
- Application is not functioning correctly after deployment
- Critical bugs are discovered in new version
- Performance degradation occurs
- Data integrity issues are detected

## Pre-Rollback Assessment

### Current State
- [ ] Identify the issue requiring rollback
- [ ] Check current release status: `helm status {release_name}`
- [ ] Review release history: `helm history {release_name}`
- [ ] Document current problems
- [ ] Assess impact of rollback

### Release History
```bash
helm history {release_name}
```

This shows all revisions of the release. Identify which revision to rollback to (typically the previous working version).

## Rollback Process

### Step 1: Review Release History
```bash
# List all revisions
helm history {release_name}

# Get details of specific revision
helm get values {release_name} --revision <revision-number>
helm get manifest {release_name} --revision <revision-number>
```

### Step 2: Identify Target Revision
- Review revision numbers
- Identify last known good revision
- Verify target revision configuration
- Check if target revision is stable

### Step 3: Perform Rollback
```bash
# Rollback to previous revision
helm rollback {release_name}

# Rollback to specific revision
helm rollback {release_name} <revision-number>

# Rollback with wait
helm rollback {release_name} <revision-number> --wait --timeout 10m
```

### Step 4: Verify Rollback
```bash
# Check release status
helm status {release_name}

# Verify pods are running
kubectl get pods -l app.kubernetes.io/instance={release_name}

# Check release history
helm history {release_name}
```

## Post-Rollback Verification

### Immediate Checks
- [ ] Verify release status shows correct revision
- [ ] Check all pods are running and healthy
- [ ] Verify services are accessible
- [ ] Review pod logs for errors
- [ ] Check for any error events

### Functional Testing
- [ ] Test application functionality
- [ ] Verify data integrity
- [ ] Check service endpoints
- [ ] Test critical workflows
- [ ] Monitor application metrics

### Monitoring
- [ ] Watch pod status for 15-30 minutes
- [ ] Monitor resource usage
- [ ] Check application logs
- [ ] Review metrics and alerts
- [ ] Verify health checks

## Rollback Scenarios

### Scenario 1: Failed Upgrade
1. Upgrade failed mid-process
2. Release is in inconsistent state
3. Rollback to previous stable revision
4. Investigate upgrade failure
5. Fix issues before retrying

### Scenario 2: Application Issues
1. New version has bugs
2. Application not functioning correctly
3. Rollback to previous working version
4. Report issues to chart maintainers
5. Wait for fix before upgrading again

### Scenario 3: Performance Degradation
1. New version performs worse
2. Resource usage increased significantly
3. Rollback to previous version
4. Analyze performance differences
5. Optimize before upgrading

## Best Practices

### Before Rollback
- ✅ Document the reason for rollback
- ✅ Review release history carefully
- ✅ Verify target revision is stable
- ✅ Backup current state if possible
- ✅ Notify stakeholders

### During Rollback
- ✅ Use `--wait` flag to ensure completion
- ✅ Monitor rollback progress
- ✅ Watch for any errors
- ✅ Verify each step completes

### After Rollback
- ✅ Document rollback in change log
- ✅ Investigate root cause
- ✅ Fix issues before retrying
- ✅ Update runbooks if needed
- ✅ Share lessons learned

## Troubleshooting Rollback Issues

### Rollback Fails
1. Check release history for available revisions
2. Verify target revision exists
3. Check for resource conflicts
4. Review Kubernetes events
5. Try manual rollback if needed

### Partial Rollback
1. Check which resources rolled back
2. Manually fix remaining resources if needed
3. Verify all components are consistent
4. Consider full uninstall/reinstall if severe

### Data Concerns
1. Verify data persistence (if applicable)
2. Check for data corruption
3. Review backup availability
4. Consider data migration if needed

## Alternative: Manual Rollback

If `helm rollback` doesn't work:

```bash
# Get previous revision values
helm get values {release_name} --revision <previous-revision> > values.yaml

# Get previous revision chart version
helm get manifest {release_name} --revision <previous-revision>

# Manually upgrade to previous configuration
helm upgrade {release_name} <previous-chart-version> --values values.yaml
```

## Prevention

To avoid needing rollbacks:
- Always test upgrades in non-production
- Review changelogs and breaking changes
- Use dry-run before actual upgrades
- Have rollback plan ready
- Monitor closely after upgrades
- Keep backups current"""
                        )
                    )
                ]
            )

