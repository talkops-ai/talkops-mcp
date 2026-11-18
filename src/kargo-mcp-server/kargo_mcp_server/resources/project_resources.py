"""Kargo server capabilities, project, pipeline topology, events, and RBAC resources."""

import json
from typing import Any, Dict, List

from kargo_mcp_server.resources.base import BaseResource
from kargo_mcp_server.utils.redaction import sanitize_manifest


class ProjectResources(BaseResource):
    """Server capabilities, project, pipeline DAG, event, and role MCP resources."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://server/capabilities",
            name="kargo_server_capabilities",
            description="Server write mode, enabled toolsets, Kargo API connectivity, and Kargo version",
            mime_type="application/json",
        )
        async def get_server_capabilities() -> str:
            """Return live server capabilities and Kargo API connectivity status."""
            try:
                if self.kargo_service and hasattr(self.kargo_service, "get_server_capabilities"):
                    caps = await self.kargo_service.get_server_capabilities()
                else:
                    caps = {
                        "server_name": self.config.name,
                        "server_version": self.config.version,
                        "allow_write": bool(self.config.allow_write),
                        "toolsets": list(self.config.toolsets),
                        "kargo_connected": False,
                    }
                return json.dumps(caps, indent=2, default=str)
            except Exception as exc:
                return json.dumps(
                    {
                        "server_name": self.config.name,
                        "server_version": self.config.version,
                        "allow_write": bool(self.config.allow_write),
                        "toolsets": list(self.config.toolsets),
                        "kargo_connected": False,
                        "error": str(exc),
                    },
                    indent=2,
                )

        @mcp_instance.resource(
            "kargo://projects",
            name="kargo_projects",
            description="List all Kargo Projects with readiness status",
            mime_type="application/json",
        )
        async def list_projects_resource() -> str:
            """List all Kargo projects."""
            try:
                projects = await self.kargo_service.list_projects()
                return json.dumps(
                    {
                        "count": len(projects),
                        "projects": [p.model_dump() for p in projects],
                    },
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                return json.dumps({"error": str(exc)}, indent=2)

        @mcp_instance.resource(
            "kargo://projects/{project}",
            name="kargo_project_detail",
            description="Project status and ProjectConfig (promotionPolicies, webhookReceivers, generated webhook URLs)",
            mime_type="application/json",
        )
        async def get_project_resource(project: str) -> str:
            """Get detailed Kargo Project and ProjectConfig summary."""
            try:
                proj_raw = await self.kargo_service.get_project(project)
                cfg_raw: Dict[str, Any] = {}
                try:
                    cfg_raw = await self.kargo_service.get_project_config(project)
                except Exception:
                    pass

                cfg_spec = (cfg_raw.get("spec") or {}) if isinstance(cfg_raw, dict) else {}
                cfg_status = (cfg_raw.get("status") or {}) if isinstance(cfg_raw, dict) else {}
                sanitized_proj = sanitize_manifest(proj_raw) if isinstance(proj_raw, dict) else proj_raw

                payload = {
                    "name": project,
                    "metadata": (sanitized_proj.get("metadata") if isinstance(sanitized_proj, dict) else {}),
                    "status": (sanitized_proj.get("status") if isinstance(sanitized_proj, dict) else {}),
                    "promotion_policies": cfg_spec.get("promotionPolicies") or [],
                    "webhook_receivers": cfg_spec.get("webhookReceivers") or [],
                    "webhook_receiver_urls": cfg_status.get("webhookReceivers") or [],
                    "freight_links": cfg_spec.get("freightLinks") or [],
                    "stage_links": cfg_spec.get("stageLinks") or [],
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)

        @mcp_instance.resource(
            "kargo://projects/{project}/pipeline",
            name="kargo_project_pipeline",
            description="Complete pipeline DAG topology (Warehouses -> Stages), current Freight, health, auto-promotion, and holds",
            mime_type="application/json",
        )
        async def get_project_pipeline_resource(project: str) -> str:
            """Get full pipeline DAG topology and Stage status overview."""
            try:
                topology = await self.kargo_service.describe_topology(project)
                return json.dumps(
                    {"project": project, **topology},
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)

        @mcp_instance.resource(
            "kargo://projects/{project}/events",
            name="kargo_project_events",
            description="Recent Kubernetes Events in a Kargo project",
            mime_type="application/json",
        )
        async def get_project_events_resource(project: str) -> str:
            """List recent Kubernetes events in the project."""
            try:
                events = await self.kargo_service.list_project_events(project)
                curated: List[Dict[str, Any]] = []
                for ev in events[:25]:
                    if not isinstance(ev, dict):
                        continue
                    involved = ev.get("involvedObject") or {}
                    curated.append(
                        {
                            "type": ev.get("type", "Normal"),
                            "reason": ev.get("reason", ""),
                            "object": f"{involved.get('kind', '')}/{involved.get('name', '')}",
                            "message": ev.get("message", ""),
                        }
                    )
                return json.dumps(
                    {"project": project, "count": len(curated), "events": curated},
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)

        @mcp_instance.resource(
            "kargo://projects/{project}/roles",
            name="kargo_project_roles",
            description="Kargo RBAC Roles, OIDC claim bindings, and permissions in a project",
            mime_type="application/json",
        )
        async def get_project_roles_resource(project: str) -> str:
            """List Kargo RBAC roles in a project."""
            try:
                roles = await self.kargo_service.list_roles(project)
                return json.dumps(
                    {"project": project, "count": len(roles), "roles": roles},
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)
