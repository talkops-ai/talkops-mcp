"""Onboarding deployment guided workflow prompt.

Provides guided workflow for converting existing Kubernetes Deployments
to Argo Rollouts with progressive delivery.
"""

from argo_rollout_mcp_server.prompts.base import BasePrompt


class OnboardingDeploymentPrompts(BasePrompt):
    """Onboarding deployment guided workflow prompts.
    
    Provides step-by-step guidance for converting existing Kubernetes
    Deployments to Argo Rollouts.
    """
    
    def register(self, mcp_instance) -> None:
        """Register onboarding deployment prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def onboard_application_guided(
            app_name: str,
            deployment_yaml: str,
            strategy: str = "canary",
            namespace: str = "default",
            prometheus_url: str = "http://prometheus:9090",
            migrating_from_nginx: bool = False
        ) -> str:
            """Guide user through onboarding an existing Deployment to Argo Rollouts.
            
            This prompt provides step-by-step guidance for converting a standard
            Kubernetes Deployment into an Argo Rollout with Prometheus-based analysis.
            
            Workflow:
            1. Validate Deployment readiness
            2. Convert Deployment to Rollout YAML
            3. Create Rollout resource
            4. Configure traffic routing (optional, for canary/blue-green)
            5. Create AnalysisTemplate for automated validation
            6. Verify onboarding
            
            Args:
                app_name: Name of the application to onboard
                deployment_yaml: Existing Kubernetes Deployment YAML as string
                strategy: Rollout strategy - "canary" or "bluegreen" (default: "canary")
                namespace: Kubernetes namespace (default: "default")
                prometheus_url: Prometheus server URL (default: "http://prometheus:9090")
                migrating_from_nginx: Include NGINX migration steps (default: False)
            
            Returns:
                Formatted guidance text for application onboarding
            """
            
            strategy_display = "Canary (Progressive Traffic Shift)" if strategy == "canary" else "Blue-Green (Instant Switch)"
            
            migration_intro = ""
            if migrating_from_nginx:
                migration_intro = """
## ⚠️ Ingress Migration Required First
Because you are migrating from NGINX Ingress, complete your Ingress migration **before** onboarding to Argo Rollouts. Ensure your ingress controller is handling traffic correctly, then return here to continue the Rollout onboarding.

---
"""
            
            prompt = f"""# 🚀 Application Onboarding Guide: {app_name}

## Onboarding Details
- **Application**: {app_name}
- **Namespace**: {namespace}
- **Strategy**: {strategy_display}
- **Prometheus**: {prometheus_url}

---

## What is Onboarding?

Onboarding converts your existing **Kubernetes Deployment** into an **Argo Rollout** with:
- Progressive delivery (canary or blue-green)
- Prometheus-based automated health analysis
- Optional traffic routing integration (link via argo_update_rollout(update_type='traffic_routing'))

---
{migration_intro}
## Phase 1: Validate Deployment Readiness

### Check if your Deployment is ready for conversion:

1. **Validate deployment readiness**:
   ```
   Tool: validate_deployment_ready
   Args:
     - deployment_yaml: <paste your Deployment YAML>
   ```
   
   This validates:
   - ✅ Replicas >= 2 (required for HA)
   - ✅ Resource limits and requests defined
   - ✅ Readiness and liveness probes configured
   - ✅ Container image specified
   
   **Result**: Readiness score (0-100)
   - Score >= 70: ✅ Ready to proceed
   - Score < 70: ❌ Fix blocking issues first

2. **Verify cluster health**:
   ```
   Resource: argorollout://cluster/health
   ```

### Success Criteria:
- ✅ Readiness score >= 70
- ✅ Cluster resources available

---

## Phase 2: Convert Deployment to Rollout

### Option A: Direct conversion (replace Deployment)

1. **Convert and apply in one step** (recommended):
   ```
   Tool: convert_deployment_to_rollout
   Args:
     - deployment_name: {app_name}
     - namespace: {namespace}
     - strategy: {strategy}
     - migration_mode: direct
     - apply: true
   ```
   This fetches the live Deployment, generates the Rollout, creates stable/canary Services, and applies to the cluster. Scale down the original Deployment first (or the tool will replace it).

### Option B: workloadRef migration (Argo CD / Helm–managed)

When the Deployment is managed by Argo CD or Helm, use workloadRef to avoid conflicts:

1. **Convert with workloadRef** (keeps Deployment running; Rollout references it):
   ```
   Tool: convert_deployment_to_rollout
   Args:
     - deployment_name: {app_name}
     - namespace: {namespace}
     - strategy: {strategy}
     - migration_mode: workload_ref
     - scale_down: never
     - apply: true
   ```
   See [WORKLOAD_REF_MIGRATION_TEST_GUIDE.md](docs/workflow-docs/WORKLOAD_REF_MIGRATION_TEST_GUIDE.md) for the full workflow.

### Option C: Generate YAML only (review before apply)

1. **Convert to Rollout YAML** (no apply):
   ```
   Tool: convert_deployment_to_rollout
   Args:
     - deployment_name: {app_name}
     - namespace: {namespace}
     - strategy: {strategy}
     - apply: false
   ```
   
   This transforms your Deployment into a Rollout with:
   - Same metadata, selector, and pod template
   - Added `{strategy}` strategy configuration
