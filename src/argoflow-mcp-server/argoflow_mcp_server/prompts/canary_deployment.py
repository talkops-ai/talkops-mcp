"""Canary deployment guided workflow prompt.

Provides guided canary deployment with metrics-driven auto-promotion.
"""

from typing import List
from argoflow_mcp_server.prompts.base import BasePrompt


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
1. ✅ **Pre-flight Checks** - Validate policies and cost impact
2. 🎯 **Create Canary** - Deploy new version with 0% traffic
3. 📊 **Progressive Promotion** - Gradually increase traffic if healthy
4. ✅ **Complete** - Promote to 100% or auto-rollback

---

## Phase 1: Pre-flight Checks

### Actions to Take:
1. **Validate deployment policies** using tool: `argo_validate_deployment_policies`
   ```
   Tool: argo_validate_deployment_policies
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

2. **Check cost impact** using tool: `argo_estimate_rollout_cost`
   ```
   Tool: argo_estimate_rollout_cost
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
   ```

### Success Criteria:
- ✅ All policies pass
- ✅ Cost is within budget
- ✅ Resources are available

---

## Phase 2: Create Canary Rollout

### Actions to Take:
1. **Update rollout image** to create canary using tool: `argo_update_rollout_image`
   ```
   Tool: argo_update_rollout_image
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
   ```

2. **Verify rollout created** using tool: `argo_get_rollout_status`
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

### Expected State:
- Phase: "Progressing"
- Canary weight: 0% (or first step weight)
- Stable weight: 100%

---

## Phase 3: Progressive Promotion

### Traffic Progression Steps:

#### Step 1: 5% Traffic
**Wait**: 60 seconds
**Check**: Error rate < 5%, P99 latency < 2x baseline

1. Monitor with tool: `argo_get_rollout_status`
2. Check metrics:
   - Error rate should be < 5%
   - P99 latency should be < 2x baseline
3. If healthy, promote to next step using: `argo_promote_rollout`

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
**Action**: Full promotion

### Auto-Rollback Triggers:
- ❌ Error rate exceeds threshold
- ❌ Latency spike detected
- ❌ Pod crash loops
- ❌ Resource exhaustion

If any trigger occurs, **automatically rollback** using tool: `argo_abort_rollout`

---

## Phase 4: Monitoring & Verification

### Continuous Monitoring:
1. **Track rollout progress** using:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

2. **Monitor traffic distribution** using:
   ```
   Tool: traefik_get_traffic_distribution
   Args:
     - route_name: {app_name}-route
     - namespace: {namespace}
   ```

3. **Check for anomalies** using resource:
   ```
   Resource: argoflow://anomalies/detected
   ```

---

## Emergency Actions

### If Deployment Fails:

1. **Abort and Rollback**:
   ```
   Tool: argo_abort_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

2. **Check rollout history** for audit:
   ```
   Tool: argo_get_rollout_history
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
1. `argo_validate_deployment_policies` - Policy validation
2. `argo_estimate_rollout_cost` - Cost check
3. `argo_update_rollout_image` - Start canary
4. `argo_get_rollout_status` - Monitor progress
5. `argo_promote_rollout` - Advance to next step
6. `argo_abort_rollout` - Emergency rollback
7. `traefik_get_traffic_distribution` - Traffic monitoring

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
