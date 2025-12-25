# ArgoCD MCP Server - Workflow Architecture

## Overview

This document outlines the **ArgoCD MCP Server** architecture, following the MCP standard three-component model. This architecture is designed to manage Kubernetes workloads using GitOps principles.

- **TOOLS (29 total)**: Atomic operations for discovery, deployment, repository management, and project management.
- **PROMPTS (7 total)**: Guided, step-by-step workflows for complex operations.
- **RESOURCES (5 total)**: Real-time data streams for monitoring and status tracking.

---

## 🏗️ LAYER 1: TOOLS (The Capabilities)

The server exposes 29 distinct tools categorized by function.

### 1. Application Management (7 tools)
*CRUD operations for ArgoCD Applications.*
- `list_applications`: Discover apps with filtering.
- `get_application_details`: Deep dive into app configuration and state.
- `create_application`: Register new apps in ArgoCD.
- `update_application`: Modify existing app config.
- `delete_application`: Remove apps.
- `validate_application_config`: Pre-deployment validation check.
- `get_application_events`: Specific history and events.

### 2. Deployment Executor (10 tools)
*Core sync and state operations.*
- `sync_application`: The primary deployment trigger.
- `get_application_diff`: Critical pre-sync check (what will change?).
- `get_sync_status`: Monitor ongoing operations.
- `rollback_application` / `rollback_to_revision`: Recovery mechanisms.
- `get_application_logs`: Debugging support with concise summaries and automatic error detection.
- `prune_resources`: Cleanup orphaned resources.
- `hard_refresh` / `soft_refresh`: Cache management.
- `cancel_deployment`: Emergency stop.

### 3. Repository Management (7 tools)
*Git repository onboarding and lifecycle management.*
- `onboard_repository_https`: Onboard Git repositories via HTTPS (credentials from env vars).
- `onboard_repository_ssh`: Onboard Git repositories via SSH (key from file path).
- `list_repositories`: List all registered repositories.
- `get_repository`: Get repository details and connection status.
- `validate_repository_connection`: Test repository connectivity.
- `delete_repository`: Remove registered repositories.
- `generate_repository_secret_manifest`: Generate Kubernetes Secret manifests for repo auth.

### 4. Project Management (5 tools)
*ArgoCD project administration and access control.*
- `create_project`: Create new ArgoCD projects with RBAC policies.
- `list_projects`: List all projects.
- `get_project`: Get project details and policies.
- `delete_project`: Remove projects.
- `generate_project_manifest`: Generate AppProject YAML manifests.

---

## 📋 LAYER 2: PROMPTS (The Workflows)

Prompts orchestrate multiple tools into cohesive, safe workflows.

### 1. `deploy_new_version`
**Goal:** Generic safe deployment wrapper.
**Flow:**
1.  **Validate**: Checks cluster connectivity and app existence.
2.  **Diff**: Calls `get_application_diff` to show pending changes.
3.  **Review**: Asks user to confirm changes.
4.  **Deploy**: Calls `sync_application`.
5.  **Monitor**: Polls status until completion.

### 2. `rollback_decision`
**Goal:** Guided recovery from failure.
**Flow:**
1.  **Assess**: Shows current version and history (`get_application_details`).
2.  **Options**: Presents choice between "Rollback 1 step" or "Specific Revision".
3.  **Impact**: Calls `get_application_diff` to show what reversions will happen.
4.  **Execute**: Runs the chosen rollback tool.

### 3. `post_deployment_validation`
**Goal:** Comprehensive health check.
**Flow:**
1.  **Status**: Checks `sync_status` and `health_status`.
2.  **Pods**: Verifies pod readiness and restart counts.
3.  **Logs**: Scans recent logs for errors.
4.  **Metrics**: Validates error rates and latency.

---

## 📡 LAYER 3: RESOURCES (The Data)

Real-time read-only streams for monitoring and context.