"""

            if strategy == "canary":
                prompt += f"""   - Canary steps: 5% → 10% → 25% → 50% (with pause gates)
   - Service names: `{app_name}-stable` and `{app_name}-canary`
"""
            else:
                prompt += f"""   - Active service: `{app_name}-active`
   - Preview service: `{app_name}-preview`
   - Auto-promotion disabled (manual approval required)
"""

            prompt += f"""
2. **Review the generated YAML** before applying:
   - Verify metadata is correct
   - Confirm strategy configuration
   - Check replica count
   - Validate container specs

---

## Phase 3: Apply Rollout to Cluster (if not using apply=true)

If you used `apply=false` in Phase 2, apply manually:

1. **For direct mode**: Scale down the original Deployment first, then create the Rollout via `argo_create_rollout` or re-run `convert_deployment_to_rollout` with `apply=true`.

2. **Verify rollout is healthy**:
   ```
   Resource: argorollout://rollouts/{namespace}/{app_name}/detail
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Expected: Phase = "Healthy", all pods running.

---

## Phase 4: Set Up Traffic Routing (Optional)

### For Canary/Blue-Green with External Traffic Control:

1. **Generate stable and canary Services**:
   ```
   Tool: convert_deployment_to_rollout(mode='generate_services_only', app_name='...') or create_stable_canary_services (legacy)
   Args:
     - app_name: {app_name}
     - namespace: {namespace}
     - port: 80
   ```

2. **Link rollout to traffic routing** (if using Traefik, Istio, or other ingress):
   ```
   Tool: argo_update_rollout(update_type='traffic_routing')
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - traefik_service_name: <your-weighted-traefik-service-name>
   ```
   The TraefikService/IngressRoute must be created separately (e.g., via your ingress controller or CI/CD).

---


## Phase 5: Set Up Analysis Template

### Create Automated Health Validation:

1. **Generate AnalysisTemplate** with Prometheus metrics:
   ```
   Tool: argo_configure_analysis_template(mode='generate_yaml')
   Args:
     - service_name: {app_name}
     - prometheus_url: {prometheus_url}
     - namespace: {namespace}
     - error_rate_threshold: 5.0
     - latency_p99_threshold: 2000
     - latency_p95_threshold: 1000
   ```
   
   This creates an AnalysisTemplate monitoring:
   - **Error rate**: Must be < 5%
   - **P99 latency**: Must be < 2000ms
   - **P95 latency**: Must be < 1000ms

2. **Attach analysis template to rollout**:
   ```
   Tool: argo_configure_analysis_template(mode='execute')
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - template_name: {app_name}-analysis
   ```

---

## Phase 6: GitOps (Optional)

### ArgoCD ignoreDifferences (if using ArgoCD):

Generate ignoreDifferences to prevent ArgoCD from marking runtime changes as OutOfSync:
   ```
   Tool: generate_argocd_ignore_differences
   Args:
     - include_rollout_status: true
     - include_analysis_run: true
     - include_traefik_service: true  # only if using Traefik traffic routing
   ```

---


## Phase 7: Final Verification

### Confirm Everything is Working:

1. **Check rollout status**:
   ```
   Resource: argorollout://rollouts/{namespace}/{app_name}/detail
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   Confirm: Phase = "Healthy"

2. **Check cluster health**:
   ```
   Resource: argorollout://health/summary
   ```

3. **Record deployment history baseline**:
   ```
   Resource: argorollout://history/{namespace}/{app_name}
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

---

## ✅ Onboarding Complete!

Your application `{app_name}` is now managed by Argo Rollouts with:
- ✅ Progressive delivery strategy ({strategy})
- ✅ Prometheus-based automated analysis
- ✅ Optional traffic routing (if argo_update_rollout(update_type='traffic_routing') was used)

### What's Next?

For future deployments, simply update the image:
```
Tool: argo_update_rollout(update_type='image')
Args:
  - name: {app_name}
  - new_image: <new-image:tag>
  - namespace: {namespace}
```

Or use a guided deployment prompt:
- `canary_deployment_guided` - For progressive canary rollout
- `blue_green_deployment_guided` - For instant blue-green switch
- `rolling_update_guided` - For standard rolling update

---

## Tools Summary

### Generator/Conversion Tools:
1. `validate_deployment_ready` - Check Deployment readiness (score 0-100)
2. `convert_deployment_to_rollout` - Convert Deployment YAML → Rollout YAML
3. `convert_deployment_to_rollout(mode='generate_services_only')` - Generate stable/canary Services
4. `argo_configure_analysis_template(mode='generate_yaml')` - Generate AnalysisTemplate YAML
5. `generate_argocd_ignore_differences` - Prevent ArgoCD OutOfSync

### Argo Rollout Tools:
6. `argo_create_rollout` - Apply Rollout to cluster
7. `argo_update_rollout(update_type='traffic_routing')` - Link rollout to traffic routing (optional)
8. `argo_configure_analysis_template(mode='execute')` - Attach analysis to rollout

### Resources:
9. `argorollout://rollouts/{namespace}/{app_name}/detail` - Verify rollout health
10. `argorollout://history/{namespace}/{app_name}` - Record baseline history
11. `argorollout://health/summary` - Cluster health

### Orchestration Tools:
12. `argorollout://cluster/health` - Cluster readiness
"""
            
            return prompt
