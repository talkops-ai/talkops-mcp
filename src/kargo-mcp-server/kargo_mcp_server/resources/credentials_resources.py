"""Kargo credentials and ConfigMaps resource (secrets strictly redacted)."""

import json
from typing import Any, Dict, List

from kargo_mcp_server.resources.base import BaseResource


class CredentialsResources(BaseResource):
    """Redacted repository credentials, generic credentials, and ConfigMaps MCP resource."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/credentials",
            name="kargo_project_credentials",
            description="Redacted repository credentials, generic credentials, and ConfigMaps in a Kargo project (secret values are never exposed)",
            mime_type="application/json",
        )
        async def list_credentials_resource(project: str) -> str:
            """List all credentials in a project with secret values strictly redacted."""
            try:
                repo_creds = await self.kargo_service.list_repo_credentials(
                    project, scope="project"
                )
                generic_creds: List[Dict[str, Any]] = []
                try:
                    generic_creds = await self.kargo_service.list_generic_credentials(
                        project, scope="project"
                    )
                except Exception:
                    pass

                def _format_repo(cred: Dict[str, Any]) -> Dict[str, Any]:
                    meta = cred.get("metadata") or {}
                    data = cred.get("data") or cred.get("stringData") or {}
                    labels = meta.get("labels") or {}
                    return {
                        "name": meta.get("name") or cred.get("name", ""),
                        "type": (
                            cred.get("type")
                            or labels.get("kargo.akuity.io/cred-type")
                            or data.get("type", "git")
                        ),
                        "repoURL": (
                            cred.get("repoURL")
                            or cred.get("repoUrl")
                            or data.get("repoURL", "")
                        ),
                        "repoURLIsRegex": bool(
                            cred.get("repoURLIsRegex")
                            or cred.get("repoUrlIsRegex")
                            or str(data.get("repoURLIsRegex", "")).lower() == "true"
                        ),
                        "redacted": True,
                    }

                def _format_generic(sec: Dict[str, Any]) -> Dict[str, Any]:
                    meta = sec.get("metadata") or {}
                    data = sec.get("data") or sec.get("stringData") or {}
                    return {
                        "name": meta.get("name") or sec.get("name", ""),
                        "keys": sorted(data.keys()) if isinstance(data, dict) else [],
                        "redacted": True,
                    }

                payload = {
                    "project": project,
                    "repo_credentials": [_format_repo(c) for c in repo_creds],
                    "generic_credentials": [_format_generic(g) for g in generic_creds],
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)
