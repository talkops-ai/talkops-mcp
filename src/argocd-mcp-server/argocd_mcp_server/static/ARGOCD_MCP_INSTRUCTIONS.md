# ArgoCD MCP Server

## Overview
This is the **ArgoCD MCP Server** - a Model Context Protocol (MCP) server for managing Kubernetes applications and resources via ArgoCD using GitOps principles.

## Capabilities

### 🛠️ Tools (29 total)

#### Application Management (7 tools)
- `list_applications` - List all ArgoCD applications with filtering and pagination
- `get_application_details` - Get detailed information about a specific application
- `create_application` - Create a new ArgoCD application
- `update_application` - Update application configuration
- `delete_application` - Delete an ArgoCD application
- `validate_application_config` - Validate application configuration for errors
- `get_application_events` - Get recent events for an application

#### Deployment Operations (10 tools)
- `sync_application` - Sync application to desired state
- `get_application_diff` - Show what changes will happen before syncing
- `get_application_logs` - Get logs from application pods (with concise summaries and error detection)
- `get_sync_status` - Get current sync status and operation progress
- `rollback_application` - Rollback application to previous sync
- `rollback_to_revision` - Rollback to specific Git revision
- `prune_resources` - Remove resources not in Git (safe cleanup)
- `hard_refresh` - Hard refresh application state (bypass cache)
- `soft_refresh` - Soft refresh application state (use cache)
- `cancel_deployment` - Cancel ongoing sync operation

#### Repository Management (7 tools)
- `onboard_repository_https` - Onboard Git repository via HTTPS (credentials from env vars)
- `onboard_repository_ssh` - Onboard Git repository via SSH (key from file path)
- `list_repositories` - List all registered repositories
- `get_repository` - Get repository details and connection status
- `validate_repository_connection` - Test repository connectivity before onboarding
- `delete_repository` - Remove a registered repository
- `generate_repository_secret_manifest` - Generate Kubernetes Secret YAML for repository auth

#### Project Management (5 tools)
- `create_project` - Create new ArgoCD project with source repos and destinations
- `list_projects` - List all ArgoCD projects
- `get_project` - Get project details and RBAC policies
- `delete_project` - Delete an ArgoCD project
- `generate_project_manifest` - Generate AppProject YAML manifest

### 📊 Resources (5 real-time data streams)
1. **applications** - Real-time list of all applications and their state
2. **application_metrics** - Real-time metrics for specific application
3. **sync_operations** - Currently running sync operations across all apps
4. **deployment_events** - Stream of deployment events (sync, rollback, etc)
5. **cluster_health** - Overall cluster and ArgoCD health status

### 💡 Prompts (7 guided workflows)

**Deployment Workflows:**
1. **deploy_new_version** - Guided step-by-step deployment workflow
2. **post_deployment_validation** - Comprehensive post-deployment validation  
3. **full_application_deployment** - End-to-end deployment from repo to running app

**Recovery & Debugging:**
4. **rollback_decision** - Guided rollback workflow with impact analysis
5. **debug_application_issues** - Comprehensive troubleshooting workflow with smart log analysis

**Management:**
6. **onboard_github_repository** - Secure repository onboarding (HTTPS/SSH)
7. **setup_argocd_project** - Multi-tenancy and RBAC project setup

## Usage Best Practices

### Deployment Strategies

**Rolling Updates** (Default)
- Use `sync_application` for standard deployments
- Best for: Small changes, low-risk updates
- Downtime: Minimal (rolling pod replacement)

### Safety Guidelines

1. **Always check diff before deployment**
   - Use `get_application_diff` to preview changes
   - Review what will be modified

2. **Validate application health**
   - Use `validate_application_config` before deployment
   - Check `get_application_events` for recent issues

3. **Monitor deployments**
   - Use `get_sync_status` to track progress
   - Watch resources via `application_metrics`

4. **Have rollback plan ready**
   - Know your previous stable version
   - Use `rollback_application` or `rollback_to_revision` if needed

5. **Post-deployment validation**
   - Use `post_deployment_validation` prompt for comprehensive checks
   - Monitor for 10-15 minutes after deployment

6. **Log Analysis Best Practices**
   - `get_application_logs` returns concise summaries (default 50 lines/pod, max 200)
   - Automatically detects and highlights errors with sample messages
   - Shows only first 20 log lines in summary to prevent overwhelming output
   - Use `tail_lines` parameter to control verbosity

### Repository & Project Management

**Repository Onboarding:**
1. **HTTPS Authentication**: Set `GIT_PASSWORD` env var, then call `onboard_repository_https()`
2. **SSH Authentication**: Set `SSH_PRIVATE_KEY_PATH` (defaults to `~/.ssh/id_rsa`), then call `onboard_repository_ssh()`
3. **Validation**: Always test with `validate_repository_connection()` before creating applications

**Project Administration:**
- Use `create_project()` to set up multi-tenancy with RBAC
- Define allowed source repositories (supports wildcards: `https://github.com/org/*`)
- Define allowed destination clusters and namespaces
- Generate manifests with `generate_project_manifest()` for GitOps workflows

### Resource Patterns

Resources provide real-time data streams. Use them for:
- **Dashboard Building**: `applications`, `cluster_health`
- **Monitoring**: `application_metrics`, `sync_operations`
- **Auditing**: `deployment_events`

## Configuration

The server uses environment variables for configuration:

### Required Configuration
- `ARGOCD_SERVER_URL` - ArgoCD server URL (required)
- `ARGOCD_AUTH_TOKEN` - ArgoCD authentication token (required)

### Optional Configuration
- `ARGOCD_INSECURE` - Skip TLS verification (default: false)
- `ARGOCD_TIMEOUT` - Request timeout in seconds (default: 300)
- `MCP_ALLOW_WRITE` - Allow write operations (default: false)
- `KUBERNETES_KUBECONFIG` - Path to kubeconfig (optional, uses in-cluster if not set)

### 🔒 Security: Repository Credentials

**For HTTPS Repository Onboarding:**
- `GIT_USERNAME` - Git username (can be empty for token-only authentication)
- `GIT_PASSWORD` - Git password or personal access token (required for HTTPS repos)

**For SSH Repository Onboarding:**
- `SSH_PRIVATE_KEY_PATH` - Path to SSH private key file (default: `~/.ssh/id_rsa`)

> 🔐 **Security Note**: All credentials are read from environment variables or secure file paths to prevent exposure to LLM models. Never pass credentials as tool parameters.

## Error Handling

The server uses specific exceptions for different failure scenarios:
- `ArgoCDOperationError` - Generic ArgoCD operation failures
- `SyncOperationFailed` - Sync-specific failures
- `ApplicationNotFound` - Application doesn't exist
- `ValidationFailed` - Configuration validation errors
- `ArgoCDConnectionError` - Connection to ArgoCD server failed

All errors include descriptive messages to help diagnose issues.

## Support

For issues, questions, or contributions, please refer to the project repository.
