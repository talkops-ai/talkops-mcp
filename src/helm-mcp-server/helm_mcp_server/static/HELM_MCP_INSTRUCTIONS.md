# Helm MCP Server Instructions

MCP server specialized in Kubernetes workload management via Helm. This server provides comprehensive tools for chart discovery, installation, validation, monitoring, and lifecycle management following security-focused and production-grade best practices.

## How to Use This Server (Required Workflow)

### Step 1: Consult the Helm Workflow Guide
ALWAYS use the `helm_workflow_guide` prompt to guide your Helm operations. This workflow:

* Provides step-by-step approaches for secure, reliable Helm deployments
* Documents all available tools, resources, and prompts
* Specifies when and how to use each MCP tool
* Includes workflow diagrams and detailed phase descriptions

For quick operations, use the `helm_quick_start` prompt instead.

### Step 2: Follow Helm Best Practices
ALWAYS consult the `helm://best_practices` resource which contains:

* Chart structure and organization principles
* Security best practices for Kubernetes workloads
* Values file management and secret handling
* Helm-specific implementation guidance

### Step 3: Validate Before Deployment
ALWAYS validate configurations before installation:

* Use `helm_validate_values` to check values against schema
* Use `helm_render_manifests` to preview what will be deployed
* Use `helm_dry_run_install` to test installation without deploying
* Use `helm_check_dependencies` to ensure all requirements are met

### Step 4: Use the Right Cluster Context
When deploying or managing releases:

* Use `kubernetes_list_contexts` to see all available Kubernetes contexts
* Use `kubernetes_set_context` to switch to the desired cluster context
* Use `kubernetes_get_cluster_info` to verify cluster connectivity
* Use `kubernetes_check_prerequisites` to validate cluster requirements
* Use namespace scoping to avoid conflicts
* Validate cluster access and permissions before running operations

---

## Available Tools

### Discovery Tools
| Tool | Purpose |
|------|---------|
| `helm_search_charts` | Search for Helm charts in repositories |
| `helm_get_chart_info` | Get detailed chart metadata and documentation |
| `helm_ensure_repository` | Ensure a Helm repository exists, adding it if necessary |

### Installation Tools
| Tool | Purpose |
|------|---------|
| `helm_install_chart` | Install a Helm chart to cluster |
| `helm_upgrade_release` | Upgrade an existing Helm release |
| `helm_rollback_release` | Rollback to a previous revision |
| `helm_uninstall_release` | Uninstall a Helm release |
| `helm_dry_run_install` | Preview installation without deploying |

### Validation Tools
| Tool | Purpose |
|------|---------|
| `helm_validate_values` | Validate chart values against schema |
| `helm_render_manifests` | Render Kubernetes manifests from chart |
| `helm_validate_manifests` | Validate rendered Kubernetes manifests |
| `helm_check_dependencies` | Check if chart dependencies are available |
| `helm_get_installation_plan` | Generate installation plan with resource estimates |

### Kubernetes Tools
| Tool | Purpose |
|------|---------|
| `kubernetes_get_cluster_info` | Get cluster information |
| `kubernetes_list_namespaces` | List all Kubernetes namespaces |
| `kubernetes_list_contexts` | List all available Kubernetes contexts from kubeconfig |
| `kubernetes_set_context` | Set/switch to a specific Kubernetes context |
| `kubernetes_get_helm_releases` | List all Helm releases in cluster |
| `kubernetes_check_prerequisites` | Check cluster prerequisites |

### Monitoring Tools
| Tool | Purpose |
|------|---------|
| `helm_monitor_deployment` | Monitor deployment health asynchronously |
| `helm_get_release_status` | Get current status of a Helm release |

---

## Available Resources

| Resource URI | Purpose |
|--------------|---------|
| `helm://releases` | List all Helm releases in cluster |
| `helm://releases/{release_name}` | Get detailed release information |
| `helm://charts` | List available charts |
| `helm://charts/{repo}/{name}` | Get specific chart metadata |
| `helm://charts/{repo}/{name}/readme` | Get chart README documentation |
| `kubernetes://cluster-info` | Get Kubernetes cluster information |
| `kubernetes://namespaces` | List all Kubernetes namespaces |
| `helm://best_practices` | Helm Best Practices guide |

