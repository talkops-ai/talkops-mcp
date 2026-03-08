# ArgoCD MCP Server - User Guide

## 📖 Table of Contents

1. [Introduction](#introduction)
2. [How to Interact](#how-to-interact)
3. [Workflow Examples](#workflow-examples)
   - [Workflow 1: Repository Onboarding](#workflow-1-repository-onboarding)
   - [Workflow 2: Project & Tenant Management](#workflow-2-project--tenant-management)
   - [Workflow 3: Application Deployment](#workflow-3-application-deployment)
   - [Workflow 4: Application Debugging](#workflow-4-application-debugging)
   - [Workflow 5: Lifecycle & Maintenance](#workflow-5-lifecycle--maintenance)
   - [Workflow 6: Rollback & Recovery](#workflow-6-rollback--recovery)
   - [Workflow 7: Declarative GitOps](#workflow-7-declarative-gitops)
   - [Workflow 8: Monitoring & Metrics](#workflow-8-monitoring--metrics)
4. [Direct Tool Usage](#direct-tool-usage)
5. [Resource Monitoring](#resource-monitoring)
6. [Best Practices](#best-practices)

---

## Introduction

The ArgoCD MCP Server allows you to interact with ArgoCD through natural language using any MCP-compatible client (like Claude Desktop or MCP-enabled IDEs). This guide explains how you and your AI assistant can collaborate to manage your GitOps deployments securely and efficiently.

## How to Interact

The best way to interact with the server is by simply declaring your intent in **natural language**. When you ask the assistant to perform a task, it doesn't just blindly fire API calls. It selects structured workflows (called *Prompts*) to guide the process, ensures you have the right context, validates changes, and asks for your confirmation before executing actions.

If you know exactly what you want, you can also ask the assistant to call specific **Tools** directly.

---

## Workflow Examples

### Workflow 1: Repository Onboarding

**The Goal:** You want to add a GitHub, GitLab, or Bitbucket repository to ArgoCD so it can be used for your deployments.

**What you might say:**
> *"I want to onboard my GitHub repository https://github.com/myorg/myapp to ArgoCD"*  
> *"Help me add the GitHub repository git@github.com:myorg/backend-api.git using SSH authentication."*

**How it works under the hood:**

1. **Environment Check:** The assistant verifies your setup, looking for credentials in your environment variables (`GIT_PASSWORD` or an SSH key). This ensures secure authentication without exposing your tokens in chat.
2. **Connection Validation:** Instead of trying to create the repo blindly, the assistant runs the `validate_repository_connection` tool to test the credentials first.
3. **Registration:** Once confirmed, it executes the onboarding by calling `onboard_repository_https` or `onboard_repository_ssh`.
4. **Cleanup:** If you no longer need a repository, simply ask to remove it, and the assistant will run `delete_repository`.

---

### Workflow 2: Project & Tenant Management

**The Goal:** You want to logically group applications together and restrict where they can be deployed or what repositories they can pull from.

**What you might say:**
> *"Create an ArgoCD project called 'frontend-team' that can only deploy to the 'frontend' namespace."*  
> *"List all the projects currently in ArgoCD, and show me the details for 'example'."*

**How it works under the hood:**

1. **Project Creation:** When you need a new isolated environment, the assistant uses the `create_project` tool. It can scope this project so that it only permits code from your validated repositories and restricts deployments to specific target destination clusters/namespaces.
2. **Auditing & Cleanup:** The assistant can use `list_projects` and `get_project` to explore how your multi-tenant environment is configured, or use `delete_project` when a team's sandbox is no longer needed.

---

### Workflow 3: Application Deployment

**The Goal:** Deploy a new application from your Git repository to a Kubernetes cluster safely and predictably.

**What you might say:**
> *"Deploy my application from https://github.com/myorg/myapp to the production cluster using the 'frontend-team' project."*  
> *"Create the 'backend-api' application and enable auto-sync."*

**How it works under the hood:**

1. **Application Creation:** The assistant prepares the application using the `create_application` tool. You can ask it to enable `auto_sync`, pruning, and self-healing right from the chat.
2. **Deployment Preview:** Before touching the cluster (if auto-sync is off), the assistant calls `get_application_diff` to fetch a side-by-side comparison of which resources will change. The assistant will **pause to ask for your confirmation**.
3. **Execution & Monitoring:** If you say "Yes", the assistant triggers the deployment by calling `sync_application`. To keep you updated on the progress, it checks `get_sync_status`. 
4. **Abort:** If something looks wrong while the sync is running, tell the assistant to *"Cancel the deployment"*, and it will use `cancel_deployment` to immediately abort the ongoing operation.

---

### Workflow 4: Application Debugging

**The Goal:** Diagnose an application that's degraded or crashing in production, without having to dig through multiple UI dashboards.

**What you might say:**
> *"My app 'payment-service' is not working, help me debug it."*  
> *"Users are reporting 500 errors from checkout. Debug this please."*

**How it works under the hood:**

1. **Assessing the State:** The assistant grabs the high-level picture with the `get_application_details` tool to see if the app is *Degraded* or *OutOfSync*.
2. **Smart Log Analysis:** The assistant calls the `get_application_logs` tool to pull recent logs directly from the failing pods. It searches the logs for errors/exceptions and extracts them for you.
3. **Event Timeline Review:** To corroborate the logs, the assistant uses `get_application_events` to pull recent Kubernetes events, identifying patterns like `CrashLoopBackOff` initialization errors.
4. **Configuration Validation:** Finally, it checks to see if any missing ConfigMaps or Secrets are to blame by calling `validate_application_config`.

---

### Workflow 5: Lifecycle & Maintenance

**The Goal:** Update application configurations, clear stuck caches, or tear down applications gracefully.

**What you might say:**
> *"Enable auto-sync and self-healing on the 'hello-world' app."*  
> *"ArgoCD seems stuck, force a hard refresh on the frontend app."*  
> *"Delete the testing app and make sure to cascade delete its resources."*

**How it works under the hood:**

1. **Modifying Policies:** The assistant can instantly flip switches on your apps using `update_application`, saving you from manual UI clicks.
2. **Cache Refreshing:** If Git is updated but Argo is lagging, you can ask for a `soft_refresh` to hit the cache, or a `hard_refresh` to bypass ArgoCD's cache and forcefully ping your Git server.
3. **Orphaned Resources:** Want to clean up stray resources that were removed from Git? Ask the assistant to run `prune_resources`.
4. **Teardown:** When an app is no longer needed, it uses `delete_application` (with cascade enabled automatically if you want its Kubernetes resources destroyed with it).

---

### Workflow 6: Rollback & Recovery

**The Goal:** Revert a breaking change in production back to the last known stable state.

**What you might say:**
> *"URGENT: Latest deployment of checkout-service is broken, rollback immediately!"*  
> *"Roll back payment-api to the git hash 4888ba8."*

**How it works under the hood:**

1. **Evaluating History:** The assistant calls the `get_application_details` tool to look at your `sync_history` and identify healthy targets.
2. **Execution:** Unlike a basic undo button, the assistant is smart enough to use either `rollback_application` (to jump back a specific number of steps) or `rollback_to_revision` (if you want to target a specific, exact Git commit hash).
3. *(Note: If your app has Auto-Sync enabled, the assistant will automatically disable it first via `update_application` so ArgoCD doesn't immediately overwrite the rollback!)*

---

### Workflow 7: Declarative GitOps

**The Goal:** Generate raw Kubernetes YAML manifests for your configurations so you can commit them as code.

**What you might say:**
> *"Generate a Kubernetes Secret manifest for my GitHub repository."*  
> *"I want the declarative AppProject YAML for the production project."*

**How it works under the hood:**

A core tenet of GitOps is keeping *everything* in Git. Instead of manually applying things via the API, you can ask the assistant to generate ready-to-run YAML files.
1. The assistant uses `generate_repository_secret_manifest` to construct a properly structured `v1/Secret` labeled for ArgoCD, complete with your auth methods.
2. It uses `generate_project_manifest` to spit out an `AppProject` CRD.
3. You can then copy these manifests directly into your tracking repository.

---

### Workflow 8: Monitoring & Metrics

**The Goal:** Keep a pulse on the general health of your applications without constantly switching browser tabs.

**What you might say:**
> *"Show me the health status of all applications."*  
> *"Give me an overview of cluster health for production."*

**How it works under the hood:**

1. Given a query like "show me all apps", the assistant will execute `list_applications`. It parses the JSON response and summarizes the health (e.g., "9 apps are Healthy, 2 are Progressing"), highlighting the ones that require your attention.

---

## Direct Tool Usage

While workflows are fantastic for complex multi-stage tasks, sometimes you just need a quick data point. You can ask the assistant to use individual tools directly:

- **Need a status check?**
  *"What's the sync status of payment-api in production?"*  
  The assistant directly calls `get_sync_status`.

- **Need logs?**
  *"Show me the last 50 lines of logs from user-service."*  
  The assistant directly calls `get_application_logs`.

- **Want to run a quick config validation?**
  *"Is the configuration valid for checkout-service?"*  
  The assistant uses `validate_application_config`.

---

## Resource Monitoring

If your conversational client supports streaming the Model Context Protocol resources explicitly, you can ask the assistant to monitor real-time data streams for a live dashboard-like experience.

| Resource URI | What it provides | Update Frequency |
|-------------|------------------|------------------|
| `argocd://applications/{cluster}` | A list of all apps and their health/sync states | Every 5s |
| `argocd://application-metrics/{cluster}/{app}` | App metrics like pod readiness and restart counts | Every 10s |
| `argocd://sync-operations/{cluster}` | Active ongoing deployments and progress percentages | Every 2s |
| `argocd://deployment-events/{cluster}` | A real-time stream of all Kubernetes events related to ArgoCD apps | Real-time |
| `argocd://cluster-health/{cluster}` | Aggregated metrics showing overall health percentage of the cluster | Every 30s |

---

## Best Practices

To get the most out of your AI assistant:

### 1. Let the Assistant Orchestrate
Instead of micromanaging the tasks (*"Call onboard_repository_https, then create_application, then sync_application"*), simply declare your intent: *"Deploy my app from [repo] to [cluster]."* The assistant knows which prompts and tools to chain together.

### 2. Provide Good Context
If you're asking the assistant to debug an issue, providing a little context helps it zero in faster.
**Okay:** *"Something is wrong with payment-service."*
**Great:** *"The payment-service started returning 500 errors after the v2.1.0 deployment 30 minutes ago."*

### 3. Trust the Preview Process
When the assistant offers to show you a Diff Preview before deploying, read it carefully. The assistant is designed to ask for your manual confirmation before modifying production cluster states. Do not skip steps!

### 4. Lean on Smart Analysis
Don't just ask to see raw logs—ask the assistant to analyze them for you. Say *"Analyze the logs and tell me what's wrong."* Tools like `get_application_logs` have built-in smart parsing to highlight errors and extract context, saving you from reading thousands of lines of boilerplate output.

---

### Command Reference Guide

| User Intent | Core Tools Associated | Example Query |
|------------|-----------------------|---------------|
| Onboard a repo | `onboard_repository_https`, `validate_repository_connection` | *"Add repo [url] to ArgoCD"* |
| Manage projects | `create_project`, `list_projects` | *"Create 'example' project for frontend apps"* |
| Deploy an app | `create_application`, `sync_application` | *"Deploy [app] from [repo] to [cluster]"* |
| Manage Lifecycle | `hard_refresh`, `update_application`, `prune_resources` | *"Hard refresh the [app] and enable auto-sync"* |
| Debug an issue | `get_application_details`, `get_application_logs` | *"App [name] is failing on production, debug it"* |
| Rollback clearly | `rollback_application`, `rollback_to_revision` | *"Rollback [app] to the previous version"* |
| Cleanup | `delete_application`, `delete_repository` | *"Delete the [app] testing application entirely"* |
| GitOps YAML | `generate_project_manifest`, `generate_repository_secret_manifest` | *"Generate the AppProject YAML for production"* |

**Happy managing! 🚀**
