"""Kubernetes operations service with per-session context isolation and real prerequisite discovery."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from helm_mcp_server.config import ServerConfig
from helm_mcp_server.exceptions import KubernetesOperationError
from helm_mcp_server.utils.helm_helper import compare_k8s_versions


class KubernetesService:
    """Service for Kubernetes cluster inspection, context management, and prerequisite discovery."""

    def __init__(self, config: ServerConfig):
        """Initialize with server configuration."""
        self.config = config
        self._session_contexts: Dict[str, str] = {}
        self._client_cache: Dict[str, Tuple[Any, Any, Any, Any]] = {}

    @staticmethod
    def _normalize_session_id(session_id: Optional[str] = None) -> str:
        """Return normalized session key."""
        return str(session_id).strip() if session_id else "default"

    def get_active_context(self, session_id: Optional[str] = None) -> Optional[str]:
        """Return the active Kubernetes context for the given session (or default session fallback)."""
        key = self._normalize_session_id(session_id)
        if key in self._session_contexts:
            return self._session_contexts[key]
        return self._session_contexts.get("default")

    def _get_api_clients(self, session_id: Optional[str] = None) -> Tuple[Any, Any, Any, Any]:
        """Lazy-load Kubernetes API clients (CoreV1Api, AppsV1Api, VersionApi, ApisApi) for the active context."""
        active_context = self.get_active_context(session_id)
        cache_key = active_context or "__default__"

        if cache_key not in self._client_cache:
            try:
                from kubernetes import client, config as k8s_config
            except Exception as exc:
                raise KubernetesOperationError(f"Kubernetes Python client is not available: {exc}")

            api_client = None
            loaded = False

            # If an explicit context was selected, load kubeconfig with that context first
            if active_context:
                try:
                    if hasattr(k8s_config, "new_client_from_config"):
                        api_client = k8s_config.new_client_from_config(
                            config_file=self.config.kubernetes.kubeconfig,
                            context=active_context,
                        )
                    else:
                        k8s_config.load_kube_config(
                            config_file=self.config.kubernetes.kubeconfig,
                            context=active_context,
                        )
                    loaded = True
                except Exception as exc:
                    raise KubernetesOperationError(
                        f"Failed to load Kubernetes context '{active_context}': {exc}. "
                        "Read resource 'kubernetes://contexts' to inspect valid contexts."
                    )

            if not loaded:
                try:
                    k8s_config.load_incluster_config()
                    loaded = True
                except Exception:
                    try:
                        k8s_config.load_kube_config(
                            config_file=self.config.kubernetes.kubeconfig,
                        )
                        loaded = True
                    except Exception as exc:
                        raise KubernetesOperationError(
                            f"Failed to load Kubernetes configuration: {exc}. "
                            "Verify KUBECONFIG is valid or read 'kubernetes://contexts'."
                        )

            core_v1 = client.CoreV1Api(api_client) if api_client is not None else client.CoreV1Api()
            apps_v1 = client.AppsV1Api(api_client) if api_client is not None else client.AppsV1Api()
            version_api = client.VersionApi(api_client) if api_client is not None else client.VersionApi()
            apis_api = client.ApisApi(api_client) if hasattr(client, "ApisApi") else None

            self._client_cache[cache_key] = (core_v1, apps_v1, version_api, apis_api)

        return self._client_cache[cache_key]

    async def get_workload_clients(self, session_id: Optional[str] = None) -> Tuple[Any, Any]:
        """Return (CoreV1Api, AppsV1Api) bound to the session's active Kubernetes context."""
        loop = asyncio.get_event_loop()
        core_v1, apps_v1, _, _ = await loop.run_in_executor(
            None,
            self._get_api_clients,
            session_id,
        )
        return core_v1, apps_v1

    async def get_cluster_info(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get Kubernetes cluster version, node summary, namespace summary, and active context."""
        try:
            loop = asyncio.get_event_loop()
            core_v1, _, version_api, _ = await loop.run_in_executor(
                None,
                self._get_api_clients,
                session_id,
            )

            version = await loop.run_in_executor(None, version_api.get_code)
            nodes = await loop.run_in_executor(None, core_v1.list_node)
            namespaces = await loop.run_in_executor(None, core_v1.list_namespace)

            return {
                "kubernetes_version": version.git_version,
                "active_context": self.get_active_context(session_id),
                "node_count": len(nodes.items),
                "nodes": [n.metadata.name for n in nodes.items],
                "namespace_count": len(namespaces.items),
                "namespaces": [ns.metadata.name for ns in namespaces.items],
            }
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(
                f"Failed to get cluster info: {exc}. "
                "Verify cluster reachability or switch context via 'kubernetes_set_context'."
            )

    async def list_namespaces(self, session_id: Optional[str] = None) -> List[str]:
        """List all Kubernetes namespace names in the active cluster."""
        try:
            loop = asyncio.get_event_loop()
            core_v1, _, _, _ = await loop.run_in_executor(
                None,
                self._get_api_clients,
                session_id,
            )
            namespaces = await loop.run_in_executor(None, core_v1.list_namespace)
            return [ns.metadata.name for ns in namespaces.items]
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(
                f"Failed to list namespaces: {exc}. "
                "Verify cluster connectivity via 'kubernetes://cluster-info'."
            )

    async def list_contexts(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """List all available Kubernetes contexts from kubeconfig."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._get_kube_contexts,
                self.config.kubernetes.kubeconfig,
                session_id,
            )
            return result
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(f"Failed to list contexts: {exc}")

    def _get_kube_contexts(
        self,
        kubeconfig_path: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve Kubernetes contexts from kubeconfig."""
        try:
            from kubernetes import config as k8s_config

            result = k8s_config.list_kube_config_contexts(config_file=kubeconfig_path)
            if result is None:
                raise KubernetesOperationError(
                    "Failed to retrieve Kubernetes contexts from kubeconfig: file is empty or inaccessible."
                )

            contexts, active_context = result
            kubeconfig_current = active_context.get("name") if isinstance(active_context, dict) else None
            session_active = self.get_active_context(session_id) or kubeconfig_current

            formatted_contexts = []
            for context in contexts:
                ctx_dict = cast(Dict[str, Any], context)
                context_name = ctx_dict.get("name", "unknown")
                context_info = ctx_dict.get("context", {})
                formatted_contexts.append({
                    "name": context_name,
                    "cluster": context_info.get("cluster", ""),
                    "user": context_info.get("user", ""),
                    "namespace": context_info.get("namespace", "default"),
                    "is_current": context_name == session_active,
                })

            return {
                "contexts": formatted_contexts,
                "current_context": session_active,
                "total_contexts": len(formatted_contexts),
            }
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(f"Failed to retrieve Kubernetes contexts: {exc}")

    async def set_context(
        self,
        context_name: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Switch the active Kubernetes context for the current session."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._switch_kube_context,
                context_name,
                self.config.kubernetes.kubeconfig,
                session_id,
            )
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(f"Failed to set context: {exc}")

    def _switch_kube_context(
        self,
        context_name: str,
        kubeconfig_path: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and switch Kubernetes context for the target session."""
        try:
            from kubernetes import config as k8s_config

            result = k8s_config.list_kube_config_contexts(config_file=kubeconfig_path)
            if result is None:
                raise KubernetesOperationError(
                    "Failed to retrieve Kubernetes contexts from kubeconfig."
                )

            contexts, _ = result
            target_context = None
            for ctx in contexts:
                ctx_dict = cast(Dict[str, Any], ctx)
                if ctx_dict.get("name") == context_name:
                    target_context = ctx_dict
                    break

            if not target_context:
                available = [str(cast(Dict[str, Any], c).get("name", "")) for c in contexts]
                raise KubernetesOperationError(
                    f"Context '{context_name}' not found in kubeconfig. "
                    f"Available contexts: {', '.join(available)}. "
                    "Read resource 'kubernetes://contexts' to inspect valid context names."
                )

            # Validate kubeconfig loads cleanly for this context
            k8s_config.load_kube_config(
                config_file=kubeconfig_path,
                context=context_name,
            )

            norm_session = self._normalize_session_id(session_id)
            self._session_contexts[norm_session] = context_name
            if norm_session != "default":
                # Also set default fallback if not set yet so background tasks without session ID inherit it
                self._session_contexts.setdefault("default", context_name)

            # Invalidate cached API client for this context so it is freshly created on next use
            self._client_cache.pop(context_name, None)

            context_details = target_context.get("context", {})
            return {
                "success": True,
                "context_name": context_name,
                "session_id": norm_session,
                "context_details": {
                    "cluster": context_details.get("cluster", ""),
                    "user": context_details.get("user", ""),
                    "namespace": context_details.get("namespace", "default"),
                },
                "message": f"Context switched to '{context_name}' for session '{norm_session}'",
            }
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(f"Failed to switch Kubernetes context: {exc}")

    def _discover_cluster_kinds(
        self,
        core_v1: Any,
        apps_v1: Any,
        apis_api: Any,
    ) -> Set[str]:
        """Discover API resource kinds supported by the cluster via Kubernetes Discovery APIs."""
        discovered_kinds: Set[str] = set()

        # 1. Core v1 resources
        try:
            core_res = core_v1.get_api_resources()
            for res in getattr(core_res, "resources", None) or []:
                kind = getattr(res, "kind", None)
                name = getattr(res, "name", None)
                if isinstance(kind, str) and kind:
                    discovered_kinds.add(kind)
                if isinstance(name, str) and name and "/" not in name:
                    discovered_kinds.add(name)
        except Exception:
            pass

        # 2. Apps v1 resources
        try:
            apps_res = apps_v1.get_api_resources()
            for res in getattr(apps_res, "resources", None) or []:
                kind = getattr(res, "kind", None)
                if isinstance(kind, str) and kind:
                    discovered_kinds.add(kind)
        except Exception:
            pass

        # 3. APIGroup discovery (CRDs, networking.k8s.io, rbac.authorization.k8s.io, etc.)
        if apis_api is not None:
            try:
                groups_resp = apis_api.get_api_versions()
                for group in getattr(groups_resp, "groups", None) or []:
                    group_name = getattr(group, "name", "")
                    if group_name:
                        discovered_kinds.add(group_name)
                    pref = getattr(group, "preferred_version", None)
                    group_version = getattr(pref, "group_version", None) if pref else None
                    if group_version:
                        discovered_kinds.add(group_version)
                    for ver in getattr(group, "versions", None) or []:
                        gv = getattr(ver, "group_version", None)
                        if gv:
                            discovered_kinds.add(gv)
            except Exception:
                pass

        # 4. CustomResourceDefinitions check if CustomObjectsApi or ApiextensionsV1Api is available
        try:
            from kubernetes import client

            if hasattr(client, "ApiextensionsV1Api"):
                ext_api = client.ApiextensionsV1Api(getattr(core_v1, "api_client", None))
                crds = ext_api.list_custom_resource_definition()
                for crd in getattr(crds, "items", None) or []:
                    spec = getattr(crd, "spec", None)
                    names = getattr(spec, "names", None) if spec else None
                    crd_kind = getattr(names, "kind", None) if names else None
                    crd_name = getattr(getattr(crd, "metadata", None), "name", None)
                    if isinstance(crd_kind, str) and crd_kind:
                        discovered_kinds.add(crd_kind)
                    if isinstance(crd_name, str) and crd_name:
                        discovered_kinds.add(crd_name)
        except Exception:
            pass

        return discovered_kinds

    async def check_prerequisites(
        self,
        min_kubernetes_version: Optional[str] = None,
        required_api_resources: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check if the cluster meets minimum Kubernetes version and API resource/CRD requirements."""
        try:
            loop = asyncio.get_event_loop()
            core_v1, apps_v1, version_api, apis_api = await loop.run_in_executor(
                None,
                self._get_api_clients,
                session_id,
            )

            version = await loop.run_in_executor(None, version_api.get_code)
            cluster_version = str(version.git_version)

            api_version_ok = True
            if min_kubernetes_version:
                api_version_ok = compare_k8s_versions(cluster_version, min_kubernetes_version)

            available_resources: List[str] = []
            missing_resources: List[str] = []

            if required_api_resources:
                discovered_kinds = await loop.run_in_executor(
                    None,
                    self._discover_cluster_kinds,
                    core_v1,
                    apps_v1,
                    apis_api,
                )
                discovered_lower = {k.lower() for k in discovered_kinds}

                for req in required_api_resources:
                    if req.lower() in discovered_lower:
                        available_resources.append(req)
                    else:
                        missing_resources.append(req)

            all_prerequisites_met = api_version_ok and len(missing_resources) == 0

            return {
                "status": "success",
                "cluster_version": cluster_version,
                "active_context": self.get_active_context(session_id),
                "api_version_check": {
                    "required": min_kubernetes_version,
                    "current": cluster_version,
                    "meets_requirement": api_version_ok,
                },
                "resource_check": {
                    "required": required_api_resources or [],
                    "available": available_resources,
                    "missing": missing_resources,
                    "all_available": len(missing_resources) == 0,
                },
                "all_prerequisites_met": all_prerequisites_met,
            }
        except KubernetesOperationError:
            raise
        except Exception as exc:
            raise KubernetesOperationError(
                f"Prerequisites check failed: {exc}. "
                "Verify cluster connectivity via 'kubernetes://cluster-info'."
            )
