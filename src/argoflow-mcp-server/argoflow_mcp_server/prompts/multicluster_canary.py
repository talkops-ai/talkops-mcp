"""Multi-cluster canary deployment guided workflow prompt.

Provides guided multi-cluster canary deployment with per-region rollout.
"""

from argoflow_mcp_server.prompts.base import BasePrompt


class MultiClusterCanaryPrompts(BasePrompt):
    """Multi-cluster canary deployment guided workflow prompts.
    
    Provides step-by-step guidance for canary deployments across
    multiple clusters/regions with coordinated rollout.
    """
    
    def register(self, mcp_instance) -> None:
        """Register multi-cluster canary prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def multi_cluster_canary_guided(
            app_name: str,
            new_image: str,
            regions: str = "us-west-2,us-east-1,eu-west-1"
        ) -> str:
            """Guide user through multi-cluster canary deployment.
            
            This prompt provides step-by-step guidance for deploying a new version
            across multiple clusters/regions using coordinated canary strategy.
            
            Workflow:
            1. Validate all clusters
            2. Deploy canary to Region 1
            3. Monitor Region 1 (5 min)
            4. If healthy → Deploy to Region 2
            5. Continue until all regions deployed
            
            Args:
                app_name: Name of the application
                new_image: New container image to deploy
                regions: Comma-separated list of regions/clusters
            
            Returns:
                Formatted guidance text for multi-cluster canary deployment
            """
            
            region_list = [r.strip() for r in regions.split(',')]
            
            prompt = f"""# 🌍 Multi-Cluster Canary Deployment Guide: {app_name}

## Deployment Details
- **Application**: {app_name}
- **New Image**: {new_image}
- **Strategy**: Multi-Cluster Canary (Sequential Regions)
- **Regions**: {', '.join(region_list)}

---

## What is Multi-Cluster Canary?

Deploy a new version **sequentially across multiple regions/clusters**, validating each region before proceeding to the next.

### Strategy:
1. Deploy to **Region 1** (e.g., us-west-2)
2. Monitor for **5-10 minutes**
3. If healthy → Deploy to **Region 2** (e.g., us-east-1)
4. Repeat for all regions
5. Rollback all if any region fails

### Advantages:
- ✅ **Regional Isolation**: Issues contained to one region
- ✅ **Progressive Rollout**: Validate before spreading
- ✅ **Global Coordination**: Consistent deployment
- ✅ **Risk Mitigation**: Failed region doesn't affect others

---

## Phase 1: Multi-Cluster Pre-flight Checks

### For Each Region:

"""

            for i, region in enumerate(region_list, 1):
                prompt += f"""
#### Region {i}: {region}

1. **Validate cluster access**:
   ```
   (Set kubeconfig context to {region})
   kubectl config use-context {region}
   ```

2. **Check policies**:
   ```
   Tool: argo_validate_deployment_policies
   Args:
     - name: {app_name}
     - namespace: default
     - context: {region}
   ```

3. **Verify resources**:
   ```
   Resource: argoflow://cluster/health
   (For cluster: {region})
   ```
   
   Ensure sufficient capacity.

"""

            prompt += f"""
### Pre-flight Checklist:
- ✅ All {len(region_list)} regions accessible
- ✅ Policies validated in all regions
- ✅ Resources available in all regions
- ✅ Cross-region communication working

---

## Phase 2: Sequential Regional Deployment

### Region-by-Region Rollout:

"""

            for i, region in enumerate(region_list, 1):
                prompt += f"""
### Region {i}: {region}

#### Step 1: Deploy Canary

1. **Switch to {region} context**:
   ```
   kubectl config use-context {region}
   ```

2. **Create canary rollout**:
   ```
   Tool: argo_update_rollout_image
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: default
     - context: {region}
   ```

3. **Verify canary created**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: default
     - context: {region}
   ```
   
   Expected:
   - Phase: "Progressing"  
   - Canary pods starting

#### Step 2: Monitor {region} (5 minutes)

**Wait 5 minutes** while monitoring:

1. **Check rollout health**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: default
     - context: {region}
   ```

2. **Monitor traffic**:
   ```
   Tool: traefik_get_traffic_distribution
   Args:
     - route_name: {app_name}-route
     - namespace: default
     - context: {region}
   ```

3. **Check for anomalies**:
   ```
   Resource: argoflow://anomalies/detected
   (For cluster: {region})
   ```

#### Step 3: Health Gate for {region}

**Health Requirements**:
- ✅ All canary pods ready
- ✅ Error rate < 5%
- ✅ No anomalies detected
- ✅ Latency within acceptable range

**Health Score Threshold**: > 70/100

If {region} health < 70:
- ❌ **STOP deployment**
- ❌ Rollback {region}
- ❌ Do NOT proceed to next region

