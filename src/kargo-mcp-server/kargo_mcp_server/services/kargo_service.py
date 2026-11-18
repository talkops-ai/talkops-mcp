"""Kargo v1.10–v1.12 REST API client service.

Async HTTP client wrapping Kargo's /v1beta1 REST API.
Handles authentication, request construction, server-side secret resolution,
N-to-1 pipeline diagnostics, and response parsing into Pydantic models.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx
import yaml

from kargo_mcp_server.config import AuthMode, ServerConfig
from kargo_mcp_server.exceptions.custom import (
    KargoApiError,
    KargoPromotionError,
    KargoResourceNotFoundError,
    KargoValidationError,
)
from kargo_mcp_server.models.credentials import CreateRepoCredentialsRequest
from kargo_mcp_server.models.freight import Freight, FreightSummary
from kargo_mcp_server.models.project import Project, ProjectConfig, ProjectSummary
from kargo_mcp_server.models.promotion import Promotion, PromotionSummary
from kargo_mcp_server.models.promotion_task import PromotionTask
from kargo_mcp_server.models.schemas import (
    CredentialOptions,
    FreightTraceReport,
    StageDiagnosisReport,
    WarehouseDiagnosisReport,
)
from kargo_mcp_server.models.stage import Stage, StageSummary
from kargo_mcp_server.models.warehouse import Warehouse, WarehouseSummary
from kargo_mcp_server.utils.kargo_helpers import (
    build_stage_dag,
    format_topology_summary,
    stages_to_summaries,
    validate_no_dag_cycles,
    validate_no_self_reference,
)
from kargo_mcp_server.utils.redaction import redact_credentials_dict
from kargo_mcp_server.utils.warehouse_spec_builder import detect_deprecated_warehouse_fields

logger = logging.getLogger(__name__)

# Backward-compatible alias
ApiError = KargoApiError


class KargoService:
    """Async wrapper around Kargo's /v1beta1 REST API (Kargo v1.10–v1.12+)."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._kargo = config.kargo
        self._base_url = self._kargo.base_url.rstrip("/")
        self._token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                verify=self._kargo.verify_ssl,
                timeout=self._kargo.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ---- JSON Parsing ----

    def _parse_json(self, resp: httpx.Response, context: str = "") -> Any:
        """Safely parse a JSON response body."""
        if not resp.content:
            return {}
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raw_preview = (resp.text or "(empty)")[:500]
            raise KargoApiError(
                resp.status_code,
                f"Non-JSON response{f' ({context})' if context else ''}: {exc}",
                raw_preview,
            )

    # ---- Authentication ----

    async def ensure_admin_login(self) -> None:
        """Obtain and cache an admin JWT token (ADMIN mode only)."""
        if self._kargo.auth_mode != AuthMode.ADMIN:
            return
        if self._token is not None:
            return
        if not self._kargo.admin_password:
            raise RuntimeError("KARGO_ADMIN_PASSWORD is required for ADMIN auth mode")

        client = self._ensure_client()
        resp = await client.post(
            "/v1beta1/login",
            headers={"Authorization": f"Bearer {self._kargo.admin_password}"},
        )
        if resp.status_code != 200:
            raise KargoApiError(resp.status_code, "Failed admin login", resp.text)
        data = self._parse_json(resp, "admin login")
        self._token = data.get("idToken")

    def _headers(self, bearer_override: Optional[str] = None) -> Dict[str, str]:
        """Build request headers with auth token."""
        token = bearer_override or self._token
        if self._kargo.auth_mode == AuthMode.STATIC and not token:
            token = self._kargo.static_bearer_token

        headers: Dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        bearer_override: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request with auth and error handling."""
        if self._kargo.auth_mode == AuthMode.ADMIN and not bearer_override:
            await self.ensure_admin_login()

        client = self._ensure_client()
        headers = self._headers(bearer_override)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        resp = await client.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise KargoApiError(
                resp.status_code,
                resp.reason_phrase or "Error",
                resp.text,
            )
        return resp

    async def _upsert_resource(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Create-or-update a Kargo resource via /v1beta1/resources."""
        payload = json.dumps(body)
        common_kwargs: Dict[str, Any] = {
            "headers": {"Content-Type": "text/plain"},
            "content": payload,
        }

        try:
            resp = await self._request("PUT", "/v1beta1/resources", **common_kwargs)
            data = self._parse_json(resp, "upsert resource (PUT)")
            results = data.get("results") or [{}]
            first = results[0] if isinstance(results, list) and results else {}
            manifest = (
                first.get("updatedResourceManifest")
                or first.get("createdResourceManifest")
            )
        except KargoApiError as e:
            if e.status_code != 404:
                raise
            resp = await self._request("POST", "/v1beta1/resources", **common_kwargs)
            data = self._parse_json(resp, "upsert resource (POST)")
            results = data.get("results") or []
            manifest = (
                results[0].get("createdResourceManifest")
                if isinstance(results, list) and results
                else None
            )

        return manifest or body

    async def delete_manifest(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a resource manifest via DELETE /v1beta1/resources."""
        payload = json.dumps(body)
        resp = await self._request(
            "DELETE",
            "/v1beta1/resources",
            headers={"Content-Type": "text/plain"},
            content=payload,
        )
        return self._parse_json(resp, "delete resource")

    # ---- System & Capabilities ----

    async def get_server_version(self) -> Dict[str, Any]:
        """Get Kargo API server version info."""
        resp = await self._request("GET", "/v1beta1/system/server-version")
        return self._parse_json(resp, "get server version")

    async def get_cluster_config(self) -> Dict[str, Any]:
        """Get cluster-scoped ClusterConfig resource (returns empty dict if none configured yet)."""
        try:
            resp = await self._request("GET", "/v1beta1/system/cluster-config")
            return self._parse_json(resp, "get cluster config")
        except KargoApiError as exc:
            if exc.status_code == 404:
                return {}
            raise

    async def refresh_cluster_config(self) -> None:
        """Refresh cluster-scoped ClusterConfig (initializing singleton 'cluster' if absent)."""
        try:
            await self._request("POST", "/v1beta1/system/cluster-config/refresh")
        except KargoApiError as exc:
            if exc.status_code != 404:
                raise
            await self._upsert_resource(
                {
                    "apiVersion": "kargo.akuity.io/v1alpha1",
                    "kind": "ClusterConfig",
                    "metadata": {"name": "cluster"},
                    "spec": {},
                }
            )
            await self._request("POST", "/v1beta1/system/cluster-config/refresh")

    async def get_controller_heartbeats(self) -> List[Dict[str, Any]]:
        """Get Kargo controller shard heartbeats (Kargo v1.10+)."""
        resp = await self._request("GET", "/v1beta1/system/controller-heartbeats")
        data = self._parse_json(resp, "get controller heartbeats")
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("heartbeats") or []

    async def get_server_capabilities(self) -> Dict[str, Any]:
        """Build capabilities status including Kargo API connectivity and version."""
        kargo_connected = False
        kargo_version = "unknown"
        error_msg: Optional[str] = None
        try:
            ver_data = await self.get_server_version()
            kargo_connected = True
            if isinstance(ver_data, dict):
                kargo_version = str(
                    ver_data.get("version")
                    or ver_data.get("gitVersion")
                    or ver_data.get("serverVersion", {}).get("version", "v1.12+")
                )
        except Exception as exc:
            error_msg = str(exc)

        result: Dict[str, Any] = {
            "server_name": self._config.name,
            "server_version": self._config.version,
            "allow_write": bool(self._config.allow_write),
            "toolsets": list(self._config.toolsets),
            "kargo_connected": kargo_connected,
            "kargo_url": self._base_url,
            "kargo_version": kargo_version,
            "auth_mode": self._kargo.auth_mode.value,
            "default_project": self._config.default_project,
        }
        if error_msg:
            result["connection_error"] = error_msg
        return result

    # ---- Projects & ProjectConfig ----

    async def list_projects(self) -> List[ProjectSummary]:
        """List all Kargo projects."""
        resp = await self._request("GET", "/v1beta1/projects")
        data = self._parse_json(resp, "list projects")
        items: List[ProjectSummary] = []
        raw_list = data.get("items") or data.get("projects") or []
        for item in raw_list:
            project = Project.model_validate(item)
            ready = project.is_ready()
            items.append(
                ProjectSummary(
                    name=project.metadata.name,
                    ready=ready,
                    phase="Ready" if ready else "NotReady",
                    creation_timestamp=(
                        project.metadata.creationTimestamp.isoformat()
                        if project.metadata.creationTimestamp
                        else None
                    ),
                )
            )
        return items

    async def get_project(self, name: str) -> Dict[str, Any]:
        """Get a detailed Project resource."""
        resp = await self._request("GET", f"/v1beta1/projects/{name}")
        return self._parse_json(resp, "get project")

    async def create_project(
        self,
        name: str,
        keep_namespace: bool = False,
        description: Optional[str] = None,
    ) -> Project:
        """Create a new Kargo Project (Project.spec was removed in v1.7; policies use ProjectConfig)."""
        annotations: Dict[str, str] = {}
        if keep_namespace:
            annotations["kargo.akuity.io/keep-namespace"] = "true"
        if description:
            annotations["kargo.akuity.io/description"] = description

        metadata: Dict[str, Any] = {"name": name}
        if annotations:
            metadata["annotations"] = annotations

        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Project",
            "metadata": metadata,
        }
        resp = await self._request(
            "POST",
            "/v1beta1/resources",
            headers={"Content-Type": "text/plain"},
            content=json.dumps(body),
        )
        data = self._parse_json(resp, "create project")
        results = data.get("results") or [{}]
        manifest = (
            results[0].get("createdResourceManifest")
            if isinstance(results, list) and results
            else None
        ) or body
        return Project.model_validate(manifest)

    async def delete_project(self, name: str) -> Dict[str, str]:
        """Delete a Kargo Project."""
        await self._request("DELETE", f"/v1beta1/projects/{name}")
        return {"message": f"Project '{name}' deleted successfully"}

    async def get_project_config(self, project: str) -> Dict[str, Any]:
        """Get ProjectConfig for a project (returns empty dict if none configured yet)."""
        try:
            resp = await self._request("GET", f"/v1beta1/projects/{project}/config")
            return self._parse_json(resp, "get project config")
        except KargoApiError as exc:
            if exc.status_code == 404:
                return {}
            raise

    async def upsert_project_config(
        self,
        project: str,
        spec: Dict[str, Any],
    ) -> ProjectConfig:
        """Create or update a ProjectConfig CRD (name and namespace must equal project name)."""
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "ProjectConfig",
            "metadata": {"name": project, "namespace": project},
            "spec": spec,
        }
        manifest = await self._upsert_resource(body)
        return ProjectConfig.model_validate(manifest)

    async def delete_project_config(self, project: str) -> Dict[str, str]:
        """Delete ProjectConfig for a project."""
        await self._request("DELETE", f"/v1beta1/projects/{project}/config")
        return {"message": f"ProjectConfig for '{project}' deleted successfully"}

    async def refresh_project_config(self, project: str) -> None:
        """Trigger refresh of a ProjectConfig (e.g. after webhook secret rotation)."""
        await self._request("POST", f"/v1beta1/projects/{project}/config/refresh")

    async def list_project_events(self, project: str) -> List[Dict[str, Any]]:
        """List Kubernetes events in a Kargo project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/events")
        data = self._parse_json(resp, "list project events")
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("events") or []

    # ---- Stages ----

    async def _get_auto_promo_stages(self, project: str) -> Set[str]:
        """Return set of stage names enabled for auto-promotion in ProjectConfig."""
        auto_stages: Set[str] = set()
        try:
            cfg = await self.get_project_config(project)
            policies = (cfg.get("spec") or {}).get("promotionPolicies") or []
            for pol in policies:
                if not isinstance(pol, dict) or not pol.get("autoPromotionEnabled"):
                    continue
                stg = pol.get("stage")
                if not stg and isinstance(pol.get("stageSelector"), dict):
                    stg = pol["stageSelector"].get("name")
                if stg:
                    auto_stages.add(str(stg))
        except Exception:
            pass
        return auto_stages

    async def list_stages(self, project: str) -> List[StageSummary]:
        """List stages in a project with DAG topology and v1.12 status."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/stages")
        data = self._parse_json(resp, "list stages")
        raw_items = data.get("items") or data.get("stages") or []
        stages: List[Stage] = [Stage.model_validate(item) for item in raw_items]

        auto_stages = await self._get_auto_promo_stages(project)
        upstream_map, downstream_map = build_stage_dag(stages)
        return stages_to_summaries(
            stages, upstream_map, downstream_map, auto_promo_stages=auto_stages
        )

    async def get_stage(self, project: str, stage: str) -> Dict[str, Any]:
        """Get a detailed Stage resource."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/stages/{stage}")
        return self._parse_json(resp, "get stage")

    async def build_merged_stage_manifest(
        self,
        project: str,
        stage: str,
        spec_updates: Dict[str, Any],
        merge_existing: bool = True,
    ) -> Dict[str, Any]:
        """Build a complete Stage manifest, merging updates with existing live Stage spec (fixes B7) and checking DAG cycles."""
        merged_spec: Dict[str, Any] = {}
        metadata: Dict[str, Any] = {"name": stage, "namespace": project}

        if merge_existing:
            try:
                existing = await self.get_stage(project, stage)
                if isinstance(existing, dict):
                    if isinstance(existing.get("spec"), dict):
                        merged_spec.update(existing["spec"])
                    existing_meta = existing.get("metadata")
                    if isinstance(existing_meta, dict):
                        if existing_meta.get("labels"):
                            metadata["labels"] = dict(existing_meta["labels"])
                        if existing_meta.get("annotations"):
                            metadata["annotations"] = dict(existing_meta["annotations"])
            except KargoApiError as exc:
                if exc.status_code != 404:
                    raise

        for k, v in spec_updates.items():
            if v is not None:
                merged_spec[k] = v

        validate_no_self_reference(stage, merged_spec)

        # Check DAG cycles against other stages in the project if available
        try:
            resp = await self._request("GET", f"/v1beta1/projects/{project}/stages")
            data = self._parse_json(resp, "list stages for cycle check")
            raw_items = data.get("items") or data.get("stages") or []
            existing_stages = [Stage.model_validate(item) for item in raw_items]
            validate_no_dag_cycles(existing_stages, stage, merged_spec)
        except ValueError:
            raise
        except Exception:
            pass

        return {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Stage",
            "metadata": metadata,
            "spec": merged_spec,
        }

    async def upsert_stage(
        self,
        project: str,
        stage: str,
        spec: Dict[str, Any],
        merge_existing: bool = True,
    ) -> Stage:
        """Create or update a Stage, preserving existing fields unless overwritten."""
        body = await self.build_merged_stage_manifest(
            project, stage, spec, merge_existing=merge_existing
        )
        manifest = await self._upsert_resource(body)
        return Stage.model_validate(manifest)

    async def delete_stage(self, project: str, stage: str) -> Dict[str, str]:
        """Delete a Stage."""
        await self._request("DELETE", f"/v1beta1/projects/{project}/stages/{stage}")
        return {"message": f"Stage '{stage}' in project '{project}' deleted successfully"}

    async def refresh_stage(self, project: str, stage: str) -> None:
        """Force immediate reconciliation of a Stage."""
        await self._request("POST", f"/v1beta1/projects/{project}/stages/{stage}/refresh")

    async def reverify_stage(
        self,
        project: str,
        stage: str,
        bearer_override: Optional[str] = None,
    ) -> Stage:
        """Trigger re-verification of current freight for a Stage."""
        path = f"/v1beta1/projects/{project}/stages/{stage}/verification"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        if resp.content:
            return Stage.model_validate(self._parse_json(resp, "reverify stage"))
        data = await self.get_stage(project, stage)
        return Stage.model_validate(data)

    async def abort_stage_verification(
        self,
        project: str,
        stage: str,
        bearer_override: Optional[str] = None,
    ) -> Stage:
        """Abort an in-progress verification on a Stage."""
        path = f"/v1beta1/projects/{project}/stages/{stage}/verification/abort"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        if resp.content:
            return Stage.model_validate(self._parse_json(resp, "abort stage verification"))
        data = await self.get_stage(project, stage)
        return Stage.model_validate(data)

    # ---- Warehouses ----

    async def list_warehouses(self, project: str) -> List[WarehouseSummary]:
        """List warehouses in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/warehouses")
        data = self._parse_json(resp, "list warehouses")
        raw_items = data.get("items") or data.get("warehouses") or []
        warehouses: List[WarehouseSummary] = []
        for item in raw_items:
            wh = Warehouse.model_validate(item)
            warehouses.append(
                WarehouseSummary(
                    name=wh.metadata.name,
                    namespace=wh.metadata.namespace or project,
                    subscription_types=wh.get_subscription_types(),
                    subscriptions_count=len(wh.spec.subscriptions),
                    freight_creation_policy=wh.spec.freight_creation_policy,
                    interval=wh.spec.interval or "5m0s",
                    ready=wh.is_ready(),
                    last_freight_id=wh.status.last_freight_id if wh.status else None,
                )
            )
        return warehouses

    async def get_warehouse(self, project: str, name: str) -> Dict[str, Any]:
        """Get a detailed Warehouse resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/warehouses/{name}"
        )
        return self._parse_json(resp, "get warehouse")

    async def refresh_warehouse(self, project: str, name: str) -> None:
        """Force immediate artifact discovery on a Warehouse."""
        await self._request(
            "POST", f"/v1beta1/projects/{project}/warehouses/{name}/refresh"
        )

    async def upsert_warehouse(
        self,
        project: str,
        name: str,
        spec: Dict[str, Any],
    ) -> Warehouse:
        """Create or update a Warehouse."""
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Warehouse",
            "metadata": {"name": name, "namespace": project},
            "spec": spec,
        }
        manifest = await self._upsert_resource(body)
        return Warehouse.model_validate(manifest)

    async def delete_warehouse(self, project: str, name: str) -> Dict[str, str]:
        """Delete a Warehouse."""
        await self._request("DELETE", f"/v1beta1/projects/{project}/warehouses/{name}")
        return {"message": f"Warehouse '{name}' in project '{project}' deleted successfully"}

    # ---- Freight ----

    def _extract_freight_objects(self, data: Any) -> List[Freight]:
        """Parse Freight objects from Kargo QueryFreight responses (items, groups, or bare list)."""
        results: List[Freight] = []
        seen_names: Set[str] = set()

        def _visit(obj: Any) -> None:
            if isinstance(obj, dict):
                if obj.get("kind") == "Freight" or (
                    "metadata" in obj
                    and ("origin" in obj or "commits" in obj or "images" in obj or "charts" in obj or "spec" in obj)
                ):
                    try:
                        f = Freight.model_validate(obj)
                        if f.metadata.name and f.metadata.name not in seen_names:
                            seen_names.add(f.metadata.name)
                            results.append(f)
                        return
                    except Exception:
                        pass
                for val in obj.values():
                    _visit(val)
            elif isinstance(obj, list):
                for item in obj:
                    _visit(item)

        _visit(data)
        return results

    async def list_freight(
        self,
        project: str,
        stage: Optional[str] = None,
        origins: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        reverse: bool = True,
    ) -> List[FreightSummary]:
        """Query Freight in a project with optional stage availability and warehouse origin filters."""
        params: Dict[str, Any] = {}
        if stage:
            params["stage"] = stage
        if origins:
            params["origins"] = ",".join(origins)
        if order_by:
            params["orderBy"] = order_by
            params["reverse"] = "true" if reverse else "false"

        resp = await self._request(
            "GET",
            f"/v1beta1/projects/{project}/freight",
            params=params or None,
        )
        data = self._parse_json(resp, "list freight")
        freight_objs = self._extract_freight_objects(data)
        return [f.to_summary() for f in freight_objs]

    async def get_freight(self, project: str, freight_or_alias: str) -> Dict[str, Any]:
        """Get a detailed Freight resource by SHA-1 name or alias."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/freight/{freight_or_alias}"
        )
        return self._parse_json(resp, "get freight")

    async def approve_freight(
        self,
        project: str,
        freight_id: str,
        stage: str,
        bearer_override: Optional[str] = None,
    ) -> Freight:
        """Manually approve Freight (by name or alias) for a specific Stage."""
        path = f"/v1beta1/projects/{project}/freight/{freight_id}/approve"
        resp = await self._request(
            "POST", path, bearer_override=bearer_override, params={"stage": stage}
        )
        if resp.content:
            return Freight.model_validate(self._parse_json(resp, "approve freight"))
        data = await self.get_freight(project, freight_id)
        return Freight.model_validate(data)

    async def update_freight_alias(
        self,
        project: str,
        freight_or_alias: str,
        new_alias: str,
    ) -> Dict[str, Any]:
        """Update human-friendly alias on a Freight resource."""
        resp = await self._request(
            "PATCH",
            f"/v1beta1/projects/{project}/freight/{freight_or_alias}/alias",
            params={"newAlias": new_alias},
        )
        if resp.content:
            return self._parse_json(resp, "update freight alias")
        return await self.get_freight(project, new_alias or freight_or_alias)

    async def delete_freight(
        self,
        project: str,
        freight_or_alias: str,
    ) -> Dict[str, str]:
        """Delete a Freight resource by name or alias."""
        await self._request(
            "DELETE", f"/v1beta1/projects/{project}/freight/{freight_or_alias}"
        )
        return {"message": f"Freight '{freight_or_alias}' in project '{project}' deleted successfully"}

    async def create_freight(
        self,
        project: str,
        warehouse: str,
        artifacts: Dict[str, Any],
        alias: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manually assemble or clone a Freight resource via POST /v1beta1/resources."""
        placeholder_name = str(artifacts.get("name") or alias or f"{warehouse}-manual")
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Freight",
            "metadata": {"name": placeholder_name, "namespace": project},
            "origin": {"kind": "Warehouse", "name": warehouse},
        }
        if alias:
            body["alias"] = alias
        for key in ("commits", "images", "charts", "artifacts"):
            if key in artifacts and artifacts[key]:
                body[key] = artifacts[key]

        resp = await self._request(
            "POST",
            "/v1beta1/resources",
            headers={"Content-Type": "text/plain"},
            content=json.dumps(body),
        )
        data = self._parse_json(resp, "create freight")
        results = data.get("results") or [{}]
        manifest = (
            results[0].get("createdResourceManifest")
            if isinstance(results, list) and results
            else None
        ) or body
        return manifest

    # ---- Promotions (fixes B2 — uses native PromoteToStage / PromoteDownstream endpoints) ----

    def _unwrap_promotion(self, data: Any) -> Promotion:
        """Accept both Kargo v1.10+ bare Promotion and Kargo v1.9 {'promotion': {...}} wrapper."""
        if isinstance(data, dict) and "promotion" in data and isinstance(data["promotion"], dict):
            data = data["promotion"]
        return Promotion.model_validate(data)

    async def promote_to_stage(
        self,
        project: str,
        stage: str,
        *,
        freight: Optional[str] = None,
        freight_alias: Optional[str] = None,
        origin_warehouse: Optional[str] = None,
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """Promote Freight (by name, alias, or origin Warehouse) to a Stage via native REST endpoint.

        Fixes B2:
        - Uses POST /v1beta1/projects/{project}/stages/{stage}/promotions
        - Server-side Kargo admission/API generates a unique ULID name (<stage>.<ulid>.<hash>)
          and inflates PromotionTask / ClusterPromotionTask steps and vars accurately.
        - Promoting the same Freight multiple times (e.g. rollback or retry) never collides!
        """
        payload: Dict[str, Any] = {}
        if freight:
            payload["freight"] = freight
        elif freight_alias:
            payload["freightAlias"] = freight_alias
        elif origin_warehouse:
            origin_val = (
                origin_warehouse
                if origin_warehouse.startswith("Warehouse/")
                else f"Warehouse/{origin_warehouse}"
            )
            payload["origin"] = origin_val
        else:
            raise KargoValidationError(
                "Must specify one of 'freight', 'freight_alias', or 'origin_warehouse' to promote."
            )

        resp = await self._request(
            "POST",
            f"/v1beta1/projects/{project}/stages/{stage}/promotions",
            json=payload,
            bearer_override=bearer_override,
        )
        data = self._parse_json(resp, "promote to stage")
        return self._unwrap_promotion(data)

    async def create_promotion(
        self,
        project: str,
        stage: str,
        freight: str,
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """Create a Promotion for a Stage using the native promote endpoint."""
        return await self.promote_to_stage(
            project, stage, freight=freight, bearer_override=bearer_override
        )

    async def promote_downstream(
        self,
        project: str,
        stage: str,
        freight: Optional[str] = None,
        freight_alias: Optional[str] = None,
        bearer_override: Optional[str] = None,
    ) -> List[Promotion]:
        """Promote Freight to all Stages immediately downstream of the specified Stage."""
        payload: Dict[str, Any] = {}
        if freight:
            payload["freight"] = freight
        elif freight_alias:
            payload["freightAlias"] = freight_alias
        else:
            raise KargoValidationError(
                "Must specify 'freight' or 'freight_alias' for downstream promotion."
            )

        resp = await self._request(
            "POST",
            f"/v1beta1/projects/{project}/stages/{stage}/promotions/downstream",
            json=payload,
            bearer_override=bearer_override,
        )
        data = self._parse_json(resp, "promote downstream")
        raw_list: List[Any] = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            raw_list = (
                data.get("promotions")
                or data.get("items")
                or ([data] if "metadata" in data else [])
            )
        return [self._unwrap_promotion(item) for item in raw_list if isinstance(item, dict)]

    async def get_promotion(
        self, project: str, promotion_name: str
    ) -> Dict[str, Any]:
        """Get detailed Promotion status."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/promotions/{promotion_name}"
        )
        return self._parse_json(resp, "get promotion")

    async def list_promotions(
        self,
        project: str,
        stage: Optional[str] = None,
    ) -> List[PromotionSummary]:
        """List promotions in a project (optionally filtered by stage)."""
        params = {"stage": stage} if stage else None
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/promotions", params=params
        )
        data = self._parse_json(resp, "list promotions")
        items: List[PromotionSummary] = []

        raw_items: List[Any] = []
        if isinstance(data, dict):
            raw_items = data.get("items") or data.get("promotions") or []
        elif isinstance(data, list):
            raw_items = data

        for item in raw_items:
            if not isinstance(item, dict) or not item.get("metadata"):
                continue
            try:
                p = Promotion.model_validate(item)
                items.append(
                    PromotionSummary(
                        name=p.metadata.name,
                        stage=p.spec.stage,
                        freight=p.spec.freight,
                        phase=p.get_phase(),
                        message=p.status.message if p.status else None,
                        started_at=p.status.started_at if p.status else None,
                        finished_at=p.status.finished_at if p.status else None,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Skipping unparseable promotion item: %s — %s",
                    item.get("metadata", {}).get("name", "?"),
                    exc,
                )

        return items

    async def abort_promotion(
        self,
        project: str,
        promotion_name: str,
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """Abort a running or pending Promotion."""
        path = f"/v1beta1/projects/{project}/promotions/{promotion_name}/abort"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        if resp.content:
            return self._unwrap_promotion(self._parse_json(resp, "abort promotion"))
        data = await self.get_promotion(project, promotion_name)
        return Promotion.model_validate(data)

    async def refresh_promotion(
        self,
        project: str,
        promotion_name: str,
    ) -> None:
        """Wake / refresh a Promotion."""
        await self._request(
            "POST", f"/v1beta1/projects/{project}/promotions/{promotion_name}/refresh"
        )

    # ---- Promotion Tasks & ClusterPromotionTasks (fixes B1: /promotion-tasks) ----

    async def list_promotion_tasks(self, project: str) -> List[Dict[str, Any]]:
        """List PromotionTasks in a project via /v1beta1/projects/{project}/promotion-tasks."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/promotion-tasks"
        )
        data = self._parse_json(resp, "list promotion tasks")
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("promotionTasks") or []

    async def get_promotion_task(self, project: str, name: str) -> Dict[str, Any]:
        """Get a detailed PromotionTask resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/promotion-tasks/{name}"
        )
        return self._parse_json(resp, "get promotion task")

    async def list_cluster_promotion_tasks(self) -> List[Dict[str, Any]]:
        """List cluster-scoped ClusterPromotionTasks."""
        resp = await self._request("GET", "/v1beta1/shared/cluster-promotion-tasks")
        data = self._parse_json(resp, "list cluster promotion tasks")
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("clusterPromotionTasks") or []

    async def get_cluster_promotion_task(self, name: str) -> Dict[str, Any]:
        """Get a detailed ClusterPromotionTask resource."""
        resp = await self._request(
            "GET", f"/v1beta1/shared/cluster-promotion-tasks/{name}"
        )
        return self._parse_json(resp, "get cluster promotion task")

    async def upsert_promotion_task(
        self,
        project: str,
        name: str,
        spec: Dict[str, Any],
        scope: str = "project",
    ) -> PromotionTask:
        """Create or update a PromotionTask or ClusterPromotionTask."""
        is_cluster = scope == "cluster"
        kind = "ClusterPromotionTask" if is_cluster else "PromotionTask"
        metadata: Dict[str, Any] = {"name": name}
        if not is_cluster:
            metadata["namespace"] = project

        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": kind,
            "metadata": metadata,
            "spec": spec,
        }
        manifest = await self._upsert_resource(body)
        return PromotionTask.model_validate(manifest)

    async def delete_promotion_task(
        self,
        project: str,
        name: str,
        scope: str = "project",
    ) -> Dict[str, str]:
        """Delete a PromotionTask or ClusterPromotionTask via DELETE /v1beta1/resources."""
        is_cluster = scope == "cluster"
        kind = "ClusterPromotionTask" if is_cluster else "PromotionTask"
        metadata: Dict[str, Any] = {"name": name}
        if not is_cluster:
            metadata["namespace"] = project
        body = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": kind,
            "metadata": metadata,
        }
        await self.delete_manifest(body)
        return {"message": f"{kind} '{name}' deleted successfully"}

    # ---- Verification (AnalysisTemplates & AnalysisRuns) ----

    async def list_analysis_templates(
        self,
        project: str,
        include_cluster: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """List AnalysisTemplates in a project and optional ClusterAnalysisTemplates."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/analysis-templates"
        )
        data = self._parse_json(resp, "list analysis templates")
        ns_items = (
            data
            if isinstance(data, list)
            else (data.get("items") or data.get("analysisTemplates") or [])
        )

        cluster_items: List[Dict[str, Any]] = []
        if include_cluster:
            try:
                c_resp = await self._request(
                    "GET", "/v1beta1/shared/cluster-analysis-templates"
                )
                c_data = self._parse_json(c_resp, "list cluster analysis templates")
                cluster_items = (
                    c_data
                    if isinstance(c_data, list)
                    else (c_data.get("items") or c_data.get("clusterAnalysisTemplates") or [])
                )
            except Exception:
                pass

        return {
            "analysis_templates": ns_items,
            "cluster_analysis_templates": cluster_items,
        }

    async def get_analysis_template(
        self,
        project: str,
        name: str,
        kind: str = "AnalysisTemplate",
    ) -> Dict[str, Any]:
        """Get an AnalysisTemplate or ClusterAnalysisTemplate."""
        if kind == "ClusterAnalysisTemplate":
            resp = await self._request(
                "GET", f"/v1beta1/shared/cluster-analysis-templates/{name}"
            )
        else:
            resp = await self._request(
                "GET", f"/v1beta1/projects/{project}/analysis-templates/{name}"
            )
        return self._parse_json(resp, "get analysis template")

    async def upsert_analysis_template(
        self,
        project: str,
        name: str,
        spec: Dict[str, Any],
        kind: str = "AnalysisTemplate",
    ) -> Dict[str, Any]:
        """Create or update an AnalysisTemplate or ClusterAnalysisTemplate via /v1beta1/resources."""
        is_cluster = kind == "ClusterAnalysisTemplate"
        metadata: Dict[str, Any] = {"name": name}
        if not is_cluster:
            metadata["namespace"] = project
        body: Dict[str, Any] = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": kind,
            "metadata": metadata,
            "spec": spec,
        }
        return await self._upsert_resource(body)

    async def delete_analysis_template(
        self,
        project: str,
        name: str,
        kind: str = "AnalysisTemplate",
    ) -> Dict[str, str]:
        """Delete an AnalysisTemplate or ClusterAnalysisTemplate."""
        if kind == "ClusterAnalysisTemplate":
            await self._request(
                "DELETE", f"/v1beta1/shared/cluster-analysis-templates/{name}"
            )
        else:
            await self._request(
                "DELETE", f"/v1beta1/projects/{project}/analysis-templates/{name}"
            )
        return {"message": f"{kind} '{name}' deleted successfully"}

    async def get_analysis_run(self, project: str, name: str) -> Dict[str, Any]:
        """Get a verification AnalysisRun resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/analysis-runs/{name}"
        )
        return self._parse_json(resp, "get analysis run")

    async def get_analysis_run_logs(self, project: str, name: str) -> str:
        """Get job metric logs for an AnalysisRun, falling back to metricResults on HTTP 501."""
        try:
            resp = await self._request(
                "GET", f"/v1beta1/projects/{project}/analysis-runs/{name}/logs"
            )
            if not resp.content:
                return ""
            try:
                parsed = resp.json()
                if isinstance(parsed, dict) and "logs" in parsed:
                    return str(parsed["logs"])
                return json.dumps(parsed, indent=2)
            except Exception:
                return resp.text
        except KargoApiError as exc:
            if getattr(exc, "status_code", None) != 501 and "501" not in str(exc):
                raise
            raw = await self.get_analysis_run(project, name)
            status = (raw.get("status") or {}) if isinstance(raw, dict) else {}
            lines = [
                f"[AnalysisRun '{name}' in project '{project}' — Kargo API external log streaming not configured (HTTP 501); synthesized metric execution log]",
                f"phase: {status.get('phase', 'Unknown')}",
            ]
            if status.get("message"):
                lines.append(f"message: {status.get('message')}")
            for mr in status.get("metricResults") or []:
                m_name = mr.get("name", "unknown")
                m_phase = mr.get("phase", "Unknown")
                m_msg = mr.get("message") or ""
                lines.append(f"- metric '{m_name}': phase={m_phase}" + (f" message={m_msg}" if m_msg else ""))
                for meas in mr.get("measurements") or []:
                    val = meas.get("value")
                    meta = meas.get("metadata") or {}
                    m_err = meas.get("message") or ""
                    lines.append(
                        f"  measurement phase={meas.get('phase')} value={val} metadata={meta}"
                        + (f" message={m_err}" if m_err else "")
                    )
            return "\n".join(lines)

    # ---- Credentials & ConfigMaps (fixes B9: server-side secret resolution) ----

    def resolve_secret_material(
        self,
        secret_ref: Optional[str] = None,
        data_keys: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Resolve secret values strictly from server-side env vars or mounted KARGO_CREDENTIALS_FILE.

        Never accepts raw secret strings from LLM tool parameters.
        """
        resolved: Dict[str, str] = {}

        is_default_ref = not secret_ref or secret_ref.strip().lower() == "default"

        # 1. Check mounted credentials file if configured
        if self._kargo.credentials_file:
            cred_path = Path(self._kargo.credentials_file)
            if cred_path.is_file():
                try:
                    raw = cred_path.read_text(encoding="utf-8")
                    file_data = yaml.safe_load(raw)
                    if isinstance(file_data, dict):
                        if secret_ref and isinstance(file_data.get(secret_ref), dict):
                            ref_block = file_data.get(secret_ref)
                        elif is_default_ref:
                            ref_block = (
                                file_data.get("default")
                                if isinstance(file_data.get("default"), dict)
                                else file_data
                            )
                        else:
                            ref_block = None
                        if isinstance(ref_block, dict):
                            for k, v in ref_block.items():
                                if isinstance(v, (str, int, float, bool)):
                                    resolved[str(k)] = str(v)
                except Exception as exc:
                    logger.warning("Failed reading KARGO_CREDENTIALS_FILE: %s", exc)

        # 2. Check KARGO_CRED_<REF>_* environment variables
        if secret_ref:
            norm_ref = (
                secret_ref.upper()
                .replace("-", "_")
                .replace(".", "_")
                .replace("/", "_")
            )
            prefix = f"KARGO_CRED_{norm_ref}_"
            for env_key, env_val in os.environ.items():
                if env_key.startswith(prefix) and env_val:
                    sub_key = env_key[len(prefix):].lower()
                    resolved[sub_key] = env_val

            if data_keys:
                for dk in data_keys:
                    norm_dk = dk.upper().replace("-", "_")
                    val = os.getenv(f"{prefix}{norm_dk}") or os.getenv(norm_dk)
                    if val is not None:
                        resolved[dk] = val

        # 3. Fallback to default KARGO_REPO_USERNAME / KARGO_REPO_PASSWORD only when secret_ref is omitted or 'default'
        if is_default_ref:
            if "username" not in resolved and self._kargo.repo_username:
                resolved["username"] = self._kargo.repo_username
            if "password" not in resolved and self._kargo.repo_password:
                resolved["password"] = self._kargo.repo_password

        return resolved

    def _scope_prefix(self, project: str, scope: str = "project") -> str:
        if scope == "shared":
            return "/v1beta1/shared"
        if scope == "system":
            return "/v1beta1/system"
        return f"/v1beta1/projects/{project}"

    async def list_repo_credentials(
        self,
        project: str,
        scope: str = "project",
    ) -> List[Dict[str, Any]]:
        """List repository credentials (project or shared scope) with secrets redacted."""
        prefix = self._scope_prefix(project, scope)
        resp = await self._request("GET", f"{prefix}/repo-credentials")
        data = self._parse_json(resp, "list repo credentials")
        raw_items = (
            data
            if isinstance(data, list)
            else (data.get("items") or data.get("credentials") or [])
        )
        return [redact_credentials_dict(c) for c in raw_items if isinstance(c, dict)]

    async def get_repo_credentials(
        self,
        project: str,
        name: str,
        scope: str = "project",
    ) -> Dict[str, Any]:
        """Get detailed repository credentials with secrets redacted."""
        prefix = self._scope_prefix(project, scope)
        resp = await self._request("GET", f"{prefix}/repo-credentials/{name}")
        data = self._parse_json(resp, "get repo credentials")
        return redact_credentials_dict(data) if isinstance(data, dict) else data

    async def list_generic_credentials(
        self,
        project: str,
        scope: str = "project",
    ) -> List[Dict[str, Any]]:
        """List generic credentials (project, shared, or system scope) with values redacted."""
        prefix = self._scope_prefix(project, scope)
        resp = await self._request("GET", f"{prefix}/generic-credentials")
        data = self._parse_json(resp, "list generic credentials")
        raw_items = (
            data
            if isinstance(data, list)
            else (data.get("items") or data.get("secrets") or [])
        )
        return [redact_credentials_dict(c) for c in raw_items if isinstance(c, dict)]

    async def list_configmaps(
        self,
        project: str,
        scope: str = "project",
    ) -> List[Dict[str, Any]]:
        """List ConfigMaps (project, shared, or system scope)."""
        prefix = self._scope_prefix(project, scope)
        resp = await self._request("GET", f"{prefix}/configmaps")
        data = self._parse_json(resp, "list configmaps")
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("configMaps") or []

    async def create_or_update_credentials(
        self,
        project: str,
        name: str,
        options: CredentialOptions,
        scope: str = "project",
        is_update: bool = False,
    ) -> Dict[str, Any]:
        """Create or update repository credentials, generic credentials, or ConfigMaps."""
        prefix = self._scope_prefix(project, scope)
        method = "PUT" if is_update else "POST"

        if options.kind == "repo":
            if scope == "system":
                raise KargoValidationError(
                    "Repository credentials are only supported in 'project' or 'shared' scope."
                )
            if not options.repo_url:
                raise KargoValidationError("'repo_url' is required when credential kind='repo'.")
            if not options.cred_type:
                raise KargoValidationError(
                    "'cred_type' ('git', 'helm', or 'image') is required when credential kind='repo'."
                )

            secret_material = self.resolve_secret_material(secret_ref=options.secret_ref)
            username = secret_material.get("username")
            password = secret_material.get("password")
            if not username or not password:
                raise KargoValidationError(
                    f"Could not resolve username/password from server-side environment for secret_ref='{options.secret_ref or 'default'}'. "
                    "Set KARGO_REPO_USERNAME and KARGO_REPO_PASSWORD (or KARGO_CRED_<REF>_USERNAME / KARGO_CRED_<REF>_PASSWORD) on the MCP server."
                )

            req = CreateRepoCredentialsRequest(
                name=name,
                repoUrl=options.repo_url,
                type=options.cred_type,
                username=username,
                password=password,
                description=options.description,
                repoUrlIsRegex=options.repo_url_is_regex,
            )
            path = (
                f"{prefix}/repo-credentials/{name}"
                if is_update
                else f"{prefix}/repo-credentials"
            )
            resp = await self._request(
                method,
                path,
                json=req.model_dump(exclude_none=True),
            )
            data = self._parse_json(resp, "save repo credentials")
            return redact_credentials_dict(data) if isinstance(data, dict) else {"name": name}

        if options.kind == "generic":
            secret_material = self.resolve_secret_material(
                secret_ref=options.secret_ref,
                data_keys=options.data_keys,
            )
            if options.data_keys:
                filtered = {k: secret_material[k] for k in options.data_keys if k in secret_material}
            else:
                filtered = secret_material

            if not filtered:
                raise KargoValidationError(
                    f"Could not resolve generic secret keys from server-side environment for secret_ref='{options.secret_ref or name}'. "
                    "Configure KARGO_CRED_<REF>_<KEY> or KARGO_CREDENTIALS_FILE on the MCP server."
                )

            payload: Dict[str, Any] = {
                "name": name,
                "data": filtered,
            }
            if options.description:
                payload["description"] = options.description
            if scope == "shared" and options.replicate_to_all_projects:
                payload["replicateTo"] = "*"

            path = (
                f"{prefix}/generic-credentials/{name}"
                if is_update
                else f"{prefix}/generic-credentials"
            )
            resp = await self._request(method, path, json=payload)
            data = self._parse_json(resp, "save generic credentials")
            return redact_credentials_dict(data) if isinstance(data, dict) else {"name": name}

        # ConfigMap
        cm_data = dict(options.config_data or {})
        if not cm_data:
            raise KargoValidationError(
                "'config_data' (non-secret key/value dict) is required when kind='configmap'."
            )
        cm_payload: Dict[str, Any] = {
            "name": name,
            "data": cm_data,
        }
        if options.description:
            cm_payload["description"] = options.description
        if scope == "shared" and options.replicate_to_all_projects:
            cm_payload["replicateTo"] = "*"

        path = f"{prefix}/configmaps/{name}" if is_update else f"{prefix}/configmaps"
        resp = await self._request(method, path, json=cm_payload)
        return self._parse_json(resp, "save configmap")

    async def delete_credentials(
        self,
        project: str,
        name: str,
        kind: str = "repo",
        scope: str = "project",
    ) -> Dict[str, str]:
        """Delete repository credentials, generic credentials, or a ConfigMap."""
        prefix = self._scope_prefix(project, scope)
        endpoint_map = {
            "repo": "repo-credentials",
            "generic": "generic-credentials",
            "configmap": "configmaps",
        }
        segment = endpoint_map.get(kind, "repo-credentials")
        await self._request("DELETE", f"{prefix}/{segment}/{name}")
        return {"message": f"{kind} credential '{name}' ({scope}) deleted successfully"}

    # ---- RBAC (Kargo Roles, Grants, Revocations) ----

    async def list_roles(self, project: str) -> List[Dict[str, Any]]:
        """List Kargo RBAC roles in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/roles")
        data = self._parse_json(resp, "list roles")
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("roles") or []

    async def get_role(self, project: str, role: str) -> Dict[str, Any]:
        """Get details of a Kargo RBAC role in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/roles/{role}")
        return self._parse_json(resp, "get role")

    async def create_role(
        self,
        project: str,
        role: str,
        claims: Optional[Dict[str, List[str]]] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a managed Kargo Role in a project (Kargo v1.12 rbac.kargo.akuity.io/v1alpha1 schema)."""
        metadata: Dict[str, Any] = {"name": role, "namespace": project}
        if description:
            metadata["annotations"] = {"kargo.akuity.io/description": description}

        payload: Dict[str, Any] = {
            "apiVersion": "rbac.kargo.akuity.io/v1alpha1",
            "kind": "Role",
            "metadata": metadata,
        }
        if claims:
            payload["claims"] = [
                {"name": k, "values": v if isinstance(v, list) else [str(v)]}
                for k, v in claims.items()
            ]
        if rules:
            normalized_rules: List[Dict[str, Any]] = []
            for r in rules:
                if not isinstance(r, dict):
                    continue
                if "resourceType" in r and "resources" not in r:
                    rule_entry: Dict[str, Any] = {
                        "apiGroups": [str(r.get("apiGroup", "kargo.akuity.io"))],
                        "resources": [str(r["resourceType"])],
                        "verbs": list(r.get("verbs") or []),
                    }
                    res_name = r.get("resourceName")
                    if res_name and res_name != "*":
                        rule_entry["resourceNames"] = (
                            res_name if isinstance(res_name, list) else [str(res_name)]
                        )
                    normalized_rules.append(rule_entry)
                else:
                    normalized_rules.append(r)
            if normalized_rules:
                payload["rules"] = normalized_rules

        resp = await self._request(
            "POST", f"/v1beta1/projects/{project}/roles", json=payload
        )
        return self._parse_json(resp, "create role")

    async def delete_role(self, project: str, role: str) -> Dict[str, str]:
        """Delete a Kargo Role in a project."""
        await self._request("DELETE", f"/v1beta1/projects/{project}/roles/{role}")
        return {"message": f"Role '{role}' in project '{project}' deleted successfully"}

    async def grant_role(
        self,
        project: str,
        role: str,
        claims: Optional[Dict[str, List[str]]] = None,
        permissions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Grant OIDC claims or resource permissions to a Kargo Role."""
        payload: Dict[str, Any] = {"role": role}
        if claims:
            payload["userClaims"] = {
                "claims": [
                    {"name": k, "values": v if isinstance(v, list) else [str(v)]}
                    for k, v in claims.items()
                ]
            }
        if permissions:
            payload["resourceDetails"] = permissions[0] if len(permissions) == 1 else permissions

        resp = await self._request(
            "POST", f"/v1beta1/projects/{project}/roles/grants", json=payload
        )
        return self._parse_json(resp, "grant role")

    async def revoke_role(
        self,
        project: str,
        role: str,
        claims: Optional[Dict[str, List[str]]] = None,
        permissions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Revoke OIDC claims or resource permissions from a Kargo Role."""
        payload: Dict[str, Any] = {"role": role}
        if claims:
            payload["userClaims"] = {
                "claims": [
                    {"name": k, "values": v if isinstance(v, list) else [str(v)]}
                    for k, v in claims.items()
                ]
            }
        if permissions:
            payload["resourceDetails"] = permissions[0] if len(permissions) == 1 else permissions

        resp = await self._request(
            "POST", f"/v1beta1/projects/{project}/roles/revocations", json=payload
        )
        return self._parse_json(resp, "revoke role")

    # ---- Topology & N-to-1 Diagnostics ----

    async def describe_topology(self, project: str) -> Dict[str, Any]:
        """Build and return a complete pipeline topology summary for a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/stages")
        data = self._parse_json(resp, "describe topology")
        raw_items = data.get("items") or data.get("stages") or []
        stages: List[Stage] = [Stage.model_validate(item) for item in raw_items]

        wh_names: List[str] = []
        try:
            whs = await self.list_warehouses(project)
            wh_names = [w.name for w in whs]
        except Exception:
            pass

        auto_stages = await self._get_auto_promo_stages(project)
        upstream_map, downstream_map = build_stage_dag(stages)
        return format_topology_summary(
            stages,
            upstream_map,
            downstream_map,
            warehouses=wh_names,
            auto_promo_stages=auto_stages,
        )

    async def trace_freight(
        self,
        project: str,
        freight_or_alias: Optional[str] = None,
        artifact_filter: Optional[str] = None,
    ) -> FreightTraceReport:
        """Correlate a Freight item or artifact version across the entire Stage DAG (N-to-1)."""
        target_freight: Optional[Freight] = None

        if freight_or_alias:
            raw = await self.get_freight(project, freight_or_alias)
            target_freight = Freight.model_validate(raw)
        elif artifact_filter:
            resp = await self._request("GET", f"/v1beta1/projects/{project}/freight")
            data = self._parse_json(resp, "list freight for trace")
            for f in self._extract_freight_objects(data):
                for art in f.normalized_artifacts():
                    if (
                        artifact_filter in art.version
                        or artifact_filter in art.repo_url
                        or (art.detail and artifact_filter in art.detail)
                    ):
                        target_freight = f
                        break
                if target_freight:
                    break
            if not target_freight:
                raise KargoResourceNotFoundError(
                    f"No Freight found in project '{project}' matching artifact '{artifact_filter}'"
                )
        else:
            raise KargoValidationError(
                "Provide either 'freight_or_alias' or 'artifact_filter' to trace Freight."
            )

        resp_stages = await self._request("GET", f"/v1beta1/projects/{project}/stages")
        stages_data = self._parse_json(resp_stages, "list stages for trace")
        raw_stages = stages_data.get("items") or stages_data.get("stages") or []
        stages = [Stage.model_validate(s) for s in raw_stages]

        currently_map = (target_freight.status.currently_in if target_freight.status else {}) or {}
        verified_map = (target_freight.status.verified_in if target_freight.status else {}) or {}
        approved_map = (target_freight.status.approved_for if target_freight.status else {}) or {}

        stage_traces: List[Dict[str, Any]] = []
        blockers: List[str] = []

        for stg in stages:
            sname = stg.metadata.name
            in_stage = sname in currently_map
            is_verified = sname in verified_map
            is_approved = sname in approved_map

            # Check eligibility from requestedFreight
            eligible = False
            blocker_reason: Optional[str] = None

            if is_approved:
                eligible = True
            else:
                for rf in stg.spec.requested_freight:
                    if rf.origin.name and target_freight.get_origin_name() and rf.origin.name != target_freight.get_origin_name():
                        continue
                    if rf.sources.direct:
                        eligible = True
                        break
                    ups = rf.sources.stages
                    strategy = rf.sources.availability_strategy or "OneOf"
                    if ups:
                        verified_ups = [u for u in ups if u in verified_map]
                        if strategy == "All" and len(verified_ups) == len(ups):
                            eligible = True
                        elif strategy != "All" and len(verified_ups) >= 1:
                            eligible = True
                        else:
                            missing_ups = [u for u in ups if u not in verified_map]
                            blocker_reason = (
                                f"Stage '{sname}' requires upstream verification in "
                                f"{missing_ups} (strategy={strategy}) or manual approval via "
                                f"kargo_approve_freight(project='{project}', freight_or_alias='{target_freight.metadata.name}', stage='{sname}')."
                            )

                    if eligible and rf.sources.required_soak_time:
                        # Check if longestSoak is recorded
                        soaks = [
                            (verified_map.get(u) or {}).get("longestSoak")
                            for u in ups
                            if isinstance(verified_map.get(u), dict)
                        ]
                        if not any(soaks):
                            blocker_reason = (
                                f"Stage '{sname}' requires soak time {rf.sources.required_soak_time} in upstream stages {ups}."
                            )

            if blocker_reason and not in_stage:
                blockers.append(blocker_reason)

            stage_traces.append(
                {
                    "stage": sname,
                    "currently_in": in_stage,
                    "verified": is_verified,
                    "approved": is_approved,
                    "eligible_for_promotion": eligible,
                    "blocker_reason": blocker_reason,
                }
            )

        fid = target_freight.metadata.name
        alias = target_freight.get_alias()
        in_count = sum(1 for st in stage_traces if st["currently_in"])
        ver_count = sum(1 for st in stage_traces if st["verified"])
        summary = (
            f"Freight '{alias or fid[:12]}' (origin '{target_freight.get_origin_name()}') is currently deployed in "
            f"{in_count}/{len(stage_traces)} stage(s) and verified in {ver_count}/{len(stage_traces)} stage(s)."
        )

        return FreightTraceReport(
            project=project,
            freight_id=fid,
            alias=alias,
            origin=target_freight.get_origin_name(),
            summary=summary,
            artifacts=[a.model_dump() for a in target_freight.normalized_artifacts()],
            stages=stage_traces,
            blockers=blockers,
            resource_uri=f"kargo://projects/{project}/freight/{fid}",
        )

    async def diagnose_stage(
        self,
        project: str,
        stage: str,
        include_events: bool = True,
    ) -> StageDiagnosisReport:
        """Correlate Stage conditions, active/last Promotion step traces, Verification AnalysisRuns, holds, and events (N-to-1)."""
        raw_stage = await self.get_stage(project, stage)
        stg = Stage.model_validate(raw_stage)

        auto_stages = await self._get_auto_promo_stages(project)
        auto_enabled = (
            bool(stg.status.auto_promotion_enabled)
            if (stg.status and stg.status.auto_promotion_enabled is not None)
            else (stage in auto_stages)
        )
        holds = (
            (stg.status.effective_auto_promotion_holds or stg.status.auto_promotion_holds)
            if stg.status
            else []
        )

        codes: List[str] = []
        recommendations: List[str] = []
        failed_promo_info: Optional[Dict[str, Any]] = None
        verification_info: Optional[Dict[str, Any]] = None

        # 1. Inspect currentPromotion / lastPromotion
        promo_ref = None
        if stg.status and stg.status.current_promotion:
            promo_ref = stg.status.current_promotion
        elif stg.status and stg.status.last_promotion:
            promo_ref = stg.status.last_promotion

        if isinstance(promo_ref, dict) and promo_ref.get("name"):
            promo_name = str(promo_ref["name"])
            try:
                p_raw = await self.get_promotion(project, promo_name)
                promo = Promotion.model_validate(p_raw)
                p_phase = promo.get_phase()
                failing_steps = [
                    {
                        "alias": s.alias,
                        "status": s.status,
                        "message": s.message,
                        "errorCount": s.error_count,
                    }
                    for s in (promo.status.step_execution_metadata if promo.status else [])
                    if s.status in ("Errored", "Failed", "Aborted", "Running")
                ]
                if p_phase in ("Failed", "Errored"):
                    codes.append("PROMOTION_STEP_FAILED")
                    msg_lower = (promo.status.message or "").lower() if promo.status else ""
                    step_msgs = " ".join(
                        (s.get("message") or "").lower() for s in failing_steps
                    )
                    combined_err = f"{msg_lower} {step_msgs}"
                    if any(
                        tok in combined_err
                        for tok in (
                            "auth",
                            "credentials",
                            "401",
                            "403",
                            "unauthorized",
                            "could not read username",
                            "could not read password",
                            "terminal prompts disabled",
                            "permission denied",
                        )
                    ):
                        codes.append("GIT_OR_REGISTRY_AUTH_ERROR")
                        recommendations.append(
                            f"Check repository credentials via 'kargo://projects/{project}/credentials' or update with kargo_manage_credentials."
                        )
                    if "authorized-stage" in combined_err or "argocd" in combined_err:
                        codes.append("ARGOCD_SYNC_OR_AUTH_FAILED")
                        recommendations.append(
                            f"Ensure the target Argo CD Application carries annotation 'kargo.akuity.io/authorized-stage: {project}:{stage}'."
                        )
                    recommendations.append(
                        f"Inspect full promotion trace at 'kargo://projects/{project}/promotions/{promo_name}' or roll back via kargo_rollback_stage(project='{project}', stage='{stage}')."
                    )
                    failed_promo_info = {
                        "name": promo_name,
                        "phase": p_phase,
                        "freight": promo.spec.freight,
                        "message": promo.status.message if promo.status else None,
                        "failing_steps": failing_steps,
                    }
                elif p_phase in ("Pending", "Running"):
                    codes.append("PROMOTION_IN_PROGRESS")
                    failed_promo_info = {
                        "name": promo_name,
                        "phase": p_phase,
                        "freight": promo.spec.freight,
                        "steps": failing_steps,
                    }
            except Exception:
                pass

        # 2. Inspect Verification status
        latest_ver = stg.get_latest_verification()
        if latest_ver:
            v_phase = latest_ver.get("phase", "Unknown")
            ar_info = latest_ver.get("analysisRun") or {}
            ar_name = ar_info.get("name") if isinstance(ar_info, dict) else None
            verification_info = {
                "id": latest_ver.get("id"),
                "phase": v_phase,
                "message": latest_ver.get("message"),
                "analysis_run": ar_name,
            }
            if v_phase in ("Failed", "Error", "Aborted", "Inconclusive"):
                codes.append("VERIFICATION_FAILED")
                recommendations.append(
                    f"Read AnalysisRun details at 'kargo://projects/{project}/analysis-runs/{ar_name or '<run>'}' "
                    f"or re-run flaky verification with kargo_manage_verification(project='{project}', stage='{stage}', action='reverify')."
                )
            elif v_phase in ("Pending", "Running"):
                codes.append("VERIFICATION_IN_PROGRESS")

        # 3. Inspect Stage health (Argo CD apps)
        health_status = stg.get_health_status()
        if health_status in ("Unhealthy", "Degraded", "Missing"):
            codes.append("STAGE_HEALTH_DEGRADED")
            recommendations.append(
                f"Stage Argo CD health is '{health_status}'. Consider rolling back with kargo_rollback_stage(project='{project}', stage='{stage}')."
            )

        # 4. Inspect Auto-Promotion Holds (Kargo v1.11+)
        if holds:
            codes.append("AUTO_PROMOTION_ON_HOLD")
            first_origin = "<warehouse>"
            if isinstance(holds[0], dict):
                raw_origin = holds[0].get("origin")
                if isinstance(raw_origin, dict) and raw_origin.get("name"):
                    first_origin = str(raw_origin["name"])
                elif isinstance(raw_origin, str) and raw_origin:
                    first_origin = raw_origin.split("/", 1)[1] if "/" in raw_origin else raw_origin
                elif holds[0].get("originName"):
                    first_origin = str(holds[0]["originName"])
            recommendations.append(
                f"Auto-promotion is held on Stage '{stage}' (typically after a rollback). "
                f"Resume auto-promotion by calling kargo_promote(project='{project}', stage='{stage}', origin_warehouse='{first_origin}')."
            )

        # 5. Check if Stage has no current Freight
        current_freight = stg.get_current_freight_id()
        if not current_freight and not codes:
            codes.append("NO_FREIGHT_DEPLOYED")
            recommendations.append(
                f"Call kargo_query_freight(project='{project}', stage='{stage}', available_only=True) to find promotable Freight."
            )

        if not codes:
            codes.append("HEALTHY")

        # 6. Correlate recent Warning events
        warning_events: List[Dict[str, Any]] = []
        if include_events:
            try:
                all_events = await self.list_project_events(project)
                for ev in all_events:
                    if not isinstance(ev, dict):
                        continue
                    involved = ev.get("involvedObject") or {}
                    ev_type = ev.get("type", "Normal")
                    if ev_type == "Warning" or involved.get("name") == stage:
                        warning_events.append(
                            {
                                "type": ev_type,
                                "reason": ev.get("reason", ""),
                                "object": f"{involved.get('kind', '')}/{involved.get('name', '')}",
                                "message": ev.get("message", ""),
                            }
                        )
                warning_events = warning_events[:10]
            except Exception:
                pass

        phase = stg.get_phase()
        summary = (
            f"Stage '{stage}' in project '{project}' is in phase '{phase}' "
            f"(health='{health_status}', current_freight='{current_freight or 'none'}', "
            f"codes={codes})."
        )

        return StageDiagnosisReport(
            project=project,
            stage=stage,
            phase=phase,
            health_status=health_status,
            current_freight=current_freight,
            auto_promotion_enabled=auto_enabled,
            auto_promotion_holds=holds,
            summary=summary,
            diagnosis_codes=codes,
            conditions=stg.status.conditions if stg.status else [],
            failed_promotion=failed_promo_info,
            verification=verification_info,
            warning_events=warning_events,
            recommendations=recommendations,
        )

    async def diagnose_warehouse(
        self,
        project: str,
        warehouse: str,
    ) -> WarehouseDiagnosisReport:
        """Diagnose Warehouse artifact discovery, conditions, and deprecated Kargo v1.9–v1.12 fields (N-to-1)."""
        raw_wh = await self.get_warehouse(project, warehouse)
        wh = Warehouse.model_validate(raw_wh)

        raw_spec = raw_wh.get("spec") if isinstance(raw_wh, dict) else {}
        deprecated = detect_deprecated_warehouse_fields(raw_spec or {})

        discovered_counts = {"git": 0, "images": 0, "charts": 0}
        if wh.status and isinstance(wh.status.discovered_artifacts, dict):
            da = wh.status.discovered_artifacts
            discovered_counts["git"] = len(da.get("git") or [])
            discovered_counts["images"] = len(da.get("images") or [])
            discovered_counts["charts"] = len(da.get("charts") or [])

        codes: List[str] = []
        recommendations: List[str] = []

        if deprecated:
            codes.append("DEPRECATED_SUBSCRIPTION_FIELDS")
            recommendations.append(
                f"Update Warehouse '{warehouse}' via kargo_apply_warehouse(project='{project}', name='{warehouse}', ...) "
                "to replace deprecated fields (constraint instead of semverConstraint; allowTagsRegexes/ignoreTagsRegexes instead of allowTags/ignoreTags)."
            )

        ready = wh.is_ready()
        if not ready:
            codes.append("WAREHOUSE_DISCOVERY_FAILED")
            cond_msgs = " ".join(
                str(c.get("message", "")).lower()
                for c in (wh.status.conditions if wh.status else [])
            )
            if any(
                tok in cond_msgs
                for tok in (
                    "auth",
                    "credential",
                    "401",
                    "403",
                    "unauthorized",
                    "could not read username",
                    "could not read password",
                    "terminal prompts disabled",
                    "permission denied",
                )
            ):
                codes.append("REPOSITORY_AUTH_FAILED")
                recommendations.append(
                    f"Configure repository credentials in project '{project}' using kargo_manage_credentials."
                )
            else:
                recommendations.append(
                    f"Check subscription repository URLs and trigger discovery via kargo_refresh(project='{project}', kind='warehouse', name='{warehouse}')."
                )

        total_discovered = sum(discovered_counts.values())
        last_freight = wh.status.last_freight_id if wh.status else None
        if ready and total_discovered == 0 and not last_freight:
            codes.append("NO_ARTIFACTS_DISCOVERED")
            recommendations.append(
                f"Call kargo_refresh(project='{project}', kind='warehouse', name='{warehouse}', wait=True) or relax tag/semver constraints."
            )

        if not codes:
            codes.append("HEALTHY")

        summary = (
            f"Warehouse '{warehouse}' in project '{project}' is "
            f"{'healthy' if ready and not deprecated else 'degraded'} "
            f"(subscriptions={len(wh.spec.subscriptions)}, discovered={discovered_counts}, "
            f"last_freight='{last_freight or 'none'}', codes={codes})."
        )

        return WarehouseDiagnosisReport(
            project=project,
            warehouse=warehouse,
            ready=ready and not deprecated,
            last_freight_id=last_freight,
            summary=summary,
            diagnosis_codes=codes,
            subscriptions_count=len(wh.spec.subscriptions),
            discovered_counts=discovered_counts,
            deprecated_fields=deprecated,
            conditions=wh.status.conditions if wh.status else [],
            recommendations=recommendations,
        )
