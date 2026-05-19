"""Manual approval guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from kargo_mcp_server.prompts.base import BasePrompt


class ApprovalPrompts(BasePrompt):
    """Manual approval workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="kargo-approval-guided",
            description="Guided workflow for manual freight approval",
        )
        def kargo_approval_guided(
            project: str,
            stage: str,
        ) -> list[PromptMessage]:
            """Manual approval workflow guide."""
            prompt_text = f"""# 📝 Kargo Manual Approval Workflow

## Context
- **Project**: {project}
- **Target Stage**: {stage}

---

## Why is Manual Approval Required?
Stages without `autoPromotionEnabled` or high-risk environments (like production) require human or external system sign-off before Kargo will allow freight to enter.

---

## Phase 1: Identify Freight Candidates

1. **List Available Freight**:
   ```
   Tool: kargo_freight_mgmt(action="list", ...)
   Args:
     - project: {project}
   ```
   Review the returned list. Look for freight that has been successfully verified in upstream stages but is not yet approved for `{stage}`.

2. **Inspect Specific Freight**:
   ```
   Tool: kargo_freight_mgmt(action="get", ...)
   Args:
     - project: {project}
     - freight_id: <id-from-step-1>
   ```
   Verify the exact Git commits, Container Images, and Helm charts to ensure this is the intended release payload.

---

## Phase 2: Approve Freight

Once you have identified the correct `freight_id` and verified its upstream health:

1. **Execute Approval**:
   ```
   Tool: kargo_freight_mgmt(action="approve", ...)
   Args:
     - project: {project}
     - stage: {stage}
     - freight_id: <your-selected-freight-id>
   ```
   *Note: This requires write access (`MCP_ALLOW_WRITE=true`) and proper RBAC `promote` permissions.*

---

## Phase 3: Trigger Promotion

Approval simply marks the freight as *eligible* for the stage. It does not actively deploy it unless Auto-Promotion is enabled.

1. **Promote the Approved Freight**:
   ```
   Tool: kargo_promotion_mgmt(action="create", ...)
   Args:
     - project: {project}
     - stage: {stage}
     - freight_id: <your-selected-freight-id>
   ```

2. **Monitor the Promotion**:
   ```
   Tool: kargo_promotion_mgmt(action="get", ...)
   Args:
     - project: {project}
     - promotion_name: <name-returned-from-creation>
   ```

## ✅ Approval Complete!
"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text)
                )
            ]
