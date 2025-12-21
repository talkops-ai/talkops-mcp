"""Workflow-related prompts including the Helm Workflow Guide."""

from pathlib import Path
from mcp.types import Prompt, PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


# Load the workflow guide from static file
def _load_workflow_guide() -> str:
    """Load the HELM_WORKFLOW_GUIDE.md content from static directory."""
    static_dir = Path(__file__).parent.parent / 'static'
    workflow_guide_path = static_dir / 'HELM_WORKFLOW_GUIDE.md'
    
    try:
        return workflow_guide_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return "# Helm Workflow Guide\n\nWorkflow guide content not found."


class WorkflowPrompts(BasePrompt):
    """Workflow prompts including the comprehensive Helm Workflow Guide."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        def helm_workflow_guide() -> Prompt:
            """Comprehensive Helm MCP Server Workflow Guide.
            
            This prompt provides the complete workflow guide for using the Helm MCP Server,
            including tools reference, resources reference, prompts reference, workflow diagrams,
            detailed workflow steps, and best practices.
            """
            workflow_content = _load_workflow_guide()
            
            return Prompt(
                name="helm-workflow-guide",
                description="Comprehensive Helm MCP Server Workflow Guide with tools, resources, prompts reference, and best practices",
                arguments=[],  # No arguments required
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=workflow_content
                        )
                    )
                ]
            )
        
        @mcp_instance.prompt()
        def helm_quick_start() -> Prompt:
            """Quick start guide for common Helm operations.
            
            This prompt provides quick reference workflows for the most common Helm operations.
            """
            return Prompt(
                name="helm-quick-start",
                description="Quick start guide for common Helm operations",
                arguments=[],
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text="""# Helm MCP Server Quick Start

## Common Workflows

### 1. Install a New Chart

```
Step 1: Ensure repository is available (optional, auto-done by search)
→ helm_ensure_repository(repo_name="bitnami")

Step 2: Search for chart
→ helm_search_charts(query="postgresql", repository="bitnami")

Step 3: Get chart info
→ helm_get_chart_info(chart_name="postgresql", repository="bitnami")

Step 4: Validate your values
→ helm_validate_values(chart_name="bitnami/postgresql", values={...})

Step 5: Preview with dry-run
→ helm_dry_run_install(chart_name="bitnami/postgresql", release_name="my-db", namespace="production", values={...})

Step 6: Install
→ helm_install_chart(chart_name="bitnami/postgresql", release_name="my-db", namespace="production", values={...})

Step 7: Monitor
→ helm_monitor_deployment(release_name="my-db", namespace="production")
```

### 2. Upgrade an Existing Release

```
Step 1: Check current status
→ helm_get_release_status(release_name="my-db", namespace="production")

Step 2: Validate new values
→ helm_validate_values(chart_name="bitnami/postgresql", values={...new values...})

Step 3: Upgrade
→ helm_upgrade_release(release_name="my-db", chart_name="bitnami/postgresql", namespace="production", values={...})

Step 4: Monitor
→ helm_monitor_deployment(release_name="my-db", namespace="production")
```

### 3. Rollback a Release

```
Step 1: Check release history
→ kubernetes_get_helm_releases(namespace="production")

Step 2: Rollback
→ helm_rollback_release(release_name="my-db", namespace="production", revision=1)

Step 3: Verify
→ helm_get_release_status(release_name="my-db", namespace="production")
```

### 4. Switch Kubernetes Context (Multi-Cluster)

```
Step 1: List available contexts
→ kubernetes_list_contexts()

Step 2: Switch to desired context
→ kubernetes_set_context(context_name="production-cluster")

Step 3: Verify cluster info
→ kubernetes_get_cluster_info()
```

### 5. Troubleshoot Issues

```
Step 1: Check release status
→ helm_get_release_status(release_name="my-db", namespace="production")

Step 2: Get cluster info
→ kubernetes_get_cluster_info()

Step 3: Use troubleshooting prompt
→ helm_troubleshooting_guide(error_type="pod-crashloop")
```

### 6. Uninstall a Release

```
Step 1: List releases
→ kubernetes_get_helm_releases(namespace="production")

Step 2: Uninstall
→ helm_uninstall_release(release_name="my-db", namespace="production")
```

## Key Tools Summary

| Category | Primary Tools |
|----------|---------------|
| Discovery | `helm_search_charts`, `helm_get_chart_info`, `helm_ensure_repository` |
| Validation | `helm_validate_values`, `helm_render_manifests`, `helm_dry_run_install` |
| Installation | `helm_install_chart`, `helm_upgrade_release` |
| Monitoring | `helm_monitor_deployment`, `helm_get_release_status` |
| Management | `helm_rollback_release`, `helm_uninstall_release` |
| Kubernetes | `kubernetes_get_cluster_info`, `kubernetes_list_contexts`, `kubernetes_set_context`, `kubernetes_get_helm_releases` |

## Key Resources

| Resource | Purpose |
|----------|---------|
| `helm://releases` | List all deployed releases |
| `helm://charts/{repo}/{name}` | Get chart metadata |
| `kubernetes://cluster-info` | Get cluster information |

## Related Prompts

- `helm_installation_guidelines` - Installation best practices
- `helm_security_checklist` - Security considerations
- `helm_troubleshooting_guide` - Troubleshooting common issues
- `helm_upgrade_guide` - Upgrade guide for specific charts
- `helm_rollback_procedures` - Rollback step-by-step guide
- `helm_workflow_guide` - Complete workflow documentation"""
                        )
                    )
                ]
            )

