"""Pipeline onboarding guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from kargo_mcp_server.prompts.base import BasePrompt


class OnboardingPrompts(BasePrompt):
    """Pipeline onboarding workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="kargo-pipeline-onboarding-guided",
            description="Guided workflow for setting up a new Kargo promotion pipeline",
        )
        def kargo_pipeline_onboarding_guided(
            project: str,
            warehouse_name: str = "default-warehouse",
            stage_prefix: str = "env"
        ) -> list[PromptMessage]:
            """Pipeline onboarding guide."""
            prompt_text = f"""# 🚀 Kargo Pipeline Onboarding Guide: {project}

## Onboarding Details
- **Project**: {project}
- **Warehouse**: {warehouse_name}
- **Stage Prefix**: {stage_prefix}

---

## What is Pipeline Onboarding?

Onboarding in Kargo means setting up the continuous promotion delivery pipeline for your application.
It involves defining:
1. **Warehouse**: The entry point that watches for new artifacts (Git commits, Container Images, Helm charts).
2. **PromotionTask**: The reusable step sequence that executes during each promotion (e.g., Git clone → update manifests → push → ArgoCD sync).
3. **Stages**: The environments (e.g., test, uat, prod) forming a DAG (Directed Acyclic Graph) for progressive promotion.

---

## Phase 1: Verify Project

### Check if your Project exists:

1. **Get Project Details**:
   ```
   Tool: kargo_project_mgmt(action="get", ...)
   Args:
     - name: {project}
   ```
   
   If the project doesn't exist, create it:
   ```
   Tool: kargo_project_mgmt(action="create", ...)
   Args:
     - name: {project}
     - auto_promotion: true
   ```

---

## Phase 2: Create the Warehouse

The warehouse watches your artifact repositories. Use the intelligent subscription builder to create it:

1. **Create Warehouse with Subscriptions**:
   ```
   Tool: kargo_warehouse_mgmt(action="upsert", ...)
   Args:
     - project: {project}
     - warehouse_name: {warehouse_name}
     - subscriptions:
       - type: "image"
         repo_url: "<your-image-registry>"
         semver_constraint: "^1.0.0"
       - type: "git"
         repo_url: "<your-git-repo-url>"
         branch: "main"
   ```

2. **Verify Warehouse**:
   ```
   Tool: kargo_warehouse_mgmt(action="get", ...)
   Args:
     - project: {project}
     - warehouse_name: {warehouse_name}
   ```

3. **Trigger Artifact Discovery**:
   ```
   Tool: kargo_warehouse_mgmt(action="refresh", ...)
   Args:
     - project: {project}
     - warehouse_name: {warehouse_name}
   ```
   This forces Kargo to discover the latest artifacts and produce `Freight`.

---

## Phase 3: Create the PromotionTask

The PromotionTask defines what happens during each promotion. Use a preset for common GitOps workflows:

1. **Create PromotionTask using a Preset**:
   ```
   Tool: kargo_promotion_task_mgmt(action="upsert", ...)
   Args:
     - project: {project}
     - task_name: "promote"
     - preset: "gitops-image-update"
     - git_repo_url: "<your-git-repo-url>"
     - image_repo_url: "<your-image-registry>"
     - argocd_app_name_pattern: "{project}-${{{{ ctx.stage }}}}"
   ```

   Available presets:
   - `gitops-image-update`: Clone → yaml-update → commit → push → argocd-update
   - `gitops-kustomize`: Clone → kustomize-set-image → build → commit → push → argocd-update
   - `gitops-helm-template`: Clone → helm-template → commit → push → argocd-update

---

## Phase 4: Create Pipeline Stages

Define the promotion DAG (e.g., Warehouse → Test → Prod).

1. **Create First Stage (e.g., Test)** — receives freight directly from the warehouse:
   ```
   Tool: kargo_stage_mgmt(action="upsert", ...)
   Args:
     - project: {project}
     - stage_name: {stage_prefix}-test
     - requested_freight_origins: [{{"kind": "Warehouse", "name": "{warehouse_name}"}}]
     - promotion_template_ref: "promote"
   ```

2. **Create Second Stage (e.g., Prod)** — receives freight from the test stage:
   ```
   Tool: kargo_stage_mgmt(action="upsert", ...)
   Args:
     - project: {project}
     - stage_name: {stage_prefix}-prod
     - requested_freight_origins: [{{"kind": "Warehouse", "name": "{warehouse_name}", "stages": ["{stage_prefix}-test"]}}]
     - promotion_template_ref: "promote"
   ```

---

## Phase 5: Verification

1. **Check the Topology (DAG)**:
   ```
   Tool: kargo_describe_topology
   Args:
     - project: {project}
   ```
   Expected: `{warehouse_name}` → `{stage_prefix}-test` → `{stage_prefix}-prod`.

2. **Check for Discovered Freight**:
   ```
   Tool: kargo_freight_mgmt(action="list", ...)
   Args:
     - project: {project}
   ```
   Expected: At least one freight item available from the warehouse.

---

## ✅ Pipeline Onboarding Complete!

Your continuous promotion pipeline is now configured.
To push changes, simply run the `kargo-promotion-guided` prompt to safely promote the available freight through your stages.
"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text)
                )
            ]
