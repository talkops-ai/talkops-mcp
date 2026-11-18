"""Kargo promotion, rollback, approval, refresh, and freight management tools (Toolset: promotion)."""

from typing import Any, Dict, List, Literal, Optional
import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from kargo_mcp_server.exceptions.custom import (
    KargoPromotionError,
    KargoValidationError,
)
from kargo_mcp_server.models.freight import Freight
from kargo_mcp_server.models.schemas import ExecutionResult, FreightQueryReport
from kargo_mcp_server.models.stage import Stage
from kargo_mcp_server.tools.base import BaseTool, confirm_destructive_action


class PromotionTools(BaseTool):
    """Tools for querying Freight, promoting to Stages/downstream, rolling back, approving, and refreshing."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register promotion tools with FastMCP."""

        # 1. Read-only Freight query tool
        if self.should_register("promotion", is_write=False):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Query Kargo Freight",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def kargo_query_freight(
                project: str = Field(..., min_length=1, description="Kargo project name."),
                stage: Optional[str] = Field(
                    default=None,
                    description="Optional Stage name to filter Freight available or verified for that stage.",
                ),
                warehouse: Optional[str] = Field(
                    default=None,
                    description="Optional origin Warehouse name filter.",
                ),
                freight_or_alias: Optional[str] = Field(
                    default=None,
                    description="Optional exact Freight SHA-1 name or alias to inspect.",
                ),
                available_only: bool = Field(
                    default=False,
                    description="When stage is specified, pass stage filter to Kargo QueryFreight API to return promotable Freight.",
                ),
                order_by: Optional[Literal["first_seen", "tag"]] = Field(
                    default=None,
                    description="Sort order ('first_seen' or 'tag').",
                ),
                limit: int = Field(
                    default=20,
                    ge=1,
                    le=100,
                    description="Maximum number of Freight summaries to return.",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> FreightQueryReport:
                """Query and filter Kargo Freight bundles in a project by stage availability, origin Warehouse, or alias.

                Returns concise Freight summaries including SHA-1 id, alias, origin Warehouse,
                artifact versions (Git commits, container images, Helm charts), and stage states.
                """
                try:
                    if freight_or_alias:
                        raw = await self.kargo_service.get_freight(project, freight_or_alias)
                        f_obj = Freight.model_validate(raw)
                        summary_item = f_obj.to_summary().model_dump()
                        return FreightQueryReport(
                            project=project,
                            total=1,
                            summary=f"Retrieved Freight '{f_obj.get_alias() or f_obj.metadata.name}' from origin '{f_obj.get_origin_name()}'.",
                            stage_filter=stage,
                            warehouse_filter=warehouse,
                            items=[summary_item],
                            resource_uri=f"kargo://projects/{project}/freight/{f_obj.metadata.name}",
                        )

                    origins = [warehouse] if warehouse else None
                    stage_param = stage if (stage and available_only) else None
                    summaries = await self.kargo_service.list_freight(
                        project=project,
                        stage=stage_param,
                        origins=origins,
                        order_by=order_by,
                        reverse=True,
                    )

                    if stage and not available_only:
                        summaries = [
                            s
                            for s in summaries
                            if (
                                stage in s.currently_in
                                or stage in s.verified_in
                                or stage in s.approved_for
                            )
                        ] or summaries

                    if warehouse:
                        summaries = [
                            s for s in summaries if not s.origin or s.origin == warehouse
                        ]

                    sliced = [s.model_dump() for s in summaries[:limit]]
                    return FreightQueryReport(
                        project=project,
                        total=len(summaries),
                        summary=f"Found {len(summaries)} Freight item(s) in project '{project}' (showing {len(sliced)}).",
                        stage_filter=stage,
                        warehouse_filter=warehouse,
                        items=sliced,
                        resource_uri=f"kargo://projects/{project}/pipeline",
                    )
                except Exception as exc:
                    self.handle_error(
                        exc,
                        "kargo_query_freight",
                        project=project,
                        resource_name=freight_or_alias or stage or warehouse,
                    )
                    raise

        # 2. Write tools in 'promotion' toolset
        if not self.should_register("promotion", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Refresh Kargo Resource",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_refresh(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            kind: Literal[
                "warehouse",
                "stage",
                "promotion",
                "project_config",
                "cluster_config",
            ] = Field(..., description="Resource type to refresh."),
            name: Optional[str] = Field(
                default=None,
                description="Resource name (required for warehouse, stage, and promotion).",
            ),
            wait: bool = Field(
                default=False,
                description="When kind='warehouse', read back Warehouse status after refresh to report discovered artifacts and lastFreightID.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Trigger immediate reconciliation or artifact discovery on a Warehouse, Stage, Promotion, ProjectConfig, or ClusterConfig."""
            self.check_write_access("kargo_refresh")

            try:
                if kind in ("warehouse", "stage", "promotion") and not name:
                    raise KargoValidationError(
                        f"Parameter 'name' is required when refreshing kind='{kind}'."
                    )

                details: Dict[str, Any] = {"project": project, "kind": kind, "name": name or project}
                resource_uri = f"kargo://projects/{project}/pipeline"

                if kind == "warehouse" and name:
                    await self.kargo_service.refresh_warehouse(project, name)
                    resource_uri = f"kargo://projects/{project}/warehouses/{name}"
                    if wait:
                        wh_raw = await self.kargo_service.get_warehouse(project, name)
                        status = (wh_raw.get("status") or {}) if isinstance(wh_raw, dict) else {}
                        details["last_freight_id"] = status.get("lastFreightID")
                        details["last_handled_refresh"] = status.get("lastHandledRefresh")
                elif kind == "stage" and name:
                    await self.kargo_service.refresh_stage(project, name)
                    resource_uri = f"kargo://projects/{project}/stages/{name}"
                elif kind == "promotion" and name:
                    await self.kargo_service.refresh_promotion(project, name)
                    resource_uri = f"kargo://projects/{project}/promotions/{name}"
                elif kind == "project_config":
                    await self.kargo_service.refresh_project_config(project)
                    resource_uri = f"kargo://projects/{project}"
                elif kind == "cluster_config":
                    await self.kargo_service.refresh_cluster_config()
                    resource_uri = "kargo://server/capabilities"

                return ExecutionResult(
                    status="success",
                    summary=f"Triggered refresh for {kind} '{name or project}' in project '{project}'.",
                    dry_run=False,
                    resource_uri=resource_uri,
                    details=details,
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_refresh", project=project, resource_name=name or project
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Promote Kargo Freight",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_promote(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            stage: str = Field(
                ...,
                min_length=1,
                description="Target Stage name (or source Stage name when downstream=True).",
            ),
            freight: Optional[str] = Field(
                default=None,
                description="Freight SHA-1 name to promote.",
            ),
            freight_alias: Optional[str] = Field(
                default=None,
                description="Freight human-friendly alias to promote (alternative to freight).",
            ),
            origin_warehouse: Optional[str] = Field(
                default=None,
                description="Origin Warehouse name to promote the current auto-promotion candidate and clear any auto-promotion hold (Kargo v1.11+).",
            ),
            downstream: bool = Field(
                default=False,
                description="Set True to promote Freight to all Stages immediately downstream of 'stage'.",
            ),
            dry_run: bool = Field(
                default=False,
                description="Set True to preview the Promotion Plan (current vs target freight, steps, verification) without executing.",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm multi-stage downstream fan-out promotion when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Promote Freight to a Stage (by SHA-1 name, alias, or origin Warehouse) or to all immediate downstream Stages.

            Uses Kargo's native PromoteToStage / PromoteDownstream REST endpoints so Kargo
            inflates PromotionTask/ClusterPromotionTask steps and generates unique Promotion names.
            """
            self.check_write_access("kargo_promote")
            resource_uri = f"kargo://projects/{project}/stages/{stage}"

            try:
                if not (freight or freight_alias or origin_warehouse):
                    raise KargoValidationError(
                        "Provide one of 'freight', 'freight_alias', or 'origin_warehouse' to promote."
                    )

                target_ref = freight or freight_alias or f"Warehouse/{origin_warehouse}"

                if dry_run:
                    stg_raw = await self.kargo_service.get_stage(project, stage)
                    stg = Stage.model_validate(stg_raw)
                    steps = (
                        (stg.spec.promotion_template or {})
                        .get("spec", {})
                        .get("steps", [])
                    )
                    ver_templates = (
                        (stg.spec.verification or {}).get("analysisTemplates", [])
                    )
                    plan_dict = {
                        "project": project,
                        "stage": stage,
                        "mode": "downstream_fanout" if downstream else "single_stage",
                        "current_freight": stg.get_current_freight_id(),
                        "target": target_ref,
                        "promotion_steps": steps,
                        "verification_templates": ver_templates,
                    }
                    return ExecutionResult(
                        status="preview",
                        summary=(
                            f"Previewed Promotion Plan for '{target_ref}' -> Stage '{stage}' "
                            f"({'downstream fan-out' if downstream else 'single stage'}). Re-run with dry_run=False to execute."
                        ),
                        dry_run=True,
                        manifest=yaml.dump(plan_dict, default_flow_style=False),
                        resource_uri=resource_uri,
                        details={
                            "project": project,
                            "stage": stage,
                            "target": target_ref,
                            "downstream": downstream,
                            "steps_count": len(steps),
                        },
                    )

                if downstream:
                    if not await confirm_destructive_action(
                        ctx,
                        action_summary=(
                            f"Promote Freight '{target_ref}' to ALL stages immediately downstream of '{stage}' in project '{project}'"
                        ),
                        confirm=confirm,
                        resource_uri=resource_uri,
                        details={"project": project, "stage": stage, "target": target_ref},
                    ):
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to fan out Freight '{target_ref}' to all stages downstream of '{stage}'. "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            resource_uri=resource_uri,
                            details={
                                "project": project,
                                "stage": stage,
                                "target": target_ref,
                                "requires_confirmation": True,
                            },
                        )

                    promos = await self.kargo_service.promote_downstream(
                        project=project,
                        stage=stage,
                        freight=freight,
                        freight_alias=freight_alias,
                    )
                    promo_names = [p.metadata.name for p in promos]
                    return ExecutionResult(
                        status="success",
                        summary=f"Created {len(promos)} downstream Promotion(s) from Stage '{stage}': {promo_names}.",
                        dry_run=False,
                        resource_uri=f"kargo://projects/{project}/promotions",
                        details={
                            "project": project,
                            "source_stage": stage,
                            "promotions": promo_names,
                            "count": len(promos),
                        },
                    )

                promo = await self.kargo_service.promote_to_stage(
                    project=project,
                    stage=stage,
                    freight=freight,
                    freight_alias=freight_alias,
                    origin_warehouse=origin_warehouse,
                )
                return ExecutionResult(
                    status="success",
                    summary=(
                        f"Created Promotion '{promo.metadata.name}' for Stage '{stage}' "
                        f"(freight='{promo.spec.freight or target_ref}', phase='{promo.get_phase()}')."
                    ),
                    dry_run=False,
                    resource_uri=f"kargo://projects/{project}/promotions/{promo.metadata.name}",
                    details={
                        "name": promo.metadata.name,
                        "project": project,
                        "stage": promo.spec.stage,
                        "freight": promo.spec.freight or target_ref,
                        "phase": promo.get_phase(),
                    },
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_promote", project=project, resource_name=stage
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Rollback Kargo Stage",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_rollback_stage(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            stage: str = Field(..., min_length=1, description="Stage name to roll back."),
            target_freight: Optional[str] = Field(
                default=None,
                description=(
                    "Optional Freight SHA-1 name or alias to roll back to. When omitted, "
                    "automatically selects the most recent previous verified Freight from Stage status.freightHistory."
                ),
            ),
            abort_running_promotion: bool = Field(
                default=True,
                description="Automatically abort any in-progress Promotion on the Stage before rolling back.",
            ),
            dry_run: bool = Field(
                default=False,
                description="Preview the rollback plan (current vs target freight, active promotion abort) without executing.",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm Stage rollback when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Roll back a Kargo Stage to a previous known-good Freight using Kargo's roll-forward promotion model (N-to-1).

            Automatically resolves the last verified Freight from status.freightHistory when
            target_freight is omitted, optionally aborts any stuck promotion, triggers the rollback
            Promotion, and warns about the Kargo v1.11+ auto-promotion hold behavior.
            """
            self.check_write_access("kargo_rollback_stage")
            resource_uri = f"kargo://projects/{project}/stages/{stage}"

            try:
                stg_raw = await self.kargo_service.get_stage(project, stage)
                stg = Stage.model_validate(stg_raw)
                current_freight = stg.get_current_freight_id()
                resolved_target = target_freight or stg.get_previous_verified_freight_id()

                if not resolved_target:
                    raise KargoPromotionError(
                        f"Could not automatically resolve a previous verified Freight in Stage '{stage}' status.freightHistory. "
                        "Specify 'target_freight' explicitly after calling kargo_query_freight."
                    )

                active_promo_name: Optional[str] = None
                if stg.status and isinstance(stg.status.current_promotion, dict):
                    active_promo_name = stg.status.current_promotion.get("name")

                hold_warning = (
                    "In Kargo v1.11+, rolling back a Stage establishes an auto-promotion hold. "
                    "When ready to resume auto-promotion, call kargo_promote with origin_warehouse='<warehouse>'."
                )

                plan_details = {
                    "project": project,
                    "stage": stage,
                    "current_freight": current_freight,
                    "target_freight": resolved_target,
                    "active_promotion_to_abort": active_promo_name if abort_running_promotion else None,
                }

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=(
                            f"Previewed rollback of Stage '{stage}' from '{current_freight or 'none'}' "
                            f"to '{resolved_target}'. Re-run with dry_run=False to execute."
                        ),
                        dry_run=True,
                        manifest=yaml.dump(plan_details, default_flow_style=False),
                        resource_uri=resource_uri,
                        warnings=[hold_warning],
                        details=plan_details,
                    )

                if not await confirm_destructive_action(
                    ctx,
                    action_summary=(
                        f"Roll back Stage '{stage}' in project '{project}' from '{current_freight or 'none'}' to Freight '{resolved_target}'"
                    ),
                    confirm=confirm,
                    resource_uri=resource_uri,
                    details=plan_details,
                ):
                    return ExecutionResult(
                        status="cancelled",
                        summary=(
                            f"Confirmation required to roll back Stage '{stage}' to Freight '{resolved_target}'. "
                            "Re-run with confirm=True after user approval."
                        ),
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={**plan_details, "requires_confirmation": True},
                    )

                aborted_promo: Optional[str] = None
                if abort_running_promotion and active_promo_name:
                    await self.kargo_service.abort_promotion(project, active_promo_name)
                    aborted_promo = active_promo_name

                promo = await self.kargo_service.promote_to_stage(
                    project=project,
                    stage=stage,
                    freight=resolved_target,
                )

                return ExecutionResult(
                    status="success",
                    summary=(
                        f"Initiated rollback Promotion '{promo.metadata.name}' on Stage '{stage}' "
                        f"to Freight '{resolved_target}'."
                    ),
                    dry_run=False,
                    resource_uri=f"kargo://projects/{project}/promotions/{promo.metadata.name}",
                    warnings=[hold_warning],
                    details={
                        **plan_details,
                        "aborted_promotion": aborted_promo,
                        "promotion_name": promo.metadata.name,
                        "phase": promo.get_phase(),
                    },
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_rollback_stage", project=project, resource_name=stage
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Approve Kargo Freight for Stage",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_approve_freight(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            freight_or_alias: str = Field(
                ..., min_length=1, description="Freight SHA-1 name or alias to approve."
            ),
            stage: str = Field(
                ..., min_length=1, description="Target Stage name to approve the Freight for."
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm manual approval (which bypasses upstream verification gates) when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Manually approve a Freight bundle (by SHA-1 name or alias) for promotion to a target Stage."""
            self.check_write_access("kargo_approve_freight")
            resource_uri = f"kargo://projects/{project}/freight/{freight_or_alias}"

            try:
                if not await confirm_destructive_action(
                    ctx,
                    action_summary=(
                        f"Approve Freight '{freight_or_alias}' for Stage '{stage}' in project '{project}' (bypasses upstream requirements)"
                    ),
                    confirm=confirm,
                    resource_uri=resource_uri,
                    details={"project": project, "freight": freight_or_alias, "stage": stage},
                ):
                    return ExecutionResult(
                        status="cancelled",
                        summary=(
                            f"Confirmation required to approve Freight '{freight_or_alias}' for Stage '{stage}'. "
                            "Re-run with confirm=True after user approval."
                        ),
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={
                            "project": project,
                            "freight": freight_or_alias,
                            "stage": stage,
                            "requires_confirmation": True,
                        },
                    )

                approved = await self.kargo_service.approve_freight(
                    project=project,
                    freight_id=freight_or_alias,
                    stage=stage,
                )
                summary_obj = approved.to_summary()
                return ExecutionResult(
                    status="success",
                    summary=f"Approved Freight '{approved.metadata.name}' for Stage '{stage}' in project '{project}'.",
                    dry_run=False,
                    resource_uri=f"kargo://projects/{project}/freight/{approved.metadata.name}",
                    details={
                        "id": approved.metadata.name,
                        "alias": summary_obj.alias,
                        "stage": stage,
                        "approved_for": summary_obj.approved_for,
                    },
                )
            except Exception as exc:
                self.handle_error(
                    exc,
                    "kargo_approve_freight",
                    project=project,
                    resource_name=freight_or_alias,
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Kargo Promotion Lifecycle",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_manage_promotion(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            promotion: str = Field(..., min_length=1, description="Promotion resource name."),
            action: Literal["abort", "refresh"] = Field(
                ..., description="Lifecycle action: 'abort' (terminate running promotion) or 'refresh' (wake)."
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm aborting the Promotion when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Abort a running/pending Kargo Promotion or refresh (wake) a waiting Promotion."""
            self.check_write_access("kargo_manage_promotion")
            resource_uri = f"kargo://projects/{project}/promotions/{promotion}"

            try:
                if action == "abort":
                    if not await confirm_destructive_action(
                        ctx,
                        action_summary=f"Abort Promotion '{promotion}' in project '{project}'",
                        confirm=confirm,
                        resource_uri=resource_uri,
                        details={"project": project, "promotion": promotion, "action": "abort"},
                    ):
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to abort Promotion '{promotion}'. "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            resource_uri=resource_uri,
                            details={
                                "project": project,
                                "promotion": promotion,
                                "action": "abort",
                                "requires_confirmation": True,
                            },
                        )

                    aborted = await self.kargo_service.abort_promotion(project, promotion)
                    return ExecutionResult(
                        status="success",
                        summary=f"Aborted Promotion '{promotion}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={
                            "name": aborted.metadata.name,
                            "stage": aborted.spec.stage,
                            "freight": aborted.spec.freight,
                            "phase": aborted.get_phase(),
                        },
                    )

                # action == "refresh"
                await self.kargo_service.refresh_promotion(project, promotion)
                return ExecutionResult(
                    status="success",
                    summary=f"Refreshed Promotion '{promotion}' in project '{project}'.",
                    dry_run=False,
                    resource_uri=resource_uri,
                    details={"project": project, "promotion": promotion, "action": "refresh"},
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_manage_promotion", project=project, resource_name=promotion
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Kargo Freight Metadata & Lifecycle",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_manage_freight(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            action: Literal["set_alias", "update_alias", "delete", "create"] = Field(
                ...,
                description="Action: 'set_alias' (rename alias), 'delete' (remove Freight), or 'create' (manual Freight assembly).",
            ),
            freight_or_alias: Optional[str] = Field(
                default=None,
                description="Target Freight SHA-1 name or current alias (required for set_alias and delete).",
            ),
            new_alias: Optional[str] = Field(
                default=None,
                description="New human-friendly alias (required for set_alias; optional for create).",
            ),
            warehouse: Optional[str] = Field(
                default=None,
                description="Origin Warehouse name (required for action='create').",
            ),
            artifacts: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Artifact references dict ({'images': [...], 'commits': [...], 'charts': [...]}) for action='create'.",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm Freight deletion when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Update a Freight human-friendly alias, manually assemble a Freight item, or delete unused Freight."""
            self.check_write_access("kargo_manage_freight")

            try:
                if action in ("set_alias", "update_alias"):
                    if not freight_or_alias or not new_alias:
                        raise KargoValidationError(
                            "Both 'freight_or_alias' and 'new_alias' are required for action='set_alias'."
                        )
                    await self.kargo_service.update_freight_alias(
                        project, freight_or_alias, new_alias
                    )
                    return ExecutionResult(
                        status="success",
                        summary=f"Updated alias on Freight '{freight_or_alias}' to '{new_alias}'.",
                        dry_run=False,
                        resource_uri=f"kargo://projects/{project}/freight/{new_alias}",
                        details={
                            "project": project,
                            "freight": freight_or_alias,
                            "new_alias": new_alias,
                        },
                    )

                if action == "delete":
                    if not freight_or_alias:
                        raise KargoValidationError(
                            "'freight_or_alias' is required for action='delete'."
                        )
                    resource_uri = f"kargo://projects/{project}/freight/{freight_or_alias}"
                    if not await confirm_destructive_action(
                        ctx,
                        action_summary=f"Delete Freight '{freight_or_alias}' in project '{project}'",
                        confirm=confirm,
                        resource_uri=resource_uri,
                        details={"project": project, "freight": freight_or_alias},
                    ):
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to delete Freight '{freight_or_alias}'. "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            resource_uri=resource_uri,
                            details={
                                "project": project,
                                "freight": freight_or_alias,
                                "requires_confirmation": True,
                            },
                        )
                    await self.kargo_service.delete_freight(project, freight_or_alias)
                    return ExecutionResult(
                        status="success",
                        summary=f"Deleted Freight '{freight_or_alias}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=f"kargo://projects/{project}/pipeline",
                        details={"project": project, "freight": freight_or_alias},
                    )

                # action == "create"
                if not warehouse or not artifacts:
                    raise KargoValidationError(
                        "Both 'warehouse' and 'artifacts' are required for action='create'."
                    )
                created = await self.kargo_service.create_freight(
                    project=project,
                    warehouse=warehouse,
                    artifacts=artifacts,
                    alias=new_alias,
                )
                fid = (created.get("metadata") or {}).get("name", "manual-freight")
                return ExecutionResult(
                    status="success",
                    summary=f"Created Freight '{fid}' for Warehouse '{warehouse}' in project '{project}'.",
                    dry_run=False,
                    resource_uri=f"kargo://projects/{project}/freight/{fid}",
                    details={"project": project, "id": fid, "warehouse": warehouse, "alias": new_alias},
                )
            except Exception as exc:
                self.handle_error(
                    exc,
                    "kargo_manage_freight",
                    project=project,
                    resource_name=freight_or_alias or warehouse,
                )
                raise
