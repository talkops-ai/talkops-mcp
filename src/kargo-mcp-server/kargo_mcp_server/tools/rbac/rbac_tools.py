"""Kargo RBAC role, OIDC claim mapping, and permission grant/revocation tools (Toolset: rbac)."""

from typing import Any, Dict, List, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from kargo_mcp_server.exceptions.custom import KargoValidationError
from kargo_mcp_server.models.schemas import ExecutionResult
from kargo_mcp_server.tools.base import BaseTool, confirm_destructive_action


class RbacTools(BaseTool):
    """Tools for managing Kargo Roles, OIDC claim bindings, and resource permissions."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register RBAC tools with FastMCP."""
        if not self.should_register("rbac", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Kargo RBAC Roles & Grants",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_manage_roles(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            action: Literal["create", "delete", "grant", "revoke"] = Field(
                ...,
                description="Action: 'create', 'delete', 'grant' (claims or permissions), or 'revoke'.",
            ),
            role: str = Field(..., min_length=1, description="Kargo Role name (e.g. 'release-engineer')."),
            claims: Optional[Dict[str, List[str]]] = Field(
                default=None,
                description="OIDC claim mappings as {'email': ['alice@example.com'], 'groups': ['sre']}.",
            ),
            permissions: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "Resource permissions to grant/revoke, e.g. "
                    "[{'resourceType': 'stages', 'resourceName': 'prod', 'verbs': ['promote']}]"
                ),
            ),
            description: Optional[str] = Field(
                default=None,
                description="Optional description when creating a Kargo Role.",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm role deletion or permission revocation when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create or delete a managed Kargo Role, or grant/revoke OIDC user claims and stage permissions."""
            self.check_write_access("kargo_manage_roles")
            resource_uri = f"kargo://projects/{project}/roles"

            try:
                if action == "create":
                    await self.kargo_service.create_role(
                        project=project,
                        role=role,
                        claims=claims,
                        rules=permissions,
                        description=description,
                    )
                    return ExecutionResult(
                        status="success",
                        summary=f"Created Kargo Role '{role}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={"project": project, "role": role, "action": "create"},
                    )

                if action == "grant":
                    if not claims and not permissions:
                        raise KargoValidationError(
                            "Provide 'claims' and/or 'permissions' when action='grant'."
                        )
                    await self.kargo_service.grant_role(
                        project=project,
                        role=role,
                        claims=claims,
                        permissions=permissions,
                    )
                    return ExecutionResult(
                        status="success",
                        summary=f"Granted claims/permissions to Kargo Role '{role}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={"project": project, "role": role, "action": "grant"},
                    )

                if action in ("delete", "revoke"):
                    if action == "revoke" and not claims and not permissions:
                        raise KargoValidationError(
                            "Provide 'claims' and/or 'permissions' when action='revoke'."
                        )
                    if not await confirm_destructive_action(
                        ctx,
                        action_summary=f"{action.capitalize()} Kargo Role '{role}' in project '{project}'",
                        confirm=confirm,
                        resource_uri=resource_uri,
                        details={"project": project, "role": role, "action": action},
                    ):
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to {action} Kargo Role '{role}' in project '{project}'. "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            resource_uri=resource_uri,
                            details={
                                "project": project,
                                "role": role,
                                "action": action,
                                "requires_confirmation": True,
                            },
                        )

                    if action == "delete":
                        await self.kargo_service.delete_role(project, role)
                    else:
                        await self.kargo_service.revoke_role(
                            project=project,
                            role=role,
                            claims=claims,
                            permissions=permissions,
                        )
                    return ExecutionResult(
                        status="success",
                        summary=f"Executed '{action}' on Kargo Role '{role}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={"project": project, "role": role, "action": action},
                    )

                raise KargoValidationError(f"Unsupported role action: {action}")
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_manage_roles", project=project, resource_name=role
                )
                raise
