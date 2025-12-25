# ArgoCD MCP Server - User Guide

## 📖 Table of Contents

1. [Introduction](#introduction)
2. [How to Interact](#how-to-interact)
3. [Workflow Examples](#workflow-examples)
   - [Repository Onboarding](#workflow-1-repository-onboarding)
   - [Application Deployment](#workflow-2-application-deployment)
   - [Application Debugging](#workflow-3-application-debugging)
   - [Rollback Scenario](#workflow-4-rollback-scenario)
   - [Monitoring & Metrics](#workflow-5-monitoring--metrics)
4. [Direct Tool Usage](#direct-tool-usage)
5. [Resource Monitoring](#resource-monitoring)
6. [Best Practices](#best-practices)

---

## Introduction

The ArgoCD MCP Server allows you to interact with ArgoCD through natural language using any MCP-compatible client (Claude Desktop, IDEs with MCP support, etc.). You can:

- **Use Prompts**: Guided workflows with step-by-step instructions
- **Call Tools Directly**: Execute specific operations
- **Monitor Resources**: Access real-time data streams

---

## How to Interact

### Using Natural Language (Recommended)

Simply describe what you want to do in natural language. The AI will:
1. Understand your intent
2. Select the appropriate prompt or tools
3. Execute the workflow
4. Guide you through steps requiring decisions

### Direct Prompt/Tool Invocation

You can also explicitly request prompts or tools:
- "Use the `onboard_github_repository` prompt for [repo-url]"
- "Call the `list_applications` tool for cluster production"

---

## Workflow Examples

## Workflow 1: Repository Onboarding

### 🎯 User Goal
Onboard a GitHub repository to ArgoCD so it can be used for deployments.

### 💬 User Query Examples

**Simple Query:**
```
"I want to onboard my GitHub repository https://github.com/myorg/myapp to ArgoCD"
```

**Detailed Query:**
```
"Help me add the GitHub repository git@github.com:myorg/backend-api.git to ArgoCD 
using SSH authentication and assign it to the 'backend-team' project"
```

**Quick Query:**
```
"Add this repo to ArgoCD: https://github.com/myorg/frontend"
```

---

### 🤖 What Happens (Agent Flow)

#### Step 1: Agent Selects Workflow
The agent recognizes this is a repository onboarding task and invokes:

**Prompt Used:** `onboard_github_repository`

**Parameters Detected:**
- `repo_url`: "https://github.com/myorg/myapp"
- `auth_method`: "https" (detected from URL)
- `project_name`: "default" (or extracted from query)

---

#### Step 2: Environment Check

**Agent Message:**
```
🔒 Checking environment setup for HTTPS authentication...

Required environment variables:
✓ GIT_PASSWORD: Set (token detected)
✓ GIT_USERNAME: Optional (empty for token auth)

You can proceed with onboarding.
```

**If credentials missing:**
```
❌ GIT_PASSWORD environment variable is not set.

Please set your GitHub personal access token:
export GIT_PASSWORD="ghp_your_token_here"

Generate token at: https://github.com/settings/tokens
Required scopes: repo (full control of private repositories)
```

---

#### Step 3: Validate Repository Connection

**Tool Called:** `validate_repository_connection`

**Agent Query:**
```
"Validating repository connection..."
```

**Tool Execution:**
```json
{
  "tool": "validate_repository_connection",
  "parameters": {
    "repo_url": "https://github.com/myorg/myapp"
  }
}
```

**Success Response:**
```
✅ Repository validation successful
✓ Repository is accessible
✓ Credentials are valid
✓ Connection established
```

**Failure Response:**
```
❌ Repository validation failed
Error: Authentication failed - Invalid token or credentials
→ Suggested action: Check your GIT_PASSWORD environment variable
```

---

#### Step 4: Onboard Repository

**Tool Called:** `onboard_repository_https`

**Agent Query:**
```
"Onboarding repository to ArgoCD..."
```

**Tool Execution:**
```json
{
  "tool": "onboard_repository_https",
  "parameters": {
    "repo_url": "https://github.com/myorg/myapp",
    "repo_type": "git",
    "enable_lfs": false,
    "project": "default"
  }
}
```

**Success Response:**
```
✅ Repository successfully onboarded!

Repository Details:
- URL: https://github.com/myorg/myapp
- Type: git
- Project: default
- Connection Status: Successful
- LFS Enabled: No

Next Steps:
→ Create applications using this repository
→ Use: create_application or full_application_deployment prompt
```

---

#### Step 5: Verification

**Tool Called:** `get_repository`

**Agent Query:**
```
"Verifying repository registration..."
```

**Tool Execution:**
```json
{
  "tool": "get_repository",
  "parameters": {
    "repo_url": "https://github.com/myorg/myapp"
  }
}
```

**Response:**
```
✅ Repository verified in ArgoCD

Repository Info:
- URL: https://github.com/myorg/myapp
- Type: git
- Connection: Successful
- Project: default
- Registered: 2025-12-25T10:30:00Z

You can now create applications using this repository!
```

---

### 📊 Complete Workflow Summary

**User Query:**
> "I want to onboard my GitHub repository https://github.com/myorg/myapp to ArgoCD"

**Tools Triggered (in order):**
1. **Prompt:** `onboard_github_repository`
2. **Tool:** `validate_repository_connection` (validation)
3. **Tool:** `onboard_repository_https` (onboarding)
4. **Tool:** `get_repository` (verification)

**Total Time:** ~5-10 seconds  
**User Interactions:** 0 (fully automated if credentials are set)

---

## Workflow 2: Application Deployment

### 🎯 User Goal
Deploy a new application from a Git repository to a Kubernetes cluster.

### 💬 User Query Examples

**Simple:**
```
"Deploy my application from https://github.com/myorg/myapp to production cluster"
```

**Detailed:**
```
"I want to deploy the 'backend-api' application from git@github.com:myorg/backend.git 
to the production cluster in the 'backend-prod' namespace. The manifests are in the 
'k8s/overlays/production' directory."
```

**With Version:**
```
"Deploy version v2.1.0 of myapp to staging cluster"
```

---

### 🤖 What Happens (Agent Flow)

#### Step 1: Agent Selects Workflow

**Prompt Used:** `full_application_deployment`

**Parameters Detected:**
- `repo_url`: "https://github.com/myorg/myapp"
- `app_name`: "myapp"
- `cluster_name`: "production"
- `namespace`: "myapp-prod"
- `path`: "k8s" (default)
- `project_name`: "default"

---

#### Step 2: Repository Check

**Agent Message:**
```
📦 Checking if repository is onboarded...
```

**Tool Called:** `get_repository`

**If Repository Not Onboarded:**
```
⚠️ Repository not found in ArgoCD

Would you like me to onboard it first?
→ I'll use the onboard_github_repository workflow
```

**User Response:**
```
"Yes, please onboard it"
```

*(Agent executes repository onboarding workflow from Workflow 1)*

---

#### Step 3: Create Application

**Tool Called:** `create_application`

**Agent Query:**
```
"Creating ArgoCD application..."
```

**Tool Execution:**
```json
{
  "tool": "create_application",
  "parameters": {
    "cluster_name": "production",
    "app_name": "myapp",
    "project": "default",
    "repo_url": "https://github.com/myorg/myapp",
    "path": "k8s",
    "target_revision": "HEAD",
    "destination_server": "https://kubernetes.default.svc",
    "destination_namespace": "myapp-prod",
    "auto_sync": false,
    "prune": true,
    "self_heal": true
  }
}
```

**Success Response:**
```
✅ Application created successfully

Application: myapp
Status: OutOfSync (not deployed yet)
Cluster: production
Namespace: myapp-prod
Repository: https://github.com/myorg/myapp
Path: k8s
Revision: HEAD

→ Ready for initial deployment
```

---

#### Step 4: Preview Changes

**Tool Called:** `get_application_diff`

**Agent Query:**
```
"Generating deployment preview..."
```

**Tool Execution:**
```json
{
  "tool": "get_application_diff",
  "parameters": {
    "cluster_name": "production",
    "app_name": "myapp"
  }
}
```

**Response:**
```
📋 Deployment Preview

Changes to be applied:

+ Deployment.apps/myapp
  - replicas: 3
  - image: myorg/myapp:latest
  - resources:
      requests: cpu=100m, memory=128Mi
      limits: cpu=500m, memory=512Mi

+ Service/myapp
  - type: ClusterIP
  - port: 8080

+ ConfigMap/myapp-config
  - data: (10 keys)

Total Resources: 3 new, 0 modified, 0 deleted

⚠️ Review carefully before proceeding!
```

**Agent asks:**
```
Do you want to proceed with the deployment?
(Required: User confirmation for production deployments)
```

---

#### Step 5: Execute Deployment

**User Confirms:**
```
"Yes, deploy it"
```

**Tool Called:** `sync_application`

**Tool Execution:**
```json
{
  "tool": "sync_application",
  "parameters": {
    "cluster_name": "production",
    "app_name": "myapp",
    "dry_run": false,
    "prune": true,
    "auto_policy": "apply"
  }
}
```

**Progress Updates:**
```
🚀 Deployment started...

Sync Status: Running
Phase: Sync
Operation: Apply

Resources being created:
→ Deployment.apps/myapp ... Creating
→ Service/myapp ... Creating
→ ConfigMap/myapp-config ... Creating
```

---

#### Step 6: Monitor Deployment

**Tool Called:** `get_sync_status` (repeatedly)

**Agent Query:**
```
"Monitoring deployment progress..."
```

**Tool Execution (polling every 5 seconds):**
```json
{
  "tool": "get_sync_status",
  "parameters": {
    "cluster_name": "production",
    "app_name": "myapp"
  }
}
```

**Progress Updates:**
```
⏳ Deployment in progress...

Sync Status: Running
Resources: 3/3 synced
Health: Progressing

Pod Status:
- myapp-7d4b8f9c-abc12: Running (Ready: 1/1)
- myapp-7d4b8f9c-def34: Running (Ready: 1/1)
- myapp-7d4b8f9c-ghi56: ContainerCreating

Waiting for all pods to be ready...
```

**Success:**
```
✅ Deployment completed successfully!

Application: myapp
Sync Status: Synced
Health Status: Healthy
All Pods: Running (3/3 ready)

Deployment Summary:
- Duration: 45 seconds
- Resources Deployed: 3
- Pod Restarts: 0
- Health: All healthy
```

---

#### Step 7: Post-Deployment Validation

**Prompt Used:** `post_deployment_validation`

**Tools Called:**
1. `get_application_details`
2. `validate_application_config`
3. `get_application_logs`

**Agent Message:**
```
🔍 Running post-deployment validation...

✅ Application Status Check
   - Sync: Synced
   - Health: Healthy
   - All resources: OK

✅ Configuration Validation
   - Config valid: true
   - No critical errors
   - Warnings: 0

✅ Pod Health Verification
   - All pods running: 3/3
   - Restart count: 0 (healthy)
   - All containers ready

✅ Log Analysis
   - Error count: 0
   - Recent logs show successful startup
   - No exceptions detected

🎉 Deployment validated successfully!

Application URL: http://myapp.production.example.com
```

---

### 📊 Complete Workflow Summary

**User Query:**
> "Deploy my application from https://github.com/myorg/myapp to production cluster"

**Tools Triggered (in order):**
1. **Prompt:** `full_application_deployment`
2. **Tool:** `get_repository` (check if repo exists)
3. **Tool:** `create_application` (create ArgoCD app)
4. **Tool:** `get_application_diff` (preview changes)
5. **User Confirmation Required** ✋
6. **Tool:** `sync_application` (execute deployment)
7. **Tool:** `get_sync_status` (monitor progress, polled)
8. **Prompt:** `post_deployment_validation`
9. **Tool:** `get_application_details` (validation)
10. **Tool:** `validate_application_config` (validation)
11. **Tool:** `get_application_logs` (validation)

**Total Time:** ~1-2 minutes  
**User Interactions:** 1 confirmation required

---

## Workflow 3: Application Debugging

### 🎯 User Goal
Debug an application that's not working correctly in production.

### 💬 User Query Examples

**Simple:**
```
"My app 'payment-service' is not working in production, help me debug it"
```

**With Symptoms:**
```
"The backend-api application in staging is showing Degraded health status. 
Pods keep restarting. Can you help me figure out what's wrong?"
```

**Error-based:**
```
"Users are reporting 500 errors from the checkout service. Debug this please"
```

---

### 🤖 What Happens (Agent Flow)

#### Step 1: Agent Selects Workflow

**Prompt Used:** `debug_application_issues`

**Parameters Detected:**
- `cluster_name`: "production"
- `app_name`: "payment-service"
- `issue_description`: "Application not working"

---

#### Step 2: Get Application Overview

**Tool Called:** `get_application_details`

**Agent Query:**
```
"🔍 Analyzing application state..."
```

**Tool Execution:**
```json
{
  "tool": "get_application_details",
  "parameters": {
    "cluster_name": "production",
    "app_name": "payment-service"
  }
}
```

**Response Analysis:**
```
📊 Application Status Overview

Application: payment-service
Sync Status: Synced ✅
Health Status: Degraded ⚠️

Current Revision: abc123def (v1.5.2)
Repository: https://github.com/myorg/payment-service
Last Sync: 2025-12-25T10:15:00Z

Resource Health:
- Deployment/payment-service: Degraded ❌
  → 2/3 pods ready
  → 1 pod failing

Pod Details:
1. payment-service-6d7f8-abc12: Running ✅ (Restarts: 0)
2. payment-service-6d7f8-def34: Running ✅ (Restarts: 0)
3. payment-service-6d7f8-ghi56: CrashLoopBackOff ❌ (Restarts: 15) ⚠️

🔴 Issue Detected: Pod in CrashLoopBackOff state with high restart count
```

---

#### Step 3: Analyze Logs with Smart Error Detection

**Tool Called:** `get_application_logs`

**Agent Query:**
```
"📜 Analyzing application logs for errors..."
```

**Tool Execution:**
```json
{
  "tool": "get_application_logs",
  "parameters": {
    "cluster_name": "production",
    "app_name": "payment-service",
    "tail_lines": 100
  }
}
```

**Response:**
```
🔍 Log Analysis Results

Total Pods Analyzed: 3
Total Log Lines: 287
Errors Detected: 15 ❌

📛 Error Summary by Pod:

Pod: payment-service-6d7f8-ghi56 (FAILING)
Error Count: 15
Sample Errors:
  1. ❌ "ERROR: Database connection failed: connection refused"
     Time: 10:30:15
     
  2. ❌ "FATAL: Unable to connect to postgres://db.prod:5432"
     Time: 10:30:14
     
  3. ❌ "Exception: psycopg2.OperationalError: could not connect to server"
     Time: 10:30:13

Pod: payment-service-6d7f8-abc12 (HEALTHY)
Error Count: 0
Status: Running normally

Pod: payment-service-6d7f8-def34 (HEALTHY)
Error Count: 0
Status: Running normally

🔍 Root Cause Identified:
  → Database connection failures
  → Likely issue: Database endpoint not reachable
  → Affected: 1/3 pods (33%)
```

---

#### Step 4: Review Application Events

**Tool Called:** `get_application_events`

**Agent Query:**
```
"📋 Checking recent Kubernetes events..."
```

**Tool Execution:**
```json
{
  "tool": "get_application_events",
  "parameters": {
    "cluster_name": "production",
    "app_name": "payment-service",
    "limit": 20
  }
}
```

**Response:**
```
📅 Recent Events (Last 20)

Warning Events:
⚠️ BackOff (10:30:20) - Pod payment-service-6d7f8-ghi56
   "Back-off restarting failed container"

⚠️ Failed (10:30:15) - Pod payment-service-6d7f8-ghi56
   "Error: CrashLoopBackOff"

Normal Events:
✓ Created (10:25:00) - Pod payment-service-6d7f8-ghi56
✓ Pulled (10:25:02) - Container image pulled successfully
✓ Started (10:25:03) - Container started

Timeline Analysis:
- 10:25:00: Pod created successfully
- 10:25:03: Container started
- 10:30:15: First crash detected
- 10:30:20: Entered CrashLoopBackOff
- Pattern: Crashes ~5-15 seconds after startup

🔍 Diagnosis: Application starts but crashes during initialization
→ Likely cause: Connection to external dependency (database) failing
```

---

#### Step 5: Configuration Validation

**Tool Called:** `validate_application_config`

**Agent Query:**
```
"⚙️ Validating application configuration..."
```

**Tool Execution:**
```json
{
  "tool": "validate_application_config",
  "parameters": {
    "cluster_name": "production",
    "app_name": "payment-service"
  }
}
```

**Response:**
```
✓ Configuration Validation

Valid: true
No schema errors

Configuration Details:
- Environment: production
- Replicas: 3
- Resources: Properly configured
- Image: myorg/payment-service:v1.5.2

Environment Variables (10 total):
  ✓ APP_ENV=production
  ✓ LOG_LEVEL=info
  ✓ PORT=8080
  ⚠️ DB_HOST=db.prod (check connectivity)
  ⚠️ DB_PORT=5432 (check connectivity)
  ✓ DB_NAME=payments
  ✓ REDIS_HOST=redis.prod
  
🔍 Potential Issue:
  → DB_HOST points to 'db.prod'
  → Need to verify this endpoint is accessible
```

---

#### Step 6: Diagnosis Summary

**Agent Message:**
```
🎯 Debugging Summary

Issue: Application Degraded (1/3 pods failing)

Root Cause Analysis:
1. ❌ Database Connection Failure
   - Error: "connection refused" to postgres://db.prod:5432
   - Impact: 1 pod in CrashLoopBackOff
   - Frequency: Consistent (15 restarts)

2. ✓ Other Pods Healthy
   - 2 pods running normally
   - No errors in successful pods
   - Suggests intermittent connectivity issue

3. 📊 Pattern Identified
   - Pod starts successfully
   - Crashes during initialization (~5-15s after start)
   - Restart loop continues

🔍 Likely Causes:
1. Network policy blocking database access
2. Database endpoint 'db.prod' not resolving
3. Database credentials incorrect
4. Firewall rules blocking connection

💡 Recommended Actions:

Immediate (to fix):
1. Check database endpoint:
   ```bash
   kubectl exec -it payment-service-6d7f8-abc12 -- nslookup db.prod
   kubectl exec -it payment-service-6d7f8-abc12 -- nc -zv db.prod 5432
   ```

2. Verify network policies:
   ```bash
   kubectl get netpol -n payment-prod
   ```

3. Check database service status:
   ```bash
   kubectl get svc db.prod -n database-prod
   ```

Long-term (to prevent):
1. Add health check endpoints that verify dependencies
2. Implement graceful degradation for database unavailability
3. Add connection retry logic with backoff
4. Monitor database connectivity metrics

Would you like me to:
a) Help you run these diagnostic commands?
b) Create a rollback to previous version?
c) Check if database service exists?
```

---

### 📊 Complete Workflow Summary

**User Query:**
> "My app 'payment-service' is not working in production, help me debug it"

**Tools Triggered (in order):**
1. **Prompt:** `debug_application_issues`
2. **Tool:** `get_application_details` (status check)
3. **Tool:** `get_application_logs` (error detection)
4. **Tool:** `get_application_events` (event timeline)
5. **Tool:** `validate_application_config` (config check)

**Diagnosis Provided:**
- Root cause: Database connection failure
- Affected pods: 1/3
- Evidence: 15 errors in logs, CrashLoopBackOff status
- Recommendations: 4 immediate actions + 4 preventive measures

**Total Time:** ~10-15 seconds  
**User Interactions:** Optional follow-up actions

---

## Workflow 4: Rollback Scenario

### 🎯 User Goal
Rollback a failed deployment to a previous working version.

### 💬 User Query Examples

**Emergency:**
```
"URGENT: Latest deployment of checkout-service is broken, rollback immediately!"
```

**Analytical:**
```
"The v3.2.0 deployment of user-service is causing high error rates. 
I want to rollback to the last stable version."
```

**Specific:**
```
"Roll back payment-api to the version deployed 2 hours ago"
```

---

### 🤖 What Happens (Agent Flow)

#### Step 1: Agent Recognizes Urgency

**Prompt Used:** `rollback_decision`

**Parameters Detected:**
- `cluster_name`: "production"
- `app_name`: "checkout-service"
- `reason`: "Latest deployment broken"

---

#### Step 2: Assess Current State

**Tool Called:** `get_application_details`

**Agent Query:**
```
"⚠️ Emergency rollback requested - analyzing current state..."
```

**Tool Execution:**
```json
{
  "tool": "get_application_details",
  "parameters": {
    "cluster_name": "production",
    "app_name": "checkout-service"
  }
}
```

**Response:**
```
🚨 Current Application State

Application: checkout-service
Current Version: v3.2.0 (revision: xyz789)
Sync Status: Synced
Health Status: Degraded ❌

Deployment History (Last 5):
1. v3.2.0 (xyz789) - CURRENT ❌ Degraded
   Deployed: 15 minutes ago
   Author: john.doe
   
2. v3.1.5 (abc456) - ✅ Healthy
   Deployed: 2 hours ago
   Author: jane.smith
   Duration: 3 days (stable)
   
3. v3.1.4 (def123) - ✅ Healthy
   Deployed: 5 days ago
   
4. v3.1.3 (ghi789) - ✅ Healthy
   Deployed: 1 week ago
   
5. v3.1.2 (jkl012) - ✅ Healthy
   Deployed: 2 weeks ago

🔍 Recommended Rollback Target:
   → v3.1.5 (abc456) - Last known stable version
   → Was healthy for 3 days before v3.2.0 deployment
```

---

#### Step 3: Review Rollback Options

**Agent Message:**
```
🎯 Rollback Options

Option 1: Quick Rollback (Recommended) ⚡
→ Rollback 1 step to v3.1.5
→ Fastest recovery (< 1 minute)
→ Last known stable state
→ Command: rollback_application with steps=1

Option 2: Rollback to Specific Version 🎯
→ Rollback to any previous version
→ More control but requires revision hash
→ Command: rollback_to_revision with revision hash

Option 3: Check Diff First 🔍
→ Preview changes before rollback
→ See what will revert
→ Command: get_application_diff first

Decision Matrix:
✅ Rollback immediately if:
   - Users experiencing outages (CURRENT STATUS)
   - Data corruption risk
   - Critical errors in production

⚠️ Investigate first if:
   - Minor performance degradation
   - Non-critical errors
   - Issue might be environmental

🚨 Your situation: Users experiencing outages
→ Recommendation: ROLLBACK IMMEDIATELY (Option 1)
```

---

#### Step 4: Preview Rollback Changes (Optional but Recommended)

**Tool Called:** `get_application_diff`

**Agent Query:**
```
"📋 Previewing rollback changes..."
```

**Tool Execution:**
```json
{
  "tool": "get_application_diff",
  "parameters": {
    "cluster_name": "production",
    "app_name": "checkout-service",
    "target_revision": "abc456"
  }
}
```

**Response:**
```
🔄 Rollback Preview (v3.2.0 → v3.1.5)

Changes that will be reverted:

~ Deployment.apps/checkout-service
  - image: myorg/checkout:v3.2.0 → v3.1.5
  - env:
      - NEW_FEATURE_FLAG: true → (removed)
      - PAYMENT_PROCESSOR_V2: enabled → (removed)
  - resources.requests.memory: 256Mi → 128Mi
  - replicas: 5 → 3

~ ConfigMap/checkout-config
  - feature.new_checkout: true → false
  - timeout.payment: 5000ms → 3000ms

Impact Summary:
- Image version: v3.2.0 → v3.1.5
- Resource usage: Reduced (256Mi → 128Mi)
- Replicas: 5 → 3
- Feature flags: Disabled (new checkout flow)

⏱️ Estimated Rollback Time: 30-60 seconds
⚠️ Impact: Brief disruption during pod replacement

Ready to proceed with rollback?
```

---

#### Step 5: Execute Rollback

**User Confirms (or auto-proceeds in emergency):**
```
"Yes, rollback now!"
```

**Tool Called:** `rollback_application`

**Tool Execution:**
```json
{
  "tool": "rollback_application",
  "parameters": {
    "cluster_name": "production",
    "app_name": "checkout-service",
    "steps": 1,
    "prune": false
  }
}
```

**Progress Updates:**
```
🔄 Rollback initiated...

Phase: Rollback
Target: v3.1.5 (abc456)
Strategy: Rolling update

Progress:
⏳ Updating deployment...
→ Scaling down new pods (v3.2.0)
→ Scaling up old pods (v3.1.5)

Pod Status:
- checkout-76d8f-v315-new1: Running ✅
- checkout-76d8f-v315-new2: Running ✅
- checkout-76d8f-v315-new3: Running ✅
- checkout-7f9ab-v320-old1: Terminating
- checkout-7f9ab-v320-old2: Terminating

⏳ Waiting for all pods to be ready...
```

**Success:**
```
✅ Rollback completed successfully!

Application: checkout-service
Previous Version: v3.2.0 (failed) ❌
Current Version: v3.1.5 (stable) ✅

Rollback Summary:
- Duration: 42 seconds
- Pods replaced: 5 → 3
- Health Status: Healthy
- Error Rate: 0%

All systems operational!
```

---

#### Step 6: Post-Rollback Validation

**Prompt Used:** `post_deployment_validation`

**Agent Message:**
```
🔍 Validating rollback...

✅ Application Health Check
   - All pods running: 3/3
   - Health status: Healthy
   - No errors in logs

✅ Traffic Recovery
   - Error rate: 0% (was 45%)
   - Response time: 120ms (was 5000ms)
   - All endpoints responding

✅ Configuration Validation
   - Config matches v3.1.5
   - No drift detected
   - All resources synced

🎉 Rollback validated successfully!

Users can now access the service normally.

📋 Post-Mortem Recommendations:
1. Investigate why v3.2.0 failed
2. Review deployment process
3. Add pre-deployment testing for future releases
4. Document this incident

Would you like me to help create an incident report?
```

---

### 📊 Complete Workflow Summary

**User Query:**
> "URGENT: Latest deployment of checkout-service is broken, rollback immediately!"

**Tools Triggered (in order):**
1. **Prompt:** `rollback_decision`
2. **Tool:** `get_application_details` (assess state, get history)
3. **Tool:** `get_application_diff` (preview changes)
4. **Tool:** `rollback_application` (execute rollback)
5. **Tool:** `get_sync_status` (monitor rollback)
6. **Prompt:** `post_deployment_validation`
7. **Tool:** `get_application_details` (validate)
8. **Tool:** `get_application_logs` (verify no errors)

**Total Time:** ~1 minute  
**User Interactions:** 1 confirmation (can be skipped in emergency)  
**Recovery:** Complete, service restored

---

## Workflow 5: Monitoring & Metrics

### 🎯 User Goal
Monitor application health and metrics in real-time.

### 💬 User Query Examples

**Dashboard:**
```
"Show me the health status of all applications in production"
```

**Specific App:**
```
"What's the current status of user-service in staging?"
```

**Cluster-Wide:**
```
"Give me an overview of cluster health for production"
```

---

### 🤖 What Happens (Agent Flow)

#### Query 1: List All Applications

**User Query:**
```
"Show me all applications in production cluster"
```

**Tool Called:** `list_applications`

**Tool Execution:**
```json
{
  "tool": "list_applications",
  "parameters": {
    "cluster_name": "production",
    "limit": 50
  }
}
```

**Response:**
```
📊 Production Cluster Applications

Total Applications: 12

✅ Healthy (9):
1. user-service (Synced, Healthy)
2. payment-api (Synced, Healthy)
3. checkout-service (Synced, Healthy)
4. notification-worker (Synced, Healthy)
5. analytics-dashboard (Synced, Healthy)
6. admin-portal (Synced, Healthy)
7. mobile-backend (Synced, Healthy)
8. search-engine (Synced, Healthy)
9. recommendation-service (Synced, Healthy)

⚠️ Progressing (2):
10. order-processor (Synced, Progressing)
    → Deployment in progress
11. inventory-sync (Synced, Progressing)
    → Rolling update

❌ Degraded (1):
12. legacy-api (OutOfSync, Degraded)
    → Needs attention

Cluster Health: 83% (10/12 healthy or progressing)
```

---

#### Query 2: Get Specific Application Metrics

**User Query:**
```
"What are the metrics for user-service?"
```

**Resource Used:** `argocd://application-metrics/production/user-service`

**Response:**
```
📈 user-service Metrics (Production)

Sync Status: Synced ✅
Health Status: Healthy ✅

Resource Health:
- Total Resources: 8
- Healthy Resources: 8
- Health Percentage: 100%

Resources Breakdown:
✅ Deployment/user-service (3/3 ready)
✅ Service/user-service
✅ ConfigMap/user-service-config
✅ Secret/user-service-secrets
✅ HPA/user-service-hpa (Autoscaling active)
✅ ServiceMonitor/user-service-metrics
✅ PodDisruptionBudget/user-service-pdb
✅ NetworkPolicy/user-service-netpol

Pod Metrics:
- Running Pods: 3
- Ready Pods: 3
- Restart Count (total): 0
- CPU Usage: 45% (avg)
- Memory Usage: 62% (avg)

Last Updated: 2025-12-25T16:10:00Z
```

---

#### Query 3: Cluster-Wide Health

**Resource Used:** `argocd://cluster-health/production`

**Response:**
```
🏥 Production Cluster Health Overview

Overall Status: Warning ⚠️

Application Metrics:
- Total Applications: 12
- Synced: 11 (92%)
- Out of Sync: 1 (8%)
- Healthy: 9 (75%)
- Progressing: 2 (17%)
- Degraded: 1 (8%)

Health Breakdown:
✅ Sync Percentage: 92%
⚠️ Health Percentage: 75%

Trends (Last 24h):
- Deployments: 5
- Rollbacks: 1
- Sync Failures: 0
- Average Sync Time: 45s

Action Items:
⚠️ 1 application needs attention:
   - legacy-api (OutOfSync, Degraded)

🔄 2 applications deploying:
   - order-processor (Progressing)
   - inventory-sync (Progressing)

Last Updated: 2025-12-25T16:10:00Z
```

---

#### Query 4: Real-Time Sync Operations

**Resource Used:** `argocd://sync-operations/production`

**Response:**
```
🔄 Active Sync Operations

Currently Running: 2

1. order-processor
   Status: Syncing
   Phase: Running
   Progress: 75%
   Started: 2 minutes ago
   Resources: 6/8 synced
   
2. inventory-sync
   Status: Syncing
   Phase: Running
   Progress: 50%
   Started: 1 minute ago
   Resources: 3/6 synced

Recent Completed (Last Hour):
✅ user-service (45s ago) - Success
✅ payment-api (1h ago) - Success
❌ legacy-api (2h ago) - Failed

Average Sync Time: 45 seconds
Success Rate: 85% (17/20)

Last Updated: 2025-12-25T16:10:05Z
```

---

#### Query 5: Deployment Events Stream

**Resource Used:** `argocd://deployment-events/production`

**Response:**
```
📅 Recent Deployment Events

Last 10 Events:

[16:10:00] ✅ SyncSucceeded - order-processor
   User: automation@company.com
   Revision: v2.3.0
   
[16:08:30] 🚀 SyncStarted - inventory-sync
   User: jane.doe@company.com
   Revision: v1.8.2
   
[16:05:15] ✅ HealthStatusChanged - user-service
   Status: Healthy → Healthy
   Reason: Periodic health check
   
[16:00:00] ⚠️ OutOfSync - legacy-api
   Reason: Git repository updated
   Drift detected: 3 resources
   
[15:55:00] ✅ SyncSucceeded - payment-api
   User: automation@company.com
   Revision: v3.1.0
   Duration: 42s
   
[15:50:00] 🔄 ResourceUpdated - checkout-service
   Resource: Deployment
   Change: Image tag updated
   
[15:45:00] ❌ SyncFailed - legacy-api
   Error: Validation failed
   Reason: Invalid manifest
   
[15:40:00] ✅ ResourceCreated - notification-worker
   Resource: ConfigMap/worker-config
   Source: Git commit abc123

Event Summary:
- Syncs: 5 (4 successful, 1 failed)
- Health Changes: 2
- Resource Updates: 3

Last Updated: 2025-12-25T16:10:00Z
```

---

### 📊 Monitoring Summary

**Available Real-Time Resources:**

| Resource URI | Purpose | Update Frequency |
|-------------|---------|------------------|
| `argocd://applications/{cluster}` | List all apps | Every 5s |
| `argocd://application-metrics/{cluster}/{app}` | App metrics | Every 10s |
| `argocd://sync-operations/{cluster}` | Active syncs | Every 2s |
| `argocd://deployment-events/{cluster}` | Event stream | Real-time |
| `argocd://cluster-health/{cluster}` | Cluster health | Every 30s |

**Monitoring Use Cases:**
- Dashboard creation
- Health monitoring
- Alert generation
- Audit trails
- Performance tracking

---

## Direct Tool Usage

When you need specific actions without guided workflows:

### Example 1: Quick Status Check

**User Query:**
```
"What's the sync status of payment-api in production?"
```

**Direct Tool Call:** `get_sync_status`

**Response:**
```
✅ payment-api Sync Status

Sync Status: Synced
Sync Phase: Succeeded
Operation State: Running
Revision: v3.1.0 (abc123)
Last Sync: 2025-12-25T15:55:00Z (15 minutes ago)
```

---

### Example 2: View Application Logs

**User Query:**
```
"Show me the last 50 lines of logs from user-service"
```

**Direct Tool Call:** `get_application_logs`

**Response:**
```
📜 user-service Logs (Last 50 lines)

Error Count: 0 ✅

Recent Logs (Pod: user-service-6d7f8-abc12):
[16:10:15] INFO Starting user service v2.1.0
[16:10:16] INFO Connected to database: postgres://db.prod:5432
[16:10:16] INFO Connected to Redis: redis://cache.prod:6379
[16:10:17] INFO HTTP server listening on :8080
[16:10:17] INFO Health check endpoint ready: /health
[16:10:18] INFO Request: GET /api/users/123 - 200 OK (12ms)
[16:10:19] INFO Request: POST /api/users - 201 Created (45ms)
[16:10:20] INFO Request: GET /api/users - 200 OK (8ms)

All systems operating normally ✅
```

---

### Example 3: Validate Config

**User Query:**
```
"Is the configuration valid for checkout-service?"
```

**Direct Tool Call:** `validate_application_config`

**Response:**
```
✅ Configuration Validation

Application: checkout-service
Valid: true
No errors found

Configuration Summary:
- Manifest valid: Yes
- Resource types: Valid
- Dependencies: All satisfied
- Secrets: All referenced secrets exist
- ConfigMaps: All referenced configmaps exist

You can safely deploy this configuration.
```

---

## Resource Monitoring

### Setting Up a Live Dashboard

**User Query:**
```
"I want to monitor all production applications in real-time"
```

**Agent Response:**
```
📊 To monitor production applications, I'll set up live data streams.

You can subscribe to these resources:

1. **Applications List**
   Resource: argocd://applications/production
   Updates: Every 5 seconds
   Shows: All app statuses

2. **Cluster Health**
   Resource: argocd://cluster-health/production
   Updates: Every 30 seconds
   Shows: Overall health metrics

3. **Active Operations**
   Resource: argocd://sync-operations/production
   Updates: Every 2 seconds
   Shows: Ongoing deployments

4. **Event Stream**
   Resource: argocd://deployment-events/production
   Updates: Real-time
   Shows: All deployment events

Would you like me to display any of these?
```

---

## Best Practices

### 1. Use Prompts for Complex Workflows

**Instead of:**
```
"Call onboard_repository_https, then create_application, then sync_application..."
```

**Say:**
```
"Deploy my application from [repo-url] to [cluster]"
```

The agent will use the `full_application_deployment` prompt which orchestrates all steps.

---

### 2. Provide Context in Queries

**❌ Vague:**
```
"Something is wrong"
```

**✅ Better:**
```
"The payment-service in production is returning 500 errors to users"
```

**✅ Best:**
```
"The payment-service in production started returning 500 errors after 
the v2.1.0 deployment 30 minutes ago. Users can't complete purchases."
```

---

### 3. Confirm Before Destructive Operations

The agent will always ask for confirmation before:
- Deleting applications
- Deleting projects
- Production deployments
- Deleting repositories

Always review the preview before confirming!

---

### 4. Use Resources for Monitoring

Don't poll tools repeatedly. Instead:

**❌ Don't:**
```
"Check status... wait 5 seconds... check status again..."
```

**✅ Do:**
```
"Monitor the sync operation for myapp"
```

The agent will subscribe to the appropriate resource stream.

---

### 5. Leverage Smart Log Analysis

**Instead of:**
```
"Show me all logs and let me search for errors"
```

**Say:**
```
"Analyze the logs and tell me what's wrong"
```

The `get_application_logs` tool automatically:
- Detects errors
- Extracts sample error messages
- Provides concise summaries
- Limits output to prevent overload

---

### 6. Trust the Validation Steps

When deploying, the agent will:
1. Validate repository
2. Show you the diff
3. Ask for confirmation
4. Execute deployment
5. Monitor progress
6. Validate success

Don't skip steps - they catch issues early!

---

## Appendix: Command Reference

### Quick Reference Table

| User Intent | Prompt/Tool Used | Example Query |
|------------|------------------|---------------|
| Onboard repo | `onboard_github_repository` | "Add repo [url] to ArgoCD" |
| Deploy app | `full_application_deployment` | "Deploy [app] from [repo] to [cluster]" |
| Debug issue | `debug_application_issues` | "App [name] is broken, debug it" |
| Rollback | `rollback_decision` | "Rollback [app] to previous version" |
| Check status | `get_application_details` | "What's the status of [app]?" |
| View logs | `get_application_logs` | "Show logs for [app]" |
| List apps | `list_applications` | "Show all apps in [cluster]" |
| Validate | `post_deployment_validation` | "Validate [app] deployment" |

---

## Getting Help

If you're unsure what to ask:

**General help:**
```
"What can you help me with for ArgoCD?"
```

**Specific scenario:**
```
"I want to deploy a new application, how do I start?"
```

**Tool discovery:**
```
"What tools are available for managing repositories?"
```

The agent will guide you through the available options and recommend the best approach!

---

**Happy deploying! 🚀**
