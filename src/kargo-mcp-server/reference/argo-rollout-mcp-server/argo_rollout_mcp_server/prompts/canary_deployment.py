"""Canary deployment guided workflow prompt.

Provides guided canary deployment with metrics-driven auto-promotion.
"""

from typing import List
from argo_rollout_mcp_server.prompts.base import BasePrompt


class CanaryDeploymentPrompts(BasePrompt):
    """Canary deployment guided workflow prompts.
    
    Provides step-by-step guidance for canary deployments with
    progressive traffic shifting based on health metrics.
    """
    
    def register(self, mcp_instance) -> None:
        """Register canary deployment prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def canary_deployment_guided(
            app_name: str,
            new_image: str,
            namespace: str = "default"
        ) -> str:
            """Guide user through metrics-driven canary deployment.
            
            This prompt provides step-by-step guidance for deploying a new version
            using canary strategy with progressive traffic shifting.
            
            Workflow:
            1. Validate policies & costs
            2. Create canary rollout (0% traffic)
            3. Monitor metrics at each step
            4. Progressive promotion: 5% → 10% → 25% → 50% → 100%
            5. Auto-rollback if health checks fail
            
            Args:
                app_name: Name of the application/rollout
                new_image: New container image to deploy
                namespace: Kubernetes namespace (default: "default")
            
            Returns:
                Formatted guidance text for canary deployment
            """
            
            # Build the guided workflow prompt
            prompt = f"""# 🚀 Canary Deployment Guide: {app_name}

## Deployment Details
- **Application**: {app_name}
- **Namespace**: {namespace}
- **New Image**: {new_image}
- **Strategy**: Canary (Progressive Traffic Shift)

---

## Workflow Overview

This guide will help you deploy a new version using **canary deployment** with automatic promotion based on health metrics.

### Canary Deployment Steps:
1. ✅ **Pre-flight Checks** - Validate readiness, policies, and cost impact
2. 🎯 **Create Canary** - Deploy new version with 0% traffic
3. 🛡️ **Safety Setup** - Analysis template + middleware protection
4. 📊 **Progressive Promotion** - Gradually increase traffic if healthy
5. ✅ **Complete** - Promote to 100% or auto-rollback

---

## Phase 1: Pre-flight Checks

### Actions to Take:
1. **Validate deployment readiness** using tool: `validate_deployment_ready`
   ```
   Tool: validate_deployment_ready
   Args:
     - deployment_yaml: (your existing Deployment YAML)
   ```
   Checks: replicas >= 2, resource limits, readiness/liveness probes.
   Produces a readiness score (0-100). Proceed only if score >= 70.

2. **Verify cluster health** using resource: `argorollout://cluster/health`

### Success Criteria:
- ✅ Deployment readiness score >= 70
- ✅ Resources are available (cluster health)

---

## Phase 2: Create Canary Rollout

### Actions to Take:
1. **Update rollout image** to create canary using tool: `argo_update_rollout(update_type='image')`
   ```
   Tool: argo_update_rollout(update_type='image')
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
   ```

2. **Verify rollout created** using resource: `argorollout://rollouts/{namespace}/{name}/detail`
   ```
   Resource: argorollout://rollouts/{namespace}/{name}/detail
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

### Expected State:
- Phase: "Progressing"
- Canary weight: 0% (or first step weight)
- Stable weight: 100%

---

## Phase 2.5: Safety Setup

### Analysis Template (Automated Health Validation):

1. **Create analysis template** for automated metrics checking:
   ```
   Tool: argo_configure_analysis_template(mode='generate_yaml')
   Args:
     - service_name: {app_name}
     - prometheus_url: http://prometheus:9090
     - namespace: {namespace}
     - error_rate_threshold: 5.0
     - latency_p99_threshold: 2000
     - latency_p95_threshold: 1000
   ```
   This generates an AnalysisTemplate with Prometheus queries for error rate, P99, and P95 latency.

2. **Attach analysis to rollout**:
   ```
   Tool: argo_configure_analysis_template(mode='execute')
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - template_name: {app_name}-analysis
   ```

---

## Phase 3: Progressive Promotion

### Traffic Progression Steps:

#### Step 1: 5% Traffic
**Wait**: 60 seconds
**Check**: Error rate < 5%, P99 latency < 2x baseline

1. Monitor with resource: `argorollout://rollouts/{namespace}/{name}/detail`
2. Check metrics:
   - Error rate should be < 5%
   - P99 latency should be < 2x baseline
3. If healthy, promote to next step using: `argo_manage_rollout_lifecycle(action='promote')`

#### Step 2: 10% Traffic  
**Wait**: 120 seconds
**Check**: Error rate < 5%, P99 latency < 2x baseline

#### Step 3: 25% Traffic
**Wait**: 300 seconds (5 minutes)
**Check**: Error rate < 3%, P99 latency < 1.5x baseline

#### Step 4: 50% Traffic
**Wait**: 300 seconds (5 minutes)
**Check**: Error rate < 2%, P99 latency < 1.2x baseline

#### Step 5: 100% Traffic
**Action**: Full promotion using `argo_manage_rollout_lifecycle(action='promote_full')`

### Auto-Rollback Triggers:
- ❌ Error rate exceeds threshold
- ❌ Latency spike detected
- ❌ Pod crash loops
- ❌ Resource exhaustion

If any trigger occurs, **automatically rollback** using tool: `argo_manage_rollout_lifecycle(action='abort')`

---

## Phase 4: Monitoring & Verification

### Continuous Monitoring:
1. **Track rollout progress** using:
   ```
   Resource: argorollout://rollouts/{namespace}/{name}/detail
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

2. **Check rollout status** (includes canary/stable weights in status):
   ```
   Resource: argorollout://rollouts/{namespace}/{name}/detail
   ```

---

## Emergency Actions

### If Deployment Fails:

1. **Abort rollout** (rollback to stable version):
   ```
   Tool: argo_manage_rollout_lifecycle (action=abort)
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

2. **Check rollout history** for audit:
   ```
   Resource: argorollout://history/{namespace}/{name}
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

---

## Success Metrics

### Deployment Successful When:
- ✅ All traffic shifted to canary (100%)
- ✅ No anomalies detected
- ✅ All pods healthy
- ✅ Error rate within threshold
- ✅ Latency within acceptable range

### Tools Summary:
1. `validate_deployment_ready` - Readiness check (score 0-100)
2. `argorollout://cluster/health` - Cluster readiness
4. `argo_update_rollout(update_type='image')` - Start canary
5. `argo_configure_analysis_template(mode='generate_yaml')` - Generate AnalysisTemplate YAML
6. `argo_configure_analysis_template(mode='execute')` - Create and link analysis to rollout
7. `argorollout://rollouts/{ns}/{name}/detail` - Monitor progress (includes canary weights)
8. `argo_manage_rollout_lifecycle` (action=promote/promote_full) - Advance to next step
9. `argo_manage_rollout_lifecycle` (action=abort) - Emergency rollback

---

## Next Steps

1. Start with **Phase 1: Pre-flight Checks**
2. Execute each tool in sequence
3. Monitor health at each step
4. Promote progressively if healthy
5. Rollback immediately if issues detected

**Ready to begin?** Start with the pre-flight checks above!
"""
            
            return prompt
