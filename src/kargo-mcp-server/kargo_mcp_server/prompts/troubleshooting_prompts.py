"""Troubleshooting guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from kargo_mcp_server.prompts.base import BasePrompt


class TroubleshootingPrompts(BasePrompt):
    """Troubleshooting workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="kargo-troubleshoot-guided",
            description="Guided workflow for diagnosing failed or stuck Kargo promotions",
        )
        def kargo_troubleshoot_guided(
            project: str,
            stage: str,
        ) -> list[PromptMessage]:
            """Failed promotion troubleshooting guide."""
            prompt_text = f"""# 🛠 Kargo Troubleshooting Guide

## Context
- **Project**: {project}
- **Affected Stage**: {stage}

---

## Diagnostics Phase: What went wrong?

1. **Identify the Stage State**:
   ```
   Resource: kargo://projects/{project}/stages/{stage}
   ```
   Look at the full YAML manifest returned:
   - Check `status.phase`
   - Check `status.message`
   - Note the `status.currentPromotion` name.

2. **Inspect the Failed Promotion**:
   ```
   Tool: kargo_promotion_mgmt(action="get", ...)
   Args:
     - project: {project}
     - promotion_name: <name-from-step-1>
   ```
   Review the execution trace. Promotions are divided into steps (e.g., Git Clone, Kustomize Build, ArgoCD Sync). Look for the step that is `Errored` or `Failed`.

3. **Fetch Diagnostics**:
   ```
   Tool: kargo_project_mgmt(action="get", ...)
   Args:
     - project: {project}
   ```
   This pulls system-level errors for the project, such as broken RBAC, missing secrets, or disconnected Argo CD instances.

---

## Common Scenarios & Fixes

### Scenario A: "ArgoCD Sync Timeout" or "Health Check Failed"
**Cause**: The application deployed, but Pods are crashing (CrashLoopBackOff) or failing readiness probes. Kargo waits for Argo CD to report `Healthy`, which times out.
**Fix**: 
1. `kargo_promotion_mgmt(action="abort", ...)` to kill the stuck promotion.
2. Debug the Kubernetes Deployment directly (use `kubectl` or cluster inspection tools).
3. Push a fix to Git/Registry, wait for new Freight, and promote again.

### Scenario B: "Git Clone Auth Error"
**Cause**: Kargo cannot read from your GitOps repository to write the new Freight manifests.
**Fix**: Verify Kargo's repository credentials secret.

### Scenario C: "Verification Failed"
**Cause**: A post-promotion `AnalysisRun` (e.g., Argo Rollouts or Jobs) failed.
**Fix**: 
- Inspect the Prometheus metrics or the Job logs.
- If it was a flaky test, you can reverify the stage:
  ```
  Tool: kargo_stage_mgmt(action="reverify", ...)
  Args:
    - project: {project}
    - stage: {stage}
  ```

---

## Emergency Mitigation

If the environment is broken and blocking other work, execute a rollback:
Run the `kargo-rollback-guided` prompt to safely roll back the stage.
"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text)
                )
            ]
