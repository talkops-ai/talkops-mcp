# Troubleshooting Guided Workflow

**Goal**: Diagnose why a promotion is stuck or why a stage is degraded.

> **Prompt**: `kargo-troubleshoot-guided(project="demo-project", stage="env-prod")`

---

## 1. Stage Health Check

Pull the full state of the stage to read raw Kubernetes condition errors.

**Natural Language Prompt:**
```text
Check the status of stage 'env-prod' in project 'demo-project' to find any errors.
```

**Resource Poll:**
```python
kargo://projects/demo-project/stages/env-prod
```
Look for `status.phase`, `status.error`, and the latest `conditions`.

---

## 2. Promotion Trace

If the issue stems from a stuck or failed promotion, trace the exact sub-steps to find what failed (e.g., Git authentication failure vs. ArgoCD sync timeout).

**Natural Language Prompt:**
```text
Get the details and error logs for promotion '<failed-promotion-name>' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_promotion_mgmt(action="get", 
    project="demo-project",
    promotion_name="<failed-promotion-name>"
)
```
Review the `status.phase` and `status.message` for precise error logs.

---

## 3. Project Diagnostics

Run topology and project-level diagnostics to hunt for systemic issues (e.g., broken DAG, missing warehouses, or disconnected Argo CD instances).

**Natural Language Prompt:**
```text
Run project diagnostics for 'demo-project'.
```

**Tool Execution:**
```python
kargo_describe_topology(
    project="demo-project"
)
```

```python
kargo_project_mgmt(
    action="get",
    name="demo-project"
)
```

---

## 4. Remediation Options

Depending on the diagnosis, you have several options:

### Option A: Flaky Verifications
If the failure is due to a flaky test, you can re-trigger verification without pushing new code.

**Natural Language Prompt:**
```text
Re-verify the 'env-prod' stage in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_stage_mgmt(action="reverify", 
    project="demo-project",
    stage="env-prod"
)
```

### Option B: Stuck Promotion
If a promotion is completely hung, abort it.

**Natural Language Prompt:**
```text
Abort the promotion '<stuck-promotion-name>' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_promotion_mgmt(action="abort", 
    project="demo-project",
    promotion_name="<stuck-promotion-name>"
)
```

### Option C: Bad Code
If the code is bad, wait for the developer to push a fix, refresh the warehouse, and promote the new Freight:

**Natural Language Prompt:**
```text
Refresh the warehouse 'default-warehouse' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_warehouse_mgmt(action="refresh", 
    project="demo-project",
    warehouse_name="default-warehouse"
)
```
