"""Cost-optimized deployment guided workflow prompt.

Provides guided deployment with budget awareness and cost optimization.
"""

from argoflow_mcp_server.prompts.base import BasePrompt


class CostOptimizedDeploymentPrompts(BasePrompt):
    """Cost-optimized deployment guided workflow prompts.
    
    Provides step-by-step guidance for budget-aware deployments
    with cost optimization strategies.
    """
    
    def register(self, mcp_instance) -> None:
        """Register cost-optimized deployment prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def cost_optimized_deployment_guided(
            app_name: str,
            new_image: str,
            namespace: str = "default",
            target_replicas: int = 3,
            monthly_budget: float = 100000.0
        ) -> str:
            """Guide user through cost-optimized deployment.
            
            This prompt provides step-by-step guidance for deploying while
            staying within budget and optimizing costs.
            
            Workflow:
            1. Analyze current costs
            2. Estimate new deployment cost
            3. Check against budget
            4. Deploy with cost optimizations
            5. Monitor cost impact
            
            Args:
                app_name: Name of the application
                new_image: New container image to deploy
                namespace: Kubernetes namespace (default: "default")
                target_replicas: Target replica count (default: 3)
                monthly_budget: Monthly budget in USD (default: $100,000)
            
            Returns:
                Formatted guidance text for cost-optimized deployment
            """
            
            daily_budget = monthly_budget / 30
            hourly_budget = monthly_budget / 30 / 24
            
            prompt = f"""# 💰 Cost-Optimized Deployment Guide: {app_name}

## Deployment Details
- **Application**: {app_name}
- **Namespace**: {namespace}
- **New Image**: {new_image}
- **Target Replicas**: {target_replicas}
- **Strategy**: Cost-Optimized Deployment

## Budget Configuration
- **Monthly Budget**: ${monthly_budget:,.2f}
- **Daily Budget**: ${daily_budget:,.2f}
- **Hourly Budget**: ${hourly_budget:,.2f}

---

## What is Cost-Optimized Deployment?

Deploy new versions while **staying within budget** and **optimizing resource usage**.

### Key Principles:
1. **Budget Validation**: Ensure deployment doesn't exceed budget
2. **Resource Optimization**: Right-size replicas and resources
3. **Waste Reduction**: Eliminate unhealthy/unused pods
4. **Auto-Scaling**: Use HPA for cost efficiency
5. **Cost Monitoring**: Track actual vs estimated costs

---

## Phase 1: Cost Analysis

### Current Cost Baseline:

1. **Get current cost analytics**:
   ```
   Resource: argoflow://cost/analytics
   ```
   
   This shows:
   - Total hourly/daily/monthly costs
   - Cost per deployment
   - Budget utilization

2. **Check deployment-specific costs**:
   ```
   Resource: argoflow://cost/{namespace}/{app_name}/details
   ```
   
   Review:
   - Current replica count
   - Cost per replica
   - Waste (unhealthy replicas)
   - Optimization suggestions

### Calculate Budget Headroom:

**Formula**:
```
headroom = daily_budget - current_daily_cost
available_for_deployment = headroom * 0.80  (20% safety margin)
```

Expected output:
- Current daily cost: $X.XX
- Budget remaining: $Y.YY
- Safe deployment budget: $Z.ZZ

---

## Phase 2: Estimate Deployment Cost

### Calculate New Deployment Cost:

1. **Estimate rollout cost**:
   ```
   Tool: argo_estimate_rollout_cost
   Args:
     - name: {app_name}
     - new_image: {new_image}
     - namespace: {namespace}
     - replicas: {target_replicas}
   ```
   
   This estimates:
   - Cost per replica
   - Total daily cost for {target_replicas} replicas
   - Projected monthly cost

2. **Calculate total cost impact**:
   ```
   Total Daily = Current Daily Cost + New Deployment Cost
   ```

3. **Budget compliance check**:
   ```
   if Total Daily > Daily Budget:
       ❌ EXCEEDS BUDGET - Need optimization
   else:
       ✅ WITHIN BUDGET - Can proceed
   ```

---

## Phase 3: Budget Validation \u0026 Optimization

### If Deployment Exceeds Budget:

#### Cost Optimization Strategies:

1. **Reduce Replica Count**:
   ```
   Suggested replicas = floor(budget_headroom / cost_per_replica)
   ```
   
   Example:
   - Budget headroom: ${daily_budget * 0.2:,.2f}/day
   - Cost per replica: $X/day
   - Suggested: Y replicas (instead of {target_replicas})

2. **Enable Horizontal Pod Autoscaler (HPA)**:
   ```
   Tool: argo_enable_hpa
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - min_replicas: 1
     - max_replicas: {target_replicas * 2}
     - target_cpu_percent: 70
   ```
   
   Benefits:
   - Start with 1-2 replicas
   - Scale up only when needed
   - Scale down during low traffic
   - **Save 40-60% on costs**

3. **Resource Right-Sizing**:
   - Review CPU/memory requests
   - Reduce if over-provisioned
   - Use Vertical Pod Autoscaler (VPA)

4. **Spot/Preemptible Instances**:
   - Use node selectors for spot instances
   - Save 60-80% on compute costs
   - Good for non-critical workloads

### If Within Budget:

✅ **Proceed with deployment**

Calculate optimal initial replicas:
```
initial_replicas = min(target_replicas, 2)  # Start small
```

---

## Phase 4: Deploy with Cost Optimization

### Deployment with Cost Controls:

1. **Pre-flight checks**:
   ```
   Tool: argo_validate_deployment_policies
   Args:
     - name: {app_name}
     - namespace: {namespace}
   ```

