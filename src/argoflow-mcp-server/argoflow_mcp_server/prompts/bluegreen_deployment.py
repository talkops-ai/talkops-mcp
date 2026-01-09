"""Blue-Green deployment guided workflow prompt.

Provides guided blue-green deployment with instant traffic switching.
"""

from argoflow_mcp_server.prompts.base import BasePrompt


class BlueGreenDeploymentPrompts(BasePrompt):
    """Blue-Green deployment guided workflow prompts.
    
    Provides step-by-step guidance for blue-green deployments with
    instant traffic switching and easy rollback.
    """
    
    def register(self, mcp_instance) -> None:
        """Register blue-green deployment prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def blue_green_deployment_guided(
            app_name: str,
            new_image: str,
            namespace: str = "default",
            auto_switch: bool = True
        ) -> str:
            """Guide user through blue-green deployment.
            
            This prompt provides step-by-step guidance for deploying a new version
            using blue-green strategy with instant traffic switching.
            
            Workflow:
            1. Deploy green version alongside blue
            2. Run validation tests on green
            3. Instant traffic switch (0% → 100%)
            4. Keep blue for instant rollback capability
            
            Args:
                app_name: Name of the application
                new_image: New container image to deploy
                namespace: Kubernetes namespace (default: "default")
                auto_switch: Automatically switch traffic after validation (default: True)
            
            Returns:
                Formatted guidance text for blue-green deployment
            """
            
            auto_mode = "Automatic" if auto_switch else "Manual"
            
            prompt = f"""# 🚀 Blue-Green Deployment Guide: {app_name}

## Deployment Details
- **Application**: {app_name}
- **Namespace**: {namespace}
- **New Image (Green)**: {new_image}
- **Strategy**: Blue-Green (Instant Switch)
- **Switch Mode**: {auto_mode}

---

## Workflow Overview

Blue-Green deployment allows **zero-downtime** instant switching between versions with easy rollback.

### Key Concepts:
- **Blue** = Current production version (100% traffic)
- **Green** = New version (0% traffic until switch)
- **Switch** = Instant traffic change (100% traffic to green)
- **Rollback** = Instant revert to blue if issues occur

### Deployment Steps:
1. ✅ **Pre-flight Checks** - Validate policies and costs
2. 🟢 **Deploy Green** - New version alongside blue
3. ✅ **Validate Green** - Run smoke tests
4. 🔄 **Switch Traffic** - Instant 100% to green
5. 🔵 **Cleanup Blue** - Remove old version (after stabilization)

---

## Phase 1: Pre-flight Checks

### Current State:
First, identify the current blue (production) version.

1. **Get current rollout status**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Note the current image (this is your "blue" version).

2. **Validate deployment policies**:
   ```
   Tool: argo_validate_deployment_policies
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

3. **Check cost impact**:
   ```
   Tool: argo_estimate_rollout_cost
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
   ```

### Success Criteria:
- ✅ Current blue version identified
- ✅ Policies validated
- ✅ Sufficient resources available
- ⚠️ Note: Blue-green requires 2x resources temporarily

---

## Phase 2: Deploy Green Version

### Create Green Deployment:

1. **Create rollout with blue-green strategy**:
   ```
   Tool: argo_create_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - image: {new_image}
     - strategy: bluegreen
     - replicas: <same as blue>
   ```

2. **Monitor green deployment readiness**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Wait for:
   - Phase: "Paused" (waiting for promotion)
   - All green pods ready
   - Blue still receiving 100% traffic

### Expected State:
- **Blue**: Active, 100% traffic
- **Green**: Ready, 0% traffic
- **Status**: Paused at traffic switch gate

---

## Phase 3: Validate Green Version

### Run Validation Tests:

Before switching traffic, validate the green version works correctly.

#### Connectivity Test:
1. Use pod exec to test green service:
   ```
   (External tool - kubectl exec)
   curl http://{app_name}-green-svc/healthz
   ```

#### Smoke Tests:
2. **Check pod health**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}  
   ```
   
   Verify:
   - All green replicas are "Ready"
   - No crash loops
   - Health check passing

