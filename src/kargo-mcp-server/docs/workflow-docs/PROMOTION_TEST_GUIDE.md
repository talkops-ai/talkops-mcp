# Promotion Execution Guided Workflow

**Goal**: Execute a `PromotionTask` to move Freight into a Stage.

> **Prompt**: `kargo-promotion-guided(project="demo-project", stage="env-prod")`

---

## 1. Pre-flight Checks

Before promoting, we must ensure the target stage is healthy and the freight is available.

**Natural Language Prompt:**
```text
Check the health of stage 'env-prod' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_stage_mgmt(action="get", 
    project="demo-project",
    stage_name="env-prod"
)
```

**Natural Language Prompt:**
```text
List all freight in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_freight_mgmt(action="list", 
    project="demo-project"
)
```

---

## 2. Create Promotion

Trigger the deployment of the selected Freight to the Stage.

**Natural Language Prompt:**
```text
Promote freight '<selected-freight-id>' to the 'env-prod' stage in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_promotion_mgmt(action="create", 
    project="demo-project",
    stage="env-prod",
    freight_id="<selected-freight-id>"
)
```
*Note: This command returns the `promotion_name` which is required for the next step.*

---

## 3. Monitor Promotion Loop

Watch the promotion task execute step-by-step (e.g., Git Clone, Kustomize, ArgoCD Sync).

**Natural Language Prompt:**
```text
Show the status of the 'env-prod' stage in project 'demo-project'.
```

**Resource Poll:**
```python
kargo://projects/demo-project/promotions/<promotion_name>
```

**Natural Language Prompt:**
```text
Get the details of promotion '<promotion_name>' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_promotion_mgmt(action="get", 
    project="demo-project",
    promotion_name="<promotion_name>"
)
```

---

## 4. Final Verification

Confirm that the Stage has successfully adopted the new Freight.

**Natural Language Prompt:**
```text
Check the status of stage 'env-prod' in project 'demo-project'.
```

**Resource Poll:**
```python
kargo://projects/demo-project/stages/env-prod
```
Verify that the `current_freight` matches the `freight_id` we just promoted, and that the stage's health is `Healthy`.