2. **Deploy with optimized settings**:
   ```
   Tool: argo_create_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - image: {new_image}
     - strategy: canary
     - replicas: <optimized_count>
     - enable_hpa: true
   ```

3. **Enable HPA** (if not already):
   ```
   Tool: argo_enable_hpa
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - min_replicas: 1
     - max_replicas: {target_replicas * 2}
     - target_cpu_percent: 70
   ```

4. **Set resource limits**:
   ```
   (Via rollout spec)
   resources:
     requests:
       cpu: 250m
       memory: 512Mi
     limits:
       cpu: 500m
       memory: 1Gi
   ```

---

## Phase 5: Cost Monitoring

### Track Actual vs Estimated Costs:

1. **Monitor deployment costs** (every 5 minutes):
   ```
   Resource: argoflow://cost/{namespace}/{app_name}/details
   ```
   
   Track:
   - Actual replicas deployed
   - Actual cost per hour
   - Actual daily cost
   - Compare to estimate

2. **Check for waste**:
   ```
   Resource: argoflow://cost/{namespace}/{app_name}/details
   ```
   
   Look for:
   - Unhealthy replicas (still cost money!)
   - Over-provisioned resources
   - Idle pods

3. **Real-time cost updates**:

   **Minute 1**: $X.XX/day (starting)
   **Minute 5**: $Y.YY/day (scaling)
   **Minute 10**: $Z.ZZ/day (stable)

### Cost Variance Analysis:

```
Estimated daily cost: ${daily_budget * 0.1:,.2f}
Actual daily cost:    $W.WW
Variance:             $V.VV (±X%)
```

**Acceptable variance**: ±10%

If variance > 10%:
- ⚠️ Investigate resource usage
- ⚠️ Check for unexpected scaling
- ⚠️ Review pod count

---

## Phase 6: Post-Deployment Optimization

### Continuous Cost Optimization:

1. **Wait 24-48 hours** for traffic patterns

2. **Analyze resource usage**:
   ```
   Resource: argoflow://cluster/health
   ```
   
   Check:
   - Actual CPU usage vs requests
   - Actual memory usage vs requests
   - HPA scaling patterns

3. **Right-size resources**:
   
   If CPU usage < 50% of requests:
   - Reduce CPU requests by 30%
   
   If memory usage < 60% of requests:
   - Reduce memory requests by 20%

4. **Optimize HPA settings**:
   
   Adjust based on scaling patterns:
   - Too much scaling? Increase target CPU %
   - Not scaling enough? Decrease target CPU %

### Cost Savings Report:

```
Initial estimate:        ${daily_budget * 0.15:,.2f}/day
Actual optimized cost:   $X.XX/day
Monthly savings:         $Y.YY
Annual savings:          $Z,ZZZ
```

---

## Cost Optimization Best Practices

### Resource Requests:
- ✅ Set requests based on actual usage (not guesses)
- ✅ Use VPA for automatic right-sizing
- ✅ Monitor and adjust quarterly

### Horizontal Scaling:
- ✅ Always enable HPA for variable workloads
- ✅ Set min=1 or 2 for cost savings
- ✅ Set max based on peak load + 20%

### Node Selection:
- ✅ Use spot instances for dev/staging (60-80% savings)
- ✅ Use reservations for stable production workloads
- ✅ Mix spot + on-demand for resilience

### Monitoring:
- ✅ Review costs weekly
- ✅ Set budget alerts
- ✅ Track cost per transaction/user

---

## Budget Alerts

### Set Up Alerts:

1. **Daily cost exceeds 80% of budget**:
   - Investigate immediately
   - Identify cost spike source
   - Scale down if necessary

2. **Unexpected scaling events**:
   - HPA scaled beyond expected
   - Check traffic patterns
   - Review HPA metrics

3. **Cost variance > 20%**:
   - Actual vs estimated significantly different
   - May indicate issue or opportunity

---

## Success Metrics

### Deployment Successful \u0026 Cost-Optimized When:
- ✅ Deployment completes within budget
- ✅ Actual cost ≤ estimated cost
- ✅ HPA enabled and working
- ✅ Resources right-sized
- ✅ No waste detected
- ✅ Cost variance < 10%

### Cost Efficiency Metrics:
- **Cost per replica**: $X/day
- **Cost per user/transaction**: $Y
- **Utilization rate**: Z% (target: > 70%)
- **Waste percentage**: W% (target: < 5%)

---

## Tools \u0026 Resources Summary

### Tools:
1. `argo_estimate_rollout_cost` - Estimate deployment cost
2. `argo_validate_deployment_policies` - Pre-flight check
3. `argo_create_rollout` - Deploy with settings
4. `argo_enable_hpa` - Enable auto-scaling

### Resources:
1. `argoflow://cost/analytics` - Global cost summary
2. `argoflow://cost/{{namespace}}/{{app}}/details` - Per-deployment costs
3. `argoflow://cluster/health` - Resource capacity

---

## Next Steps

1. 💰 **Analyze Current Costs** (Phase 1)
2. 📊 **Estimate New Deployment** (Phase 2)
3. ✅ **Validate Budget** (Phase 3)
4. 🚀 **Deploy Optimized** (Phase 4)
5. 📈 **Monitor Costs** (Phase 5)
6. 🎯 **Optimize Further** (Phase 6)

**Ready to begin?** Start with cost analysis!

---

**Tip**: The cheapest deployment is one that scales to zero during idle periods. Consider serverless options for very low traffic applications.
"""
            
            return prompt
