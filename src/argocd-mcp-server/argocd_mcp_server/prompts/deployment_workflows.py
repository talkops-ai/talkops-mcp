"""Guided workflow prompts for ArgoCD operations."""

from typing import Dict, Any, Optional

from argocd_mcp_server.prompts.base import BasePrompt


class ArgoCDPrompts(BasePrompt):
    """All ArgoCD prompts for guided workflows."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        async def deploy_new_version(
            cluster_name: str,
            app_name: str,
            new_version: str,
            strategy: str = 'canary'
        ) -> str:
            """Guided step-by-step deployment workflow.
            
            Steps:
            1. Get current state
            2. Show what changes
            3. Review safety checks
            4. Execute deployment
            5. Monitor progress
            6. Verify success
            
            Args:
                cluster_name: Target Kubernetes cluster
                app_name: Application name
                new_version: New version to deploy
                strategy: Deployment strategy (rolling, canary, blue_green)
            
            Returns:
                Formatted prompt with step-by-step instructions
            """
            prompt_text = f"""# Deploy New Version: {app_name} → {new_version}

## Deployment Strategy: {strategy.upper()}

### Step 1: Validate Deployment Prerequisites
Before proceeding with the deployment, let's validate the prerequisites:

1. **Check cluster connectivity**
   - Cluster: `{cluster_name}`
   - Use: `list_applications` to verify connectivity

2. **Check application exists**
   - Application: `{app_name}`
   - Use: `get_application_details` with cluster_name="{cluster_name}" and app_name="{app_name}"

3. **Verify current state**
   - Check sync status and health status
   - Review current version from application details

### Step 2: Show Deployment Diff
Get the changes that will be applied:

```
Use: get_application_diff
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - target_revision: "{new_version}"
```

**Review the diff carefully before proceeding!**

### Step 3: Execute Deployment

**ROLLING UPDATE**
Use: sync_application
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - revision: "{new_version}"
  - dry_run: false
  - prune: true

### Step 4: Monitor Progress

**For Rolling Updates:**
Use: get_sync_status repeatedly to monitor

Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"

Monitor until status shows completion or failure.

### Step 5: Post-Deployment Validation

1. **Check health status**
   - Use: `validate_application_config`
   - Ensure all resources are healthy

2. **Get application logs**
   - Use: `get_application_logs`
   - Check for errors or warnings

3. **Verify metrics**
   - Use resource: `application_metrics`
   - Ensure metrics are stable

### Step 6: Complete or Rollback

**If successful:**
✅ Deployment complete! Monitor metrics for the next 10-15 minutes.

**If failed:**
❌ Use: `rollback_application`
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - steps: 1

---

## Safety Checklist Before Deployment
- [ ] Reviewed deployment diff
- [ ] Verified application is healthy
- [ ] Checked recent sync history
- [ ] Confirmed correct version: {new_version}
- [ ] Strategy appropriate for change: {strategy}

**Ready to proceed? Execute the commands above in sequence.**
"""
            return prompt_text
        

        
        @mcp_instance.prompt()
        async def rollback_decision(
            cluster_name: str,
            app_name: str,
            reason: str
        ) -> str:
            """Guided rollback workflow.
            
            Shows:
            - Current version
            - Previous versions available
            - Rollback impact
            - Asks for confirmation
            
            Args:
                cluster_name: Target Kubernetes cluster
                app_name: Application name
                reason: Reason for rollback
            
            Returns:
                Formatted prompt with rollback decision guide
            """
            prompt_text = f"""# Rollback Decision Guide: {app_name}

## Rollback Reason
**{reason}**

---

### Step 1: Assess Current State

```
Use: get_application_details
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Review:**
- Current sync status
- Current health status
- Current Git revision
- Recent sync history

### Step 2: Review Rollback Options

**Check available previous versions:**

From `get_application_details` response, review the `sync_history` field.
This shows recent deployments with:
- Revision (Git commit)
- Timestamp
- Author
- Status

**Recommended Rollback Options:**

#### Option 1: Rollback 1 Step (Most Recent Stable)
```
Use: rollback_application
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - steps: 1
```
**Impact:** Reverts to the immediately previous version

#### Option 2: Rollback to Specific Revision
```
Use: rollback_to_revision
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - revision: "<git-commit-hash>"
```
**Impact:** Reverts to a specific known-good version

### Step 3: Preview Rollback Changes

**Before rolling back, see what will change:**
```
Use: get_application_diff
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - target_revision: "<target-revision>"
```

### Step 4: Decision Matrix

**Rollback Immediately if:**
- ❌ Application is unhealthy/degraded
- ❌ Critical errors in logs
- ❌ Users experiencing outages
- ❌ Data corruption risk

**Investigate First if:**
- ⚠️ Minor performance degradation
- ⚠️ Non-critical errors
- ⚠️ Feature-specific issues
- ⚠️ Issue might be environmental

### Step 5: Execute Rollback

**After reviewing the above, execute:**

1. **Notify team** about the rollback
2. **Execute rollback command** (from Step 2)
3. **Monitor deployment**:
```
Use: get_sync_status
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

### Step 6: Post-Rollback Validation

