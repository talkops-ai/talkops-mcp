# Pipeline Onboarding Guided Workflow

**Goal**: Set up a complete Kargo continuous promotion pipeline from scratch — including project, credentials, warehouse, promotion task, and stages.

> **Prompt**: `kargo-pipeline-onboarding-guided(project="demo-project", warehouse_name="default-warehouse", stage_prefix="env")`

---

## 1. Verify Project

The first step is to verify the Kargo project boundary exists. Projects in Kargo are namespace-level boundaries that isolate pipelines.

**Natural Language Prompt:**
```text
Check if the project 'demo-project' exists. If not, create it.
```

**Tool Execution:**
```python
kargo_project_mgmt(
    action="get",
    name="demo-project"
)
```

If the project doesn't exist, create it:
```python
kargo_project_mgmt(
    action="create",
    name="demo-project",
    auto_promotion=True
)
```

---

## 2. Setup Repository Credentials

Before creating a warehouse, ensure Kargo can authenticate to your artifact repositories.

**Natural Language Prompt:**
```text
Create Git credentials for repo 'https://github.com/org/repo.git' in project 'demo-project'.
```

**Tool Execution:**
```python
kargo_credentials_mgmt(
    action="create",
    project="demo-project",
    name="git-creds",
    type="git",
    repo_url="https://github.com/org/repo.git",
    username="<username>",
    password="<token>"
)
```

---

## 3. Create the Warehouse

The Warehouse watches your artifact repositories. Use declarative subscriptions — no raw YAML needed.

**Natural Language Prompt:**
```text
Create a warehouse 'default-warehouse' in project 'demo-project' that watches the container image 'ghcr.io/org/app' and the Git repo 'https://github.com/org/repo.git'.
```

**Tool Execution:**
```python
kargo_warehouse_mgmt(
    action="upsert",
    project="demo-project",
    warehouse_name="default-warehouse",
    subscriptions=[
        {"type": "image", "repo_url": "ghcr.io/org/app", "semver_constraint": "^1.0.0"},
        {"type": "git", "repo_url": "https://github.com/org/repo.git", "branch": "main"}
    ]
)
```

### Trigger Discovery

Force Kargo to discover the latest artifacts and produce Freight payloads.

**Natural Language Prompt:**
```text
Refresh the warehouse 'default-warehouse' in project 'demo-project' to discover new artifacts.
```

**Tool Execution:**
```python
kargo_warehouse_mgmt(action="refresh", 
    project="demo-project",
    warehouse_name="default-warehouse"
)
```

---

## 4. Create the PromotionTask

Define the reusable promotion workflow using a built-in preset.

**Natural Language Prompt:**
```text
Create a promotion task called 'promote' in project 'demo-project' using the gitops-image-update preset for the Git repo and image.
```

**Tool Execution:**
```python
kargo_promotion_task_mgmt(
    action="upsert",
    project="demo-project",
    task_name="promote",
    preset="gitops-image-update",
    git_repo_url="https://github.com/org/repo.git",
    image_repo_url="ghcr.io/org/app",
    argocd_app_name_pattern="demo-project-${{ ctx.stage }}"
)
```

Available presets:
- `gitops-image-update` — Clone → yaml-update → commit → push → argocd-update
- `gitops-kustomize` — Clone → kustomize-set-image → build → commit → push → argocd-update
- `gitops-helm-template` — Clone → helm-template → commit → push → argocd-update

---

## 5. Create Pipeline Stages

Build the promotion DAG by creating stages that reference the warehouse and each other.

**Natural Language Prompt:**
```text
Create test and prod stages for project 'demo-project' connected as: warehouse → test → prod.
```

**Tool Execution — Test Stage:**
```python
kargo_stage_mgmt(
    action="upsert",
    project="demo-project",
    stage_name="env-test",
    requested_freight_origins=[{"kind": "Warehouse", "name": "default-warehouse"}],
    promotion_template_ref="promote"
)
```

**Tool Execution — Prod Stage:**
```python
kargo_stage_mgmt(
    action="upsert",
    project="demo-project",
    stage_name="env-prod",
    requested_freight_origins=[{"kind": "Warehouse", "name": "default-warehouse", "stages": ["env-test"]}],
    promotion_template_ref="promote"
)
```

---

## 6. Verify Pipeline Topology

Confirm the DAG is correctly assembled.

**Natural Language Prompt:**
```text
Describe the topology of the pipeline for project 'demo-project'.
```

**Tool Execution:**
```python
kargo_describe_topology(
    project="demo-project"
)
```

**Expected DAG Structure:**
`default-warehouse` → `env-test` → `env-prod`

---

## 7. Locate Initial Freight

Confirm that artifacts are entering the start of the pipeline.

**Natural Language Prompt:**
```text
List all available freight for project 'demo-project'.
```

**Tool Execution:**
```python
kargo_freight_mgmt(action="list", 
    project="demo-project"
)
```

If Freight exists, the pipeline is successfully discovering new commits/images and is ready for Promotion operations.
