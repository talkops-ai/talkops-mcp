"""Cost-optimized deployment guided workflow prompt.

Provides guided deployment with budget awareness and cost optimization.
"""

from argo_rollout_mcp_server.prompts.base import BasePrompt


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

> **Note:** Orchestration tools (`orch_configure_cost_aware_deployment`, `orch_validate_deployment_policy`) are a future enhancement (see Roadmap). This prompt provides **cost-conscious best practices** and uses standard tools (`validate_deployment_ready`, `argo_update_rollout`, `argorollout://cluster/health`).

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

## Phase 0: Deployment Readiness

### Validate Before Cost Analysis:

1. **Validate deployment readiness**:
   ```
   Tool: validate_deployment_ready
   Args:
     - deployment_yaml: (your existing Deployment YAML)
   ```
   Produces a readiness score (0-100). Proceed only if score >= 70.
   Checks: replicas >= 2, resource limits, readiness/liveness probes.

---

## Phase 1: Cost Analysis (Future Enhancement)

Cost analysis tools are excluded from this release. For now, use manual budget tracking and the standard deployment flow below.

---

## Phase 2: Deploy Using Standard Flow

### Steps:

1. **Validate deployment readiness**:
   ```
   Tool: validate_deployment_ready
   Args:
     - deployment_yaml: (your existing Deployment YAML)
   ```

2. **Verify cluster health**:
   ```
   Resource: argorollout://cluster/health
   ```

3. **Deploy new image** (if already a Rollout):
   ```
   Tool: argo_update_rollout
   Args:
     - name: {app_name}
     - namespace: {namespace}
     - update_type: image
     - new_image: {new_image}
   ```

4. **Monitor rollout**:
   ```
   Resource: argorollout://rollouts/{namespace}/{app_name}/detail
   ```

---

## Phase 3: Cost-Conscious Practices (Manual)

Until cost tools are available, apply these manually:
- Right-size replicas and resource requests
- Use HPA for variable workloads
- Track costs via your cloud provider's billing console

---

## Phase 4: Deploy with Cost Optimization

### Deployment Steps:

1. **Deploy with optimized settings**:
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
   (kubectl command - HPA is not yet available as an MCP tool)
   kubectl autoscale rollout {app_name} -n {namespace} \\
     --min=1 --max={target_replicas * 2} --cpu-percent=70
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

## Phase 5: Cost Monitoring (Future Enhancement)

Cost monitoring tools are excluded from this release. Track costs via your cloud provider's billing console.

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
   Resource: argorollout://cluster/health
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
1. `validate_deployment_ready` - Readiness check (score 0-100)
2. `validate_deployment_ready` - Structural readiness
3. `argorollout://cluster/health` - Cluster capacity
4. `argo_create_rollout` - Deploy with settings
5. `argo_configure_analysis_template` - Automated health metrics for cost tracking

### Resources:
1. `argorollout://cluster/health` - Cluster capacity

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
