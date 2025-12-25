"""Repository and project management workflow prompts for ArgoCD."""

from typing import Dict, Any, Optional

from argocd_mcp_server.prompts.base import BasePrompt


class RepositoryWorkflowPrompts(BasePrompt):
    """Repository onboarding and project management guided workflows."""
    
    def register(self, mcp_instance) -> None:
        """Register repository workflow prompts with FastMCP."""
        
        @mcp_instance.prompt()
        async def onboard_github_repository(
            repo_url: str,
            auth_method: str = "https",
            project_name: Optional[str] = None
        ) -> str:
            """Guided workflow for onboarding a GitHub repository to ArgoCD.
            
            Steps:
            1. Verify credentials are set
            2. Validate repository connection
            3. Onboard repository
            4. Verify registration
            5. Optional: Assign to project
            
            Args:
                repo_url: GitHub repository URL (https:// or git@github.com:)
                auth_method: Authentication method ('https' or 'ssh')
                project_name: Optional ArgoCD project to scope this repository to
            
            Returns:
                Formatted prompt with step-by-step repository onboarding instructions
            """
            is_ssh = auth_method.lower() == "ssh" or repo_url.startswith("git@")
            
            prompt_text = f"""# Onboard GitHub Repository: {repo_url}

## Authentication Method: {auth_method.upper()}

### Step 1: Verify Environment Setup

🔒 **Security Check:** Ensure credentials are configured properly.

"""
            if is_ssh:
                prompt_text += """**For SSH Authentication:**

Check that SSH key is available:
```bash
# Verify SSH key exists (default location)
ls -la ~/.ssh/id_rsa

# Or check custom location from environment
echo $SSH_PRIVATE_KEY_PATH
```

**Environment Variable:**
- `SSH_PRIVATE_KEY_PATH`: Path to SSH private key (defaults to ~/.ssh/id_rsa if not set)

**If key doesn't exist:**
```bash
# Generate new SSH key
ssh-keygen -t rsa -b 4096 -C "argocd@yourdomain.com"

# Add public key to GitHub
cat ~/.ssh/id_rsa.pub
# Copy and paste into GitHub Settings > SSH and GPG keys
```
"""
            else:
                prompt_text += f"""**For HTTPS Authentication:**

Check that Git credentials are set:
```bash
# Verify credentials are set
echo $GIT_PASSWORD  # Should show your token (will be hidden)
echo $GIT_USERNAME  # Optional, can be empty for token auth
```

**Required Environment Variables:**
- `GIT_PASSWORD`: GitHub personal access token (required)
- `GIT_USERNAME`: GitHub username (optional, leave empty for token-only auth)

**If not set:**
```bash
# Set your GitHub personal access token
export GIT_PASSWORD="ghp_your_github_token_here"

# Optional: Set username (can be empty for token auth)
export GIT_USERNAME=""
```

**Generate GitHub Token:**
1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes: `repo` (full control of private repositories)
4. Copy token and set as GIT_PASSWORD
"""

            prompt_text += f"""
---

### Step 2: Validate Repository Connection

**Test connectivity before onboarding:**

```
Use: validate_repository_connection
Parameters:
  - repo_url: "{repo_url}"
```

**Expected Response:**
✅ Connection successful
✅ Repository is accessible
✅ Credentials are valid

**If validation fails:**
- ❌ Check credentials are set correctly
- ❌ Verify repository URL is correct
- ❌ Ensure you have access to the repository on GitHub
"""

            if is_ssh:
                prompt_text += """- ❌ Verify SSH key is added to your GitHub account
- ❌ Check SSH key has proper permissions (chmod 600 ~/.ssh/id_rsa)
"""

            prompt_text += f"""
---

### Step 3: Onboard Repository to ArgoCD

"""

            if is_ssh:
                prompt_text += f"""**Using SSH Authentication:**

```
Use: onboard_repository_ssh
Parameters:
  - repo_url: "{repo_url}"
  - repo_type: "git"
  - enable_lfs: false
"""
                if project_name:
                    prompt_text += f"""  - project: "{project_name}"
"""
                prompt_text += """```

**Notes:**
- SSH key is automatically read from `SSH_PRIVATE_KEY_PATH`
- Defaults to `~/.ssh/id_rsa` if environment variable not set
- 🔒 Key is never exposed to LLM or logs
"""
            else:
                prompt_text += f"""**Using HTTPS Authentication:**

```
Use: onboard_repository_https
Parameters:
  - repo_url: "{repo_url}"
  - repo_type: "git"
  - enable_lfs: false
"""
                if project_name:
                    prompt_text += f"""  - project: "{project_name}"
"""
                prompt_text += """```

**Notes:**
- Credentials are automatically read from `GIT_USERNAME` and `GIT_PASSWORD` environment variables
- 🔒 Credentials are never exposed to LLM or logs
"""

            prompt_text += f"""
---

### Step 4: Verify Repository Registration

**Check that repository was registered successfully:**

```
Use: get_repository
Parameters:
  - repo_url: "{repo_url}"
```

**Verify the response shows:**
✅ Repository URL matches
✅ Connection state is "Successful"
✅ Type is "git"
"""
            if project_name:
                prompt_text += f"""✅ Project is "{project_name}"
"""

            prompt_text += """
**Alternative: List all repositories**

```
Use: list_repositories
```

This will show all registered repositories including the one you just onboarded.

---

### Step 5: Test Repository Access

**Optional: Generate Kubernetes Secret manifest for backup:**

```
Use: generate_repository_secret_manifest
Parameters:
  - repo_url: "{repo_url}"
  - namespace: "argocd"
```

This generates a Kubernetes Secret YAML that you can store in your GitOps repository for disaster recovery.

---

"""

            prompt_text += f"""## Repository Onboarding Checklist

- [ ] Environment credentials verified (Step 1)
- [ ] Repository connection validated (Step 2)
- [ ] Repository onboarded to ArgoCD (Step 3)
- [ ] Registration verified (Step 4)
"""
            if project_name:
                prompt_text += f"""- [ ] Assigned to project: {project_name}
"""

            prompt_text += """
---

## Next Steps

**Now that your repository is onboarded, you can:**

1. **Create ArgoCD Applications** using this repository
   ```
   Use: create_application
   ```

2. **Update Application to use this repo**
   ```
   Use: update_application
   ```

3. **List applications** to see which apps are using this repository
   ```
   Use: list_applications
   ```

---

## Troubleshooting

**If onboarding fails:**

### SSH Authentication Issues:
- Verify SSH key is in correct format (PEM)
- Check private key has BEGIN/END headers
- Ensure key was added to GitHub account
- Test manually: `ssh -T git@github.com`

### HTTPS Authentication Issues:
- Verify token has `repo` scope
- Check token hasn't expired
- Ensure $GIT_PASSWORD is set correctly
- For GitHub, use token as password

### Connection Issues:
- Check network connectivity
- Verify repository exists and you have access
- Check repository URL format is correct
- Review firewall/proxy settings

---

## Repository Management

**After onboarding, you can:**

**Get Repository Details:**
```
Use: get_repository
Parameters:
  - repo_url: "{repo_url}"
```

**Delete Repository** (if needed):
```
Use: delete_repository
Parameters:
  - repo_url: "{repo_url}"
```

**Repository successfully onboarded! 🎉**
"""
            return prompt_text

        @mcp_instance.prompt()
        async def setup_argocd_project(
            project_name: str,
            team_name: str,
            allowed_repos: str = "*",
            allowed_namespaces: str = "*"
        ) -> str:
            """Guided workflow for setting up an ArgoCD project with RBAC.
            
            Steps:
            1. Plan project structure
            2. Define source repositories
            3. Define destination clusters/namespaces
            4. Create project
            5. Verify project
            6. Generate manifest for GitOps
            
            Args:
                project_name: Name of the ArgoCD project
                team_name: Team who will own this project
                allowed_repos: Allowed repository patterns (e.g., 'https://github.com/org/*')
                allowed_namespaces: Allowed namespace patterns (e.g., 'team-*')
            
            Returns:
                Formatted prompt with step-by-step project setup instructions
            """
            prompt_text = f"""# Setup ArgoCD Project: {project_name}

## Project Owner: {team_name}

### What is an ArgoCD Project?

ArgoCD Projects provide a logical grouping of applications with:
- **Multi-tenancy**: Isolate teams and permissions
- **Security**: Control which repositories and clusters teams can use
- **RBAC**: Define who can deploy what and where

---

### Step 1: Plan Project Structure

**Project Scope:**
- Name: `{project_name}`
- Owner Team: `{team_name}`
- Repository Pattern: `{allowed_repos}`
- Namespace Pattern: `{allowed_namespaces}`

**Define Source Repositories:**

Examples:
- Single repo: `https://github.com/myorg/myrepo.git`
- Organization wildcard: `https://github.com/myorg/*`
- All repos: `*`

**Your allowed repos:** `{allowed_repos}`

**Define Destination Clusters and Namespaces:**

Examples for namespaces:
- Specific namespace: `production`
- Team namespaces: `{team_name}-*`
- All namespaces: `*`

**Your allowed namespaces:** `{allowed_namespaces}`

---

### Step 2: Create the ArgoCD Project

```
Use: create_project
Parameters:
  - project_name: "{project_name}"
  - description: "ArgoCD project for {team_name} team"
  - source_repos: ["{allowed_repos}"]
  - destinations: [
      {{
        "server": "https://kubernetes.default.svc",
        "namespace": "{allowed_namespaces}"
      }}
    ]
```

**Optional Advanced Parameters:**

**Cluster Resource Whitelist** (allow cluster-scoped resources):
```python
cluster_resource_whitelist: [
  {{"group": "", "kind": "Namespace"}},
  {{"group": "rbac.authorization.k8s.io", "kind": "ClusterRole"}},
  {{"group": "rbac.authorization.k8s.io", "kind": "ClusterRoleBinding"}}
]
```

**Namespace Resource Whitelist** (allow namespace-scoped resources):
```python
namespace_resource_whitelist: [
  {{"group": "apps", "kind": "Deployment"}},
  {{"group": "apps", "kind": "StatefulSet"}},
  {{"group": "", "kind": "Service"}},
  {{"group": "", "kind": "ConfigMap"}},
  {{"group": "", "kind": "Secret"}}
]
```

**Cluster Resource Blacklist** (deny specific cluster resources):
```python
cluster_resource_blacklist: [
  {{"group": "", "kind": "ResourceQuota"}}
]
```

---

### Step 3: Verify Project Creation

**Check project was created successfully:**

```
Use: get_project
Parameters:
  - project_name: "{project_name}"
```

**Verify the response shows:**
✅ Project name: {project_name}
✅ Description mentions: {team_name}
✅ Source repos include: {allowed_repos}
✅ Destinations include namespace pattern: {allowed_namespaces}

**Alternative: List all projects**

```
Use: list_projects
```

This will show all ArgoCD projects including the one you just created.

---

### Step 4: Generate Project Manifest (GitOps)

**Generate Kubernetes AppProject YAML:**

```
Use: generate_project_manifest
Parameters:
  - project_name: "{project_name}"
  - description: "ArgoCD project for {team_name} team"
  - source_repos: ["{allowed_repos}"]
  - destinations: [
      {{
        "server": "https://kubernetes.default.svc",
        "namespace": "{allowed_namespaces}"
      }}
    ]
```

**Save the generated YAML to your GitOps repository:**

```yaml
# Example location: argocd/projects/{project_name}.yaml
```

**Benefits of storing in Git:**
- ✅ Version control for project configuration
- ✅ Audit trail of changes
- ✅ Easy disaster recovery
- ✅ GitOps principles applied to ArgoCD itself

---

### Step 5: Onboard Repositories to Project

**Now onboard repositories scoped to this project:**

```
Use: onboard_repository_https  # or onboard_repository_ssh
Parameters:
  - repo_url: "https://github.com/myorg/myrepo.git"
  - project: "{project_name}"  # ← Scope to this project
```

**Repositories scoped to a project can only be used by applications in that project.**

---

### Step 6: Create Applications in Project

**Create an application that uses this project:**

```
Use: create_application
Parameters:
  - cluster_name: "production"
  - app_name: "{team_name}-app"
  - project: "{project_name}"  # ← Must match this project
  - repo_url: "https://github.com/myorg/myrepo.git"
  - path: "k8s"
  - dest_namespace: "{team_name}-production"  # ← Must match allowed namespaces
```

**Security Enforcement:**
- ❌ Application cannot use repositories outside allowed patterns
- ❌ Application cannot deploy to namespaces outside allowed patterns
- ❌ Application cannot use cluster resources if not whitelisted

---

## Project Setup Checklist

- [ ] Project structure planned
- [ ] Source repository patterns defined
- [ ] Destination clusters and namespaces defined
- [ ] Project created in ArgoCD
- [ ] Project verified with get_project
- [ ] Project manifest generated for GitOps
- [ ] Repositories onboarded and scoped to project
- [ ] Sample application created in project

---

## Project Management

**After setup, you can:**

**Update Project:**
Currently not directly supported. Delete and recreate if needed, or update via Kubernetes API.

**Delete Project:**
```
Use: delete_project
Parameters:
  - project_name: "{project_name}"
```
⚠️ **Warning:** Deleting a project does not delete applications in it, but they'll become orphaned.

**List All Projects:**
```
Use: list_projects
```

---

## Multi-Tenancy Best Practices

**1. Repository Isolation:**
- Use organization wildcards: `https://github.com/team-name/*`
- Or specific repository allow-lists

**2. Namespace Isolation:**
- Use team-prefixed namespaces: `{team_name}-*`
- Or environment-specific: `{team_name}-{{dev,staging,prod}}`

**3. Resource Restrictions:**
- Whitelist only necessary resource types
- Blacklist dangerous cluster resources
- Limit cluster-scoped access

**4. RBAC Integration:**
- Combine with Kubernetes RBAC for full security
- Use ArgoCD RBAC policies for UI/API access
- Integrate with SSO/LDAP for user management

---

## Example Multi-Team Setup

**Team Frontend:**
```
Project: frontend-team
Repos: https://github.com/company/frontend-*
Namespaces: frontend-*
```

**Team Backend:**
```
Project: backend-team
Repos: https://github.com/company/backend-*
Namespaces: backend-*
```

**Team Platform (admins):**
```
Project: platform-team
Repos: *  # All repositories
Namespaces: *  # All namespaces
Cluster Resources: Allowed
```

---

**Project '{project_name}' setup complete! 🎉**

**Next:** Onboard repositories and create applications scoped to this project.
"""
            return prompt_text

        @mcp_instance.prompt()
        async def debug_application_issues(
            cluster_name: str,
            app_name: str,
            issue_description: str = "Application not working as expected"
        ) -> str:
            """Comprehensive debugging workflow for ArgoCD applications.
            
            Steps:
            1. Check application status
            2. Analyze sync and health status
            3. Review application logs with error detection
            4. Check application events
            5. Inspect resource details
            6. Review recent changes
            7. Recommended actions
            
            Args:
                cluster_name: Target Kubernetes cluster
                app_name: Application name to debug
                issue_description: Description of the issue
            
            Returns:
                Formatted prompt with step-by-step debugging instructions
            """
            prompt_text = f"""# Debug Application: {app_name}

## Issue Description
**{issue_description}**

## Cluster: {cluster_name}

---

### Step 1: Get Application Overview

**First, get the complete application state:**

```
Use: get_application_details
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Check the following in the response:**

#### Sync Status
- ✅ **Synced**: Application state matches Git
- ⚠️ **OutOfSync**: Drift detected between Git and cluster
- ❌ **Unknown**: ArgoCD cannot determine state

#### Health Status
- ✅ **Healthy**: All resources are healthy
- ⚠️ **Progressing**: Resources are being created/updated
- ⚠️ **Degraded**: Some resources are unhealthy
- ❌ **Missing**: Resources are missing

#### Current Revision
- Note the Git commit hash currently deployed
- This helps track what version is running

---

### Step 2: Analyze Application Logs (with Smart Error Detection)

**Get recent logs with automatic error detection:**

```
Use: get_application_logs
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - tail_lines: 50  # Default, increase to 200 if needed
```

**This tool automatically:**
- ✅ Provides concise summaries (shows only first 20 lines per pod)
- ✅ Detects errors, exceptions, and failures
- ✅ Extracts up to 5 sample error messages per pod
- ✅ Prevents overwhelming output with smart filtering

**What to look for in the response:**

**Check `error_count` field:**
- If > 0: Review `sample_errors` array for actual error messages
- Common error patterns:
  - `CrashLoopBackOff`: Pod keeps crashing
  - `ImagePullBackOff`: Cannot pull container image
  - `Error: *`: Application-level errors
  - `Exception: *`: Code exceptions
  - `FATAL: *`: Critical failures

**Check `line_count` field:**
- If high (> 100 lines in short time): Possible logging storm
- If too low (< 10 lines): Application might not be running

**Check `has_more` field:**
- If `true`: More log lines available, consider increasing `tail_lines`

---

### Step 3: Review Application Events

**Get recent Kubernetes events for this application:**

```
Use: get_application_events
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - limit: 20
```

**Common event types and meanings:**

#### Sync-Related Events:
- `SyncStarted`: Deployment began
- `SyncSucceeded`: Deployment completed successfully
- `SyncFailed`: Deployment failed
- `OutOfSync`: Drift detected

#### Health-Related Events:
- `HealthStatusChanged`: Health state changed
- `ResourceHealthDegraded`: A resource became unhealthy
- `ResourceHealthHealthy`: Resource recovered

#### Resource Events:
- `ResourceCreated`: New resource added
- `ResourceUpdated`: Resource modified
- `ResourceDeleted`: Resource removed

**Timeline Analysis:**
Review events chronologically to understand what happened and when.

---

### Step 4: Inspect Pod Resources

**From Step 1 (`get_application_details`), review the `resources` field:**

**For each Pod, check:**

1. **Status**
   - `Running`: ✅ Good
   - `Pending`: ⏳ Waiting for resources or scheduling
   - `CrashLoopBackOff`: ❌ Container crashes repeatedly
   - `ImagePullBackOff`: ❌ Cannot pull container image
   - `Error`: ❌ Pod failed
   - `Unknown`: ❓ State cannot be determined

2. **Restart Count**
   - 0-5: ✅ Normal
   - 5-20: ⚠️ Investigate why restarts are happening
   - > 20: ❌ Serious issue causing frequent crashes

3. **Ready Status**
   - `true`: ✅ Container passed health checks
   - `false`: ❌ Container failing health checks

4. **Container Information**
   - Image version deployed
   - Resource requests/limits
   - Environment variables

---

### Step 5: Check Sync/Deployment D iff

**See what changes (if any) are pending:**

```
Use: get_application_diff
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**If `changes_detected: true`:**
- Review the `diffs` array
- Check if unintended drift occurred
- Determine if sync is needed

**If drift detected:**
```
Use: sync_application to reconcile
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - prune: true  # Remove resources not in Git
```

---

### Step 6: Validate Application Configuration

**Check for configuration errors:**

```
Use: validate_application_config
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Expected:**
- `valid: true`
- No critical errors

**If validation fails:**
- Review error messages
- Fix configuration in Git
- Re-sync application

---

### Step 7: Review Recent Deployment History

**From Step 1 (`get_application_details`), check `sync_history` field:**

**For recent syncs:**
- Timestamp: When did it happen?
- Revision: What Git commit?
- Status: Did it succeed or fail?
- Author: Who triggered it?

**Compare with current state:**
- Has application been recently updated?
- Was the last sync successful?
- Are we running the expected version?

---

## Common Issues and Solutions

### Issue 1: OutOfSync Status

**Symptoms:**
- Sync status shows "OutOfSync"
- Changes detected in diff

**Diagnosis:**
```
Use: get_application_diff
```

**Solution:**
```
Use: sync_application
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - prune: true
```

---

### Issue 2: Degraded Health

**Symptoms:**
- Health status shows "Degraded"
- Some pods not ready

**Diagnosis:**
1. Check logs (Step 2) for errors
2. Review events (Step 3) for failures
3. Inspect pod status (Step 4)

**Common Causes:**
- Container crashing (check logs)
- Health check failing (check readiness/liveness probes)
- Resource limits too low (check resource requests)
- Missing dependencies (database, cache, etc.)

**Solution:**
- Fix underlying issue in code/config
- Update in Git
- Sync application

---

### Issue 3: CrashLoopBackOff

**Symptoms:**
- Pods status: "CrashLoopBackOff"
- High restart count
- Error logs showing startup failures

**Diagnosis:**
```
Use: get_application_logs
Parameters:
  - tail_lines: 100  # Get more logs
```

**Common Causes:**
- Application crashes on startup
- Missing environment variables
- Database connection failures
- Invalid configuration

**Solution:**
- Review error logs for root cause
- Fix configuration/code
- Update in Git and re-deploy

---

### Issue 4: ImagePullBackOff

**Symptoms:**
- Pods status: "ImagePullBackOff"
- Events show image pull errors

**Common Causes:**
- Image doesn't exist
- Wrong image tag
- No credentials for private registry
- Network/registry issues

**Solution:**
1. Verify image exists in registry
2. Check image tag is correct
3. Ensure image pull secrets are configured
4. Update image reference in Git

---

### Issue 5: High Error Count in Logs

**Symptoms:**
- `get_application_logs` shows `error_count > 0`
- Sample errors indicate application issues

**Diagnosis:**
- Review `sample_errors` array
- Identify error patterns
- Check if errors are temporary or persistent

**Solution:**
- Fix code/configuration causing errors
- Roll out fix via Git
- Monitor error count after deployment

---

## Debugging Checklist

- [ ] Application status checked (sync, health)
- [ ] Logs analyzed for errors (with automatic error detection)
- [ ] Recent events reviewed
- [ ] Pod resources inspected (status, restarts, readiness)
- [ ] Sync diff checked for drift
- [ ] Configuration validated
- [ ] Deployment history reviewed
- [ ] Root cause identified

---

## Recommended Actions

**Based on your investigation:**

### If Application is Healthy:
✅ Issue might be resolved  
✅ Monitor for recurrence  
✅ Check application-level metrics

### If Configuration Issues:
1. Fix configuration in Git
2. Commit and push changes
3. Sync application:
   ```
   Use: sync_application
   ```

### If Application Code Issues:
1. Fix code
2. Build new image
3. Update image tag in Git
4. Sync application

### If Deployment Failed:
1. Review sync errors
2. Check for resource conflicts
3. Consider rollback:
   ```
   Use: rollback_decision prompt
   Parameters:
     - cluster_name: "{cluster_name}"
     - app_name: "{app_name}"
     - reason: "{issue_description}"
   ```

### If Persistent Issues:
1. Collect all diagnostic data
2. Check cluster-level issues
3. Review resource quotas
4. Engage platform team

---

## Next Steps

**After identifying the root cause:**

1. **Implement Fix**
   - Update code/configuration
   - Test locally first
   - Commit to Git

2. **Deploy Fix**
   ```
   Use: deploy_new_version prompt
   Parameters:
     - cluster_name: "{cluster_name}"
     - app_name: "{app_name}"
     - new_version: "<fixed-version>"
   ```

3. **Validate Fix**
   ```
   Use: post_deployment_validation prompt
   Parameters:
     - cluster_name: "{cluster_name}"
     - app_name: "{app_name}"
   ```

4. **Post-Mortem**
   - Document findings
   - Update runbooks
   - Prevent recurrence

---

**Debugging session for '{app_name}' complete!**

**Issue:** {issue_description}  
**Next:** Implement the recommended actions above to resolve the issue.
"""
            return prompt_text

        @mcp_instance.prompt()
        async def full_application_deployment(
            repo_url: str,
            app_name: str,
            cluster_name: str = "production",
            namespace: str = "default",
            path: str = "k8s",
            project_name: str = "default"
        ) -> str:
            """Complete end-to-end workflow from repository onboarding to application deployment.
            
            Steps:
            1. Check environment setup
            2. Onboard repository
            3. Create ArgoCD application
            4. Deploy application
            5. Monitor deployment
            6. Validate deployment
            
            Args:
                repo_url: Git repository URL
                app_name: Name for the ArgoCD application
                cluster_name: Target Kubernetes cluster
                namespace: Target namespace
                path: Path in repo containing manifests
                project_name: ArgoCD project name
            
            Returns:
                Formatted prompt with complete deployment workflow
            """
            is_ssh = repo_url.startswith("git@") or repo_url.startswith("ssh://")
            auth_method = "SSH" if is_ssh else "HTTPS"
            
            prompt_text = f"""# Complete Application Deployment Workflow

## Deploy: {app_name}
**Repository:** {repo_url}  
**Cluster:** {cluster_name}  
**Namespace:** {namespace}  
**Project:** {project_name}

---

## Overview

This workflow guides you through the complete process:
1. ✅ Repository onboarding ({auth_method})
2. ✅ Application creation in ArgoCD
3. ✅ Initial deployment
4. ✅ Monitoring and validation

---

### PHASE 1: Repository Onboarding

Use the specialized prompt for detailed repository onboarding:

```
Use prompt: onboard_github_repository
Parameters:
  - repo_url: "{repo_url}"
  - auth_method: "{auth_method.lower()}"
  - project_name: "{project_name}"
```

**Quick version (if you've done this before):**

"""
            if is_ssh:
                prompt_text += f"""```
Use: onboard_repository_ssh
Parameters:
  - repo_url: "{repo_url}"
  - project: "{project_name}"
```
"""
            else:
                prompt_text += f"""```
Use: onboard_repository_https
Parameters:
  - repo_url: "{repo_url}"
  - project: "{project_name}"
```
"""

            prompt_text += f"""
**Verify repository onboarding:**
```
Use: get_repository
Parameters:
  - repo_url: "{repo_url}"
```

---

### PHASE 2: Create ArgoCD Application

**Create the application configuration:**

```
Use: create_application
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - project: "{project_name}"
  - repo_url: "{repo_url}"
  - path: "{path}"
  - target_revision: "HEAD"  # Or specific branch/tag
  - dest_namespace: "{namespace}"
  - dest_server: "https://kubernetes.default.svc"
  - sync_policy_automated: false  # Manual sync for initial deployment
  - auto_create_namespace: true
```

**Verify application creation:**
```
Use: get_application_details
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Expected State After Creation:**
- Sync Status: "OutOfSync" (not deployed yet)
- Health Status: "Missing" (resources don't exist yet)

---

### PHASE 3: Preview DeploymentChanges

**See what will be deployed:**

```
Use: get_application_diff
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Review the diff output:**
- Check all Kubernetes resources that will be created
- Verify configurations are correct
- Confirm image versions
- Review  resource requests/limits

**⚠️ IMPORTANT:** Carefully review the diff before proceeding!

---

### PHASE 4: Initial Deployment

**Deploy the application for the first time:**

```
Use: sync_application
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - dry_run: false
  - prune: true
  - auto_policy: "apply"
```

**During sync:**
- ArgoCD applies all manifests from `{path}`
- Kubernetes creates the resources
- Pods are scheduled and started
- Services are created

---

### PHASE 5: Monitor Deployment Progress

**Check sync status:**

```
Use: get_sync_status
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Poll every 10-15 seconds until:**
- ✅ Sync Status: "Synced"
- ✅ Sync Phase: "Succeeded"

**If sync fails:**
- Review sync errors in the response
- Check application logs
- Use debug_application_issues prompt

---

### PHASE 6: Post-Deployment Validation

**Use comprehensive validation prompt:**

```
Use prompt: post_deployment_validation
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Quick validation (if time-constrained):**

**1. Check application status:**
```
Use: get_application_details
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Expected:**
- Sync Status: "Synced"
- Health Status: "Healthy"
- All pods: Running

**2. Check logs for errors:**
```
Use: get_application_logs
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - tail_lines: 50
```

**Expected:**
- `error_count: 0` (no errors detected)
- Successful startup messages in `recent_logs`

**3. Verify configuration:**
```
Use: validate_application_config
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
```

**Expected:**
- `valid: true`

---

## Deployment Checklist

- [ ] **Phase 1:** Repository onboarded and verified
- [ ] **Phase 2:** Application created in ArgoCD
- [ ] **Phase 3:** Deployment diff reviewed and approved
- [ ] **Phase 4:** Initial sync executed
- [ ] **Phase 5:** Sync completed successfully
- [ ] **Phase 6:** Post-deployment validation passed

---

## Optional: Enable Auto-Sync

**After successful initial deployment, consider enabling auto-sync:**

```
Use: update_application
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - sync_policy_automated: true
  - auto_prune: true
  - self_heal: true
```

**Benefits:**
- ✅ Automatic deployment of new versions
- ✅ Self-healing if manual changes are made
- ✅ GitOps principles fully automated

**Considerations:**
- ⚠️ Changes in Git immediately deploy to cluster
- ⚠️ Ensure you have proper Git branch protection
- ⚠️ Consider using separate branches for staging/production

---

## Monitoring and Maintenance

**After deployment:**

**1. Monitor Application Health:**
```
Use resource: argocd://application-metrics/{cluster_name}/{app_name}
```

**2. Watch for Events:**
```
Use resource: argocd://deployment-events/{cluster_name}
```

**3. Check Sync Operations:**
```
Use resource: argocd://sync-operations/{cluster_name}
```

---

## Updating the Application

**For future updates:**

1. **Update code /manifests in Git**
2. **Push changes to repository**
3. **Deploy new version:**
   ```
   Use prompt: deploy_new_version
   Parameters:
     - cluster_name: "{cluster_name}"
     - app_name: "{app_name}"
     - new_version: "<git-commit-or-tag>"
   ```

---

## Troubleshooting

**If deployment fails at any phase:**

```
Use prompt: debug_application_issues
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - issue_description: "<describe-the-issue>"
```

---

## Rollback (If Needed)

**If deployment causes issues:**

```
Use prompt: rollback_decision
Parameters:
  - cluster_name: "{cluster_name}"
  - app_name: "{app_name}"
  - reason: "<reason-for-rollback>"
```

---

## Success! 🎉

**Your application is now deployed and managed by ArgoCD:**

✅ Repository onboarded with secure credentials  
✅ Application created and synced  
✅ Resources deployed to {namespace} namespace  
✅ Application is healthy and running

**Next steps:**
- Monitor application metrics
- Set up alerts for health changes
- Enable auto-sync for continuous deployment
- Document your deployment process

**GitOps Benefits:**
- 🔄 Declarative configuration in Git
- 📜 Full audit trail of changes
- 🔙 Easy rollbacks to any previous version
- 🔒 Git as single source of truth

---

**Deployment workflow complete!**
"""
            return prompt_text