#### API Version Test:
3. Validate the green version endpoint:
   ```
   (Custom validation)
   - Check /version endpoint
   - Verify expected version number
   - Test key API endpoints
   ```

### Validation Checklist:
- ✅ All green pods ready
- ✅ Health checks passing
- ✅ No errors in logs
- ✅ API endpoints responding
- ✅ Database connections working

---

## Phase 4: Switch Traffic to Green

### {"Automatic" if auto_switch else "Manual"} Traffic Switch:

"""

            if auto_switch:
                prompt += f"""
#### Automatic Switch (After Validation):

1. **Promote rollout to green**:
   ```
   Tool: argo_promote_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - full: true
   ```
   
   This will:
   - Switch 100% traffic from blue to green
   - Blue remains running (for rollback)

2. **Verify traffic switch**:
   ```
   Tool: traefik_get_traffic_distribution
   Args:
     - route_name: {app_name}-route
     - namespace: {namespace}
   ```
   
   Confirm:
   - Green: 100% traffic
   - Blue: 0% traffic

3. **Monitor green in production**:
   ```
   Resource: argoflow://anomalies/detected
   ```
   
   Watch for 5-10 minutes for any issues.
"""
            else:
                prompt += f"""
#### Manual Switch (Requires Approval):

Green version is validated and ready. **When ready to switch**:

1. **Manually promote rollout**:
   ```
   Tool: argo_promote_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - full: true
   ```

2. **Verify traffic switch**:
   ```
   Tool: traefik_get_traffic_distribution
   Args:
     - route_name: {app_name}-route
     - namespace: {namespace}
   ```

**Note**: Take your time. Green is stable and ready. Switch when appropriate.
"""

            prompt += f"""
---

## Phase 5: Cleanup Blue Version

### After Green is Stable (Recommended: 1 hour):

1. **Confirm green stability**:
   - Monitor metrics for at least 1 hour
   - No anomalies detected
   - Error rates normal
   - User feedback positive

2. **Delete blue rollout**:
   ```
   Tool: argo_delete_rollout
   Args:
     - name: {app_name}-blue
     - namespace: {namespace}
   ```

**Important**: Keep blue running until you're confident green is stable!

---

## Emergency Rollback

### If Issues Detected on Green:

#### Instant Rollback to Blue:

1. **Abort current rollout**:
   ```
   Tool: argo_abort_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   This will:
   - Instantly switch traffic back to blue
   - Green remains running for debugging

2. **Verify rollback**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```
   
   Confirm blue is serving 100% traffic.

### Rollback is instant (< 1 second)!

---

## Advantages of Blue-Green

- ✅ **Instant Switch**: 0-second deployment
- ✅ **Instant Rollback**: If issues detected
- ✅ **Full Validation**: Test green before switch
- ✅ **Zero Downtime**: Both versions running
- ⚠️ **Resource Cost**: Requires 2x resources temporarily

---

## Success Metrics

### Deployment Successful When:
- ✅ Green version deployed and validated
- ✅ Traffic switched to green (100%)
- ✅ No anomalies for stabilization period
- ✅ Blue cleaned up after confidence

### Tools Summary:
1. `argo_get_rollout_status` - Check current state
2. `argo_validate_deployment_policies` - Policy check
3. `argo_estimate_rollout_cost` - Cost validation
4. `argo_create_rollout` - Deploy green
5. `argo_promote_rollout` - Switch traffic
6. `argo_abort_rollout` - Emergency rollback
7. `argo_delete_rollout` - Cleanup blue
8. `traefik_get_traffic_distribution` - Verify traffic

---

## Next Steps

1. ✅ Complete **Pre-flight Checks** (Phase 1)
2. 🟢 Deploy **Green Version** (Phase 2)
3. ✅ **Validate** green thoroughly (Phase 3)
4. 🔄 **Switch** traffic when ready (Phase 4)
5. 🔵 **Cleanup** blue after stabilization (Phase 5)

**Ready to begin?** Start with identifying your current blue version!
"""
            
            return prompt
