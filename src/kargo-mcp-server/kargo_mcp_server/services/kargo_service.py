"""Kargo REST API client service.

Async HTTP client wrapping Kargo's /v1beta1 REST API.
Handles authentication, request construction, and response parsing
into Pydantic models.
"""


import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import httpx

from kargo_mcp_server.config import AuthMode, ServerConfig
from kargo_mcp_server.models.project import Project, ProjectSummary, ProjectSpec
from kargo_mcp_server.models.stage import Stage, StageSummary
from kargo_mcp_server.models.warehouse import Warehouse, WarehouseSummary
from kargo_mcp_server.models.freight import (
    Freight,
    FreightSummary,
)
from kargo_mcp_server.models.promotion import Promotion, PromotionSummary
from kargo_mcp_server.models.promotion_task import PromotionTask
from kargo_mcp_server.models.credentials import CreateRepoCredentialsRequest
from kargo_mcp_server.utils.kargo_helpers import (
    build_stage_dag,
    format_topology_summary,
    stages_to_summaries,
    validate_no_self_reference,
)


class ApiError(Exception):
    """Raised for non-2xx responses from Kargo API."""

    def __init__(self, status_code: int, message: str, body: Optional[str] = None) -> None:
        super().__init__(f"Kargo API error {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class KargoService:
    """Async wrapper around Kargo REST API.

    Responsibilities:
    - Construct REST paths under /v1beta1
    - Inject Authorization headers based on auth mode
    - Parse JSON into Pydantic models
    - Raise typed ApiError for non-2xx responses
    """

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
        """Safely parse a JSON response body.

        Returns the parsed dict/list.  If the body is empty or not valid
        JSON, raises ``ApiError`` with the raw response text so callers
        never crash with a bare ``JSONDecodeError``.
        """
        if not resp.content:
            return {}
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raw_preview = (resp.text or "(empty)")[:500]
            raise ApiError(
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
            raise ApiError(resp.status_code, "Failed admin login", resp.text)
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
            
        resp = await client.request(
            method, path, headers=headers, **kwargs
        )
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.reason_phrase or "Error", resp.text)
        return resp

    async def _upsert_resource(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Create-or-update a Kargo resource via the unified /v1beta1/resources endpoint.

        Kargo exposes separate verbs for creation (POST) and update (PUT).
        This helper implements true upsert semantics:
          1. Try PUT (update) first.
          2. If the resource does not exist (404), fall back to POST (create).

        Returns the manifest dict from the API response.
        """
        payload = json.dumps(body)
        common_kwargs: Dict[str, Any] = {
            "headers": {"Content-Type": "text/plain"},
            "content": payload,
        }

        try:
            # Attempt update first — succeeds if the resource already exists.
            resp = await self._request("PUT", "/v1beta1/resources", **common_kwargs)
            data = self._parse_json(resp, "upsert resource (PUT)")
            manifest = (
                data.get("results", [{}])[0].get("updatedResourceManifest")
                or data.get("results", [{}])[0].get("createdResourceManifest")
            )
        except ApiError as e:
            if e.status_code != 404:
                raise
            # Resource doesn't exist yet — create it.
            resp = await self._request("POST", "/v1beta1/resources", **common_kwargs)
            data = self._parse_json(resp, "upsert resource (POST)")
            results = data.get("results")
            if results and isinstance(results, list) and len(results) > 0:
                manifest = results[0].get("createdResourceManifest")
            else:
                manifest = None

        return manifest or body

    # ---- Projects ----

    async def list_projects(self) -> List[ProjectSummary]:
        """List all Kargo projects."""
        resp = await self._request("GET", "/v1beta1/projects")
        data = self._parse_json(resp, "list projects")
        items: List[ProjectSummary] = []
        for item in data.get("items", []):
            project = Project.model_validate(item)
            items.append(
                ProjectSummary(
                    name=project.metadata.name,
                    namespace=project.metadata.namespace or "",
                    stage_count=0,
                    auto_promotion_enabled=bool(
                        project.spec.promotion_policy
                        and project.spec.promotion_policy.auto_promotion_enabled
                    ),
                )
            )
        return items

    async def get_project(self, name: str) -> Dict[str, Any]:
        """Get a detailed project resource."""
        resp = await self._request("GET", f"/v1beta1/projects/{name}")
        return self._parse_json(resp, "get project")

    async def create_project(
        self, name: str, spec: Optional[ProjectSpec] = None
    ) -> Project:
        """Create a new Kargo project."""
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Project",
            "metadata": {"name": name},
        }
        if spec:
            body["spec"] = spec.model_dump(by_alias=True)
        resp = await self._request(
            "POST", 
            "/v1beta1/resources", 
            headers={"Content-Type": "text/plain"}, 
            content=json.dumps(body)
        )
        data = self._parse_json(resp, "create project")
        manifest = data.get("results", [{}])[0].get("createdResourceManifest", {})
        if not manifest:
            manifest = body  # fallback if not returned
        return Project.model_validate(manifest)

    async def update_project(
        self, name: str, spec: ProjectSpec
    ) -> Project:
        """Update an existing Kargo project."""
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Project",
            "metadata": {"name": name},
            "spec": spec.model_dump(by_alias=True),
        }
        resp = await self._request(
            "PUT", 
            "/v1beta1/resources", 
            headers={"Content-Type": "text/plain"}, 
            content=json.dumps(body)
        )
        data = self._parse_json(resp, "update project")
        manifest = data.get("results", [{}])[0].get("updatedResourceManifest", {})
        if not manifest:
            manifest = body  # fallback
        return Project.model_validate(manifest)

    async def delete_project(self, name: str) -> Dict[str, str]:
        """Delete a Kargo project."""
        await self._request("DELETE", f"/v1beta1/projects/{name}")
        return {"message": f"Project '{name}' deleted successfully"}


    # ---- Stages ----

    async def list_stages(self, project: str) -> List[StageSummary]:
        """List stages in a project with DAG topology."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/stages")
        data = self._parse_json(resp, "list stages")
        stages: List[Stage] = [
            Stage.model_validate(item) for item in data.get("items", [])
        ]

        upstream_map, downstream_map = build_stage_dag(stages)
        return stages_to_summaries(stages, upstream_map, downstream_map)

    async def get_stage(self, project: str, stage: str) -> Dict[str, Any]:
        """Get a detailed stage resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/stages/{stage}"
        )
        return self._parse_json(resp, "get stage")

    async def upsert_stage(
        self,
        project: str,
        stage: str,
        spec: Dict[str, Any],
    ) -> Stage:
        """Create or update a stage."""
        validate_no_self_reference(stage, spec)

        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Stage",
            "metadata": {"name": stage, "namespace": project},
            "spec": spec,
        }
        manifest = await self._upsert_resource(body)
        return Stage.model_validate(manifest)

    # ---- Warehouses ----

    async def list_warehouses(self, project: str) -> List[WarehouseSummary]:
        """List warehouses in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/warehouses")
        data = self._parse_json(resp, "list warehouses")
        warehouses: List[WarehouseSummary] = []
        for item in data.get("items", []):
            wh = Warehouse.model_validate(item)
            source_types = sorted({src.type for src in wh.spec.sources})
            warehouses.append(
                WarehouseSummary(
                    name=wh.metadata.name,
                    source_types=source_types,
                )
            )
        return warehouses

    async def get_warehouse(self, project: str, name: str) -> Dict[str, Any]:
        """Get a detailed warehouse resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/warehouses/{name}"
        )
        return self._parse_json(resp, "get warehouse")

    async def refresh_warehouse(self, project: str, name: str) -> None:
        """Force immediate reconciliation of a Warehouse."""
        await self._request(
            "POST", f"/v1beta1/projects/{project}/warehouses/{name}/refresh"
        )

    async def upsert_warehouse(
        self,
        project: str,
        name: str,
        spec: Dict[str, Any],
    ) -> Warehouse:
        """Create or update a warehouse."""
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Warehouse",
            "metadata": {"name": name, "namespace": project},
            "spec": spec,
        }
        manifest = await self._upsert_resource(body)
        return Warehouse.model_validate(manifest)

    # ---- Freight ----

    async def list_freight(self, project: str) -> List[FreightSummary]:
        """List freight in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/freight")
        data = self._parse_json(resp, "list freight")
        freight_items: List[FreightSummary] = []
        
        def extract_freight(obj: Any) -> None:
            if isinstance(obj, dict):
                # Is this a Freight object itself?
                if obj.get("kind") == "Freight":
                    freight = Freight.model_validate(obj)
                    freight_items.append(
                        FreightSummary(
                            id=freight.metadata.name,
                            artifacts=freight.spec.artifacts,
                            per_stage=freight.status.stage_states if freight.status else [],
                        )
                    )
                else:
                    for val in obj.values():
                        extract_freight(val)
            elif isinstance(obj, list):
                for item in obj:
                    extract_freight(item)
                    
        extract_freight(data)
        return freight_items

    async def get_freight(self, project: str, freight_id: str) -> Dict[str, Any]:
        """Get a detailed freight resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/freight/{freight_id}"
        )
        return self._parse_json(resp, "get freight")

    async def approve_freight(
        self,
        project: str,
        freight_id: str,
        stage: str,
        bearer_override: Optional[str] = None,
    ) -> Freight:
        """Approve freight for a specific stage."""
        path = f"/v1beta1/projects/{project}/freight/{freight_id}/approve"
        resp = await self._request(
            "POST", path, bearer_override=bearer_override, params={"stage": stage}
        )
        if resp.content:
            return Freight.model_validate(self._parse_json(resp, "approve freight"))
        data = await self.get_freight(project, freight_id)
        return Freight.model_validate(data)

    # ---- Promotions ----

    async def _inflate_promotion_steps(
        self,
        project: str,
        steps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Inflate PromotionTask references into concrete promotion steps.

        Kargo's Admission Webhook requires every Promotion to contain fully
        populated ``uses``-based steps.  When a Stage's promotionTemplate
        references a PromotionTask (``task: {name: ...}``), the Kargo CLI /
        API Server normally "inflates" that reference into the concrete steps
        defined inside the PromotionTask.

        Because the MCP Server creates Promotions via the generic
        ``/v1beta1/resources`` endpoint (bypassing the buggy RPC endpoint),
        inflation is *not* performed server-side.  This method replicates
        that inflation client-side:

        1. Walk the steps array.
        2. If a step has ``uses`` → it is already concrete; keep it.
        3. If a step has ``task.name`` → fetch the PromotionTask, extract
           its ``spec.steps``, and splice them in place of the reference.
        4. Return the fully flattened list of concrete steps.

        Variable resolution (``${{ vars.X }}``) is intentionally left to
        Kargo's runtime controller — the webhook only validates that
        concrete step runners (``uses``) are present.
        """
        inflated: List[Dict[str, Any]] = []

        for step in steps:
            if "uses" in step:
                # Already a concrete step — keep as-is
                inflated.append(step)
            elif "task" in step:
                task_ref = step["task"]
                task_name = task_ref.get("name", "")

                if not task_name:
                    # Malformed reference — pass through and let the
                    # webhook return a descriptive error.
                    inflated.append(step)
                    continue

                logger.info(
                    "Inflating PromotionTask reference '%s' in project '%s'",
                    task_name,
                    project,
                )

                try:
                    task_data = await self.get_promotion_task(project, task_name)
                except ApiError as exc:
                    raise ApiError(
                        exc.status_code,
                        f"Cannot inflate PromotionTask '{task_name}': {exc}",
                        exc.body,
                    )

                task_steps = task_data.get("spec", {}).get("steps", [])

                if not task_steps:
                    raise ApiError(
                        422,
                        f"PromotionTask '{task_name}' contains no steps. "
                        "Ensure the task is correctly defined with at least "
                        "one 'uses' step.",
                    )

                inflated.extend(task_steps)
            else:
                # Unknown step shape — pass through
                inflated.append(step)

        return inflated

    async def create_promotion(
        self,
        project: str,
        stage: str,
        freight: str,
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """Create a Promotion by creating a Custom Resource directly.

        Implements client-side PromotionTask inflation: if the Stage's
        promotionTemplate references a PromotionTask (``task: {name: ...}``),
        the task's concrete steps are fetched and spliced into the Promotion
        CRD before submission.  This is required because the generic
        ``/v1beta1/resources`` endpoint does not perform server-side inflation.
        """

        # We MUST provide an exact 'name' instead of 'generateName'. 
        # Kargo's generic /v1beta1/resources endpoint uses Kubernetes Server-Side Apply
        # which silently drops resources that don't have a specific name!
        promo_name = f"{stage}-{freight[:7]}"

        # Fetch the stage to get its promotion steps (since we are bypassing the Kargo API Server
        # which normally inflates this for us, we must inject the steps directly into the CRD)
        stage_data = await self.get_stage(project, stage)
        stage_steps = stage_data.get("spec", {}).get("promotionTemplate", {}).get("spec", {}).get("steps", [])

        # Inflate any PromotionTask references into concrete steps so the
        # Admission Webhook does not reject the Promotion.
        stage_steps = await self._inflate_promotion_steps(project, stage_steps)

        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Promotion",
            "metadata": {
                "name": promo_name,
                "namespace": project
            },
            "spec": {
                "stage": stage,
                "freight": freight,
                "steps": stage_steps
            },
        }

        logger.debug(
            "create_promotion: project=%s stage=%s freight=%s steps_count=%d",
            project, stage, freight, len(stage_steps)
        )

        resp = await self._request(
            "POST",
            "/v1beta1/resources",
            headers={"Content-Type": "text/plain"},
            content=json.dumps(body),
            bearer_override=bearer_override,
        )

        logger.debug(
            "create_promotion response: status=%d body=%s",
            resp.status_code, (resp.text or "")[:1000],
        )

        data = self._parse_json(resp, "create promotion")
        
        # The result of POST /v1beta1/resources is in `results[0].createdResourceManifest`
        manifest = data.get("results", [{}])[0].get("createdResourceManifest", {})
        if not manifest:
            # If it already existed, it might be in updatedResourceManifest
            manifest = data.get("results", [{}])[0].get("updatedResourceManifest", {})
            
        if not manifest:
            raise ApiError(
                resp.status_code,
                "Kargo API did not return a createdResourceManifest for the Promotion.",
                resp.text,
            )

        return Promotion.model_validate(manifest)

    async def get_promotion(
        self, project: str, promotion_name: str
    ) -> Dict[str, Any]:
        """Get detailed promotion status."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/promotions/{promotion_name}"
        )
        return self._parse_json(resp, "get promotion")

    async def list_promotions(self, project: str) -> List[PromotionSummary]:
        """List promotions in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/promotions")

        logger.debug(
            "list_promotions response: status=%d body=%s",
            resp.status_code, (resp.text or "")[:1000],
        )

        data = self._parse_json(resp, "list promotions")
        items: List[PromotionSummary] = []

        # Kargo list responses use "items" (or sometimes "promotions") as the
        # array key.  Items may or may not include a "kind" field.
        raw_items: List[Any] = []
        if isinstance(data, dict):
            raw_items = data.get("items") or data.get("promotions") or []
        elif isinstance(data, list):
            raw_items = data

        logger.debug("list_promotions: found %d raw items", len(raw_items))

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            # Items without "metadata" are not Promotion objects
            if not item.get("metadata"):
                continue
            try:
                p = Promotion.model_validate(item)
                items.append(
                    PromotionSummary(
                        name=p.metadata.name,
                        stage=p.spec.stage,
                        freight=p.spec.freight,
                        state=p.status.state if p.status else "Unknown",
                        started_at=p.status.started_at if p.status else None,
                        finished_at=p.status.finished_at if p.status else None,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Skipping unparseable promotion item: %s — %s",
                    item.get("metadata", {}).get("name", "?"), exc,
                )

        return items

    async def abort_promotion(
        self,
        project: str,
        promotion_name: str,
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """Abort a running promotion."""
        path = f"/v1beta1/projects/{project}/promotions/{promotion_name}/abort"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        if resp.content:
            return Promotion.model_validate(self._parse_json(resp, "abort promotion"))
        data = await self.get_promotion(project, promotion_name)
        return Promotion.model_validate(data)

    # ---- Promotion Tasks ----

    async def list_promotion_tasks(self, project: str) -> List[Dict[str, Any]]:
        """List promotion tasks in a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/promotiontasks")
        data = self._parse_json(resp, "list promotion tasks")
        return data.get("items", [])

    async def get_promotion_task(self, project: str, name: str) -> Dict[str, Any]:
        """Get a detailed promotion task resource."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/promotiontasks/{name}"
        )
        return self._parse_json(resp, "get promotion task")

    async def upsert_promotion_task(
        self,
        project: str,
        name: str,
        spec: Dict[str, Any],
    ) -> PromotionTask:
        """Create or update a promotion task."""
        body: Dict[str, Any] = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "PromotionTask",
            "metadata": {"name": name, "namespace": project},
            "spec": spec,
        }
        manifest = await self._upsert_resource(body)
        return PromotionTask.model_validate(manifest)

    # ---- Credentials ----

    async def create_repo_credentials(
        self, project: str, req: CreateRepoCredentialsRequest
    ) -> Dict[str, Any]:
        """Create repository credentials for a project."""
        resp = await self._request(
            "POST",
            f"/v1beta1/projects/{project}/repo-credentials",
            json=req.model_dump(exclude_none=True),
        )
        return self._parse_json(resp, "create repo credentials")

    async def list_repo_credentials(self, project: str) -> List[Dict[str, Any]]:
        """List repository credentials for a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/repo-credentials")
        data = self._parse_json(resp, "list repo credentials")
        return data.get("items", [])

    async def get_repo_credentials(self, project: str, name: str) -> Dict[str, Any]:
        """Get detailed repository credentials."""
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/repo-credentials/{name}"
        )
        return self._parse_json(resp, "get repo credentials")

    async def delete_repo_credentials(self, project: str, name: str) -> Dict[str, str]:
        """Delete repository credentials."""
        await self._request("DELETE", f"/v1beta1/projects/{project}/repo-credentials/{name}")
        return {"message": f"Credentials '{name}' deleted successfully"}

    # ---- Verification ----

    async def reverify_stage(
        self,
        project: str,
        stage: str,
        bearer_override: Optional[str] = None,
    ) -> Stage:
        """Trigger re-verification of current freight for a stage."""
        path = f"/v1beta1/projects/{project}/stages/{stage}/verification"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        if resp.content:
            return Stage.model_validate(self._parse_json(resp, "reverify stage"))
        data = await self.get_stage(project, stage)
        return Stage.model_validate(data)

    # ---- Topology ----

    async def describe_topology(self, project: str) -> Dict[str, Any]:
        """Build and return a pipeline topology summary for a project."""
        resp = await self._request("GET", f"/v1beta1/projects/{project}/stages")
        data = self._parse_json(resp, "describe topology")
        stages: List[Stage] = [
            Stage.model_validate(item) for item in data.get("items", [])
        ]
        upstream_map, downstream_map = build_stage_dag(stages)
        return format_topology_summary(stages, upstream_map, downstream_map)
