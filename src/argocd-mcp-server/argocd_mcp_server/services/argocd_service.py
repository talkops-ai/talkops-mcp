"""ArgoCD operations service - business logic layer."""

import asyncio
import datetime
import json
from typing import Any, Dict, List, Literal, Optional

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import (
    ApplicationNotFound,
    ArgoCDConflictError,
    ArgoCDConnectionError,
    ArgoCDNotFoundError,
    ArgoCDOperationError,
    ArgoCDPermissionError,
    ArgoDBNotAvailable,
    SyncOperationFailed,
    ValidationFailed,
)
from argocd_mcp_server.services.argocd_client import ArgoCDClient


class ArgoCDService:
    """Service for ArgoCD application and deployment operations."""

    def __init__(self, config: ServerConfig, client: Optional[ArgoCDClient] = None):
        """Initialize with configuration and optional shared ArgoCDClient."""
        self.config = config
        self.client = client or ArgoCDClient(config)
        self.argocd_url = self.client.argocd_url

    def _check_write_access(
        self,
        operation: str,
        allow_dry_run: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Check if write operations are allowed."""
        self.client.check_write_access(
            operation=operation,
            allow_dry_run=allow_dry_run,
            dry_run=dry_run,
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _normalize_history_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an ArgoCD RevisionHistory item with real API fields."""
        initiated_by = entry.get("initiatedBy") or {}
        source = entry.get("source") or {}
        return {
            "id": entry.get("id"),
            "revision": entry.get("revision"),
            "deployed_at": entry.get("deployedAt") or entry.get("timestamp"),
            "deploy_started_at": entry.get("deployStartedAt"),
            "initiated_by": initiated_by.get("username") or entry.get("author") or "automated",
            "source_path": source.get("path"),
            "target_revision": source.get("targetRevision"),
        }

    async def list_applications(
        self,
        cluster: Optional[str] = None,
        namespace: Optional[str] = None,
        project_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        health_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        cluster_name: Optional[str] = None,
        project: Optional[str] = None,
        sync_status: Optional[str] = None,
        health_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List ArgoCD applications with filtering and pagination."""
        effective_cluster = cluster or cluster_name
        project_filter = project_filter or project
        status_filter = status_filter or sync_status
        health_filter = health_filter or health_status
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        params: Dict[str, Any] = {}
        if project_filter:
            params["projects"] = project_filter

        try:
            data = await self.client.request("GET", "/api/v1/applications", params=params)
            items = (data.get("items") if isinstance(data, dict) else None) or []

            filtered_apps: List[Dict[str, Any]] = []
            for app in items:
                metadata = app.get("metadata", {})
                spec = app.get("spec", {})
                status = app.get("status", {})
                sync_status = status.get("sync", {}).get("status")
                health_status = status.get("health", {}).get("status")
                destination = spec.get("destination", {})
                dest_server = destination.get("server") or ""
                dest_name = destination.get("name") or ""
                dest_ns = destination.get("namespace") or metadata.get("namespace")

                if project_filter and spec.get("project") != project_filter:
                    continue

                if effective_cluster:
                    c_low = effective_cluster.lower()
                    if c_low not in dest_server.lower() and c_low not in dest_name.lower():
                        continue

                if namespace and dest_ns != namespace and metadata.get("namespace") != namespace:
                    continue

                if status_filter and sync_status != status_filter:
                    continue

                if health_filter and health_status != health_filter:
                    continue

                filtered_apps.append({
                    "name": metadata.get("name"),
                    "project": spec.get("project", "default"),
                    "sync_status": sync_status,
                    "health_status": health_status,
                    "target_revision": spec.get("source", {}).get("targetRevision"),
                    "destination": {
                        "server": dest_server or None,
                        "name": dest_name or None,
                        "namespace": dest_ns,
                    },
                })

            total = len(filtered_apps)
            paginated_apps = filtered_apps[offset : offset + limit]

            result: Dict[str, Any] = {
                "total": total,
                "limit": limit,
                "offset": offset,
                "applications": paginated_apps,
            }

            if total == 0:
                result["message"] = (
                    "No matching applications found. "
                    "Call 'create_application' to register a new application, or "
                    "remove filters to view all applications."
                )

            return result
        except (ArgoCDConnectionError, ArgoCDPermissionError, ArgoDBNotAvailable):
            raise
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list applications: {str(e)}") from e

    async def get_application_details(
        self,
        app_name: str,
        detail_level: Literal["summary", "full"] = "summary",
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get application state, resources, and real deployment history."""
        try:
            app = await self.client.request("GET", f"/api/v1/applications/{app_name}")

            metadata = app.get("metadata", {})
            spec = app.get("spec", {})
            status = app.get("status", {})

            raw_resources = status.get("resources") or []
            resources = [
                {
                    "group": res.get("group", ""),
                    "kind": res.get("kind"),
                    "namespace": res.get("namespace"),
                    "name": res.get("name"),
                    "status": res.get("status"),
                    "health": (res.get("health") or {}).get("status"),
                }
                for res in raw_resources
            ]

            raw_history = status.get("history") or []
            normalized_history = [self._normalize_history_entry(h) for h in raw_history]
            # Sort ascending by ID if present so [-1] is latest
            normalized_history.sort(
                key=lambda h: (h["id"] is not None, h["id"] if h["id"] is not None else 0)
            )

            sync_policy = spec.get("syncPolicy") or {}
            automated = sync_policy.get("automated")
            auto_sync_enabled = bool(automated is not None and automated != {})

            total_res = len(resources)
            healthy_res = sum(
                1 for r in resources if r.get("health") in ("Healthy", None) and r.get("status") == "Synced"
            )
            out_of_sync_res = sum(1 for r in resources if r.get("status") == "OutOfSync")
            degraded_res = sum(1 for r in resources if r.get("health") == "Degraded")

            base: Dict[str, Any] = {
                "name": metadata.get("name", app_name),
                "namespace": metadata.get("namespace", "argocd"),
                "project": spec.get("project", "default"),
                "sync_status": (status.get("sync") or {}).get("status"),
                "health_status": (status.get("health") or {}).get("status"),
                "current_revision": (status.get("sync") or {}).get("revision"),
                "auto_sync_enabled": auto_sync_enabled,
                "source": {
                    "repo_url": (spec.get("source") or {}).get("repoURL"),
                    "path": (spec.get("source") or {}).get("path"),
                    "target_revision": (spec.get("source") or {}).get("targetRevision"),
                },
                "destination": {
                    "server": (spec.get("destination") or {}).get("server"),
                    "namespace": (spec.get("destination") or {}).get("namespace"),
                },
                "sync_policy": {
                    "automated": (
                        {
                            "prune": bool(automated.get("prune")),
                            "selfHeal": bool(automated.get("selfHeal")),
                        }
                        if isinstance(automated, dict)
                        else None
                    ),
                    "sync_options": sync_policy.get("syncOptions") or [],
                },
                "resource_summary": {
                    "total": total_res,
                    "healthy_and_synced": healthy_res,
                    "out_of_sync": out_of_sync_res,
                    "degraded": degraded_res,
                },
            }

            if detail_level == "full":
                base["resources"] = resources
                base["sync_history"] = normalized_history
                base["conditions"] = status.get("conditions") or []
            else:
                # In summary mode, highlight problem resources first (up to 10) and last 5 history entries
                problem_resources = [
                    r for r in resources
                    if r.get("status") != "Synced" or r.get("health") in ("Degraded", "Missing", "Progressing")
                ]
                base["resources"] = (problem_resources or resources)[:10]
                base["sync_history"] = normalized_history[-5:]

            return base
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. "
                "Call 'list_applications' to discover valid application names, or "
                "'create_application' to register a new application."
            ) from e
        except (ArgoCDConnectionError, ArgoCDPermissionError, ArgoDBNotAvailable):
            raise
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to get application details for '{app_name}': {str(e)}"
            ) from e

    async def get_application_history(self, app_name: str) -> Dict[str, Any]:
        """Return deployment history with history IDs for an application."""
        details = await self.get_application_details(app_name=app_name, detail_level="full")
        history = details.get("sync_history", [])
        return {
            "app_name": app_name,
            "current_revision": details.get("current_revision"),
            "auto_sync_enabled": details.get("auto_sync_enabled"),
            "total_deployments": len(history),
            "history": history,
        }

    async def create_application(
        self,
        app_name: str,
        project: str,
        repo_url: str,
        path: str,
        destination_namespace: str,
        target_revision: str = "HEAD",
        destination_server: str = "https://kubernetes.default.svc",
        sync_policy: Optional[Dict[str, Any]] = None,
        auto_sync: bool = False,
        prune: bool = True,
        self_heal: bool = True,
        create_namespace: bool = False,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new ArgoCD application."""
        self._check_write_access("application creation")

        if sync_policy:
            auto_sync = bool(
                sync_policy.get("automated", sync_policy.get("auto_sync", auto_sync))
            )
            prune = bool(sync_policy.get("prune", prune))
            self_heal = bool(sync_policy.get("self_heal", sync_policy.get("selfHeal", self_heal)))
            create_namespace = bool(
                sync_policy.get("create_namespace", sync_policy.get("createNamespace", create_namespace))
            )

        body: Dict[str, Any] = {
            "metadata": {"name": app_name},
            "spec": {
                "project": project,
                "source": {
                    "repoURL": repo_url,
                    "path": path,
                    "targetRevision": target_revision,
                },
                "destination": {
                    "server": destination_server,
                    "namespace": destination_namespace,
                },
            },
        }

        if auto_sync or create_namespace:
            body["spec"]["syncPolicy"] = {}

        if auto_sync:
            body["spec"]["syncPolicy"]["automated"] = {
                "prune": prune,
                "selfHeal": self_heal,
            }

        if create_namespace:
            body["spec"]["syncPolicy"].setdefault("syncOptions", [])
            if "CreateNamespace=true" not in body["spec"]["syncPolicy"]["syncOptions"]:
                body["spec"]["syncPolicy"]["syncOptions"].append("CreateNamespace=true")

        try:
            await self.client.request("POST", "/api/v1/applications", json=body)
            return {
                "name": app_name,
                "project": project,
                "destination_namespace": destination_namespace,
                "target_revision": target_revision,
                "auto_sync_enabled": auto_sync,
                "created": True,
                "message": f"Application '{app_name}' created successfully.",
            }
        except ArgoCDConflictError as e:
            raise ArgoCDOperationError(
                f"Application '{app_name}' already exists. "
                "Call 'update_application' to modify its configuration or 'sync_application' to deploy changes."
            ) from e
        except Exception as e:
            if "already exists" in str(e).lower():
                raise ArgoCDOperationError(
                    f"Application '{app_name}' already exists. "
                    "Call 'update_application' to modify its configuration or 'sync_application' to deploy changes."
                ) from e
            raise ArgoCDOperationError(f"Failed to create application '{app_name}': {str(e)}") from e

    async def update_application(
        self,
        app_name: str,
        target_revision: Optional[str] = None,
        sync_policy: Optional[Dict[str, Any]] = None,
        path: Optional[str] = None,
        destination_namespace: Optional[str] = None,
        auto_sync: Optional[bool] = None,
        prune: Optional[bool] = None,
        self_heal: Optional[bool] = None,
        create_namespace: Optional[bool] = None,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing ArgoCD application's configuration."""
        self._check_write_access("application update")

        if sync_policy is not None:
            if "automated" in sync_policy or "auto_sync" in sync_policy:
                auto_sync = bool(sync_policy.get("automated", sync_policy.get("auto_sync")))
            if "prune" in sync_policy:
                prune = bool(sync_policy["prune"])
            if "self_heal" in sync_policy or "selfHeal" in sync_policy:
                self_heal = bool(sync_policy.get("self_heal", sync_policy.get("selfHeal")))
            if "create_namespace" in sync_policy or "createNamespace" in sync_policy:
                create_namespace = bool(
                    sync_policy.get("create_namespace", sync_policy.get("createNamespace"))
                )

        try:
            app = await self.client.request("GET", f"/api/v1/applications/{app_name}")
            spec = app.get("spec") or {}
            updated_fields: List[str] = []

            if target_revision is not None:
                spec.setdefault("source", {})["targetRevision"] = target_revision
                updated_fields.append("target_revision")

            if path is not None:
                spec.setdefault("source", {})["path"] = path
                updated_fields.append("path")

            if destination_namespace is not None:
                spec.setdefault("destination", {})["namespace"] = destination_namespace
                updated_fields.append("destination_namespace")

            if auto_sync is not None:
                spec.setdefault("syncPolicy", {})
                if auto_sync:
                    automated = spec["syncPolicy"].setdefault("automated", {})
                    if prune is not None:
                        automated["prune"] = prune
                    if self_heal is not None:
                        automated["selfHeal"] = self_heal
                else:
                    spec["syncPolicy"].pop("automated", None)
                updated_fields.append("auto_sync")
            else:
                if prune is not None or self_heal is not None:
                    automated = spec.setdefault("syncPolicy", {}).setdefault("automated", {})
                    if prune is not None:
                        automated["prune"] = prune
                        updated_fields.append("prune")
                    if self_heal is not None:
                        automated["selfHeal"] = self_heal
                        updated_fields.append("self_heal")

            if create_namespace is not None:
                spec.setdefault("syncPolicy", {})
                sync_options = list(spec["syncPolicy"].get("syncOptions") or [])
                if create_namespace:
                    if "CreateNamespace=true" not in sync_options:
                        sync_options.append("CreateNamespace=true")
                else:
                    sync_options = [opt for opt in sync_options if opt != "CreateNamespace=true"]

                if sync_options:
                    spec["syncPolicy"]["syncOptions"] = sync_options
                else:
                    spec["syncPolicy"].pop("syncOptions", None)
                updated_fields.append("create_namespace")

            if "syncPolicy" in spec and not spec["syncPolicy"]:
                del spec["syncPolicy"]

            app["spec"] = spec
            await self.client.request("PUT", f"/api/v1/applications/{app_name}", json=app)

            auto_sync_now = bool(spec.get("syncPolicy", {}).get("automated"))
            return {
                "name": app_name,
                "updated": True,
                "updated_fields": updated_fields,
                "auto_sync_enabled": auto_sync_now,
                "target_revision": spec.get("source", {}).get("targetRevision"),
                "message": f"Application '{app_name}' updated successfully.",
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Cannot update '{app_name}' because it does not exist. "
                "Call 'list_applications' to check the name or 'create_application' to create it."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to update application '{app_name}': {str(e)}") from e

    async def delete_application(
        self,
        app_name: str,
        cascade: bool = True,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete an ArgoCD application."""
        self._check_write_access("application deletion")

        params = {"cascade": str(cascade).lower()}
        try:
            await self.client.request("DELETE", f"/api/v1/applications/{app_name}", params=params)
            return {
                "name": app_name,
                "deleted": True,
                "cascade": cascade,
                "message": f"Application '{app_name}' deleted successfully.",
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found; it may have already been deleted."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to delete application '{app_name}': {str(e)}") from e

    async def sync_application(
        self,
        app_name: str,
        revision: Optional[str] = None,
        dry_run: bool = True,
        prune: bool = False,
        force: bool = False,
        resources: Optional[List[Dict[str, str]]] = None,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync an ArgoCD application to its target Git state."""
        self._check_write_access("application sync", allow_dry_run=True, dry_run=dry_run)

        strategy: Dict[str, Any] = (
            {"hook": {"force": True}} if force else {"apply": {"force": False}}
        )
        body: Dict[str, Any] = {
            "dryRun": dry_run,
            "prune": prune,
            "strategy": strategy,
        }
        if revision:
            body["revision"] = revision
        if resources:
            body["resources"] = resources

        try:
            try:
                result = await self.client.request(
                    "POST", f"/api/v1/applications/{app_name}/sync", json=body
                )
            except ArgoCDOperationError as sync_busy_err:
                if "another operation is already in progress" not in str(sync_busy_err).lower():
                    raise
                for _ in range(10):
                    await asyncio.sleep(0.4)
                    cur = await self.client.request("GET", f"/api/v1/applications/{app_name}")
                    if not cur.get("operation"):
                        break
                result = await self.client.request(
                    "POST", f"/api/v1/applications/{app_name}/sync", json=body
                )

            operation_state = (result.get("status") or {}).get("operationState") or {}
            if dry_run and (result.get("operation") or operation_state.get("phase") == "Running"):
                for _ in range(15):
                    await asyncio.sleep(0.4)
                    polled = await self.client.request("GET", f"/api/v1/applications/{app_name}")
                    operation_state = (polled.get("status") or {}).get("operationState") or {}
                    if not polled.get("operation") and operation_state.get("phase") != "Running":
                        break
                if operation_state.get("phase") in ("Failed", "Error"):
                    raise SyncOperationFailed(
                        operation_state.get("message") or "Dry-run sync failed validation."
                    )

            sync_info = (operation_state.get("operation") or {}).get("sync") or {}

            mode_label = "DRY-RUN PREVIEW" if dry_run else "SYNC EXECUTED"
            phase = operation_state.get("phase") or ("Succeeded" if dry_run else "Running")
            message = (
                "Dry-run sync succeeded. No cluster resources were modified."
                if dry_run
                else "Sync operation initiated on cluster."
            )

            return {
                "app_name": app_name,
                "mode": "dry_run" if dry_run else "executed",
                "status": phase,
                "message": f"[{mode_label}] {message}",
                "details": {
                    "dry_run": dry_run,
                    "prune": prune,
                    "force": force,
                    "target_revision": sync_info.get("revision") or revision or "HEAD",
                    "initiated_by": (
                        ((operation_state.get("operation") or {}).get("initiatedBy") or {}).get("username")
                        or "mcp-operator"
                    ),
                },
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Cannot sync '{app_name}' because it does not exist. "
                "Call 'list_applications' to verify the application name."
            ) from e
        except Exception as e:
            raise SyncOperationFailed(
                f"Failed to sync application '{app_name}': {str(e)}. "
                "Call 'get_application_diff' to inspect manifest errors or 'get_application_logs' for runtime failures."
            ) from e

    async def get_application_diff(
        self,
        app_name: str,
        revision: Optional[str] = None,
        validate: bool = True,
        refresh: bool = True,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute live-vs-target resource diffs and optionally validate via dry-run sync (N-to-1)."""
        try:
            params = {"refresh": "normal"} if refresh else None
            app = await self.client.request(
                "GET", f"/api/v1/applications/{app_name}", params=params
            )

            spec = app.get("spec") or {}
            status = app.get("status") or {}
            target_rev = revision or (spec.get("source") or {}).get("targetRevision") or "HEAD"

            diffs: List[Dict[str, Any]] = []

            # 1. Try managed-resources endpoint for liveState vs targetState comparison
            managed_items: List[Dict[str, Any]] = []
            try:
                managed_resp = await self.client.request(
                    "GET", f"/api/v1/applications/{app_name}/managed-resources"
                )
                if isinstance(managed_resp, dict):
                    managed_items = managed_resp.get("items") or []
            except Exception:
                managed_items = []

            if managed_items:
                for item in managed_items:
                    live_str = item.get("normalizedLiveState") or item.get("liveState") or ""
                    target_str = item.get("targetState") or ""
                    if live_str != target_str or item.get("status") == "OutOfSync":
                        diffs.append({
                            "group": item.get("group", ""),
                            "kind": item.get("kind"),
                            "namespace": item.get("namespace"),
                            "name": item.get("name"),
                            "status": "OutOfSync",
                            "has_live_state": bool(live_str),
                            "has_target_state": bool(target_str),
                        })
            else:
                for res in status.get("resources") or []:
                    if res.get("status") == "OutOfSync":
                        diffs.append({
                            "group": res.get("group", ""),
                            "kind": res.get("kind"),
                            "namespace": res.get("namespace"),
                            "name": res.get("name"),
                            "status": res.get("status"),
                            "message": "Resource is OutOfSync with target Git state",
                        })

            # 2. If a specific revision was requested, query manifests for that revision if available
            revision_manifests_count: Optional[int] = None
            if revision:
                try:
                    manifests_resp = await self.client.request(
                        "GET",
                        f"/api/v1/applications/{app_name}/manifests",
                        params={"revision": revision},
                    )
                    if isinstance(manifests_resp, dict) and "manifests" in manifests_resp:
                        revision_manifests_count = len(manifests_resp.get("manifests") or [])
                except Exception:
                    pass

            # 3. Optional server-side dry-run validation (absorbs validate_application_config)
            validation: Dict[str, Any] = {"checked": False, "valid": True, "error": None}
            if validate:
                val_res = await self.validate_application_config(
                    app_name=app_name, revision=revision
                )
                validation = {
                    "checked": True,
                    "valid": val_res["valid"],
                    "error": val_res["error"],
                }

            result: Dict[str, Any] = {
                "app_name": app_name,
                "source_revision": target_rev,
                "changes_detected": len(diffs) > 0,
                "diff_count": len(diffs),
                "diffs": diffs,
                "validation": validation,
            }
            if revision_manifests_count is not None:
                result["revision_manifests_count"] = revision_manifests_count
            return result

        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. Call 'list_applications' to verify valid names."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get diff for '{app_name}': {str(e)}") from e

    async def validate_application_config(
        self,
        app_name: str,
        revision: Optional[str] = None,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate application manifests and Kubernetes schema via dry-run sync."""
        try:
            await self.sync_application(
                app_name=app_name,
                revision=revision,
                dry_run=True,
                prune=False,
            )
            return {
                "valid": True,
                "error": None,
                "details": [],
                "message": "Configuration validated successfully via dry-run sync.",
            }
        except (ApplicationNotFound, ArgoCDNotFoundError) as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. Cannot validate configuration."
            ) from e
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "details": [str(e)],
                "message": f"Validation failed: {str(e)}",
            }

    async def get_application_resource_tree(
        self,
        app_name: str,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the hierarchical resource tree of an application."""
        try:
            tree = await self.client.request(
                "GET", f"/api/v1/applications/{app_name}/resource-tree"
            )
            nodes = (tree.get("nodes") if isinstance(tree, dict) else None) or []
            concise_nodes = [
                {
                    "kind": n.get("kind"),
                    "name": n.get("name"),
                    "namespace": n.get("namespace"),
                    "health": (n.get("health") or {}).get("status"),
                    "parent_refs": [
                        f"{p.get('kind')}/{p.get('name')}" for p in (n.get("parentRefs") or [])
                    ],
                }
                for n in nodes
            ]
            return {
                "app_name": app_name,
                "total_nodes": len(concise_nodes),
                "nodes": concise_nodes,
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(f"Application '{app_name}' not found.") from e
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to get resource tree for '{app_name}': {str(e)}"
            ) from e

    async def get_application_events(
        self,
        app_name: str,
        limit: int = 50,
        warnings_only: bool = False,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get recent Kubernetes events for an ArgoCD application."""
        limit = max(1, min(limit, 200))
        try:
            data = await self.client.request(
                "GET", f"/api/v1/applications/{app_name}/events"
            )
            raw_events = (data.get("items") if isinstance(data, dict) else None) or []

            formatted: List[Dict[str, Any]] = []
            for event in raw_events:
                event_type = event.get("type", "Normal")
                if warnings_only and event_type != "Warning":
                    continue
                involved = event.get("involvedObject") or {}
                formatted.append({
                    "timestamp": event.get("lastTimestamp") or event.get("firstTimestamp") or "",
                    "type": event_type,
                    "reason": event.get("reason"),
                    "message": event.get("message"),
                    "object": f"{involved.get('kind', 'Resource')}/{involved.get('name', 'unknown')}",
                })

            formatted.sort(key=lambda x: x["timestamp"] or "", reverse=True)
            limited = formatted[:limit]

            return {
                "app_name": app_name,
                "total_events": len(limited),
                "events": limited,
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. Call 'list_applications' to verify valid names."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to get events for '{app_name}': {str(e)}"
            ) from e

    @staticmethod
    def _parse_argocd_log_stream(raw_payload: Any) -> List[str]:
        """Parse ArgoCD NDJSON log stream or plain text into clean log lines."""
        if not raw_payload:
            return []
        if isinstance(raw_payload, dict):
            content = (raw_payload.get("result") or {}).get("content")
            if content is not None:
                return [str(content)]
            return [json.dumps(raw_payload)]

        text = str(raw_payload).strip()
        if not text:
            return []

        lines: List[str] = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    obj = json.loads(stripped)
                    if isinstance(obj, dict) and "result" in obj:
                        res = obj.get("result") or {}
                        content = res.get("content")
                        if content is not None:
                            lines.append(str(content))
                            continue
                except Exception:
                    pass
            lines.append(raw_line)
        return lines

    async def get_application_logs(
        self,
        app_name: str,
        pod_name: Optional[str] = None,
        container: Optional[str] = None,
        namespace: Optional[str] = None,
        tail_lines: int = 50,
        since_seconds: Optional[int] = None,
        errors_only: bool = False,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve and summarize pod logs for an application with NDJSON parsing and error detection."""
        tail_lines = max(1, min(tail_lines, 200))
        error_keywords = ("error", "fatal", "exception", "failed", "panic", "crashloopbackoff")

        try:
            if pod_name:
                target_pods = [{"name": pod_name, "namespace": namespace}]
            else:
                try:
                    tree = await self.get_application_resource_tree(app_name=app_name)
                    target_pods = [
                        {"name": n.get("name"), "namespace": n.get("namespace")}
                        for n in tree.get("nodes", [])
                        if n.get("kind") == "Pod" and n.get("name")
                    ]
                except ApplicationNotFound:
                    raise
                except Exception:
                    details = await self.get_application_details(
                        app_name=app_name, detail_level="full"
                    )
                    target_pods = [
                        {"name": r.get("name"), "namespace": r.get("namespace")}
                        for r in details.get("resources", [])
                        if r.get("kind") == "Pod" and r.get("name")
                    ]

            pod_logs: List[Dict[str, Any]] = []
            total_lines_collected = 0

            for pod in target_pods[:5]:
                p_name = pod["name"]
                p_ns = pod.get("namespace") or namespace
                params: Dict[str, Any] = {"tailLines": tail_lines, "follow": "false"}
                if p_ns:
                    params["namespace"] = p_ns
                if container:
                    params["container"] = container
                if since_seconds:
                    params["sinceSeconds"] = since_seconds

                try:
                    raw = await self.client.request(
                        "GET",
                        f"/api/v1/applications/{app_name}/pods/{p_name}/logs",
                        params=params,
                        is_json_response=False,
                    )
                    parsed_lines = self._parse_argocd_log_stream(raw)
                    parsed_lines = parsed_lines[-tail_lines:]
                    error_lines = [
                        line for line in parsed_lines
                        if any(kw in line.lower() for kw in error_keywords)
                    ]

                    display_lines = error_lines if errors_only else parsed_lines
                    total_lines_collected += len(display_lines)

                    entry: Dict[str, Any] = {
                        "pod_name": p_name,
                        "namespace": p_ns,
                        "line_count": len(display_lines),
                        "error_count": len(error_lines),
                        "recent_logs": display_lines[:20],
                    }
                    if error_lines:
                        entry["sample_errors"] = error_lines[:5]
                    pod_logs.append(entry)
                except Exception as pod_err:
                    pod_logs.append({
                        "pod_name": p_name,
                        "namespace": p_ns,
                        "error": str(pod_err),
                    })

            pods_with_errors = sum(1 for p in pod_logs if p.get("error_count", 0) > 0)
            summary = (
                f"Retrieved logs from {len([p for p in pod_logs if 'error' not in p])}/{len(target_pods)} "
                f"pod(s) for '{app_name}' ({total_lines_collected} lines)."
            )
            if pods_with_errors:
                summary += f" {pods_with_errors} pod(s) contain error signatures."

            return {
                "summary": summary,
                "app_name": app_name,
                "total_pods": len(target_pods),
                "pods_checked": len(pod_logs),
                "pod_logs": pod_logs,
            }
        except ApplicationNotFound:
            raise
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to get logs for '{app_name}': {str(e)}. "
                "Call 'get_application_details' to verify pod status."
            ) from e

    async def get_sync_status(
        self,
        app_name: str,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get current sync status, operation phase, and per-resource sync results."""
        try:
            data = await self.client.request("GET", f"/api/v1/applications/{app_name}")
            status = data.get("status") or {}
            sync_status = status.get("sync") or {}
            health_status = status.get("health") or {}
            operation_state = status.get("operationState") or {}
            sync_result = operation_state.get("syncResult") or {}
            history = status.get("history") or []

            resource_results = [
                {
                    "kind": r.get("kind"),
                    "name": r.get("name"),
                    "namespace": r.get("namespace"),
                    "status": r.get("status"),
                    "message": r.get("message"),
                }
                for r in (sync_result.get("resources") or [])[:10]
            ]

            formatted_history = [self._normalize_history_entry(item) for item in history[-5:]]

            return {
                "app_name": app_name,
                "overall_sync_status": sync_status.get("status"),
                "health_status": health_status.get("status"),
                "sync_details": {
                    "revision": sync_status.get("revision"),
                    "target_revision": (
                        ((sync_status.get("comparedTo") or {}).get("source") or {}).get("targetRevision")
                    ),
                },
                "last_operation": {
                    "phase": operation_state.get("phase"),
                    "message": operation_state.get("message"),
                    "started_at": operation_state.get("startedAt"),
                    "finished_at": operation_state.get("finishedAt"),
                    "revision": sync_result.get("revision"),
                    "resources": resource_results,
                },
                "sync_history": formatted_history,
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. Call 'list_applications' to see valid names."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get sync status for '{app_name}': {str(e)}") from e

    async def rollback_application(
        self,
        app_name: str,
        history_id: Optional[int] = None,
        dry_run: bool = True,
        prune: bool = False,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Preview or execute an application rollback to a deployment history ID."""
        self._check_write_access("application rollback", allow_dry_run=True, dry_run=dry_run)

        try:
            app = await self.client.request("GET", f"/api/v1/applications/{app_name}")
            spec = app.get("spec") or {}
            status = app.get("status") or {}

            automated = (spec.get("syncPolicy") or {}).get("automated")
            auto_sync_enabled = bool(automated is not None and automated != {})

            if auto_sync_enabled and not dry_run:
                raise SyncOperationFailed(
                    f"Cannot execute rollback on '{app_name}' while auto-sync is enabled; "
                    "ArgoCD blocks rollbacks when automated sync is active. "
                    f"Call update_application(app_name='{app_name}', sync_policy={{'automated': False}}) first, "
                    "or revert the offending commit in Git."
                )

            raw_history = status.get("history") or []
            normalized = [self._normalize_history_entry(h) for h in raw_history]
            normalized.sort(
                key=lambda h: (h["id"] is not None, h["id"] if h["id"] is not None else 0)
            )

            if history_id is None:
                if len(normalized) < 2:
                    raise ArgoCDOperationError(
                        f"Cannot rollback '{app_name}' to previous version: at least 2 history entries "
                        f"are required, but only {len(normalized)} exist."
                    )
                target_entry = normalized[-2]
                resolved_id = target_entry["id"] if target_entry["id"] is not None else len(normalized) - 2
            else:
                resolved_id = history_id
                matching = [h for h in normalized if h.get("id") == history_id]
                if normalized and not matching:
                    valid_ids = [h.get("id") for h in normalized if h.get("id") is not None]
                    raise ArgoCDOperationError(
                        f"History ID {history_id} not found for application '{app_name}'. "
                        f"Valid history IDs: {valid_ids}. Call 'get_application_details' to inspect history."
                    )
                target_entry = matching[0] if matching else {"id": history_id, "revision": None}

            current_entry = normalized[-1] if normalized else {"id": None, "revision": (status.get("sync") or {}).get("revision")}

            body = {
                "name": app_name,
                "id": int(resolved_id),
                "dryRun": dry_run,
                "prune": prune,
            }

            try:
                rb_res = await self.client.request(
                    "POST", f"/api/v1/applications/{app_name}/rollback", json=body
                )
                if dry_run and isinstance(rb_res, dict) and rb_res.get("operation"):
                    for _ in range(12):
                        await asyncio.sleep(0.4)
                        polled = await self.client.request("GET", f"/api/v1/applications/{app_name}")
                        if not polled.get("operation"):
                            break
            except ArgoCDOperationError as rb_err:
                if not (dry_run and auto_sync_enabled and "auto-sync" in str(rb_err).lower()):
                    raise

            mode_label = "DRY-RUN PREVIEW" if dry_run else "ROLLBACK EXECUTED"
            warning = (
                f"Auto-sync is currently enabled on '{app_name}'. You MUST disable auto-sync via "
                f"update_application(app_name='{app_name}', sync_policy={{'automated': False}}) "
                "before calling rollback_application with dry_run=False."
                if auto_sync_enabled
                else None
            )

            return {
                "app_name": app_name,
                "mode": "dry_run" if dry_run else "executed",
                "dry_run": dry_run,
                "history_id": int(resolved_id),
                "target_revision": target_entry.get("revision"),
                "current_revision": current_entry.get("revision"),
                "auto_sync_blocker": auto_sync_enabled,
                "warning": warning,
                "status": "PreviewSucceeded" if dry_run else "RollingBack",
                "message": (
                    f"[{mode_label}] Rollback '{app_name}' to history ID {resolved_id} "
                    f"(revision {target_entry.get('revision')})."
                ),
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. Call 'list_applications' to see valid names."
            ) from e
        except (SyncOperationFailed, ArgoCDOperationError):
            raise
        except Exception as e:
            raise SyncOperationFailed(
                f"Failed to rollback '{app_name}': {str(e)}. "
                "Call 'get_application_details' to inspect available history IDs."
            ) from e

    async def refresh_application(
        self,
        app_name: str,
        mode: Literal["normal", "hard"] = "normal",
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Refresh application cache (normal=soft cache check, hard=re-read Git manifest)."""
        if mode not in ("normal", "hard"):
            raise ValueError(f"Invalid refresh mode '{mode}'. Must be 'normal' or 'hard'.")
        try:
            app = await self.client.request(
                "GET",
                f"/api/v1/applications/{app_name}",
                params={"refresh": mode},
            )
            status = app.get("status") or {}
            return {
                "app_name": app_name,
                "refreshed": True,
                "mode": mode,
                "sync_status": (status.get("sync") or {}).get("status"),
                "health_status": (status.get("health") or {}).get("status"),
                "message": f"Application '{app_name}' refreshed ({mode}).",
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found. Cannot refresh."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to refresh '{app_name}': {str(e)}") from e

    async def cancel_deployment(
        self,
        app_name: str,
        cluster_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an ongoing sync operation on an application."""
        self._check_write_access("deployment cancellation")
        try:
            await self.client.request(
                "DELETE", f"/api/v1/applications/{app_name}/operation"
            )
            return {
                "app_name": app_name,
                "cancelled": True,
                "message": f"Ongoing operation for '{app_name}' cancelled.",
            }
        except ArgoCDNotFoundError as e:
            raise ApplicationNotFound(
                f"Application '{app_name}' not found or no active operation to cancel."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to cancel deployment for '{app_name}': {str(e)}"
            ) from e

    async def list_clusters(self) -> Dict[str, Any]:
        """List registered target Kubernetes clusters with credentials redacted."""
        try:
            data = await self.client.request("GET", "/api/v1/clusters")
            items = (data.get("items") if isinstance(data, dict) else None) or []
            clusters = [
                {
                    "name": c.get("name"),
                    "server": c.get("server"),
                    "connection_state": (c.get("connectionState") or {}).get("status", "Unknown"),
                    "server_version": c.get("serverVersion"),
                    "namespaces": c.get("namespaces") or [],
                }
                for c in items
            ]
            return {
                "total": len(clusters),
                "clusters": clusters,
            }
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list clusters: {str(e)}") from e

    async def check_health(self) -> Dict[str, Any]:
        """Check ArgoCD API connectivity, version, and MCP server guardrail posture."""
        try:
            data = await self.client.request("GET", "/api/version")
            version = data.get("Version", "unknown") if isinstance(data, dict) else "unknown"
            return {
                "status": "healthy",
                "server_url": self.argocd_url,
                "version": version,
                "allow_write": self.config.allow_write,
                "toolsets": self.config.toolsets,
                "timestamp": self._now_iso(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "server_url": self.argocd_url,
                "error": str(e),
                "allow_write": self.config.allow_write,
                "toolsets": self.config.toolsets,
                "timestamp": self._now_iso(),
            }