| URI Template | Description |
| :--- | :--- |
| `argocd://applications/{cluster_name}` | List of all apps with their live health/sync state. |
| `argocd://application-metrics/{cluster}/{app}` | Live metrics (CPU, Memory, Error Rates) for an app. |
| `argocd://sync-operations/{cluster_name}` | Active sync ops (good for finding stuck deployments). |
| `argocd://deployment-events/{cluster_name}` | Event stream (SyncStarted, SyncFailed, HealthChanged). |
| `argocd://cluster-health/{cluster_name}` | Aggregate health score of the cluster. |

---

## Workflow Diagram

```mermaid
graph TB
    User[User / AI Agent]
    
    User --> |Discovers & Executes| Prompts["📋 PROMPTS (7)<br/>Workflow Orchestration"]
    User --> |Discovers & Calls| Tools["✨ TOOLS (29)<br/>Atomic Operations"]
    User --> |Fetches| Resources["📚 RESOURCES (5)<br/>Real-time Data"]
    
    subgraph "ArgoCD MCP Server"
        
        subgraph "PROMPTS - Guided Workflows"
            P1["🚀 deploy_new_version<br/>(validate → diff → deploy → monitor)"]
            P2["🔄 rollback_decision<br/>(assess → options → impact → execute)"]
            P3["✅ post_deployment_validation<br/>(status → pods → logs → metrics)"]
        end
        
        subgraph "TOOLS - Model Controlled"
            subgraph Discovery["Discovery"]
                T1["list_applications"]
                T2["get_application_details"]
                T3["get_application_events"]
            end
            
            subgraph Deployment["Deployment"]
                T4["sync_application"]
                T5["create_application"]
                T6["update_application"]
                T7["delete_application"]
            end
            
            subgraph Validation["Validation"]
                T8["get_application_diff"]
                T9["validate_application_config"]
                T10["get_sync_status"]
            end
            
            subgraph Operations["Operations"]
                T11["rollback_application"]
                T12["rollback_to_revision"]
                T13["get_application_logs"]
                T14["prune_resources"]
                T15["cancel_deployment"]
            end
            
            subgraph Utilities["Utilities"]
                T16["hard_refresh"]
                T17["soft_refresh"]
            end
        end
        
        subgraph "RESOURCES - Live Streams"
            R1["argocd://applications/{cluster}<br/>(Live App List)"]
            R2["argocd://application-metrics/{app}<br/>(Live Metrics)"]
            R3["argocd://sync-operations/{cluster}<br/>(Active Ops)"]
            R4["argocd://deployment-events/{cluster}<br/>(Event Stream)"]
            R5["argocd://cluster-health/{cluster}<br/>(Aggregate Health)"]
        end
        
        P1 --> T8
        P1 --> T4
        P1 --> T10
        P1 --> R2
        
        P2 --> T2
        P2 --> T8
        P2 --> T11
        P2 --> T12
        P2 --> R3
        
        P3 --> T2
        P3 --> T13
        P3 --> R2
        P3 --> R4
    end
    
    Tools -->|Execute Against| ArgoCD_API["ArgoCD API<br/>(Core Operations)"]
    Tools -->|Control| K8s_API["Kubernetes API<br/>(Cluster State)"]
    Resources -.->|Feeds From| ArgoCD_API
    
    classDef prompt fill:#4A90E2,stroke:#2E5C8A,color:#fff
    classDef tool fill:#7ED321,stroke:#5FA118,color:#000
    classDef resource fill:#F5A623,stroke:#C17817,color:#000
    classDef api fill:#BD10E0,stroke:#7A0880,color:#fff
    
    class P1,P2,P3 prompt
    class T1,T2,T3,T4,T5,T6,T7,T8,T9,T10,T11,T12,T13,T14,T15,T16,T17 tool
    class R1,R2,R3,R4,R5 resource
    class ArgoCD_API,K8s_API api
```
