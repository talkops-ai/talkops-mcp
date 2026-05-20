"""Rollback guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from kargo_mcp_server.prompts.base import BasePrompt


class RollbackPrompts(BasePrompt):
    """Rollback workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="kargo-rollback-guided",
            description="Guided workflow for safely rolling back a Kargo promotion",
        )
        def kargo_rollback_guided(
            project: str,
            stage: str,
        ) -> list[PromptMessage]:
            """Rollback guidelines."""
            prompt_text = f"""# ⏪ Kargo Rollback Guide

## Context
- **Project**: {project}
- **Affected Stage**: {stage}

---

## The Kargo Rollback Paradigm
Kargo relies on a "Roll Forward" paradigm. To roll back, you do not revert the stage state directly. Instead, you promote a *previously known-good* `Freight` back into the stage. This guarantees that the exact same pipeline promotion mechanisms (ArgoCD Sync, Health Checks, Analysis) are executed.

---

## Phase 1: Halt and Assess

1. **Check for Running Promotions**:
   ```
   Tool: kargo_stage_mgmt(action="get", ...)
   Args:
     - project: {project}
     - stage_name: {stage}
   ```
   Look at `status.currentPromotion`. If a broken promotion is currently running or stuck, you must abort it.

2. **Abort Stuck Promotion** (If applicable):
   ```
   Tool: kargo_promotion_mgmt(action="abort", ...)
   Args:
     - project: {project}
     - promotion_name: <name-from-step-1>
   ```

---

## Phase 2: Identify Known-Good Freight

1. **List Historical Freight**:
   ```
   Tool: kargo_freight_mgmt(action="list", ...)
   Args:
     - project: {project}
   ```
   Find the `freight_id` that was running successfully *before* the outage.
   Alternatively, view the Git history or ask the user for the last stable version.

---

## Phase 3: Execute Rollback (Roll Forward)

1. **Approve the Old Freight** (If required):
   ```
   Tool: kargo_freight_mgmt(action="approve", ...)
   Args:
     - project: {project}
     - stage: {stage}
     - freight_id: <known-good-freight-id>
   ```

2. **Trigger the Rollback Promotion**:
   ```
   Tool: kargo_promotion_mgmt(action="create", ...)
   Args:
     - project: {project}
     - stage: {stage}
     - freight_id: <known-good-freight-id>
   ```

---

## Phase 4: Verification

1. **Monitor the Rollback**:
   ```
   Resource: kargo://projects/{project}/stages/{stage}
   ```
   Ensure the stage converges back to a `Healthy` phase.

## ✅ Rollback Complete!
The environment is now running the previous stable payload.
"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text)
                )
            ]