```
Use: post_deployment_validation prompt
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

Verify the rollback was successful and issue is resolved.

---

## Rollback Impact Analysis

**What happens during rollback:**
1. ArgoCD syncs to previous Git revision
2. Kubernetes applies previous manifests
3. Pods are recreated with old version
4. Service continues with minimal disruption

**Estimated Rollback Time:** 2-5 minutes

**Data Considerations:**
⚠️ **Database Migrations:** If the current version ran database migrations, 
rolling back code might cause compatibility issues. Check migration history!

⚠️ **API Changes:** If current version introduced breaking API changes, 
clients might fail after rollback.

---

## Pre-Rollback Checklist
- [ ] Identified target rollback version
- [ ] Reviewed changes via `get_application_diff`
- [ ] Checked for database migration impacts
- [ ] Notified team about rollback
- [ ] Confirmed reason warrants immediate rollback
- [ ] Have monitoring ready for post-rollback

**Ready to rollback? Execute the commands above.**

---

## After Rollback

1. **Root Cause Analysis**
   - Why did the deployment fail?
   - What can we improve?

2. **Fix and Redeploy**
   - Fix the issue in code
   - Test thoroughly
   - Redeploy using proper strategy

**Reason for this rollback:** {reason}
**Action Required:** Fix the underlying issue before redeploying.
"""
            return prompt_text
        
        @mcp_instance.prompt()
        async def post_deployment_validation(
            cluster_name: str,
            app_name: str
        ) -> str:
            """Validate deployment after completion.
            
            Checks:
            - All pods are running
            - Health checks passing
            - No errors in logs
            - Metrics are stable
            - API endpoints responding
            
            Args:
                cluster_name: Target Kubernetes cluster
                app_name: Application name
            
            Returns:
                Formatted prompt with validation checklist
            """
            prompt_text = f"""# Post-Deployment Validation: {app_name}

## Comprehensive Health Check After Deployment

### Step 1: Application Status Check

```
Use: get_application_details
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Verify:**
- ✅ Sync Status: Should be "Synced"
- ✅ Health Status: Should be "Healthy"
- ✅ All resources showing correct status

### Step 2: Validate Configuration

```
Use: validate_application_config
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Expected:**
- ✅ `valid: true`
- ✅ No critical errors
- ⚠️ Review any warnings

### Step 3: Pod Health Verification

**From `get_application_details` response, check resources:**

For each Pod resource:
- ✅ Status: "Running" or "Healthy"
- ✅ Restart count: Low (< 5)
- ✅ Ready: true



### Step 4: Application Logs Analysis

```
Use: get_application_logs
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - tail_lines: 100
```

**Check for:**
- ❌ ERROR or FATAL level logs
- ❌ Exception stack traces
- ❌ Database connection errors
- ❌ API call failures
- ✅ Successful startup messages

### Step 5: Metrics Validation

```
Use resource: application_metrics
URI: argocd://application-metrics/{cluster_name}/{app_name}
```

**Verify:**
- ✅ Error rate: < 1%
- ✅ All resources healthy
- ✅ Health percentage: 100%

### Step 6: Integration Tests

**Run your smoke tests against the deployed application:**

#### 6.1 Health Endpoints
Test:
- `/health`
- `/ready`
- `/metrics`

Expected: All return 200 OK

#### 6.2 Critical API Paths
Test your most important API endpoints:
- User authentication
- Core business logic paths
- Database read/write operations

#### 6.3 External Dependencies
Verify connectivity to:
- Database
- Cache (Redis/Memcached)
- Message Queue
- External APIs

### Step 7: Performance Baseline

**Compare with pre-deployment metrics:**

- Response time: Should be similar or better
- Throughput: Should maintain or improve
- Resource usage: Should be within expected range

**Monitor for 10-15 minutes:**
```
Use resource: application_metrics
# Refresh every 30 seconds
```

### Step 8: Recent Events Review

```
Use: get_application_events
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - limit: 20
```

**Look for:**
- ❌ SyncFailed events
- ❌ Degraded health events
- ✅ Recent SyncSuccess

---

## Validation Checklist

### Critical (Must Pass)
- [ ] Sync status: Synced
- [ ] Health status: Healthy
- [ ] All pods running
- [ ] No critical errors in logs
- [ ] Basic health endpoints responding

### Important (Should Pass)
- [ ] Metrics within normal range
- [ ] Integration tests passing
- [ ] No unusual log patterns
- [ ] Resource usage normal
- [ ] Recent events show success

### Nice to Have
- [ ] Performance equal or better than before
- [ ] All smoke tests passed
- [ ] Documentation updated
- [ ] Monitoring alerts configured

---

## If Validation Fails

**Found issues?** Consider:

1. **Minor Issues (warnings, non-critical errors)**
   → Create tickets, monitor, fix in next release

2. **Major Issues (errors, degraded health)**
   → Consider rollback using `rollback_decision` prompt

3. **Critical Issues (outage, data corruption)**
   → **IMMEDIATE ROLLBACK REQUIRED**
   ```
   Use: rollback_application
   Parameters:
     - cluster_name: "{cluster_name}"
     - app_name: "{app_name}"
     - steps: 1
   ```

---

## Validation Complete!

**If all checks pass:** ✅
- Deployment is successful
- Application is healthy
- Monitor for next 24 hours
- Document any learnings

**Post-deployment monitoring:**
- Check metrics dashboard hourly for first 6 hours
- Review logs at 1hr, 6hr, 24hr marks
- Keep rollback option available for 48 hours

**Great job on the deployment! 🎉**
"""
            return prompt_text
