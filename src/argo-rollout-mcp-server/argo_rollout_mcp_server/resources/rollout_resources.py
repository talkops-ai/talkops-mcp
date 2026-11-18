"""Rollout, AnalysisRun, AnalysisTemplate, and Experiment resources."""

import json
import logging
import yaml

from argo_rollout_mcp_server.resources.base import BaseResource
from argo_rollout_mcp_server.utils.redaction import sanitize_manifest

logger = logging.getLogger(__name__)


class RolloutResources(BaseResource):
    """Rollout status, sanitized manifest, AnalysisRun, AnalysisTemplate, and Experiment resources."""

    def register(self, mcp_instance) -> None:
        """Register rollout resources with FastMCP."""

        @mcp_instance.resource("argorollout://rollouts/list")
        async def list_rollouts() -> str:
            """List all rollouts across namespaces with health scores."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available", "rollouts": []}, indent=2)

                namespace = getattr(self.config, "namespace", None) if self.config else None
                result = await self.argo_service.list_rollouts(namespace=namespace)
                rollouts = result.get("rollouts", []) if isinstance(result, dict) else []

                summary_data = []
                for rollout in rollouts:
                    name = rollout.get("name", "unknown")
                    ns = rollout.get("namespace", "default")
                    replicas_info = {
                        "desired": rollout.get("desired_replicas", 0),
                        "current": rollout.get("current_replicas", 0),
                        "ready": rollout.get("ready_replicas", 0),
                        "available": rollout.get("available_replicas", rollout.get("ready_replicas", 0)),
                    }
                    summary_data.append(
                        {
                            "name": name,
                            "namespace": ns,
                            "phase": rollout.get("phase", "Unknown"),
                            "healthScore": rollout.get("health_score", 0),
                            "strategy": rollout.get("strategy", "unknown"),
                            "replicas": replicas_info,
                            "image": rollout.get("image", ""),
                            "created": rollout.get("created", ""),
                        }
                    )

                return json.dumps(summary_data, indent=2)
            except Exception as e:
                logger.error(f"Error listing rollouts: {e}")
                return json.dumps({"error": str(e), "rollouts": []}, indent=2)

        @mcp_instance.resource("argorollout://rollouts/{namespace}/{name}/detail")
        async def rollout_status(namespace: str, name: str) -> str:
            """Get concise Rollout status (phase, step, weights, hashes, healthScore, conditions) without YAML bloat."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)

                status_data = await self.argo_service.get_rollout_status(
                    name=name,
                    namespace=namespace,
                )
                if not isinstance(status_data, dict):
                    return json.dumps({"error": "Invalid status response"}, indent=2)

                replicas_info = status_data.get("replicas", {})
                if not isinstance(replicas_info, dict):
                    replicas_info = {}

                details = {
                    "name": status_data.get("name", name),
                    "namespace": status_data.get("namespace", namespace),
                    "phase": status_data.get("phase", "Unknown"),
                    "healthScore": status_data.get("health_score", 0),
                    "message": status_data.get("message", ""),
                    "strategy": status_data.get("strategy", "unknown"),
                    "image": status_data.get("image", ""),
                    "currentStep": status_data.get("current_step"),
                    "totalSteps": status_data.get("total_steps"),
                    "canaryWeight": status_data.get("canary_weight"),
                    "stableRS": status_data.get("stable_rs", ""),
                    "currentPodHash": status_data.get("current_pod_hash", ""),
                    "paused": status_data.get("paused", False),
                    "pauseConditions": status_data.get("pause_conditions", []),
                    "aborted": status_data.get("aborted", False),
                    "workloadRef": status_data.get("workload_ref"),
                    "replicas": {
                        "total": replicas_info.get("total", 0),
                        "updated": replicas_info.get("updated", 0),
                        "ready": replicas_info.get("ready", 0),
                        "available": replicas_info.get("available", 0),
                    },
                    "desired_replicas": status_data.get("desired_replicas", 0),
                    "conditions": status_data.get("conditions", []),
                    "timestamp": status_data.get("timestamp", ""),
                }
                return json.dumps(details, indent=2)
            except Exception as e:
                logger.error(f"Error getting rollout details: {e}")
                return json.dumps({"error": str(e), "name": name, "namespace": namespace}, indent=2)

        @mcp_instance.resource("argorollout://rollouts/{namespace}/{name}/manifest")
        async def rollout_manifest(namespace: str, name: str) -> str:
            """Get sanitized YAML manifest for a Rollout (strips managedFields and redacts literal env values)."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)

                raw_manifest = await self.argo_service.get_rollout_manifest(
                    name=name,
                    namespace=namespace,
                )
                manifest_dict = (
                    yaml.safe_load(raw_manifest)
                    if isinstance(raw_manifest, str)
                    else raw_manifest
                )
                sanitized = sanitize_manifest(manifest_dict)
                return yaml.dump(
                    sanitized,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            except Exception as e:
                logger.error(f"Error getting rollout manifest: {e}")
                return json.dumps({"error": str(e), "name": name, "namespace": namespace}, indent=2)

        @mcp_instance.resource("argorollout://rollouts/{namespace}/{name}/analysisruns")
        async def rollout_analysis_runs(namespace: str, name: str) -> str:
            """Get the 5 most recent AnalysisRuns for a Rollout."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)

                result = await self.argo_service.list_analysis_runs(
                    rollout_name=name,
                    namespace=namespace,
                    limit=5,
                )
                return json.dumps(result, indent=2)
            except Exception as e:
                logger.error(f"Error listing AnalysisRuns: {e}")
                return json.dumps({"error": str(e), "rollout_name": name, "namespace": namespace}, indent=2)

        @mcp_instance.resource("argorollout://analysistemplates/{namespace}")
        async def namespace_analysis_templates(namespace: str) -> str:
            """List namespace AnalysisTemplates and ClusterAnalysisTemplates."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)

                result = await self.argo_service.list_analysis_templates(namespace=namespace)
                return json.dumps(result, indent=2)
            except Exception as e:
                logger.error(f"Error listing AnalysisTemplates: {e}")
                return json.dumps({"error": str(e), "namespace": namespace}, indent=2)

        @mcp_instance.resource("argorollout://experiments/{namespace}/{name}/status")
        async def experiment_status(namespace: str, name: str) -> str:
            """Get Argo Experiment status."""
            try:
                if not self.argo_service:
                    return json.dumps({"error": "Argo service not available"}, indent=2)

                result = await self.argo_service.get_experiment_status(
                    name=name,
                    namespace=namespace,
                )
                return json.dumps(result, indent=2)
            except Exception as e:
                logger.error(f"Error getting experiment status: {e}")
                return json.dumps({"error": str(e)}, indent=2)
