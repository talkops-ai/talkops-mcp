"""Promotion guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from kargo_mcp_server.prompts.base import BasePrompt


class PromotionPrompts(BasePrompt):
    """Promotion workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="kargo-promotion-guided",
            description="Guided workflow for promoting freight across stages",
        )
        def kargo_promotion_guided(
            project: str,
            target_stage: str,
        ) -> list[PromptMessage]:
            """Kargo promotion guidelines and best practices."""
            prompt_text = f"""# 🚀 Kargo Promotion Workflow

## Context
- **Project**: {project}
- **Target Stage**: {target_stage}

---

## What is a Promotion?
A promotion is the execution of a `PromotionTask` to transition a specific `Freight` (collection of artifacts) into a target `Stage`. 

---

## Phase 1: Pre-Promotion Checks

1. **Check Topology (DAG)**:
   ```
   Tool: kargo_describe_topology
   Args:
     - project: {project}
   ```
   Identify the upstream stages for `{target_stage}`.

2. **List Available Freight**:
   ```
   Tool: kargo_freight_mgmt(action="list", ...)
   Args:
     - project: {project}
   ```
   Find the `freight_id` you want to promote. Ensure it has been successfully verified in the upstream stages identified in Step 1.

3. **Check Target Stage Health**:
   ```
   Tool: kargo_stage_mgmt(action="get", ...)
   Args:
     - project: {project}
     - stage_name: {target_stage}
   ```
   Ensure the stage is healthy and has no conflicting or stuck promotions currently running.

---

## Phase 2: Execute Promotion

1. **Check if Approval is Needed**:
   If the stage requires manual approval, run the `kargo-approval-guided` prompt first, or execute:
   ```
   Tool: kargo_freight_mgmt(action="approve", ...)
   Args:
     - project: {project}
     - stage: {target_stage}
     - freight_id: <selected-freight-id>
   ```

2. **Create the Promotion**:
   ```
   Tool: kargo_promotion_mgmt(action="create", ...)
   Args:
     - project: {project}
     - stage: {target_stage}
     - freight_id: <selected-freight-id>
   ```

---

## Phase 3: Monitor & Verify

1. **Track Promotion Status**:
   ```
   Tool: kargo_promotion_mgmt(action="get", ...)
   Args:
     - project: {project}
     - promotion_name: <name-from-creation>
   ```
   Watch the `state` transition from `Pending` → `Running` → `Succeeded`.

2. **Verify Stage Health**:
   ```
   Resource: kargo://projects/{project}/stages/{target_stage}
   ```
   Ensure the `current_freight` matches your promoted freight and the stage phase is `Healthy`.

## ✅ Promotion Complete!
If the promotion gets stuck or fails, use the `kargo-troubleshoot-guided` prompt.
"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text)
                )
            ]