---

## Available Prompts

| Prompt | Purpose | Arguments |
|--------|---------|-----------|
| `helm_workflow_guide` | Complete workflow documentation | *(none)* |
| `helm_quick_start` | Quick start for common operations | *(none)* |
| `helm_installation_guidelines` | Installation best practices | *(none)* |
| `helm_troubleshooting_guide` | Troubleshooting common issues | `error_type` |
| `helm_security_checklist` | Security considerations | *(none)* |
| `helm_upgrade_guide` | Upgrade guide for charts | `chart_name` |
| `helm_rollback_procedures` | Rollback step-by-step guide | `release_name` |

---

## Recommended Workflow

### For New Installations
1. `helm_ensure_repository` → Ensure repository is available (if needed)
2. `helm_search_charts` → Find the chart
3. `helm_get_chart_info` → Review chart details
4. `kubernetes_get_cluster_info` → Verify cluster
5. `kubernetes_check_prerequisites` → Validate requirements
6. `helm_validate_values` → Validate configuration
7. `helm_dry_run_install` → Preview installation
8. `helm_install_chart` → Deploy to cluster
9. `helm_monitor_deployment` → Track deployment health

### For Upgrades
1. `helm_get_release_status` → Check current state
2. `helm_validate_values` → Validate new values
3. `helm_upgrade_release` → Perform upgrade
4. `helm_monitor_deployment` → Monitor upgrade

### For Troubleshooting
1. `helm_get_release_status` → Check release status
2. `kubernetes_get_helm_releases` → List all releases
3. Use `helm_troubleshooting_guide` prompt with appropriate `error_type`
4. If needed: `helm_rollback_release` → Rollback to working version

### For Rollbacks
1. `kubernetes_get_helm_releases` → Review release history
2. `helm_rollback_release` → Execute rollback
3. `helm_get_release_status` → Verify rollback success

### For Multi-Cluster Operations
1. `kubernetes_list_contexts` → List all available contexts
2. `kubernetes_set_context` → Switch to the desired cluster context
3. `kubernetes_get_cluster_info` → Verify you're connected to the correct cluster
4. Proceed with your Helm operations (install, upgrade, etc.)

---

## Best Practices

When interacting with this server:

1. **ALWAYS** use `helm_workflow_guide` or `helm_quick_start` prompts for guidance
2. **ALWAYS** consult `helm://best_practices` resource before deployments
3. **ALWAYS** validate with `helm_validate_values` before installation
4. **ALWAYS** use `helm_dry_run_install` before actual installation
5. **ALWAYS** use namespace scoping and RBAC for production workloads
6. **NEVER** hardcode secrets in values files
7. **ALWAYS** use version pinning for critical workloads
8. **ALWAYS** monitor deployments with `helm_monitor_deployment`
9. **ALWAYS** have a rollback plan using `helm_rollback_procedures` prompt
10. **ALWAYS** use `helm_security_checklist` prompt for production deployments

---

## Examples

- "Search for postgresql charts" → Use `helm_search_charts`
- "Add the prometheus-community repository" → Use `helm_ensure_repository(repo_name="prometheus-community")`
- "Install nginx-ingress in production namespace" → Follow installation workflow
- "Upgrade my-app release to latest version" → Follow upgrade workflow
- "My pods are in CrashLoopBackOff" → Use `helm_troubleshooting_guide` with `error_type="pod-crashloop"`
- "Rollback my-release to previous version" → Follow rollback workflow
- "What security checks should I do?" → Use `helm_security_checklist` prompt
- "Show me all releases in the cluster" → Use `kubernetes_get_helm_releases`
- "List all Kubernetes contexts" → Use `kubernetes_list_contexts`
- "Switch to production cluster context" → Use `kubernetes_set_context(context_name="production-cluster")`

---

For detailed documentation, use the `helm_workflow_guide` prompt or consult the `helm://best_practices` resource.
 