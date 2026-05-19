# Kargo MCP Server — Application Workflow Journeys

**A comprehensive guide to how Tools, Resources, and Prompts coordinate across real-world continuous promotion scenarios.**

> 💬 **New to the tools?** See the **[README.md](../../README.md)** for an overview of all tools and resources available in this server.

---

## Table of Contents

1. [Workflow 1: Pipeline Onboarding](#1-workflow-1-pipeline-onboarding)
2. [Workflow 2: Manual Approval](#2-workflow-2-manual-approval)
3. [Workflow 3: Promotion Execution](#3-workflow-3-promotion-execution)
4. [Workflow 4: Emergency Rollback](#4-workflow-4-emergency-rollback)
5. [Workflow 5: Troubleshooting](#5-workflow-5-troubleshooting)

---

## 1. Workflow 1: Pipeline Onboarding

### Scenario

You have a new Kargo project and want to set up the full continuous promotion pipeline from scratch — including warehouse, promotion task, stages, and credentials.

### Journey Diagram

```mermaid
flowchart TD
    A["1️⃣ GET PROJECT\nkargo_project_mgmt\n(action=get, name=project_name)"] --> B{"Exists?"}
    
    B -->|"NO"| CREATE["CREATE PROJECT\nkargo_project_mgmt\n(action=create, name=project_name)"]
    
    CREATE --> CREDS
    B --> |"YES"| CREDS["2️⃣ SETUP CREDENTIALS\nkargo_credentials_mgmt\n(action=create)\n🔐 Git/Image auth"]
    
    CREDS --> C["3️⃣ CREATE WAREHOUSE\nkargo_warehouse_mgmt\n(action=upsert)\n📦 Declarative subscriptions\n(image, git, chart)"]
    
    C --> PT["4️⃣ CREATE PROMOTION TASK\nkargo_promotion_task_mgmt\n(action=upsert)\n🔧 Preset: gitops-image-update"]
    
    PT --> D["5️⃣ CREATE STAGES\nkargo_stage_mgmt\n(action=upsert)\n🔗 Build the DAG"]
    
    D --> E["6️⃣ REFRESH WAREHOUSE\nkargo_warehouse_mgmt\n(action=refresh)\n🟩 Forces artifact discovery"]
    
    E --> F["7️⃣ VERIFY DAG\nkargo_describe_topology\n(project)\nShows Warehouse → Stage flow"]
    
    F --> G["8️⃣ VERIFY FREIGHT\nkargo_freight_mgmt\n(action=list)"]

    G --> H["✅ Ready for\nPromotion"]

    style H fill:#4e9e6b
    style CREATE fill:#c57b7b
```

### Tool & Resource Coordination

| Phase | Tools Used | Resources Polled | Purpose |
|-------|-----------|-----------------|---------|
| Pre-flight | `kargo_project_mgmt` | `kargo://projects/{project}` | Verify or create the namespace |
| Credentials | `kargo_credentials_mgmt(action="create")` | — | Authenticate Kargo to Git/Image repos |
| Warehouse | `kargo_warehouse_mgmt(action="upsert")` | — | Create warehouse with image/git/chart subscriptions |
| PromotionTask | `kargo_promotion_task_mgmt(action="upsert")` | — | Create promotion steps using a preset (e.g., `gitops-image-update`) or custom steps |
| Stages | `kargo_stage_mgmt(action="upsert")` | — | Build the promotion DAG |
| Discovery | `kargo_warehouse_mgmt(action="refresh")` | — | Force Kargo to pull new Git/Image artifacts |
| Verification | `kargo_describe_topology`, `kargo_freight_mgmt(action="list")` | — | Validate that Freight was generated and the DAG is correct |

**Detailed Guide:** [ONBOARDING_TEST_GUIDE.md](ONBOARDING_TEST_GUIDE.md)

---

## 2. Workflow 2: Manual Approval

### Scenario

A high-risk stage (e.g., Production) requires human or external verification before a payload can enter.

### Journey Diagram

```mermaid
flowchart TD
    A["1️⃣ LIST FREIGHT\nkargo_freight_mgmt\n(action=list)"] --> B["Identify candidate\npassed upstream"]
    
    B --> C["2️⃣ INSPECT FREIGHT\nkargo_freight_mgmt\n(action=get)\nShows Git SHAs, Image digests"]
    
    C --> D{"Human/Agent\nVerification"}
    
    D -->|"REJECTED"| REJECT["❌ Do not approve"]
    
    D -->|"VERIFIED"| E["3️⃣ APPROVE FREIGHT\nkargo_freight_mgmt\n(action=approve)\n🟩 Writes approval to Stage"]

    E --> G["✅ Ready for\nPromotion"]

    style G fill:#4e9e6b
    style REJECT fill:#c57b7b
```

### Tool & Resource Coordination

| Phase | Tools Used | Resources Polled | Purpose |
|-------|-----------|-----------------|---------|
| Identify | `kargo_freight_mgmt(action="list")` | `kargo://projects/{project}/freight/{freight_id}` | Find payloads verified in upstream stages |
| Verify | `kargo_freight_mgmt(action="get")` | — | Check exact artifact content (Git/Image) |
| Approve | `kargo_freight_mgmt(action="approve")` | `kargo://projects/{project}/stages/{stage}` | Gate the payload for promotion |

**Detailed Guide:** [APPROVAL_TEST_GUIDE.md](APPROVAL_TEST_GUIDE.md)

---

## 3. Workflow 3: Promotion Execution

### Scenario

You want to move an approved Freight payload into a Stage.

### Journey Diagram

```mermaid
flowchart TD
    A["1️⃣ STAGE HEALTH\nkargo_stage_mgmt\n(action=get)"] --> B{"Healthy?"}
    
    B -->|"NO"| TROUBLESHOOT["Refer to Troubleshooting"]
    
    B --> |"YES"| C["2️⃣ EXECUTE PROMOTION\nkargo_promotion_mgmt\n(action=create)\n🟩 Creates PromotionTask"]
    
    C --> D["3️⃣ MONITOR\nkargo_promotion_mgmt\n(action=get)\nPoll every 10s"]
    
    D --> E{"Task Phase"}
    
    E -->|"Failed"| FAIL["❌ Promotion Failed\n(Abort)"]
    
    E -->|"Successful"| F["4️⃣ FINAL CHECK\nkargo://projects/{project}/stages/{stage}\nVerify current_freight"]

    F --> G["✅ Stage Updated"]

    style G fill:#4e9e6b
    style FAIL fill:#c57b7b
    style TROUBLESHOOT fill:#e6c229
```

### Tool & Resource Coordination

| Phase | Tools Used | Resources Polled | Purpose |
|-------|-----------|-----------------|---------|
| Pre-flight | `kargo_stage_mgmt(action="get")`, `kargo_freight_mgmt(action="list")` | — | Ensure stage is ready to receive Freight |
| Execution | `kargo_promotion_mgmt(action="create")` | — | Trigger Kargo Promotion |
| Monitor | `kargo_promotion_mgmt(action="get")` | `kargo://projects/{project}/promotions/{promotion_name}` | Track Promotion steps (Git clone, Kustomize, ArgoCD sync) |
| Verify | — | `kargo://projects/{project}/stages/{stage}` | Confirm `current_freight` is updated |

**Detailed Guide:** [PROMOTION_TEST_GUIDE.md](PROMOTION_TEST_GUIDE.md)

---

## 4. Workflow 4: Emergency Rollback

### Scenario

A promotion caused an outage. You need to roll back immediately using Kargo's "Roll Forward" paradigm.

### Journey Diagram

```mermaid
flowchart TD
    A["1️⃣ ABORT RUNNING\nkargo_promotion_mgmt\n(action=abort)\n🟩 Stop active degradation"] --> B["2️⃣ LOCATE STABLE\nkargo_freight_mgmt\n(action=list)"]
    
    B --> C["Identify previous\nstable Freight ID"]
    
    C --> D["3️⃣ ROLL FORWARD\nkargo_promotion_mgmt\n(action=create)\n🟩 Deploy old payload"]
    
    D --> E["Monitor Promotion\n(See Workflow 3)"]

    E --> G["✅ System Restored"]

    style G fill:#4e9e6b
    style A fill:#e6c229
```

### Tool & Resource Coordination

| Phase | Tools Used | Resources Polled | Purpose |
|-------|-----------|-----------------|---------|
| Halt | `kargo_promotion_mgmt(action="abort")` | `kargo://projects/{project}/promotions/{promotion_name}` | Stop broken state transitions |
| Locate | `kargo_freight_mgmt(action="list")` | — | Find the last known good configuration |
| Restore | `kargo_promotion_mgmt(action="create")` | — | Trigger the roll-forward operation |

**Detailed Guide:** [ROLLBACK_TEST_GUIDE.md](ROLLBACK_TEST_GUIDE.md)

---

## 5. Workflow 5: Troubleshooting

### Scenario

A stage is degraded or a promotion is stuck.

### Journey Diagram

```mermaid
flowchart TD
    A["1️⃣ CHECK STAGE\nkargo://projects/{project}/stages/{stage}"] --> B{"Error Type"}
    
    B -->|"Stage Degraded"| C["2️⃣ CHECK DIAGNOSTICS\nkargo_describe_topology\n(project)"]
    
    B -->|"Promotion Failed"| D["3️⃣ TRACE PROMOTION\nkargo_promotion_mgmt\n(action=get)"]
    
    C --> E{"Root Cause"}
    D --> E
    
    E -->|"Flaky Verification"| F1["kargo_stage_mgmt\n(action=reverify)"]
    E -->|"Stuck Process"| F2["kargo_promotion_mgmt\n(action=abort)"]
    E -->|"Bad Code"| F3["Push fix & refresh\nwarehouse"]

    style F1 fill:#add8e6
    style F2 fill:#add8e6
    style F3 fill:#add8e6
```

### Tool & Resource Coordination

| Phase | Tools Used | Resources Polled | Purpose |
|-------|-----------|-----------------|---------|
| Diagnosis | `kargo_promotion_mgmt(action="get")`, `kargo_project_mgmt(action="get")` | `kargo://projects/{project}/stages/{stage}` | Read raw K8s conditions and error messages |
| Remediation | `kargo_stage_mgmt(action="reverify")`, `kargo_promotion_mgmt(action="abort")` | — | Retry flaky tests or kill stuck processes |

**Detailed Guide:** [TROUBLESHOOTING_TEST_GUIDE.md](TROUBLESHOOTING_TEST_GUIDE.md)