If {region} health ≥ 70:
- ✅ Promote {region} to 100%
- ✅ Proceed to next region

#### Step 4: Promote {region}

1. **Full promotion in {region}**:
   ```
   Tool: argo_promote_rollout
   Args:
     - name: {app_name}
     - namespace: default
     - full: true
     - context: {region}
   ```

2. **Verify promotion**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: default
     - context: {region}
   ```
   
   Confirm 100% traffic to new version.

{"---" if i < len(region_list) else ""}

"""

            prompt += f"""
---

## Phase 3: Global Verification

### After All Regions Deployed:

1. **Verify all regions healthy**:

"""

            for region in region_list:
                prompt += f"""
   **{region}**:
   ```
   Tool: argo_get_rollout_status
   Args:
     - name: {app_name}
     - namespace: default
     - context: {region}
   ```
"""

            prompt += f"""

2. **Check global traffic distribution**:
   - All regions serving new version
   - No anomalies across any region
   - Error rates normal globally

3. **Monitor for 30 minutes**:
   - Set up alerts for all regions
   - Watch for any regional issues
   - Verify cross-region communication

---

## Emergency: Multi-Region Rollback

### If Any Region Fails:

#### Coordinated Rollback Strategy:

1. **Identify failing region**:
   ```
   Resource: argoflow://anomalies/detected
   ```
   
   Determine which region has issues.

2. **Rollback ALL regions** (coordinated):

"""

            for region in region_list:
                prompt += f"""
   **Rollback {region}**:
   ```
   Tool: argo_abort_rollout
   Args:
     - name: {app_name}
     - namespace: default
     - context: {region}
   ```
"""

            prompt += f"""

3. **Verify global rollback**:
   - All regions back to previous version
   - Traffic stable across all regions
   - No ongoing deployments

### Why Rollback All Regions?
- Ensures **version consistency** globally
- Prevents **cross-region compatibility issues**
- Maintains **predictable behavior**

---

## Best Practices

### Regional Ordering:
1. **Start with lowest-traffic region** (e.g., dev/staging cluster)
2. **Then medium-traffic** (e.g., us-west-2)
3. **Finally highest-traffic** (e.g., us-east-1 for US customers)

### Monitoring:
- ✅ Set up centralized monitoring dashboard
- ✅ Aggregate metrics across regions
- ✅ Alert on any regional anomaly
- ✅ Track deployment progress globally

### Timing:
- **Initial region**: Monitor for 10 minutes
- **Subsequent regions**: 5 minutes each
- **Final verification**: 30 minutes post-deployment

---

## Regional Health Scoring

### Calculate Region Health:

**Formula**:
```
health = (ready_pods / desired_pods) * 50 +
         (error_rate < 5% ? 25 : 0) +
         (no_anomalies ? 25 : 0)
```

**Thresholds**:
- 90-100: Excellent - Proceed immediately
- 70-89: Good - Proceed with caution
- < 70: Poor - STOP and investigate

---

## Coordination Checklist

### Before Deployment:
- ✅ All regions accessible
- ✅ Uniform configuration across regions
- ✅ Cross-region networking verified
- ✅ Rollback plan documented

### During Deployment:
- ✅ One region at a time (sequential)
- ✅ Health gate between regions
- ✅ Continuous monitoring
- ✅ Ready to rollback any time

### After Deployment:
- ✅ All regions on same version
- ✅ Global health monitoring active
- ✅ Audit trail captured
- ✅ Lessons learned documented

---

## Success Metrics

### Deployment Successful When:
- ✅ All {len(region_list)} regions deployed
- ✅ All regions passing health checks
- ✅ No anomalies in any region
- ✅ Global traffic flowing correctly
- ✅ Version consistency across regions

### Tools Summary:
1. `argo_validate_deployment_policies` - Per-region validation
2. `argo_update_rollout_image` - Deploy to each region
3. `argo_get_rollout_status` - Monitor each region
4. `argo_promote_rollout` - Promote each region
5. `argo_abort_rollout` - Rollback if needed
6. `traefik_get_traffic_distribution` - Per-region traffic
7. `argoflow://cluster/health` - Region health
8. `argoflow://anomalies/detected` - Cross-region anomalies

---

## Next Steps

1. ✅ **Pre-flight Checks** for all {len(region_list)} regions
2. 🌍 Deploy to **{region_list[0]}** first
3. 📊 Monitor and validate
4. 🌍 Proceed to remaining regions sequentially
5. ✅ Global verification

**Ready to begin?** Start with multi-cluster pre-flight checks!

---

**Important**: Multi-cluster deployments require careful coordination. Always validate health at each step before proceeding.
"""
            
            return prompt
