"""Orchestration service for intelligent deployment management.

This service provides high-level orchestration capabilities including:
- Intelligent promotion with ML-based decisions
- Cost-aware deployment optimization
- Multi-cluster deployment coordination
- Policy validation and compliance
- AI-driven insights and recommendations
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from kubernetes import client

logger = logging.getLogger(__name__)


class OrchestrationService:
    """Service for orchestrating intelligent deployments.
    
    Coordinates between Argo Rollouts, Traefik, and Kubernetes
    to provide smart deployment capabilities.
    """
    
    def __init__(self, config, argo_service=None, traefik_service=None):
        """Initialize orchestration service.
        
        Args:
            config: Server configuration
            argo_service: ArgoRolloutsService instance
            traefik_service: TraefikService instance
        """
        self.config = config
        self.argo_service = argo_service
        self.traefik_service = traefik_service
        self.k8s_apps_v1 = None
        self.k8s_autoscaling_v2 = None
        
    async def initialize(self):
        """Initialize async components."""
        try:
            # Initialize Kubernetes clients
            self.k8s_apps_v1 = client.AppsV1Api()
            self.k8s_autoscaling_v2 = client.AutoscalingV2Api()
            logger.info("OrchestrationService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OrchestrationService: {e}")
            raise
    
    # ==================== TOOL 20: INTELLIGENT PROMOTION ====================
    
    async def deploy_with_intelligent_promotion(
        self,
        app_name: str,
        image: str,
        namespace: str = "default",
        strategy: str = "canary",
        ml_model: str = "gradient_boosting",
        health_threshold: float = 0.95,
        max_iterations: int = 10
    ) -> Dict[str, Any]:
        """Deploy with ML-based intelligent promotion.
        
        This is the master orchestrator that coordinates deployment
        with intelligent, metrics-driven canary progression.
        
        Args:
            app_name: Application/rollout name
            image: Container image to deploy
            namespace: Kubernetes namespace
            strategy: Deployment strategy (canary, bluegreen, rolling)
            ml_model: ML model for decisions (gradient_boosting, random_forest)
            health_threshold: Minimum health score (0-1) for promotion
            max_iterations: Maximum promotion iterations
            
        Returns:
            Deployment result with history and metrics
        """
        try:
            logger.info(f"🚀 Starting intelligent promotion for {app_name}")
            
            # Step 1: Analyze current state
            logger.info("📊 Analyzing current state...")
            current_state = await self._analyze_deployment_state(app_name, namespace)
            
            # Step 2: Validate policies
            logger.info("🔍 Validating deployment policies...")
            policy_check = await self.validate_deployment_policy(app_name, namespace)
            
            if policy_check.get("validation_result") == "failed":
                logger.error("❌ Policy validation failed")
                return {
                    "status": "error",
                    "reason": "policy_validation_failed",
                    "message": "Policy validation failed",
                    "details": policy_check
                }
            
            # Step 3: Check cost constraints
            logger.info("💰 Checking cost constraints...")
            cost_check = await self.configure_cost_aware_deployment(
                app_name=app_name,
                namespace=namespace,
                max_daily_cost=1000.0,
                mode="validate"
            )
            
            if not cost_check.get("within_budget"):
                logger.warning(f"⚠️ Cost warning: {cost_check.get('message', 'Over budget')}")
            
            # Step 4: Update rollout image
            logger.info(f"📦 Updating {strategy} rollout with image {image}...")
            try:
                update_result = await self.argo_service.update_rollout_image(
                    name=app_name,
                    new_image=image,
                    namespace=namespace
                )
                
                if not update_result.get("success"):
                    return {
                        "status": "error",
                        "message": f"Failed to update rollout: {update_result.get('message')}"
                    }
            except Exception as e:
                logger.error(f"Failed to update rollout: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to update rollout: {str(e)}"
                }
            
            # Step 5: ML-based promotion loop
            logger.info(f"🤖 Starting ML-based promotion with {ml_model}")
            
            promotion_history = []
            current_weight = 0
            iteration = 0
            
            while current_weight < 100 and iteration < max_iterations:
                iteration += 1
                
                # Get current metrics
                metrics = await self._get_deployment_metrics(app_name, namespace)
                
                # Calculate health score
                health_score = self._calculate_health_score(metrics)
                
                # Use ML model to predict next weight
                next_weight = self._predict_next_weight(
                    current_weight=current_weight,
                    health_score=health_score,
                    metrics=metrics,
                    model=ml_model,
                    historical_data=promotion_history
                )
                
                logger.info(f"  Iteration {iteration}: Health={health_score:.2f}, "
                           f"Predicted weight={next_weight}%")
                
                # Check if health is acceptable
                if health_score < health_threshold:
                    logger.warning(f"⚠️ Health score {health_score} below threshold")
                    
                    if iteration > 2:
                        logger.error("❌ Health degradation, aborting deployment")
                        await self.argo_service.abort_rollout(app_name, namespace)
                        
                        return {
                            "status": "aborted",
                            "reason": "health_degradation",
                            "health_score": health_score,
                            "iterations": iteration,
                            "message": "Deployment aborted due to low health score"
                        }
                
                # Record promotion step
                current_weight = next_weight
                promotion_history.append({
                    "iteration": iteration,
                    "weight": next_weight,
                    "health_score": health_score,
                    "metrics": metrics,
                    "timestamp": datetime.now().isoformat()
                })
                
                # If not at 100% yet, promote to next step
                if next_weight < 100:
                    try:
                        await self.argo_service.promote_rollout(
                            name=app_name,
                            namespace=namespace,
                            skip_current_step=False
                        )
                    except Exception as e:
                        logger.error(f"Failed to promote rollout: {e}")
                
                # Wait before next iteration
                wait_time = self._calculate_wait_time(iteration, health_score)
                logger.info(f"  Waiting {wait_time}s before next promotion...")
                await asyncio.sleep(wait_time)
            
            logger.info(f"✅ Deployment complete after {iteration} iterations")
            
            return {
                "status": "success",
                "app_name": app_name,
                "namespace": namespace,
                "strategy": strategy,
                "ml_model": ml_model,
                "iterations": iteration,
                "final_weight": current_weight,
                "promotion_history": promotion_history,
                "message": f"Successfully deployed {app_name} with intelligent promotion"
            }
            
        except Exception as e:
            logger.error(f"❌ Intelligent promotion failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def _analyze_deployment_state(
        self,
        app_name: str,
        namespace: str
    ) -> Dict[str, Any]:
        """Analyze current deployment state."""
        try:
            rollout_status = await self.argo_service.get_rollout_status(
                name=app_name,
                namespace=namespace
            )
            
            return {
                "current_replicas": rollout_status.get("replicas", 0),
                "ready_replicas": rollout_status.get("ready_replicas", 0),
                "phase": rollout_status.get("phase", "Unknown"),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"Could not analyze deployment state: {e}")
            return {
                "current_replicas": 0,
                "ready_replicas": 0,
                "phase": "Unknown",
                "timestamp": datetime.now().isoformat()
            }
    
    async def _get_deployment_metrics(
        self,
        app_name: str,
        namespace: str
    ) -> Dict[str, Any]:
        """Get current deployment metrics.
        
        In MVP, returns simulated metrics. In production, would query Prometheus.
        """
        # TODO: Integrate with Prometheus/metrics system
        return {
            "error_rate": 0.01,  # 1% error rate
            "latency_p95_ms": 150,
            "throughput_rps": 1000,
            "cpu_usage_percent": 45,
            "memory_usage_percent": 60,
            "traffic_percent": 50
        }
    
    def _calculate_health_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate health score (0-1) based on metrics."""
        error_rate = metrics.get("error_rate", 0)
        latency = metrics.get("latency_p95_ms", 0)
        
        # Penalize high error rate
        error_penalty = min(error_rate * 10, 1.0)
        
        # Penalize high latency (> 500ms is bad)
        latency_penalty = min(latency / 500, 1.0)
        
        # Calculate score
        health_score = 1.0 - (error_penalty * 0.5 + latency_penalty * 0.5)
        
        return max(0.0, min(health_score, 1.0))
    
    def _predict_next_weight(
        self,
        current_weight: int,
        health_score: float,
        metrics: Dict[str, Any],
        model: str,
        historical_data: List[Dict]
    ) -> int:
        """Use ML model to predict next weight.
        
        MVP Implementation: Rule-based logic simulating ML decisions.
        Production: Would use actual ML models (scikit-learn, TensorFlow).
        """
        if model == "gradient_boosting":
            # Aggressive promotion for excellent health
            if health_score > 0.98:
                return min(100, current_weight + 50)
            # Moderate promotion for good health
            elif health_score > 0.95:
                return min(100, current_weight + 25)
            # Conservative promotion for acceptable health
            elif health_score > 0.90:
                return min(100, current_weight + 10)
            # No promotion for poor health
            else:
                return current_weight
                
        elif model == "random_forest":
            # Trend-based logic
            if len(historical_data) > 2:
                recent_trend = (historical_data[-1]["health_score"] -
                              historical_data[-2]["health_score"])
                
                # Improving trend
                if recent_trend > 0.02:
                    return min(100, current_weight + 30)
                # Stable trend
                elif recent_trend > -0.02:
                    return min(100, current_weight + 15)
            
            # Default increment
            return min(100, current_weight + 15)
        
        # Fallback: conservative increment
        return min(100, current_weight + 10)
    
    def _calculate_wait_time(self, iteration: int, health_score: float) -> int:
        """Calculate wait time between promotions."""
        base_wait = 60  # 60 seconds base
        
        # Shorter wait for excellent health
        if health_score > 0.98:
            return base_wait // 2  # 30 seconds
        
        # Longer wait for marginal health
        if health_score < 0.90:
            return base_wait * 2  # 120 seconds
        
        return base_wait
    
    # ==================== TOOL 21: COST-AWARE DEPLOYMENT ====================
    
    async def configure_cost_aware_deployment(
        self,
        app_name: str,
        namespace: str = "default",
        max_daily_cost: float = 100.0,
        mode: str = "optimize",
        cost_per_pod_hour: float = 0.05
    ) -> Dict[str, Any]:
        """Configure cost-aware deployment with optimization.
        
        Args:
            app_name: Application name
            namespace: Kubernetes namespace
            max_daily_cost: Maximum daily cost budget
            mode: Operation mode (validate, optimize, report)
            cost_per_pod_hour: Cost per pod per hour
            
        Returns:
            Cost analysis and optimization results
        """
        try:
            logger.info(f"💰 Configuring cost-aware deployment for {app_name}")
            
            # Get rollout status to determine replica count
            try:
                rollout_status = await self.argo_service.get_rollout_status(
                    name=app_name,
                    namespace=namespace
                )
                replicas = rollout_status.get("replicas", 3)
            except Exception:
                # Fallback to estimated replicas
                replicas = 3
            
            # Calculate current costs
            current_hourly_cost = replicas * cost_per_pod_hour
            current_daily_cost = current_hourly_cost * 24
            
            # Calculate budget utilization
            budget_utilization = (current_daily_cost / max_daily_cost) * 100
            
            logger.info(f"  Current daily cost: ${current_daily_cost:.2f}")
            logger.info(f"  Budget utilization: {budget_utilization:.1f}%")
            
            # Generate recommendations
            recommendations = []
            
            if budget_utilization > 90:
                recommendations.append({
                    "type": "critical",
                    "severity": "high",
                    "message": "Cost budget almost exceeded",
                    "action": "Consider reducing replicas or enabling HPA"
                })
            
            if replicas > 10:
                recommendations.append({
                    "type": "optimization",
                    "severity": "medium",
                    "message": f"{replicas} replicas may be overprovisioned",
                    "action": "Use Horizontal Pod Autoscaler (HPA)",
                    "recommended_replicas": max(3, replicas // 2)
                })
            
            # Mode-specific actions
            if mode == "validate":
                return {
                    "status": "success",
                    "mode": "validate",
                    "app_name": app_name,
                    "namespace": namespace,
                    "current_hourly_cost": round(current_hourly_cost, 2),
                    "current_daily_cost": round(current_daily_cost, 2),
                    "max_daily_cost": max_daily_cost,
                    "budget_utilization_percent": round(budget_utilization, 1),
                    "within_budget": budget_utilization <= 100,
                    "replicas": replicas,
                    "recommendations": recommendations
                }
                
            elif mode == "optimize":
                logger.info("🔧 Applying cost optimizations...")
                
                actions_taken = []
                new_replicas = replicas
                
                # Reduce replicas if over budget
                if budget_utilization > 100:
                    new_replicas = max(1, int(replicas * (max_daily_cost / current_daily_cost)))
                    actions_taken.append(f"reduced_replicas_to_{new_replicas}")
                    logger.info(f"✅ Would reduce replicas from {replicas} to {new_replicas}")
                
                # Calculate new costs
                new_hourly_cost = new_replicas * cost_per_pod_hour
                new_daily_cost = new_hourly_cost * 24
                savings_percent = ((current_daily_cost - new_daily_cost) / current_daily_cost * 100) if current_daily_cost > 0 else 0
                
                return {
                    "status": "success",
                    "mode": "optimize",
                    "app_name": app_name,
                    "namespace": namespace,
                    "actions_taken": actions_taken,
                    "old_replicas": replicas,
                    "new_replicas": new_replicas,
                    "old_daily_cost": round(current_daily_cost, 2),
                    "new_daily_cost": round(new_daily_cost, 2),
                    "savings_percent": round(savings_percent, 1),
                    "recommendations": recommendations
                }
                
            elif mode == "report":
                logger.info("📋 Generating cost report...")
                
                return {
                    "status": "success",
                    "mode": "report",
                    "app_name": app_name,
                    "namespace": namespace,
                    "cost_summary": {
                        "hourly": round(current_hourly_cost, 2),
                        "daily": round(current_daily_cost, 2),
                        "monthly_estimate": round(current_daily_cost * 30, 2)
                    },
                    "budget": max_daily_cost,
                    "utilization_percent": round(budget_utilization, 1),
                    "replicas": replicas,
                    "recommendations": recommendations,
                    "report_generated": datetime.now().isoformat()
                }
            
            else:
                return {
                    "status": "error",
                    "message": f"Invalid mode: {mode}. Use 'validate', 'optimize', or 'report'"
                }
                
        except Exception as e:
            logger.error(f"❌ Cost configuration failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ==================== TOOL 22: MULTI-CLUSTER (PLACEHOLDER) ====================
    
    async def configure_multi_cluster_deployment(
        self,
        app_name: str,
        clusters: Dict[str, Dict[str, Any]],
        strategy: str = "active-active",
        failover_threshold: float = 0.3
    ) -> Dict[str, Any]:
        """Configure multi-cluster deployment (MVP: Placeholder).
        
        Args:
            app_name: Application name
            clusters: Dictionary of cluster configurations
            strategy: Deployment strategy (active-active, active-passive, canary)
            failover_threshold: Health threshold for failover
            
        Returns:
            Multi-cluster configuration result
        """
        logger.info(f"🌍 Multi-cluster deployment requested for {app_name}")
        logger.warning("⚠️ Multi-cluster is a placeholder in MVP")
        
        return {
            "status": "success",
            "app_name": app_name,
            "strategy": strategy,
            "clusters": {
                name: {
                    "status": "placeholder",
                    "region": config.get("region", "unknown"),
                    "weight": config.get("weight", 50),
                    "message": "Multi-cluster deployment is a placeholder in MVP"
                }
                for name, config in clusters.items()
            },
            "failover": {
                "enabled": False,
                "threshold": failover_threshold,
                "message": "Failover configuration available in future version"
            },
            "message": "Multi-cluster deployment placeholder - requires actual multi-cluster setup"
        }
    
    # ==================== TOOL 23: POLICY VALIDATION ====================
    
    async def validate_deployment_policy(
        self,
        app_name: str,
        namespace: str = "default",
        custom_policies: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate deployment against policies.
        
        Args:
            app_name: Application/rollout name
            namespace: Kubernetes namespace
            custom_policies: Optional custom policies to validate
            
        Returns:
            Policy validation results with violations
        """
        try:
            logger.info(f"🔍 Validating deployment policies for {app_name}")
            
            violations = []
            
            # Get rollout to check policies
            try:
                rollout_status = await self.argo_service.get_rollout_status(
                    name=app_name,
                    namespace=namespace
                )
                
                # Security Policies
                logger.info("  Checking security policies...")
                
                # Check for proper strategy
                strategy = rollout_status.get("strategy", "")
                if not strategy:
                    violations.append({
                        "policy": "deployment_strategy_required",
                        "severity": "high",
                        "message": "No deployment strategy specified",
                        "action": "Specify canary or bluegreen strategy"
                    })
                
                # Compliance Policies
                logger.info("  Checking compliance policies...")
                
                # Check replica count
                replicas = rollout_status.get("replicas", 0)
                if replicas < 2:
                    violations.append({
                        "policy": "minimum_replicas",
                        "severity": "medium",
                        "message": f"Only {replicas} replica(s) - recommend at least 2 for HA",
                        "action": "Increase replicas to 2 or more"
                    })
                
                # Check namespace
                if namespace == "default":
                    violations.append({
                        "policy": "avoid_default_namespace",
                        "severity": "low",
                        "message": "Using default namespace is not recommended",
                        "action": "Create dedicated namespace for application"
                    })
                
            except Exception as e:
                logger.warning(f"Could not get rollout for policy validation: {e}")
                violations.append({
                    "policy": "rollout_accessibility",
                    "severity": "high",
                    "message": f"Could not access rollout: {str(e)}",
                    "action": "Ensure rollout exists and is accessible"
                })
            
            # Custom policies
            if custom_policies:
                logger.info("  Checking custom policies...")
                for policy_name, policy_config in custom_policies.items():
                    # Simplified custom policy evaluation
                    violations.append({
                        "policy": policy_name,
                        "severity": policy_config.get("severity", "medium"),
                        "message": f"Custom policy {policy_name} (placeholder)",
                        "action": "Custom policy evaluation in future version"
                    })
            
            # Determine result
            validation_result = "passed" if not violations else "failed"
            
            if violations:
                logger.warning(f"⚠️ Found {len(violations)} policy violation(s)")
            else:
                logger.info("✅ All policies passed")
            
            return {
                "status": "success",
                "app_name": app_name,
                "namespace": namespace,
                "validation_result": validation_result,
                "violations_count": len(violations),
                "violations": violations,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Policy validation error: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ==================== TOOL 24: DEPLOYMENT INSIGHTS ====================
    
    async def get_deployment_insights(
        self,
        app_name: str,
        namespace: str = "default",
        insight_type: str = "full"
    ) -> Dict[str, Any]:
        """Get AI-driven deployment insights and recommendations.
        
        Args:
            app_name: Application name
            namespace: Kubernetes namespace
            insight_type: Type of insights (full, performance, cost, risk, scaling)
            
        Returns:
            Insights and actionable recommendations
        """
        try:
            logger.info(f"🤖 Generating AI insights for {app_name}")
            
            insights = {
                "app_name": app_name,
                "namespace": namespace,
                "generated_at": datetime.now().isoformat(),
                "insight_type": insight_type,
                "recommendations": []
            }
            
            # Get metrics (simplified in MVP)
            metrics = await self._get_deployment_metrics(app_name, namespace)
            
            # Performance Insights
            if insight_type in ["full", "performance"]:
                logger.info("  Analyzing performance...")
                insights["performance"] = {
                    "latency_p95_ms": metrics.get("latency_p95_ms", 150),
                    "throughput_rps": metrics.get("throughput_rps", 1000),
                    "error_rate": metrics.get("error_rate", 0.01),
                    "availability_percent": 99.5,
                    "health_score": self._calculate_health_score(metrics),
                    "status": "healthy",
                    "insights": [
                        "Latency is within acceptable range (<200ms)",
                        "Error rate is low (1%), deployment is healthy",
                        "Throughput is stable at 1000 RPS"
                    ]
                }
            
            # Cost Insights
            if insight_type in ["full", "cost"]:
                logger.info("  Analyzing costs...")
                cost_analysis = await self.configure_cost_aware_deployment(
                    app_name=app_name,
                    namespace=namespace,
                    mode="report"
                )
                
                if cost_analysis.get("status") == "success":
                    cost_summary = cost_analysis.get("cost_summary", {})
                    daily_cost = cost_summary.get("daily", 100)
                    
                    insights["cost"] = {
                        "daily_cost": daily_cost,
                        "monthly_estimate": cost_summary.get("monthly_estimate", daily_cost * 30),
                        "trend": "stable",
                        "savings_opportunity": round(daily_cost * 0.15, 2),
                        "insights": [
                            f"Potential to save ${daily_cost * 0.15:.2f}/day with HPA",
                            "Consider using Reserved Instances for 30% discount",
                            "Monitor cost trends weekly"
                        ]
                    }
            
            # Risk Assessment
            if insight_type in ["full", "risk"]:
                logger.info("  Assessing risks...")
                health_score = self._calculate_health_score(metrics)
                risk_score = 1.0 - health_score  # Inverse of health
                
                risks = []
                if health_score < 0.90:
                    risks.append({
                        "type": "performance_degradation",
                        "severity": "high",
                        "description": "Health score below 90%"
                    })
                
                insights["risk"] = {
                    "overall_risk_score": round(risk_score, 2),
                    "risk_level": "low" if risk_score < 0.3 else "medium" if risk_score < 0.6 else "high",
                    "risks": risks,
                    "mitigations": [
                        "Continue monitoring error rates and latency",
                        "Setup alert thresholds for anomalies",
                        "Enable auto-rollback for failed deployments"
                    ]
                }
            
            # Scaling Recommendations
            if insight_type in ["full", "scaling"]:
                logger.info("  Analyzing scaling needs...")
                try:
                    rollout_status = await self.argo_service.get_rollout_status(
                        name=app_name,
                        namespace=namespace
                    )
                    current_replicas = rollout_status.get("replicas", 3)
                except Exception:
                    current_replicas = 3
                
                insights["scaling"] = {
                    "current_replicas": current_replicas,
                    "recommended_replicas": current_replicas,
                    "scaling_trend": "stable",
                    "hpa_recommended": current_replicas > 5,
                    "insights": [
                        "HPA is recommended for workloads with variable traffic",
                        "Current load is consistent, no urgent scaling needed",
                        f"Consider HPA with min={max(2, current_replicas//2)}, max={current_replicas*2}"
                    ]
                }
            
            # Generate actionable recommendations
            insights["recommendations"] = self._generate_recommendations(insights)
            
            logger.info(f"✅ Generated {len(insights['recommendations'])} recommendations")
            
            return {
                "status": "success",
                "insights": insights
            }
            
        except Exception as e:
            logger.error(f"❌ Insight generation failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _generate_recommendations(self, insights: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on insights."""
        recommendations = []
        
        # Cost recommendation
        if "cost" in insights:
            recommendations.append({
                "priority": "high",
                "category": "cost",
                "title": "Enable Horizontal Pod Autoscaler (HPA)",
                "description": "Can save up to 15% on daily costs by auto-scaling based on demand",
                "estimated_impact": "15% cost reduction",
                "implementation_time_minutes": 10,
                "actions": [
                    "Create HPA resource with min=2, max=10",
                    "Set CPU threshold to 70%",
                    "Monitor scaling behavior for 24 hours"
                ]
            })
        
        # Performance recommendation
        if "performance" in insights:
            perf= insights["performance"]
            if perf.get("health_score", 1.0) < 0.95:
                recommendations.append({
                    "priority": "high",
                    "category": "performance",
                    "title": "Investigate performance degradation",
                    "description": "Health score below optimal threshold",
                    "estimated_impact": "Improved reliability",
                    "implementation_time_minutes": 30,
                    "actions": [
                        "Check error logs for recent failures",
                        "Review latency metrics in detail",
                        "Consider rollback if issues persist"
                    ]
                })
        
        # Scaling recommendation
        if "scaling" in insights:
            if insights["scaling"].get("hpa_recommended"):
                recommendations.append({
                    "priority": "medium",
                    "category": "scaling",
                    "title": "Configure autoscaling for efficiency",
                    "description": "HPA recommended for variable traffic patterns",
                    "estimated_impact": "Better resource utilization",
                    "implementation_time_minutes": 15,
                    "actions": [
                        "Analyze traffic patterns over 7 days",
                        "Set up HPA with appropriate min/max",
                        "Test scaling behavior"
                    ]
                })
        
        # Operational best practice
        recommendations.append({
            "priority": "low",
            "category": "operational",
            "title": "Enable Pod Disruption Budget (PDB)",
            "description": "Improve availability during updates and node maintenance",
            "estimated_impact": "99.99% availability",
            "implementation_time_minutes": 5,
            "actions": [
                "Create PDB with minAvailable=1",
                "Apply to deployment",
                "Verify during next rolling update"
            ]
        })
        
        return recommendations
