# Manual Approval Guided Workflow

**Goal**: Safely identify and approve a Freight payload for a protected stage (e.g., Production).

> **Prompt**: `kargo-approval-guided(project="demo-project", stage="env-prod")`

---

## 1. Identify Freight Candidates

When a stage does not have `autoPromotionEnabled`, a human or external system must approve the payload before it can enter.

**Natural Language Prompt:**
```text
List all available freight for the 'demo-project' project.
```

**Tool Execution:**
```python
kargo_freight_mgmt(action="list", 
    project="demo-project"
)
```
The agent reviews the returned list, looking for Freight that has been successfully verified in upstream stages but is not yet approved for the target stage (`env-prod`).

---

## 2. Deep Dive Verification

Before approving, we must confirm exactly what code and images are in the payload.

**Natural Language Prompt:**
```text
Get the details of freight ID <id-from-step-1> in 'demo-project'.
```

**Tool Execution:**
```python
kargo_freight_mgmt(action="get", 
    project="demo-project",
    freight_id="<id-from-step-1>"
)
```

This returns the exact Git commits, Container Images, and Helm charts allowing the human (or agent) to verify the payload content.

---

## 3. Approve Freight

Once the Freight is verified, we approve it for the target stage.

**Natural Language Prompt:**
```text
Approve freight <your-selected-freight-id> for the 'env-prod' stage in 'demo-project'.
```

**Tool Execution:**
```python
kargo_freight_mgmt(action="approve", 
    project="demo-project",
    stage="env-prod",
    freight_id="<your-selected-freight-id>"
)
```

> **Note:** This requires write access (`MCP_ALLOW_WRITE=true`) and proper RBAC `promote` permissions.

---

## Next Steps

Approval simply marks the freight as *eligible* for the stage. It does not actively deploy it. To deploy it, proceed to the [Promotion Workflow](PROMOTION_TEST_GUIDE.md).
