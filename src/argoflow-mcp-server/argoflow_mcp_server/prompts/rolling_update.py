"""Rolling update guided workflow prompt.

Provides guided standard Kubernetes rolling update.
"""

from argoflow_mcp_server.prompts.base import BasePrompt


class RollingUpdatePrompts(BasePrompt):
    """Rolling update guided workflow prompts.
    
    Provides step-by-step guidance for standard Kubernetes
    rolling updates (pod-by-pod replacement).
    """
    
    def register(self, mcp_instance) -> None:
        """Register rolling update prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def rolling_update_guided(
            app_name: str,
            new_image: str,
            namespace: str = "default"
        ) -> str:
            """Guide user through standard rolling update.
            
            This prompt provides step-by-step guidance for deploying a new version
            using standard Kubernetes rolling update strategy.
            
            Workflow:
            1. Validate policies & costs
            2. Update deployment image
            3. Kubernetes replaces pods one-by-one
            4. Monitor rollout progress
            5. Verify completion
            
            Args:
                app_name: Name of the application/rollout
                new_image: New container image to deploy
                namespace: Kubernetes namespace (default: "default")
            
            Returns:
                Formatted guidance text for rolling update
            """
            
            prompt = f"""# 🚀 Rolling Update Guide: {app_name}

## Deployment Details
- **Application**: {app_name}
- **Namespace**: {namespace}
- **New Image**: {new_image}
- **Strategy**: Rolling Update (Standard K8s)

---

## What is Rolling Update?

Rolling update is the **default Kubernetes deployment strategy** that replaces pods one-by-one or in small batches.

### How it Works:
1. Create 1 new pod with new version
2. Wait for new pod to be ready
3. Terminate 1 old pod
4. Repeat until all pods are new version

### Advantages:
- ✅ **Resource Efficient**: No doubling of resources
- ✅ **Gradual**: Issues affect fewer users
- ✅ **Built-in**: Native Kubernetes support
- ⚠️ **Slower**: Takes longer than blue-green

---

## Phase 1: Pre-flight Checks

### Get Current State:

1. **Check current rollout**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Note:
   - Current replicas count
   - Current image version
   - Current health status

2. **Validate policies**:
   ```
   Tool: argo_validate_deployment_policies
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

3. **Estimate cost impact**:
   ```
   Tool: argo_estimate_rollout_cost
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
   ```

### Rolling Update Configuration:
- **maxSurge**: 1 (1 extra pod during update)
- **maxUnavailable**: 0 (no downtime)
- **Strategy**: Replace 1 pod at a time

---

## Phase 2: Update Rollout Image

### Trigger Rolling Update:

1. **Update the rollout image**:
   ```
   Tool: argo_update_rollout_image
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
   ```
   
   This will:
   - Update the rollout spec
   - Trigger Kubernetes rolling update
   - Start replacing pods one-by-one

2. **Verify update started**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Confirm:
   - Phase: "Progressing"
   - updatedReplicas > 0

---

## Phase 3: Monitor Rollout Progress

### Track Pod Replacement:

The rolling update will proceed automatically. Monitor progress:

1. **Check rollout status continuously**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Watch for:
   - **updatedReplicas**: Number of pods with new version
   - **readyReplicas**: Number of healthy pods
   - **replicas**: Total desired replicas
   
   Progress = (updatedReplicas / replicas) * 100%

2. **Monitor for issues**:
   ```
   Resource: argoflow://anomalies/detected
   ```
   
   Watch for:
   - Pod crash loops
   - Failed pod starts
   - Health check failures

### Example Progress:
```
[████░░░░░░] 40% (2/5 pods updated, 5 ready)
```

### Rollout Timeline:
- Each pod replacement: ~30-60 seconds
- Total time: (replica_count × 45 seconds) approximately

---

## Phase 4: Verify Completion

### Confirm Successful Rollout:

1. **Check final status**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Success indicators:
   - ✅ Phase: "Healthy" or "Running"
   - ✅ updatedReplicas == replicas
   - ✅ readyReplicas == replicas
   - ✅ All pods running new image

2. **Verify traffic distribution**:
   ```
   Tool: traefik_get_traffic_distribution
   Args:
     - route_name: {app_name}-route
     - namespace: {namespace}
   ```
   
   Confirm all traffic going to new version.

3. **Check deployment health**:
   ```
   Resource: argoflow://health/summary
   ```
   
   Verify health score is high (> 90).

---

## Monitoring During Rollout

### What to Watch:

1. **Pod Status**: Ensure new pods start successfully
2. **Health Checks**: Readiness/liveness probes passing
3. **Error Rates**: No spike in errors
4. **Resource Usage**: CPU/memory within limits

### Normal Behavior:
- Replica count may temporarily exceed desired (maxSurge)
- Some pods in "Terminating" state
- Gradual increase in updated pods

### Warning Signs:
- ❌ Pods stuck in "CrashLoopBackOff"
- ❌ New pods not becoming ready
- ❌ Error rate increasing
- ❌ Health checks failing

---

## Rollback if Needed

### If Update Fails:

1. **Abort the rollout**:
   ```
   Tool: argo_abort_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   This will:
   - Stop the rolling update
   - Roll back to previous version
   - Restore previous pod spec

2. **Verify rollback**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Confirm pods are back to previous version.

---

## Best Practices

### Before Rolling Update:
- ✅ Test new image in staging
- ✅ Verify resource requirements
- ✅ Check breaking changes
- ✅ Plan rollback strategy

### During Rolling Update:
- 📊 Monitor pod status continuously
- 📊 Watch error rates and latency
- 📊 Check logs for issues
- ⏱️ Be patient - rolling updates take time

### After Rolling Update:
- ✅ Verify all pods updated
- ✅ Monitor for 15-30 minutes
- ✅ Check audit trail
- ✅ Update documentation

---

## Advantages vs Other Strategies

### Rolling Update vs Canary:
- **Simpler**: No traffic management needed
- **Faster**: No waiting between steps
- **Lower Risk**: Can pause/rollback anytime

### Rolling Update vs Blue-Green:
- **Resource Efficient**: No 2x resource requirement
- **Gradual**: Issues detected incrementally
- **Native**: Built into Kubernetes

---

## Success Metrics

### Deployment Successful When:
- ✅ All pods updated to new image
- ✅ All pods in "Running" state
- ✅ Health checks passing
- ✅ No increase in error rate
- ✅ Rollout status: "Healthy"

### Tools Summary:
1. `argo_get_rollout_status` - Monitor progress
2. `argo_validate_deployment_policies` - Pre-flight check
3. `argo_estimate_rollout_cost` - Cost validation
4. `argo_update_rollout_image` - Trigger update
5. `argo_abort_rollout` - Rollback if needed
6. `traefik_get_traffic_distribution` - Verify traffic

---

## Next Steps

1. ✅ Run **Pre-flight Checks** (Phase 1)
2. 🔄 **Update Image** (Phase 2)
3. 📊 **Monitor Progress** (Phase 3)
4. ✅ **Verify Completion** (Phase 4)

**Ready to begin?** Start with the pre-flight checks above!

---

**Tip**: Rolling updates are the safest default strategy for most applications. Use canary or blue-green for higher-risk deployments.
"""
            
            return prompt
