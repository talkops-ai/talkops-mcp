"""Kargo credentials and ConfigMap management tools (Toolset: credentials).

Enforces the 0->1 secret omission rule: tool parameters NEVER accept raw passwords,
tokens, or private keys. Secret material is resolved strictly from server-side
environment variables or mounted credential files via symbolic ``secret_ref``.
"""

from typing import Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from kargo_mcp_server.exceptions.custom import KargoValidationError
from kargo_mcp_server.models.schemas import CredentialOptions, ExecutionResult
from kargo_mcp_server.tools.base import BaseTool, confirm_destructive_action


class CredentialsTools(BaseTool):
    """Tools for managing Kargo repository credentials, generic credentials, and ConfigMaps."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register credential tools with FastMCP."""
        if not self.should_register("credentials", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Kargo Credentials & ConfigMaps",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_manage_credentials(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            action: Literal["create", "update", "delete"] = Field(
                ..., description="Operation to perform: 'create', 'update', or 'delete'."
            ),
            name: str = Field(..., min_length=1, description="Credential or ConfigMap resource name."),
            credential: Optional[CredentialOptions] = Field(
                default=None,
                description=(
                    "Credential options (kind: 'repo'|'generic'|'configmap', cred_type: 'git'|'helm'|'image', "
                    "repo_url, repo_url_is_regex, secret_ref, data_keys, config_data, replicate_to_all_projects). "
                    "Never pass raw secret values."
                ),
            ),
            scope: Literal["project", "shared", "system"] = Field(
                default="project",
                description="Namespace scope ('project', 'shared' for kargo-shared-resources, or 'system').",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm credential deletion when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create, update, or delete Kargo repository credentials, generic secrets, or ConfigMaps without exposing secret values."""
            self.check_write_access("kargo_manage_credentials")
            resource_uri = f"kargo://projects/{project}/credentials"

            try:
                opts = (
                    credential
                    if isinstance(credential, CredentialOptions)
                    else (
                        CredentialOptions.model_validate(credential)
                        if isinstance(credential, dict)
                        else CredentialOptions()
                    )
                )

                if action == "delete":
                    if not await confirm_destructive_action(
                        ctx,
                        action_summary=(
                            f"Delete {opts.kind} credential '{name}' (scope={scope}) in project '{project}'"
                        ),
                        confirm=confirm,
                        resource_uri=resource_uri,
                        details={"project": project, "name": name, "kind": opts.kind, "scope": scope},
                    ):
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to delete {opts.kind} credential '{name}' (scope={scope}). "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            resource_uri=resource_uri,
                            details={
                                "project": project,
                                "name": name,
                                "kind": opts.kind,
                                "scope": scope,
                                "requires_confirmation": True,
                            },
                        )

                    await self.kargo_service.delete_credentials(
                        project=project,
                        name=name,
                        kind=opts.kind,
                        scope=scope,
                    )
                    return ExecutionResult(
                        status="success",
                        summary=f"Deleted {opts.kind} credential '{name}' (scope={scope}).",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={"project": project, "name": name, "kind": opts.kind, "scope": scope},
                    )

                if credential is None:
                    raise KargoValidationError(
                        f"Parameter 'credential' is required when action='{action}'."
                    )

                await self.kargo_service.create_or_update_credentials(
                    project=project,
                    name=name,
                    options=opts,
                    scope=scope,
                    is_update=(action == "update"),
                )
                return ExecutionResult(
                    status="success",
                    summary=f"{'Updated' if action == 'update' else 'Created'} {opts.kind} credential '{name}' (scope={scope}).",
                    dry_run=False,
                    resource_uri=resource_uri,
                    details={
                        "project": project,
                        "name": name,
                        "kind": opts.kind,
                        "cred_type": opts.cred_type,
                        "scope": scope,
                        "secret_ref": opts.secret_ref or "default",
                    },
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_manage_credentials", project=project, resource_name=name
                )
                raise
