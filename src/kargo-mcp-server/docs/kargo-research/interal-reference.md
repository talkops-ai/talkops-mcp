The best way to make this usable as an internal reference is to give you a clean module‑level skeleton that uses the official MCP Python SDK (`mcp.server.fastmcp.FastMCP`) and a thin, well‑typed Kargo REST client with Pydantic models. Below is a structured skeleton you can drop into a repo and then refine endpoints and fields as you implement against your actual Kargo instance. [github](https://github.com/modelcontextprotocol/python-sdk)

I’ll organize it as if you had four modules:

- `config.py` – settings and auth modes  
- `kargo_models.py` – Pydantic models for Kargo objects  
- `kargo_client.py` – HTTP client with all Kargo API calls (list, get, promote, approve, refresh, etc.)  
- `server.py` – MCP server wiring tools + resources to the client using FastMCP  

You can collapse them into a single file if you prefer.

***

## config.py – configuration & auth strategy

```python
# config.py
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseSettings, HttpUrl, SecretStr


class AuthMode(str, Enum):
    ADMIN = "admin"          # MCP server logs in as Kargo admin
    STATIC_BEARER = "static" # MCP server uses a preconfigured bearer token
    PASSTHROUGH = "passthrough"  # forward caller token from MCP client (if you wire that up)


class KargoApiSettings(BaseSettings):
    """
    Kargo API connection settings.

    Values are typically provided via env vars:
    - KARGO_BASE_URL
    - KARGO_VERIFY_SSL
    - KARGO_AUTH_MODE
    - KARGO_ADMIN_PASSWORD
    - KARGO_STATIC_BEARER_TOKEN
    """
    base_url: HttpUrl = "http://localhost:8080"  # for local port-forward; override in prod
    verify_ssl: bool = True

    auth_mode: AuthMode = AuthMode.ADMIN

    # Used in ADMIN mode – server will login and obtain JWT
    admin_password: Optional[SecretStr] = None

    # Used in STATIC_BEARER mode
    static_bearer_token: Optional[SecretStr] = None

    # Optional timeout (seconds) for HTTP calls
    timeout_seconds: float = 30.0

    class Config:
        env_prefix = "KARGO_"
        case_sensitive = False
```

***

## kargo_models.py – Pydantic models for Kargo REST payloads

These are intentionally minimal; add/remove fields based on the concrete REST schema you observe from `/v1beta1`. [burrell](https://burrell.tech/blog/kargo-v1-9/)

```python
# kargo_models.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Common metadata wrapper (Kubernetes-style)
class ObjectMeta(BaseModel):
    name: str
    namespace: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    creationTimestamp: Optional[datetime] = None


# ---- Project ----

class PromotionPolicy(BaseModel):
    auto_promotion_enabled: bool = Field(default=True, alias="autoPromotionEnabled")
    selection_strategy: Optional[str] = Field(default=None, alias="selectionStrategy")


class ProjectSpec(BaseModel):
    promotion_policy: Optional[PromotionPolicy] = Field(
        default=None, alias="promotionPolicy"
    )
    # add additional project-level settings as needed


class ProjectStatus(BaseModel):
    # populate with whatever fields you care about
    conditions: List[Dict[str, Any]] = Field(default_factory=list)


class Project(BaseModel):
    apiVersion: str
    kind: str
    metadata: ObjectMeta
    spec: ProjectSpec
    status: Optional[ProjectStatus] = None


class ProjectSummary(BaseModel):
    name: str
    namespace: str
    stage_count: int
    auto_promotion_enabled: bool


# ---- Stage ----

class RequestedFreightOrigin(BaseModel):
    kind: str  # Warehouse / Stage
    name: str


class RequestedFreight(BaseModel):
    origin: RequestedFreightOrigin
    availability_strategy: str = Field(alias="availabilityStrategy")


class StageSpec(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)
    requestedFreight: List[RequestedFreight] = Field(default_factory=list)
    promotionTemplateRef: Optional[str] = None  # name of PromotionTask
    # verification config, etc., can be added here


class StageStatus(BaseModel):
    current_freight_id: Optional[str] = Field(default=None, alias="currentFreightId")
    last_promotion_id: Optional[str] = Field(default=None, alias="lastPromotionId")
    conditions: List[Dict[str, Any]] = Field(default_factory=list)


class Stage(BaseModel):
    apiVersion: str
    kind: str
    metadata: ObjectMeta
    spec: StageSpec
    status: Optional[StageStatus] = None


class StageSummary(BaseModel):
    name: str
    upstream_stages: List[str] = Field(default_factory=list)
    downstream_stages: List[str] = Field(default_factory=list)
    current_freight_id: Optional[str] = None
    auto_promotion_enabled: bool = True


# ---- Warehouse ----

class WarehouseSource(BaseModel):
    type: str  # e.g. "git", "image", "helm"
    url: str
    selector: Optional[str] = None  # tag filter/semver, etc.


class WarehouseSpec(BaseModel):
    sources: List[WarehouseSource] = Field(default_factory=list)


class WarehouseStatus(BaseModel):
    last_sync_time: Optional[datetime] = Field(default=None, alias="lastSyncTime")
    conditions: List[Dict[str, Any]] = Field(default_factory=list)


class Warehouse(BaseModel):
    apiVersion: str
    kind: str
    metadata: ObjectMeta
    spec: WarehouseSpec
    status: Optional[WarehouseStatus] = None


class WarehouseSummary(BaseModel):
    name: str
    source_types: List[str]


# ---- Freight ----

class ArtifactReference(BaseModel):
    type: str   # "image", "git", "helm", etc.
    ref: str    # repo/tag, commit SHA, chart version, etc.


class FreightSpec(BaseModel):
    artifacts: List[ArtifactReference] = Field(default_factory=list)


class FreightStageState(BaseModel):
    stage: str
    available: bool
    promoted: bool
    verified: bool


class FreightStatus(BaseModel):
    discovered_time: Optional[datetime] = Field(default=None, alias="discoveredTime")
    stage_states: List[FreightStageState] = Field(default_factory=list, alias="stageStates")
    message: Optional[str] = None
    state: Optional[str] = None  # e.g., "Succeeded", "Failed", etc.


class Freight(BaseModel):
    apiVersion: str
    kind: str
    metadata: ObjectMeta
    spec: FreightSpec
    status: Optional[FreightStatus] = None


class FreightSummary(BaseModel):
    id: str
    artifacts: List[ArtifactReference]
    per_stage: List[FreightStageState]


# ---- Promotion ----

class PromotionStepStatus(BaseModel):
    name: str
    type: str
    status: str
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")
    log_url: Optional[str] = Field(default=None, alias="logUrl")


class PromotionSpec(BaseModel):
    stage: str
    project: str
    freight_id: str = Field(alias="freightId")
    trigger_type: str = Field(alias="triggerType")  # "auto" or "manual"


class PromotionStatus(BaseModel):
    state: str
    message: Optional[str] = None
    steps: List[PromotionStepStatus] = Field(default_factory=list)
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")


class Promotion(BaseModel):
    apiVersion: str
    kind: str
    metadata: ObjectMeta
    spec: PromotionSpec
    status: Optional[PromotionStatus] = None


class PromotionSummary(BaseModel):
    name: str
    stage: str
    freight_id: str
    state: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
```

***

## kargo_client.py – HTTP client and backend logic

This is where you wire endpoints like `/v1beta1/projects`, `/stages/{stage}/promotions`, `/freight/{freight}/approve`, and `/warehouses/{warehouse}/refresh`. [tenable](https://www.tenable.com/cve/CVE-2026-27111)

```python
# kargo_client.py
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

import httpx
from pydantic import BaseModel

from config import KargoApiSettings, AuthMode
from kargo_models import (
    Project,
    ProjectSummary,
    Stage,
    StageSummary,
    Warehouse,
    WarehouseSummary,
    Freight,
    FreightSummary,
    Promotion,
    PromotionSummary,
    StageSpec,
)


class ApiError(Exception):
    """Raised for non-2xx responses from Kargo API."""

    def __init__(self, status_code: int, message: str, body: str | None = None) -> None:
        super().__init__(f"Kargo API error {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class KargoApiClient:
    """
    Thin wrapper around Kargo REST API.

    - Handles auth header injection
    - Parses responses into Pydantic models
    - Centralizes URL construction
    """

    def __init__(self, settings: KargoApiSettings, token: Optional[str] = None) -> None:
        self._settings = settings
        self._base_url = settings.base_url.rstrip("/")
        self._token = token  # admin or static token
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            verify=self._settings.verify_ssl,
            timeout=self._settings.timeout_seconds,
        )

    @property
    def token(self) -> Optional[str]:
        return self._token

    async def close(self) -> None:
        await self._client.aclose()

    async def ensure_admin_login(self) -> None:
        """
        Ensure we have an admin JWT token (ADMIN mode).
        You will need to adapt this to the actual login endpoint your Kargo instance exposes.
        """
        if self._settings.auth_mode != AuthMode.ADMIN:
            return
        if self._token is not None:
            return
        if not self._settings.admin_password:
            raise RuntimeError("KARGO_ADMIN_PASSWORD is required for ADMIN auth mode")

        # TODO: confirm endpoint path from your deployment / CLI
        login_path = "/v1beta1/admin/login"
        resp = await self._client.post(
            login_path,
            json={"password": self._settings.admin_password.get_secret_value()},
        )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, "Failed admin login", resp.text)
        data = resp.json()
        self._token = data["token"]

    def _headers(self, bearer_override: Optional[str] = None) -> dict:
        token = bearer_override or self._token

        headers: dict = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        bearer_override: Optional[str] = None,
        **kwargs,
    ) -> httpx.Response:
        # In admin mode, make sure we have a token
        if self._settings.auth_mode == AuthMode.ADMIN and not bearer_override:
            await self.ensure_admin_login()

        resp = await self._client.request(
            method, path, headers=self._headers(bearer_override), **kwargs
        )
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.reason_phrase, resp.text)
        return resp

    # ---- Projects ----

    async def list_projects(self) -> List[ProjectSummary]:
        resp = await self._request("GET", "/v1beta1/projects")
        data = resp.json()
        items: list[ProjectSummary] = []
        for item in data.get("items", []):
            project = Project.model_validate(item)
            # Derive summary fields
            items.append(
                ProjectSummary(
                    name=project.metadata.name,
                    namespace=project.metadata.namespace or "",
                    stage_count=0,  # optionally compute via list_stages()
                    auto_promotion_enabled=bool(
                        project.spec.promotion_policy
                        and project.spec.promotion_policy.auto_promotion_enabled
                    ),
                )
            )
        return items

    async def get_project(self, name: str) -> Project:
        resp = await self._request("GET", f"/v1beta1/projects/{name}")
        return Project.model_validate(resp.json())

    # ---- Stages ----

    async def list_stages(self, project: str) -> List[StageSummary]:
        resp = await self._request("GET", f"/v1beta1/projects/{project}/stages")
        data = resp.json()
        stages: list[Stage] = [
            Stage.model_validate(item) for item in data.get("items", [])
        ]
        # Basic DAG derivation from requestedFreight
        upstream_map: dict[str, set[str]] = {s.metadata.name: set() for s in stages}
        downstream_map: dict[str, set[str]] = {s.metadata.name: set() for s in stages}

        for stage in stages:
            for rf in stage.spec.requestedFreight:
                if rf.origin.kind.lower() == "stage":
                    upstream_map[stage.metadata.name].add(rf.origin.name)
                    downstream_map[rf.origin.name].add(stage.metadata.name)

        summaries: list[StageSummary] = []
        for s in stages:
            summaries.append(
                StageSummary(
                    name=s.metadata.name,
                    upstream_stages=sorted(upstream_map[s.metadata.name]),
                    downstream_stages=sorted(downstream_map[s.metadata.name]),
                    current_freight_id=(
                        s.status.current_freight_id if s.status else None
                    ),
                    auto_promotion_enabled=True,  # refine from spec or project policy
                )
            )
        return summaries

    async def get_stage(self, project: str, stage: str) -> Stage:
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/stages/{stage}"
        )
        return Stage.model_validate(resp.json())

    async def upsert_stage(
        self,
        project: str,
        stage: str,
        spec: StageSpec,
    ) -> Stage:
        """
        Apply a stage definition.

        You may choose to call a dedicated 'apply' endpoint or directly PUT the CRD.
        Here we assume a REST 'apply' style path.
        """
        # Client-side DAG guardrail example:
        self._validate_stage_spec_for_cycles(project, stage, spec)

        body = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Stage",
            "metadata": {"name": stage, "namespace": project},
            "spec": spec.model_dump(by_alias=True),
        }
        resp = await self._request(
            "PUT", f"/v1beta1/projects/{project}/stages/{stage}", json=body
        )
        return Stage.model_validate(resp.json())

    def _validate_stage_spec_for_cycles(
        self, project: str, stage: str, spec: StageSpec
    ) -> None:
        """
        Basic guardrail: a stage cannot list itself or directly mutually refer with another stage.
        Full DAG validation is best done across all stages; this just protects obvious errors.
        """
        for rf in spec.requestedFreight:
            if rf.origin.kind.lower() == "stage":
                if rf.origin.name == stage:
                    raise ValueError(
                        f"Stage {stage!r} cannot list itself as requestedFreight origin"
                    )
        # Advanced: fetch all stages and run full cycle detection (left as TODO)

    # ---- Warehouses ----

    async def list_warehouses(self, project: str) -> List[WarehouseSummary]:
        resp = await self._request("GET", f"/v1beta1/projects/{project}/warehouses")
        data = resp.json()
        warehouses: list[WarehouseSummary] = []
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

    async def get_warehouse(self, project: str, name: str) -> Warehouse:
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/warehouses/{name}"
        )
        return Warehouse.model_validate(resp.json())

    async def refresh_warehouse(self, project: str, name: str) -> None:
        """
        Force immediate reconciliation of a Warehouse.
        """
        await self._request(
            "POST",
            f"/v1beta1/projects/{project}/warehouses/{name}/refresh",
        )

    # ---- Freight ----

    async def list_freight(self, project: str) -> List[FreightSummary]:
        resp = await self._request("GET", f"/v1beta1/projects/{project}/freight")
        data = resp.json()
        freight_items: list[FreightSummary] = []
        for item in data.get("items", []):
            freight = Freight.model_validate(item)
            freight_items.append(
                FreightSummary(
                    id=freight.metadata.name,
                    artifacts=freight.spec.artifacts,
                    per_stage=freight.status.stage_states if freight.status else [],
                )
            )
        return freight_items

    async def get_freight(self, project: str, freight_id: str) -> Freight:
        resp = await self._request(
            "GET", f"/v1beta1/projects/{project}/freight/{freight_id}"
        )
        return Freight.model_validate(resp.json())

    async def approve_freight(
        self,
        project: str,
        freight_id: str,
        stage: str,
        bearer_override: Optional[str] = None,
    ) -> Freight:
        """
        Approve freight for a specific stage. This should be protected by RBAC (`promote` verb).
        """
        path = f"/v1beta1/projects/{project}/freight/{freight_id}/approve"
        body = {"stage": stage}
        resp = await self._request("POST", path, bearer_override=bearer_override, json=body)
        return Freight.model_validate(resp.json())

    # ---- Promotions ----

    async def create_promotion(
        self,
        project: str,
        stage: str,
        freight_id: str,
        trigger_type: str = "manual",
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """
        Create a Promotion for a specific freight & stage.
        """
        path = f"/v1beta1/projects/{project}/stages/{stage}/promotions"
        body = {
            "freightId": freight_id,
            "triggerType": trigger_type,
        }
        resp = await self._request("POST", path, bearer_override=bearer_override, json=body)
        return Promotion.model_validate(resp.json())

    async def get_promotion(
        self, project: str, promotion_name: str
    ) -> Promotion:
        resp = await self._request(
            "GET",
            f"/v1beta1/projects/{project}/promotions/{promotion_name}",
        )
        return Promotion.model_validate(resp.json())

    async def list_promotions(self, project: str) -> List[PromotionSummary]:
        resp = await self._request("GET", f"/v1beta1/projects/{project}/promotions")
        data = resp.json()
        items: list[PromotionSummary] = []
        for item in data.get("items", []):
            p = Promotion.model_validate(item)
            items.append(
                PromotionSummary(
                    name=p.metadata.name,
                    stage=p.spec.stage,
                    freight_id=p.spec.freight_id,
                    state=p.status.state if p.status else "Unknown",
                    started_at=p.status.started_at if p.status else None,
                    finished_at=p.status.finished_at if p.status else None,
                )
            )
        return items

    async def abort_promotion(
        self,
        project: str,
        promotion_name: str,
        bearer_override: Optional[str] = None,
    ) -> Promotion:
        """
        Abort a running promotion.
        """
        path = f"/v1beta1/projects/{project}/promotions/{promotion_name}:abort"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        return Promotion.model_validate(resp.json())

    # ---- Verification ----

    async def reverify_stage(
        self, project: str, stage: str, bearer_override: Optional[str] = None
    ) -> Stage:
        """
        Trigger re-verification of current freight for a stage.

        Implement by mirroring the CLI's `kargo verify stage` call.
        """
        path = f"/v1beta1/projects/{project}/stages/{stage}:verify"
        resp = await self._request("POST", path, bearer_override=bearer_override)
        return Stage.model_validate(resp.json())


@asynccontextmanager
async def kargo_client_ctx(settings: KargoApiSettings) -> AsyncIterator[KargoApiClient]:
    client = KargoApiClient(settings)
    try:
        yield client
    finally:
        await client.close()
```

You’ll adjust the concrete REST paths to match your cluster / version (keep the structure; change the strings).

***

## server.py – MCP server wiring tools and resources

This uses the official Python SDK’s `FastMCP` with typed lifespan context so tools/resources can get a `KargoApiClient` instance. [dev](https://dev.to/m_sea_bass/practical-guide-to-mcp-model-context-protocol-in-python-ijd)

```python
# server.py
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from config import KargoApiSettings, AuthMode
from kargo_client import KargoApiClient
from kargo_models import (
    ProjectSummary,
    StageSummary,
    WarehouseSummary,
    FreightSummary,
    PromotionSummary,
    StageSpec,
)

# ---- Lifespan context ----

@dataclass
class AppContext:
    kargo: KargoApiClient
    settings: KargoApiSettings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Initialize shared resources for the MCP server:
    - Kargo API client
    - Configuration
    """
    settings = KargoApiSettings()  # loads from env
    from kargo_client import KargoApiClient

    kargo_client = KargoApiClient(settings)
    try:
        yield AppContext(kargo=kargo_client, settings=settings)
    finally:
        await kargo_client.close()


# Create FastMCP server instance
mcp = FastMCP(name="kargo-mcp-server", lifespan=app_lifespan)


# ---- Helper to get typed context ----

def _ctx(ctx: Context[ServerSession, AppContext]) -> AppContext:
    return ctx.request_context.lifespan_context


# ---- MCP Resources ----
# These map kargo:// URIs to Kargo API calls.

@mcp.resource("kargo://projects")
async def list_projects_resource(
    ctx: Context[ServerSession, AppContext],
) -> list[ProjectSummary]:
    """
    kargo://projects → list of project summaries
    """
    app = _ctx(ctx)
    return await app.kargo.list_projects()


@mcp.resource("kargo://projects/{project}/stages")
async def list_stages_resource(
    project: str,
    ctx: Context[ServerSession, AppContext],
) -> list[StageSummary]:
    """
    kargo://projects/{project}/stages → stage summaries
    """
    app = _ctx(ctx)
    return await app.kargo.list_stages(project)


@mcp.resource("kargo://projects/{project}/warehouses")
async def list_warehouses_resource(
    project: str,
    ctx: Context[ServerSession, AppContext],
) -> list[WarehouseSummary]:
    app = _ctx(ctx)
    return await app.kargo.list_warehouses(project)


@mcp.resource("kargo://projects/{project}/freight")
async def list_freight_resource(
    project: str,
    ctx: Context[ServerSession, AppContext],
) -> list[FreightSummary]:
    app = _ctx(ctx)
    return await app.kargo.list_freight(project)


@mcp.resource("kargo://projects/{project}/promotions")
async def list_promotions_resource(
    project: str,
    ctx: Context[ServerSession, AppContext],
) -> list[PromotionSummary]:
    app = _ctx(ctx)
    return await app.kargo.list_promotions(project)


# ---- MCP Tools: promotion execution ----

@mcp.tool()
async def promote_to_stage(
    project: str,
    stage: str,
    freight_id: str,
    ctx: Context[ServerSession, AppContext],
) -> PromotionSummary:
    """
    Create a Promotion to move a freight into a stage.

    - Respects auth mode; in PASSTHROUGH, you would forward the caller's token.
    """
    app = _ctx(ctx)

    # Example: in PASSTHROUGH mode, pull bearer from request metadata (you'll define how).
    bearer_override: Optional[str] = None
    if app.settings.auth_mode == AuthMode.PASSTHROUGH:
        # e.g. ctx.request_context.meta.get("authorization")
        bearer_override = None  # TODO: implement

    promotion = await app.kargo.create_promotion(
        project=project,
        stage=stage,
        freight_id=freight_id,
        trigger_type="manual",
        bearer_override=bearer_override,
    )
    return PromotionSummary(
        name=promotion.metadata.name,
        stage=promotion.spec.stage,
        freight_id=promotion.spec.freight_id,
        state=promotion.status.state if promotion.status else "Unknown",
        started_at=promotion.status.started_at if promotion.status else None,
        finished_at=promotion.status.finished_at if promotion.status else None,
    )


@mcp.tool()
async def approve_freight(
    project: str,
    freight_id: str,
    stage: str,
    ctx: Context[ServerSession, AppContext],
) -> FreightSummary:
    """
    Approve freight for a specific stage.

    - Kargo enforces RBAC (`promote` verb) based on bearer token.
    """
    app = _ctx(ctx)
    bearer_override: Optional[str] = None
    if app.settings.auth_mode == AuthMode.PASSTHROUGH:
        bearer_override = None  # TODO: extract from ctx.request_context.meta

    freight = await app.kargo.approve_freight(
        project=project,
        freight_id=freight_id,
        stage=stage,
        bearer_override=bearer_override,
    )
    return FreightSummary(
        id=freight.metadata.name,
        artifacts=freight.spec.artifacts,
        per_stage=freight.status.stage_states if freight.status else [],
    )


@mcp.tool()
async def abort_promotion(
    project: str,
    promotion_name: str,
    ctx: Context[ServerSession, AppContext],
) -> PromotionSummary:
    """
    Abort a running promotion.
    """
    app = _ctx(ctx)
    promotion = await app.kargo.abort_promotion(project, promotion_name)
    return PromotionSummary(
        name=promotion.metadata.name,
        stage=promotion.spec.stage,
        freight_id=promotion.spec.freight_id,
        state=promotion.status.state if promotion.status else "Unknown",
        started_at=promotion.status.started_at if promotion.status else None,
        finished_at=promotion.status.finished_at if promotion.status else None,
    )


@mcp.tool()
async def reverify_stage(
    project: str,
    stage: str,
    ctx: Context[ServerSession, AppContext],
) -> StageSummary:
    """
    Re-run verification of the current freight in a stage.
    """
    app = _ctx(ctx)
    updated_stage = await app.kargo.reverify_stage(project, stage)
    # Optionally derive summary here
    return StageSummary(
        name=updated_stage.metadata.name,
        upstream_stages=[],
        downstream_stages=[],
        current_freight_id=(
            updated_stage.status.current_freight_id
            if updated_stage.status
            else None
        ),
        auto_promotion_enabled=True,
    )


# ---- MCP Tools: lifecycle & discovery ----

@mcp.tool()
async def refresh_warehouse(
    project: str,
    warehouse: str,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """
    Force a Warehouse to refresh artifacts.
    """
    app = _ctx(ctx)
    await app.kargo.refresh_warehouse(project, warehouse)
    return f"Warehouse {warehouse!r} in project {project!r} scheduled for refresh."


@mcp.tool()
async def list_projects(
    ctx: Context[ServerSession, AppContext],
) -> list[ProjectSummary]:
    """
    Convenience tool version of kargo://projects.
    """
    app = _ctx(ctx)
    return await app.kargo.list_projects()


@mcp.tool()
async def list_stages(
    project: str,
    ctx: Context[ServerSession, AppContext],
) -> list[StageSummary]:
    app = _ctx(ctx)
    return await app.kargo.list_stages(project)


# ---- MCP Tools: stage/spec management with Pydantic input ----

class UpsertStageInput(BaseModel):
    project: str
    stage: str
    spec: StageSpec


from pydantic import BaseModel  # keep this import near class if you prefer


@mcp.tool()
async def upsert_stage(
    args: UpsertStageInput,
    ctx: Context[ServerSession, AppContext],
) -> StageSummary:
    """
    Create or update a Stage using a typed Pydantic payload.

    This makes the tool schema explicit to the model.
    """
    app = _ctx(ctx)
    stage = await app.kargo.upsert_stage(
        project=args.project,
        stage=args.stage,
        spec=args.spec,
    )
    return StageSummary(
        name=stage.metadata.name,
        upstream_stages=[],   # optional: recompute DAG
        downstream_stages=[],
        current_freight_id=(
            stage.status.current_freight_id if stage.status else None
        ),
        auto_promotion_enabled=True,
    )


# ---- Entry point ----

if __name__ == "__main__":
    # stdio is the default transport for most editors / Claude Desktop
    mcp.run(transport="stdio")
```

***

## How to use this skeleton

- Your team can now:
  - Fill in **exact REST paths** for login, verify, abort, etc., by looking at your Kargo API docs / generated clients and adjusting the strings in `KargoApiClient` while keeping function signatures stable. [main.docs.kargo](https://main.docs.kargo.io/api-documentation/)
  - Add/remove fields on the Pydantic models to match the actual JSON payloads from your `/v1beta1` endpoints. [burrell](https://burrell.tech/blog/kargo-v1-9/)
  - Implement **PASSTHROUGH** auth by deciding how caller tokens are propagated into `ctx.request_context.meta` and then forwarded to Kargo. [docs.kargo](https://docs.kargo.io/user-guide/security/access-controls/)
  - Extend with more tools (e.g., `get_promotion_logs`, `describe_topology`) that call into the same `KargoApiClient`.

Structurally, though, this gives you the end‑to‑end wiring: FastMCP server → typed MCP tools/resources → Pydantic models → Kargo REST client with clear separation of concerns and enough internal logic (auth, DAG guardrail, summaries) to serve as a solid implementation reference. [github](https://github.com/modelcontextprotocol/python-sdk)
