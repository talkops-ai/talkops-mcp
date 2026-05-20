# Emergency Rollback Guided Workflow

**Goal**: Return a broken environment to a stable state using the "Roll Forward" paradigm.

> **Prompt**: `kargo-rollback-guided(project="demo-project", stage="env-prod")`

---

## The "Roll Forward" Paradigm

Kargo does not have a native "rollback" button. Instead, it uses a **Roll Forward** paradigm. To roll back, you simply create a *new* promotion of an *old*, previously stable Freight ID.

---

## 1. Abort Current Chaos

If a promotion is currently stuck or failing, kill it to prevent further degradation.

**Natural Language Prompt:**
```text
Abort the stuck promotion '<stuck-promotion-name>' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_promotion_mgmt(action="abort", 
    project="demo-project",
    promotion_name="<stuck-promotion-name>"
)
```

---

## 2. Find Known Good State

Analyze the history of Freight to locate the ID that was stable *before* the outage.

**Natural Language Prompt:**
```text
List all freight in project 'demo-project' to find the previous stable ID.
```

**Tool Execution:**
```python
kargo_freight_mgmt(action="list", 
    project="demo-project"
)
```
Look for the `freight_id` that was running previously.

---

## 3. Roll Forward

Approve (if necessary) and execute a new promotion for the *old* Freight ID. The pipeline will execute identically, restoring the previous application state.

**Natural Language Prompt:**
```text
Promote the old stable freight '<old-stable-freight-id>' to the 'env-prod' stage in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_promotion_mgmt(action="create", 
    project="demo-project",
    stage="env-prod",
    freight_id="<old-stable-freight-id>"
)
```

Monitor this promotion until complete using the steps outlined in the [Promotion Workflow](PROMOTION_TEST_GUIDE.md).
