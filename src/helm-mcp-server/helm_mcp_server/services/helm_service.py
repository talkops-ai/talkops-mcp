"""Helm operations service — execution-layer business logic."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple

import yaml

from helm_mcp_server.config import ServerConfig
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.utils.helm_helper import (
    compute_manifest_diff,
    is_helm_installed,
    redact_secrets_in_manifests,
    redact_sensitive_values,
)

if TYPE_CHECKING:
    from helm_mcp_server.services.kubernetes_service import KubernetesService

ValuesStrategy = Literal["reuse", "reset", "reset_then_reuse"]

STATUS_FLAG_MAP: Dict[str, str] = {
    "deployed": "--deployed",
    "failed": "--failed",
    "pending": "--pending",
    "superseded": "--superseded",
    "uninstalled": "--uninstalled",
    "uninstalling": "--uninstalling",
}


class HelmService:
    """Service encapsulating Helm CLI execution, release diffing, and rollout monitoring."""

    TERMINAL_CONTAINER_STATES = frozenset({
        "CrashLoopBackOff",
        "ImagePullBackOff",
        "ErrImagePull",
        "CreateContainerConfigError",
        "InvalidImageName",
        "CreateContainerError",
    })

    def __init__(
        self,
        config: ServerConfig,
        k8s_service: Optional[KubernetesService] = None,
    ):
        """Initialize with configuration and optional KubernetesService for context propagation."""
        self.config = config
        self.k8s_service = k8s_service

    # ------------------------------------------------------------------
    # Command construction, validation, and subprocess execution
    # ------------------------------------------------------------------

    def _check_helm_installed(self) -> None:
        """Raise HelmOperationError if helm binary is not found in PATH."""
        if not is_helm_installed():
            raise HelmOperationError("Helm binary is not installed or not found in PATH.")

    def _check_write_access(
        self,
        operation: str,
        *,
        allow_dry_run: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Verify mutating operations are permitted by server configuration."""
        if allow_dry_run and dry_run:
            return
        if not self.config.is_mutate_enabled:
            raise HelmOperationError(
                f"Helm '{operation}' is disabled because the server is in read-only mode. "
                "Set MCP_ALLOW_WRITE=true (and ensure MCP_TOOLSETS includes 'mutate' or 'all') "
                "or use helm_plan_release for a read-only preview."
            )

    @staticmethod
    def validate_chart_ref(chart_ref: str) -> str:
        """Validate that chart_ref explicitly specifies a repository prefix, OCI URI, URL, or path."""
        cleaned = (chart_ref or "").strip()
        if not cleaned:
            raise HelmOperationError("Parameter 'chart_ref' cannot be empty.")

        if (
            "/" in cleaned
            or cleaned.startswith("oci://")
            or cleaned.startswith("http://")
            or cleaned.startswith("https://")
            or cleaned.startswith(".")
        ):
            return cleaned

        raise HelmOperationError(
            f"Chart reference '{cleaned}' must include an explicit repository prefix "
            f"(e.g., '<repo>/{cleaned}') or OCI URI ('oci://...'). "
            f"Call helm_search_charts(query='{cleaned}') or read resource 'helm://repositories' "
            "to find the repository prefix."
        )

    def _build_cmd(
        self,
        args: List[str],
        *,
        include_cluster_flags: bool = True,
        session_id: Optional[str] = None,
    ) -> List[str]:
        """Construct a Helm CLI command list, injecting kubeconfig and session kube-context."""
        cmd = ["helm", *args]
        if include_cluster_flags:
            if self.config.kubernetes.kubeconfig:
                cmd.extend(["--kubeconfig", self.config.kubernetes.kubeconfig])
            if self.k8s_service is not None:
                active_ctx = self.k8s_service.get_active_context(session_id)
                if active_ctx:
                    cmd.extend(["--kube-context", active_ctx])
        return cmd

    @staticmethod
    def _write_temp_values_file(values: Optional[Dict[str, Any]]) -> Optional[str]:
        """Write a values dictionary to a temporary YAML file and return its path."""
        if not values:
            return None
        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".yaml", encoding="utf-8") as f:
            yaml.safe_dump(values, f, sort_keys=False)
            return f.name

    @staticmethod
    def _cleanup_temp_file(path: Optional[str]) -> None:
        """Remove a temporary file if it exists."""
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass

    async def _run_helm_command(
        self,
        cmd: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        """Execute a Helm CLI command asynchronously with timeout enforcement."""
        self._check_helm_installed()
        try:
            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.helm.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                raise HelmOperationError(
                    f"Helm command timed out after {self.config.helm.timeout}s: {' '.join(cmd[:3])}"
                )

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                raise HelmOperationError(error_msg or f"Helm exited with code {process.returncode}")

            return stdout.decode("utf-8", errors="replace").strip()
        except HelmOperationError:
            raise
        except Exception as exc:
            raise HelmOperationError(f"Helm command execution failed: {exc}")

    # ------------------------------------------------------------------
    # Repository Management & Discovery
    # ------------------------------------------------------------------

    async def list_repositories(self) -> List[Dict[str, str]]:
        """List all configured Helm chart repositories."""
        try:
            cmd = self._build_cmd(["repo", "list", "-o", "json"], include_cluster_flags=False)
            result = await self._run_helm_command(cmd)
            repos = json.loads(result) if result else []
            return [
                {"name": str(r.get("name", "")), "url": str(r.get("url", ""))}
                for r in (repos or [])
                if isinstance(r, dict)
            ]
        except HelmOperationError as exc:
            if "no repositories to show" in str(exc).lower():
                return []
            raise

    async def repository_exists(self, repo_name: str) -> bool:
        """Return True if a repository with repo_name is already configured."""
        try:
            repos = await self.list_repositories()
            return any(r.get("name", "").lower() == repo_name.lower() for r in repos)
        except Exception:
            return False

    async def ensure_repository(
        self,
        repo_name: str,
        repo_url: str,
    ) -> Dict[str, Any]:
        """Ensure a Helm chart repository is configured and updated."""
        self._check_write_access("ensure_repository")

        cleaned_name = (repo_name or "").strip()
        cleaned_url = (repo_url or "").strip()
        if not cleaned_name:
            raise HelmOperationError("Parameter 'repo_name' cannot be empty.")

        if await self.repository_exists(cleaned_name):
            return {
                "repository": cleaned_name,
                "added": False,
                "message": f"Repository '{cleaned_name}' is already configured.",
            }

        if not cleaned_url or not (cleaned_url.startswith("https://") or cleaned_url.startswith("http://")):
            raise HelmOperationError(
                f"Repository '{cleaned_name}' is not configured and requires a valid HTTP/HTTPS 'repo_url'. "
                "Read 'helm://repositories' to see currently configured repositories."
            )

        try:
            add_cmd = self._build_cmd(
                ["repo", "add", cleaned_name, cleaned_url],
                include_cluster_flags=False,
            )
            await self._run_helm_command(add_cmd)

            update_cmd = self._build_cmd(
                ["repo", "update", cleaned_name],
                include_cluster_flags=False,
            )
            await self._run_helm_command(update_cmd)

            return {
                "repository": cleaned_name,
                "repo_url": cleaned_url,
                "added": True,
                "message": f"Repository '{cleaned_name}' ({cleaned_url}) added and indexed.",
            }
        except Exception as exc:
            raise HelmOperationError(f"Failed to add repository '{cleaned_name}': {exc}")

    async def search_charts(
        self,
        query: str,
        repository: Optional[str] = None,
        versions: bool = False,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search configured Helm chart repositories."""
        search_target = f"{repository}/{query}" if repository and "/" not in query else query
        args = ["search", "repo", search_target, "-o", "json"]
        if versions:
            args.append("--versions")

        cmd = self._build_cmd(args, include_cluster_flags=False)
        try:
            raw = await self._run_helm_command(cmd)
            charts = json.loads(raw) if raw else []
            if not isinstance(charts, list):
                charts = []

            if repository:
                prefix = f"{repository.strip()}/"
                charts = [c for c in charts if isinstance(c, dict) and str(c.get("name", "")).startswith(prefix)]

            clamped_limit = max(1, min(limit, 50))
            return [
                {
                    "name": c.get("name", ""),
                    "version": c.get("version", ""),
                    "app_version": c.get("app_version", ""),
                    "description": c.get("description", ""),
                }
                for c in charts[:clamped_limit]
                if isinstance(c, dict)
            ]
        except json.JSONDecodeError as exc:
            raise HelmOperationError(f"Invalid JSON output from helm search: {exc}")
        except HelmOperationError as exc:
            raise HelmOperationError(
                f"Chart search failed for '{query}': {exc}. "
                "Read resource 'helm://repositories' to verify configured repositories or call 'helm_ensure_repository'."
            )

    @staticmethod
    def _build_repo_chart_ref(repository: str, chart_name: str) -> str:
        """Combine repository and chart_name into repo/chart format."""
        if "/" in chart_name:
            return chart_name
        return f"{repository.strip()}/{chart_name.strip()}"

    async def get_chart_info(
        self,
        chart_name: str,
        repository: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get Chart.yaml metadata and dependency list for a specific chart."""
        chart_ref = self._build_repo_chart_ref(repository, chart_name)
        args = ["show", "chart", chart_ref]
        if version:
            args.extend(["--version", version])

        try:
            raw = await self._run_helm_command(self._build_cmd(args, include_cluster_flags=False))
            info = yaml.safe_load(raw)
            return info if isinstance(info, dict) else {}
        except Exception as exc:
            raise HelmOperationError(
                f"Chart '{chart_ref}' not found: {exc}. "
                f"Call helm_search_charts(query='{chart_name}') or read 'helm://repositories'."
            )

    async def get_chart_values(
        self,
        chart_name: str,
        repository: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get default values.yaml dictionary for a specific chart."""
        chart_ref = self._build_repo_chart_ref(repository, chart_name)
        args = ["show", "values", chart_ref]
        if version:
            args.extend(["--version", version])

        try:
            raw = await self._run_helm_command(self._build_cmd(args, include_cluster_flags=False))
            values = yaml.safe_load(raw)
            return values if isinstance(values, dict) else {}
        except Exception as exc:
            raise HelmOperationError(
                f"Default values for chart '{chart_ref}' not found: {exc}. "
                f"Call helm_search_charts(query='{chart_name}') to verify chart name and version."
            )

    async def get_chart_readme(
        self,
        chart_name: str,
        repository: str,
        version: Optional[str] = None,
    ) -> str:
        """Get README markdown for a specific chart."""
        chart_ref = self._build_repo_chart_ref(repository, chart_name)
        args = ["show", "readme", chart_ref]
        if version:
            args.extend(["--version", version])

        try:
            return await self._run_helm_command(self._build_cmd(args, include_cluster_flags=False))
        except Exception as exc:
            raise HelmOperationError(
                f"README for chart '{chart_ref}' not found: {exc}. "
                f"Read 'helm://charts/{repository}/{chart_name}' for chart metadata instead."
            )

    # ------------------------------------------------------------------
    # Release Inspection & Resource Backing Methods
    # ------------------------------------------------------------------

    async def release_exists(
        self,
        release_name: str,
        namespace: str = "default",
        session_id: Optional[str] = None,
    ) -> bool:
        """Return True if release_name exists in namespace."""
        try:
            cmd = self._build_cmd(
                ["status", release_name, "-n", namespace, "-o", "json"],
                session_id=session_id,
            )
            await self._run_helm_command(cmd)
            return True
        except Exception:
            return False

    async def list_releases(
        self,
        namespace: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List Helm releases with optional namespace/status filtering and pagination."""
        clamped_limit = max(1, min(limit, 250))
        clamped_offset = max(0, offset)

        args = ["list", "-o", "json", "--max", str(clamped_limit), "--offset", str(clamped_offset)]
        if namespace:
            args.extend(["-n", namespace])
        else:
            args.append("--all-namespaces")

        if status:
            flag = STATUS_FLAG_MAP.get(status.strip().lower())
            if not flag:
                valid = ", ".join(sorted(STATUS_FLAG_MAP.keys()))
                raise HelmOperationError(
                    f"Invalid status filter '{status}'. Valid options: {valid}."
                )
            args.append(flag)

        try:
            raw = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            parsed = json.loads(raw) if raw else []
            if isinstance(parsed, dict):
                parsed = [parsed]

            releases = [
                {
                    "name": r.get("name", ""),
                    "namespace": r.get("namespace", namespace or "default"),
                    "revision": int(r.get("revision", 0)) if str(r.get("revision", "")).isdigit() else r.get("revision"),
                    "updated": r.get("updated", ""),
                    "status": r.get("status", "unknown"),
                    "chart": r.get("chart", ""),
                    "app_version": r.get("app_version", ""),
                }
                for r in (parsed or [])
                if isinstance(r, dict)
            ]

            return {
                "releases": releases,
                "count": len(releases),
                "limit": clamped_limit,
                "offset": clamped_offset,
                "namespace": namespace or "all",
            }
        except HelmOperationError as exc:
            raise HelmOperationError(
                f"Failed to list Helm releases: {exc}. "
                "Verify cluster connectivity via 'kubernetes://cluster-info' or switch context via 'kubernetes_set_context'."
            )

    @staticmethod
    def _summarize_manifest_resources(manifest: str) -> Tuple[Dict[str, int], int]:
        """Count Kubernetes resources by kind from a YAML manifest string."""
        counts: Dict[str, int] = {}
        total = 0
        if not manifest or not manifest.strip():
            return counts, 0
        try:
            for doc in yaml.safe_load_all(manifest):
                if isinstance(doc, dict) and doc.get("kind"):
                    kind = str(doc["kind"])
                    counts[kind] = counts.get(kind, 0) + 1
                    total += 1
        except yaml.YAMLError:
            total = manifest.count("kind:")
        return counts, total

    async def get_release_status(
        self,
        release_name: str,
        namespace: str = "default",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a concise status summary for a single Helm release (1 subprocess call)."""
        cmd = self._build_cmd(
            ["status", release_name, "-n", namespace, "-o", "json"],
            session_id=session_id,
        )
        try:
            raw = await self._run_helm_command(cmd)
            data = json.loads(raw) if raw else {}
        except Exception as exc:
            raise HelmOperationError(
                f"Release '{release_name}' not found in namespace '{namespace}': {exc}. "
                f"Call helm_list_releases(namespace='{namespace}') to see valid release names."
            )

        info = data.get("info", {}) if isinstance(data.get("info"), dict) else {}
        manifest = str(data.get("manifest") or "")
        resource_counts, total_resources = self._summarize_manifest_resources(manifest)

        # If manifest wasn't included in status payload, count from info.resources if present
        if total_resources == 0 and isinstance(info.get("resources"), dict):
            for key, items in info["resources"].items():
                if isinstance(items, list):
                    kind = key.split("/")[-1] if "/" in key else key
                    resource_counts[kind] = resource_counts.get(kind, 0) + len(items)
                    total_resources += len(items)

        notes = str(info.get("notes") or "")
        if len(notes) > 500:
            notes = notes[:500] + "... (truncated)"

        return {
            "release_name": data.get("name", release_name),
            "namespace": data.get("namespace", namespace),
            "revision": data.get("version"),
            "status": info.get("status", "unknown"),
            "description": info.get("description", ""),
            "first_deployed": info.get("first_deployed"),
            "last_deployed": info.get("last_deployed"),
            "total_resources": total_resources,
            "resource_counts": resource_counts,
            "notes": notes or None,
            "resource_uris": {
                "history": f"helm://releases/{namespace}/{release_name}/history",
                "values": f"helm://releases/{namespace}/{release_name}/values",
                "manifest": f"helm://releases/{namespace}/{release_name}/manifest",
            },
        }

    async def get_release_history(
        self,
        release_name: str,
        namespace: str = "default",
        max_revisions: int = 25,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return revision history for a Helm release."""
        cmd = self._build_cmd(
            ["history", release_name, "-n", namespace, "-o", "json", "--max", str(max(1, min(max_revisions, 100)))],
            session_id=session_id,
        )
        try:
            raw = await self._run_helm_command(cmd)
            parsed = json.loads(raw) if raw else []
            if isinstance(parsed, dict):
                parsed = [parsed]
            return [
                {
                    "revision": r.get("revision"),
                    "updated": r.get("updated"),
                    "status": r.get("status"),
                    "chart": r.get("chart"),
                    "app_version": r.get("app_version"),
                    "description": r.get("description", ""),
                }
                for r in (parsed or [])
                if isinstance(r, dict)
            ]
        except Exception as exc:
            raise HelmOperationError(
                f"Failed to get history for release '{release_name}' in namespace '{namespace}': {exc}. "
                f"Call helm_list_releases(namespace='{namespace}') to verify release existence."
            )

    async def get_release_values(
        self,
        release_name: str,
        namespace: str = "default",
        all_values: bool = False,
        revision: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return redacted user-supplied (or computed) values for a deployed Helm release."""
        args = ["get", "values", release_name, "-n", namespace, "-o", "json"]
        if all_values:
            args.append("--all")
        if revision is not None:
            args.extend(["--revision", str(revision)])

        try:
            raw = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            parsed = json.loads(raw) if raw else {}
            if not isinstance(parsed, dict):
                parsed = {}
            return redact_sensitive_values(parsed)
        except Exception as exc:
            raise HelmOperationError(
                f"Failed to get values for release '{release_name}' in namespace '{namespace}': {exc}. "
                f"Call helm_list_releases(namespace='{namespace}') to verify release existence."
            )

    async def get_release_manifest(
        self,
        release_name: str,
        namespace: str = "default",
        revision: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Return secret-redacted Kubernetes YAML manifest for a deployed Helm release."""
        args = ["get", "manifest", release_name, "-n", namespace]
        if revision is not None:
            args.extend(["--revision", str(revision)])

        try:
            raw = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            return redact_secrets_in_manifests(raw)
        except Exception as exc:
            raise HelmOperationError(
                f"Failed to get manifest for release '{release_name}' in namespace '{namespace}': {exc}. "
                f"Call helm_list_releases(namespace='{namespace}') to verify release existence."
            )

    # ------------------------------------------------------------------
    # Manifest Rendering & Release Planning (N -> 1)
    # ------------------------------------------------------------------

    async def _render_raw_manifests(
        self,
        chart_ref: str,
        release_name: str = "release-preview",
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Render raw Kubernetes YAML manifests via helm template."""
        validated_ref = self.validate_chart_ref(chart_ref)
        temp_file = self._write_temp_values_file(values)
        try:
            args = ["template", release_name, validated_ref, "-n", namespace]
            if version:
                args.extend(["--version", version])
            if temp_file:
                args.extend(["-f", temp_file])

            return await self._run_helm_command(self._build_cmd(args, session_id=session_id))
        finally:
            self._cleanup_temp_file(temp_file)

    async def render_manifests(
        self,
        chart_ref: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        include_full: bool = False,
        preview_lines: int = 100,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Render Kubernetes manifests from a Helm chart with automatic Secret redaction."""
        try:
            raw_manifests = await self._render_raw_manifests(
                chart_ref=chart_ref,
                namespace=namespace,
                values=values,
                version=version,
                session_id=session_id,
            )
            sanitized = redact_secrets_in_manifests(raw_manifests)
            lines = sanitized.split("\n")
            total_lines = len(lines)

            resource_counts, total_resources = self._summarize_manifest_resources(sanitized)
            clamped_preview = max(10, min(preview_lines, 500))
            preview = "\n".join(lines[:clamped_preview])
            if total_lines > clamped_preview:
                preview += f"\n... ({total_lines - clamped_preview} more lines; set include_full=True to retrieve all)"

            response: Dict[str, Any] = {
                "summary": {
                    "chart_ref": chart_ref,
                    "namespace": namespace,
                    "version": version,
                    "total_resources": total_resources,
                    "resource_types": resource_counts,
                    "total_lines": total_lines,
                    "secrets_redacted": True,
                },
                "preview": preview,
            }
            if include_full:
                response["full_manifests"] = sanitized
            return response
        except HelmOperationError:
            raise
        except Exception as exc:
            raise HelmOperationError(f"Manifest rendering failed for '{chart_ref}': {exc}")

    async def plan_release(
        self,
        chart_ref: str,
        release_name: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """N-to-1 release planner: computes install preview (for new release) or live diff (for existing release)."""
        validated_ref = self.validate_chart_ref(chart_ref)
        exists = await self.release_exists(release_name, namespace, session_id=session_id)
        mode: Literal["install", "upgrade"] = "upgrade" if exists else "install"

        # 1. Render proposed manifests
        proposed_raw = await self._render_raw_manifests(
            chart_ref=validated_ref,
            release_name=release_name,
            namespace=namespace,
            values=values,
            version=version,
            session_id=session_id,
        )
        proposed_sanitized = redact_secrets_in_manifests(proposed_raw)
        resource_counts, total_resources = self._summarize_manifest_resources(proposed_sanitized)

        # 2. Fetch chart metadata & dependencies if chart_ref is repo/chart
        chart_meta: Dict[str, Any] = {}
        if "/" in validated_ref and not validated_ref.startswith(("oci://", "http://", "https://", ".")):
            repo_part, chart_part = validated_ref.split("/", 1)
            try:
                chart_meta = await self.get_chart_info(chart_part, repo_part, version=version)
            except Exception:
                chart_meta = {}

        dependencies = [
            {
                "name": d.get("name"),
                "version": d.get("version"),
                "repository": d.get("repository"),
            }
            for d in (chart_meta.get("dependencies") or [])
            if isinstance(d, dict)
        ]

        plan: Dict[str, Any] = {
            "mode": mode,
            "release_name": release_name,
            "namespace": namespace,
            "chart_ref": validated_ref,
            "chart_version": chart_meta.get("version") or version,
            "app_version": chart_meta.get("appVersion"),
            "kube_version_constraint": chart_meta.get("kubeVersion"),
            "total_resources": total_resources,
            "resource_counts": resource_counts,
            "crd_count": resource_counts.get("CustomResourceDefinition", 0),
            "dependency_count": len(dependencies),
            "dependencies": dependencies,
        }

        if mode == "upgrade":
            current_sanitized = await self.get_release_manifest(
                release_name=release_name,
                namespace=namespace,
                session_id=session_id,
            )
            plan["diff"] = compute_manifest_diff(
                current_manifest=current_sanitized,
                proposed_manifest=proposed_sanitized,
                default_namespace=namespace,
            )
        else:
            # For new installs, compute diff against empty state so added_resources is populated
            plan["diff"] = compute_manifest_diff(
                current_manifest="",
                proposed_manifest=proposed_sanitized,
                default_namespace=namespace,
            )

        return plan

    # ------------------------------------------------------------------
    # Mutating Release Lifecycle Operations
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_mutation_summary(
        full_output: Dict[str, Any],
        release_name: str,
        namespace: str,
    ) -> Dict[str, Any]:
        """Extract concise 6-field summary from helm install/upgrade JSON output."""
        info = full_output.get("info", {}) if isinstance(full_output.get("info"), dict) else {}
        chart = full_output.get("chart", {}) if isinstance(full_output.get("chart"), dict) else {}
        meta = chart.get("metadata", {}) if isinstance(chart.get("metadata"), dict) else {}
        manifest = str(full_output.get("manifest") or "")
        resource_counts, total_resources = HelmService._summarize_manifest_resources(manifest)

        notes = str(info.get("notes") or "")
        if len(notes) > 500:
            notes = notes[:500] + "... (truncated)"

        return {
            "status": info.get("status", "deployed"),
            "release_name": full_output.get("name", release_name),
            "namespace": full_output.get("namespace", namespace),
            "revision": full_output.get("version"),
            "chart": meta.get("name"),
            "chart_version": meta.get("version"),
            "app_version": meta.get("appVersion") or full_output.get("app_version"),
            "total_resources": total_resources,
            "resource_counts": resource_counts,
            "notes": notes or None,
        }

    async def install_chart(
        self,
        chart_ref: str,
        release_name: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        create_namespace: bool = False,
        skip_crds: bool = False,
        wait_timeout: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Install a new Helm release into a Kubernetes namespace."""
        self._check_write_access("install_chart")
        validated_ref = self.validate_chart_ref(chart_ref)

        if await self.release_exists(release_name, namespace, session_id=session_id):
            raise HelmOperationError(
                f"Release '{release_name}' already exists in namespace '{namespace}'. "
                f"Call helm_upgrade_release(release_name='{release_name}', chart_ref='{validated_ref}', namespace='{namespace}') "
                "to update it, or helm_uninstall_release to remove it first."
            )

        temp_file = self._write_temp_values_file(values)
        try:
            args = ["install", release_name, validated_ref, "-n", namespace, "-o", "json"]
            if version:
                args.extend(["--version", version])
            if create_namespace:
                args.append("--create-namespace")
            if skip_crds:
                args.append("--skip-crds")
            if wait_timeout:
                args.extend(["--wait", "--timeout", wait_timeout])
            if temp_file:
                args.extend(["-f", temp_file])

            raw = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            parsed = json.loads(raw) if raw else {}
            return self._extract_mutation_summary(parsed, release_name, namespace)
        except HelmOperationError as exc:
            err_str = str(exc)
            if "invalid ownership metadata" in err_str.lower() or "customresourcedefinition" in err_str.lower():
                raise HelmOperationError(
                    f"CRD ownership conflict while installing '{release_name}' in namespace '{namespace}': {err_str}. "
                    "Retry helm_install_chart with skip_crds=True if compatible CRDs are already installed, "
                    "or call helm_list_releases() to inspect the release that owns the CRDs."
                )
            raise HelmOperationError(f"Installation of '{release_name}' failed: {err_str}")
        finally:
            self._cleanup_temp_file(temp_file)

    async def upgrade_release(
        self,
        release_name: str,
        chart_ref: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        values_strategy: ValuesStrategy = "reuse",
        wait_timeout: Optional[str] = None,
        atomic: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upgrade an existing Helm release."""
        self._check_write_access("upgrade_release")
        validated_ref = self.validate_chart_ref(chart_ref)

        strategy_flag_map = {
            "reuse": "--reuse-values",
            "reset": "--reset-values",
            "reset_then_reuse": "--reset-then-reuse-values",
        }
        if values_strategy not in strategy_flag_map:
            raise HelmOperationError(
                f"Invalid values_strategy '{values_strategy}'. Must be one of: reuse, reset, reset_then_reuse."
            )

        temp_file = self._write_temp_values_file(values)
        try:
            args = [
                "upgrade",
                release_name,
                validated_ref,
                "-n",
                namespace,
                strategy_flag_map[values_strategy],
                "-o",
                "json",
            ]
            if version:
                args.extend(["--version", version])
            if atomic:
                args.append("--atomic")
            if wait_timeout:
                args.extend(["--wait", "--timeout", wait_timeout])
            if temp_file:
                args.extend(["-f", temp_file])

            raw = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            parsed = json.loads(raw) if raw else {}
            return self._extract_mutation_summary(parsed, release_name, namespace)
        except HelmOperationError as exc:
            err_str = str(exc)
            if "has no deployed releases" in err_str.lower() or "not found" in err_str.lower():
                raise HelmOperationError(
                    f"Cannot upgrade '{release_name}' in namespace '{namespace}': {err_str}. "
                    f"Call helm_list_releases(namespace='{namespace}') to verify existing releases or use helm_install_chart."
                )
            raise HelmOperationError(f"Upgrade of '{release_name}' failed: {err_str}")
        finally:
            self._cleanup_temp_file(temp_file)

    async def rollback_release(
        self,
        release_name: str,
        namespace: str = "default",
        revision: Optional[int] = None,
        wait_timeout: Optional[str] = None,
        dry_run: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rollback a Helm release to a previous revision (or preview with dry_run=True)."""
        self._check_write_access("rollback_release", allow_dry_run=True, dry_run=dry_run)

        args = ["rollback", release_name]
        if revision is not None:
            args.append(str(revision))
        args.extend(["-n", namespace])
        if dry_run:
            args.append("--dry-run")
        if wait_timeout:
            args.extend(["--wait", "--timeout", wait_timeout])

        try:
            output = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            return {
                "status": "dry_run_success" if dry_run else "rolled_back",
                "release_name": release_name,
                "namespace": namespace,
                "target_revision": revision,
                "dry_run": dry_run,
                "message": output or ("Rollback dry-run succeeded" if dry_run else "Rollback succeeded"),
            }
        except HelmOperationError as exc:
            raise HelmOperationError(
                f"Rollback of '{release_name}' in namespace '{namespace}' failed: {exc}. "
                f"Read resource 'helm://releases/{namespace}/{release_name}/history' to inspect valid revision numbers."
            )

    async def uninstall_release(
        self,
        release_name: str,
        namespace: str = "default",
        keep_history: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uninstall a Helm release and delete its managed Kubernetes resources."""
        self._check_write_access("uninstall_release")

        args = ["uninstall", release_name, "-n", namespace]
        if keep_history:
            args.append("--keep-history")

        try:
            output = await self._run_helm_command(self._build_cmd(args, session_id=session_id))
            return {
                "status": "uninstalled",
                "release_name": release_name,
                "namespace": namespace,
                "keep_history": keep_history,
                "message": output or f"Release '{release_name}' uninstalled from namespace '{namespace}'.",
            }
        except HelmOperationError as exc:
            raise HelmOperationError(
                f"Uninstall of '{release_name}' in namespace '{namespace}' failed: {exc}. "
                f"Call helm_list_releases(namespace='{namespace}') to verify existing releases."
            )

    # ------------------------------------------------------------------
    # Multi-Layer Deployment Health Monitor (N -> 1)
    # ------------------------------------------------------------------

    async def monitor_deployment_health(
        self,
        release_name: str,
        namespace: str = "default",
        max_wait_seconds: int = 60,
        check_interval: int = 5,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Monitor deployment readiness across Helm status, Deployments/StatefulSets, and Pod containers."""
        clamped_wait = max(1, min(max_wait_seconds, 300))
        clamped_interval = max(1, min(check_interval, 30))

        try:
            start_time = time.time()

            # Layer 1: Helm Release Status Gate (context-aware via _build_cmd)
            helm_status = await self._get_helm_release_status_quick(
                release_name,
                namespace,
                session_id=session_id,
            )
            if helm_status in ("failed", "pending-rollback", "uninstalling"):
                return self._build_monitor_result(
                    status="failed",
                    release_name=release_name,
                    namespace=namespace,
                    duration=int(time.time() - start_time),
                    helm_status=helm_status,
                    issues=[{
                        "severity": "error",
                        "resource": f"release/{release_name}",
                        "reason": f"HelmRelease{helm_status.replace('-', ' ').title().replace(' ', '')}",
                        "message": (
                            f"Helm release is in '{helm_status}' state. "
                            f"Read 'helm://releases/{namespace}/{release_name}/history' for failure details."
                        ),
                    }],
                )

            # Obtain context-aware Kubernetes clients from KubernetesService
            loop = asyncio.get_event_loop()
            if self.k8s_service is not None:
                v1, apps_v1 = await self.k8s_service.get_workload_clients(session_id=session_id)
            else:
                from kubernetes import client, config as k8s_config

                def _load_default_clients():
                    try:
                        k8s_config.load_incluster_config()
                    except Exception:
                        k8s_config.load_kube_config(config_file=self.config.kubernetes.kubeconfig)
                    return client.CoreV1Api(), client.AppsV1Api()

                v1, apps_v1 = await loop.run_in_executor(None, _load_default_clients)

            label_selectors = [
                f"app.kubernetes.io/instance={release_name}",
                f"release={release_name}",
                f"app.kubernetes.io/managed-by=Helm,app.kubernetes.io/name={release_name}",
            ]

            deployment_snapshots: List[Dict[str, Any]] = []
            pod_summary: Dict[str, int] = {
                "total": 0,
                "running": 0,
                "pending": 0,
                "failed": 0,
                "succeeded": 0,
            }
            issues: List[Dict[str, str]] = []

            while True:
                issues = []
                deployment_snapshots = []
                pod_summary = {"total": 0, "running": 0, "pending": 0, "failed": 0, "succeeded": 0}

                workloads_found = False
                all_workloads_ready = True

                for selector in label_selectors:
                    deployments = await loop.run_in_executor(
                        None,
                        lambda sel=selector: apps_v1.list_namespaced_deployment(
                            namespace, label_selector=sel
                        ),
                    )
                    statefulsets = await loop.run_in_executor(
                        None,
                        lambda sel=selector: apps_v1.list_namespaced_stateful_set(
                            namespace, label_selector=sel
                        ),
                    )

                    if deployments.items or statefulsets.items:
                        workloads_found = True
                        for dep in deployments.items:
                            snapshot, dep_issues, dep_ready = self._evaluate_deployment(dep)
                            deployment_snapshots.append(snapshot)
                            issues.extend(dep_issues)
                            if not dep_ready:
                                all_workloads_ready = False

                        for sts in statefulsets.items:
                            snapshot, sts_issues, sts_ready = self._evaluate_statefulset(sts)
                            deployment_snapshots.append(snapshot)
                            issues.extend(sts_issues)
                            if not sts_ready:
                                all_workloads_ready = False
                        break

                pods = None
                for selector in label_selectors:
                    pods = await loop.run_in_executor(
                        None,
                        lambda sel=selector: v1.list_namespaced_pod(
                            namespace, label_selector=sel
                        ),
                    )
                    if pods.items:
                        break

                if pods and pods.items:
                    for pod in pods.items:
                        phase = (pod.status.phase or "Unknown").lower()
                        pod_summary["total"] += 1
                        if phase in pod_summary:
                            pod_summary[phase] += 1
                        issues.extend(self._check_pod_containers(pod))

                terminal_issues = [i for i in issues if i["severity"] == "error"]
                if terminal_issues:
                    return self._build_monitor_result(
                        status="failed",
                        release_name=release_name,
                        namespace=namespace,
                        duration=int(time.time() - start_time),
                        helm_status=helm_status,
                        deployments=deployment_snapshots,
                        pod_summary=pod_summary,
                        issues=issues,
                    )

                if workloads_found and all_workloads_ready and pod_summary["total"] > 0:
                    return self._build_monitor_result(
                        status="ready",
                        release_name=release_name,
                        namespace=namespace,
                        duration=int(time.time() - start_time),
                        helm_status=helm_status,
                        deployments=deployment_snapshots,
                        pod_summary=pod_summary,
                        issues=issues,
                    )

                if not workloads_found and pods and pods.items:
                    if all(self._is_pod_ready(pod) for pod in pods.items) and pod_summary["total"] > 0:
                        return self._build_monitor_result(
                            status="ready",
                            release_name=release_name,
                            namespace=namespace,
                            duration=int(time.time() - start_time),
                            helm_status=helm_status,
                            deployments=deployment_snapshots,
                            pod_summary=pod_summary,
                            issues=issues,
                        )

                if time.time() - start_time >= clamped_wait:
                    break

                await asyncio.sleep(clamped_interval)

            return self._build_monitor_result(
                status="timeout",
                release_name=release_name,
                namespace=namespace,
                duration=int(time.time() - start_time),
                helm_status=helm_status,
                deployments=deployment_snapshots,
                pod_summary=pod_summary,
                issues=issues if issues else [{
                    "severity": "warning",
                    "resource": f"release/{release_name}",
                    "reason": "Timeout",
                    "message": f"Deployment did not become ready within {clamped_wait}s",
                }],
            )
        except HelmOperationError:
            raise
        except Exception as exc:
            raise HelmOperationError(f"Deployment monitoring failed for '{release_name}': {exc}")

    async def _get_helm_release_status_quick(
        self,
        release_name: str,
        namespace: str,
        session_id: Optional[str] = None,
    ) -> str:
        """Fetch only the Helm release status string."""
        try:
            cmd = self._build_cmd(
                ["status", release_name, "-n", namespace, "-o", "json"],
                session_id=session_id,
            )
            raw = await self._run_helm_command(cmd)
            data = json.loads(raw) if raw else {}
            return str(data.get("info", {}).get("status", "unknown"))
        except Exception:
            return "unknown"

    @staticmethod
    def _build_monitor_result(
        *,
        status: str,
        release_name: str,
        namespace: str,
        duration: int,
        helm_status: str,
        deployments: Optional[List[Dict[str, Any]]] = None,
        pod_summary: Optional[Dict[str, int]] = None,
        issues: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "release_name": release_name,
            "namespace": namespace,
            "duration_seconds": duration,
            "helm_status": helm_status,
            "deployments": deployments or [],
            "pod_summary": pod_summary or {},
            "issues": issues or [],
        }

    @staticmethod
    def _evaluate_deployment(dep: Any) -> tuple:
        spec_replicas = dep.spec.replicas if dep.spec.replicas is not None else 1
        status = dep.status
        updated = status.updated_replicas or 0
        ready = status.ready_replicas or 0
        available = status.available_replicas or 0
        unavailable = status.unavailable_replicas or 0

        conditions = []
        issues = []
        rollout_complete = False

        for cond in status.conditions or []:
            conditions.append({
                "type": cond.type,
                "status": cond.status,
                "reason": cond.reason or "",
                "message": cond.message or "",
            })
            if (
                cond.type == "Progressing"
                and cond.status == "False"
                and cond.reason == "ProgressDeadlineExceeded"
            ):
                issues.append({
                    "severity": "error",
                    "resource": f"deployment/{dep.metadata.name}",
                    "reason": "ProgressDeadlineExceeded",
                    "message": cond.message or "Deployment exceeded its progress deadline",
                })
            if (
                cond.type == "Progressing"
                and cond.status == "True"
                and cond.reason == "NewReplicaSetAvailable"
            ):
                rollout_complete = True

        numerically_ready = (
            updated >= spec_replicas
            and ready >= spec_replicas
            and available >= spec_replicas
            and unavailable == 0
        )
        is_ready = (rollout_complete or numerically_ready) and not issues

        snapshot = {
            "name": dep.metadata.name,
            "kind": "Deployment",
            "replicas": spec_replicas,
            "ready_replicas": ready,
            "updated_replicas": updated,
            "available_replicas": available,
            "unavailable_replicas": unavailable,
            "rollout_complete": is_ready,
            "conditions": conditions,
        }
        return snapshot, issues, is_ready

    @staticmethod
    def _evaluate_statefulset(sts: Any) -> tuple:
        spec_replicas = sts.spec.replicas if sts.spec.replicas is not None else 1
        status = sts.status
        ready = status.ready_replicas or 0
        updated = status.updated_replicas or 0
        current = status.current_replicas or 0

        issues: List[Dict[str, str]] = []
        conditions = []
        for cond in status.conditions or []:
            conditions.append({
                "type": cond.type,
                "status": cond.status,
                "reason": cond.reason or "",
                "message": cond.message or "",
            })

        is_ready = updated >= spec_replicas and ready >= spec_replicas and current >= spec_replicas

        update_strategy = sts.spec.update_strategy
        if update_strategy and update_strategy.type == "RollingUpdate":
            partition = (
                update_strategy.rolling_update.partition
                if update_strategy.rolling_update
                else 0
            ) or 0
            if partition > 0:
                expected_updated = spec_replicas - partition
                is_ready = updated >= expected_updated and ready >= spec_replicas

        snapshot = {
            "name": sts.metadata.name,
            "kind": "StatefulSet",
            "replicas": spec_replicas,
            "ready_replicas": ready,
            "updated_replicas": updated,
            "current_replicas": current,
            "rollout_complete": is_ready,
            "conditions": conditions,
        }
        return snapshot, issues, is_ready

    def _check_pod_containers(self, pod: Any) -> List[Dict[str, str]]:
        issues = []
        pod_name = pod.metadata.name

        all_statuses = list(pod.status.container_statuses or [])
        all_statuses.extend(pod.status.init_container_statuses or [])

        for cs in all_statuses:
            if cs.state and cs.state.waiting:
                reason = cs.state.waiting.reason or ""
                if reason in self.TERMINAL_CONTAINER_STATES:
                    issues.append({
                        "severity": "error",
                        "resource": f"pod/{pod_name}/container/{cs.name}",
                        "reason": reason,
                        "message": cs.state.waiting.message or f"Container '{cs.name}' is in {reason} state",
                    })

            if cs.state and cs.state.terminated:
                term_reason = cs.state.terminated.reason or ""
                if term_reason == "OOMKilled" and (cs.restart_count or 0) >= 3:
                    issues.append({
                        "severity": "error",
                        "resource": f"pod/{pod_name}/container/{cs.name}",
                        "reason": "OOMKilledRecurring",
                        "message": (
                            f"Container '{cs.name}' has been OOMKilled {cs.restart_count} times. "
                            "Increase resources.limits.memory."
                        ),
                    })

            if (cs.restart_count or 0) >= 5 and not issues:
                last_reason = ""
                if cs.last_state and cs.last_state.terminated:
                    last_reason = cs.last_state.terminated.reason or "Unknown"
                issues.append({
                    "severity": "warning",
                    "resource": f"pod/{pod_name}/container/{cs.name}",
                    "reason": "HighRestartCount",
                    "message": (
                        f"Container '{cs.name}' has restarted {cs.restart_count} times. "
                        f"Last termination reason: {last_reason or 'unknown'}"
                    ),
                })

        for cond in pod.status.conditions or []:
            if cond.type == "PodScheduled" and cond.status == "False":
                issues.append({
                    "severity": "error",
                    "resource": f"pod/{pod_name}",
                    "reason": cond.reason or "SchedulingFailed",
                    "message": cond.message or "Pod could not be scheduled",
                })

        return issues

    @staticmethod
    def _is_pod_ready(pod: Any) -> bool:
        if pod.status.phase != "Running":
            return False
        conditions = pod.status.conditions or []
        if not conditions:
            return False
        return any(c.type == "Ready" and c.status == "True" for c in conditions)
