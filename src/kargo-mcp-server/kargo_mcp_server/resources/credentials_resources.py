"""Kargo credentials resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class CredentialsResources(BaseResource):
    """Credentials-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects/{project}/credentials",
            name="kargo_project_credentials",
            description="List all repository credentials in a Kargo project",
            mime_type="application/json",
        )
        async def list_credentials_resource(project: str) -> str:
            """List all repository credentials in a project."""
            try:
                creds = await self.kargo_service.list_repo_credentials(project)
                if not creds:
                    return json.dumps({
                        "message": (
                            f"No repository credentials found in project '{project}'. "
                            "Next step: Use 'kargo_credentials_mgmt' with action "
                            "'create' to add Git or image registry credentials."
                        )
                    })
                # Redact sensitive fields before returning
                redacted = []
                for cred in creds:
                    entry = {
                        "name": cred.get("metadata", {}).get("name", ""),
                        "type": cred.get("type", ""),
                        "repoURL": cred.get("repoURL", ""),
                        "username": cred.get("username", ""),
                        # Never expose passwords in resource listings
                        "hasPassword": bool(cred.get("password")),
                    }
                    redacted.append(entry)
                return json.dumps(redacted, default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list credentials: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project}/credentials/{cred_name}",
            name="kargo_credential_detail",
            description="Get detailed repository credential information (passwords are redacted)",
            mime_type="text/markdown",
        )
        async def get_credential_resource(project: str, cred_name: str) -> str:
            """Get detailed credential information (password redacted)."""
            try:
                cred = await self.kargo_service.get_repo_credentials(project, cred_name)

                details = {
                    "name": cred_name,
                    "project": project,
                    "type": cred.get("type", ""),
                    "repoURL": cred.get("repoURL", ""),
                    "username": cred.get("username", ""),
                    "hasPassword": bool(cred.get("password")),
                }

                # Redact password from the YAML manifest
                safe_cred = dict(cred)
                if "password" in safe_cred:
                    safe_cred["password"] = "***REDACTED***"

                yaml_manifest = yaml.dump(
                    safe_cred,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## Credential Details: {cred_name}",
                    "",
                    "```json",
                    json.dumps(details, indent=2, default=str),
                    "```",
                    "",
                    "## Full YAML Manifest (password redacted)",
                    "",
                    "```yaml",
                    yaml_manifest.rstrip(),
                    "```",
                ]
                return "\n".join(output_parts)
            except Exception as e:
                raise KargoResourceError(f"Failed to get credential: {e}")
