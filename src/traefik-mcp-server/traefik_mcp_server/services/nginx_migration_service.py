"""NGINX migration service — orchestrates scan → analyze → migrate → apply.

Business logic layer for the native NGINX-to-Traefik migration pipeline.
"""

import yaml as pyyaml
from typing import Any, Dict, List, Optional

from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client import (
    CustomObjectsApi,
    NetworkingV1Api,
    CoreV1Api,
)
from kubernetes.client.rest import ApiException

from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.services.traefik_service import (
    TraefikService,
    parse_multidoc_yaml_objects,
)
from traefik_mcp_server.migration_nginx.scanner import (
    NginxMigrationScanner,
    ScanResult,
    scan_result_to_dict,
)
from traefik_mcp_server.migration_nginx.analyzer import (
    NginxMigrationAnalyzer,
    AnalysisReport,
    analysis_report_to_dict,
)
from traefik_mcp_server.migration_nginx.migration_plan import (
    apply_plan_to_analysis,
    parse_migration_plan,
)
from traefik_mcp_server.migration_nginx.migrator_traefik import (
    TraefikMigrator,
    GeneratedFile,
    generate_middlewares,
    generate_servers_transports,
    generate_service_patches,
)
from traefik_mcp_server.migration_nginx.migrator_gateway_api import (
    GatewayAPIMigrator,
)
from traefik_mcp_server.migration_nginx.generator import (
    bundle_migration_output,
    generate_migration_report,
)


# Merged into migrate() return for internal use; omitted from MCP **tool** JSON so
# clients stay under typical inline limits — full report via Resources.
MIGRATE_RESPONSE_ANALYSIS_KEYS = frozenset({"target", "ingressReports", "summary"})


def slim_migrate_tool_payload(full: Dict[str, Any], namespace: str) -> Dict[str, Any]:
    """Strip analysis fields from migrate tool output; point agents at analyze resources."""
    out = {k: v for k, v in full.items() if k not in MIGRATE_RESPONSE_ANALYSIS_KEYS}
    out["compatibilityReport"] = {
        "schema": "traefik.mcp/nginx-ingress-analyze/1",
        "readResourceClusterUri": "traefik://migration/nginx-ingress-analyze",
        "readResourceNamespaceUri": f"traefik://migration/nginx-ingress-analyze/{namespace}",
        "note": (
            "Full per-annotation compatibility: read_resource on the URIs above "
            "(not returned inline on this tool to avoid client size limits)."
        ),
    }
    return out


class NginxMigrationService:
    """Orchestrates the native NGINX → Traefik migration pipeline.

    Provides three high-level operations:
      scan()    — discover Ingress objects and detect the controller
      analyze() — classify every nginx annotation for the target controller
      migrate() — generate bundles; apply Middleware + Ingress patches for ``target=traefik`` only
    """

    TRAEFIK_CRD_GROUP = "traefik.io"
    TRAEFIK_CRD_VERSION = "v1alpha1"
    TRAEFIK_MIDDLEWARE_PLURAL = "middlewares"
    TRAEFIK_SERVERSTRANSPORT_PLURAL = "serverstransports"

    def __init__(self, config: ServerConfig, traefik_service: TraefikService):
        self.config = config
        self._traefik = traefik_service
        self._networking: Optional[NetworkingV1Api] = None
        self._core: Optional[CoreV1Api] = None
        self._custom: Optional[CustomObjectsApi] = None
        # Rollback cache: {"namespace/name": {original annotations dict}}
        self._rollback_cache: Dict[str, Dict[str, str]] = {}
        # Service patch rollback: {"namespace/ingress_name": [(svc_ns, svc_name, [annotation_keys])]}
        self._service_patch_cache: Dict[str, List[tuple]] = {}

    # ── Lazy Kubernetes client init ────────────────────────────────────────

    def _ensure_clients(self):
        """Initialise Kubernetes API clients lazily using the same kubeconfig
        pattern as TraefikService.
        """
        if self._networking is not None:
            return

        assert self.config.kubernetes is not None
        try:
            if self.config.kubernetes.in_cluster:
                k8s_config.load_incluster_config()
            else:
                k8s_config.load_kube_config(
                    config_file=self.config.kubernetes.kubeconfig,
                    context=self.config.kubernetes.context_name,
                )
        except Exception:
            # Fallback: try in-cluster, then default kubeconfig
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        self._networking = NetworkingV1Api()
        self._core = CoreV1Api()
        self._custom = CustomObjectsApi()

    @property
    def networking_api(self) -> NetworkingV1Api:
        self._ensure_clients()
        assert self._networking is not None
        return self._networking

    @property
    def core_api(self) -> CoreV1Api:
        self._ensure_clients()
        assert self._core is not None
        return self._core

    @property
    def custom_api(self) -> CustomObjectsApi:
        self._ensure_clients()
        assert self._custom is not None
        return self._custom

    # ── Public API ─────────────────────────────────────────────────────────

    async def scan(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Scan the cluster for NGINX Ingress resources.

        Args:
            namespace: Limit to a single namespace; None = all.

        Returns:
            ScanResult as JSON-serializable dict.
        """
        scanner = NginxMigrationScanner(
            networking_api=self.networking_api,
            core_api=self.core_api,
            cluster_name=self._get_cluster_name(),
        )
        result = scanner.scan(namespace=namespace)
        return scan_result_to_dict(result)

    async def analyze(
        self,
        namespace: Optional[str] = None,
        target: str = "traefik",
    ) -> Dict[str, Any]:
        """Scan + analyze annotations for the given target.

        Returns the analysis schema at the **root** (``target``, ``ingressReports``,
        ``summary``) — same shape as ``analysis_report_to_dict``.  Cluster inventory
        (paths, annotation values) lives on MCP resource
        ``traefik://migration/nginx-ingress-scan``.

        Args:
            namespace: Optional namespace filter.
            target: "traefik" or "gateway-api".

        Returns:
            Analysis report dict (no ``scan_result`` wrapper).
        """
        self._ensure_clients()

        scanner = NginxMigrationScanner(
            networking_api=self.networking_api,
            core_api=self.core_api,
            cluster_name=self._get_cluster_name(),
        )
        scan_result = scanner.scan(namespace=namespace)

        analyzer = NginxMigrationAnalyzer(target=target)
        analysis = analyzer.analyze(scan_result)

        return analysis_report_to_dict(analysis)

    async def generate_runbook(
        self,
        namespace: Optional[str] = None,
        target: str = "traefik",
    ) -> str:
        """Scan → analyze → generate runbook (read-only, no apply).

        This is the read-only pipeline used by the MCP resource endpoint.
        For mutations (apply) or agent overrides (migration_plan), use
        ``migrate()`` instead.

        Args:
            namespace: Optional namespace filter.
            target: ``traefik`` or ``gateway-api``.

        Returns:
            Markdown runbook string with inline YAML.
        """
        self._ensure_clients()

        scanner = NginxMigrationScanner(
            networking_api=self.networking_api,
            core_api=self.core_api,
            cluster_name=self._get_cluster_name(),
        )
        scan_result = scanner.scan(namespace=namespace)

        analyzer = NginxMigrationAnalyzer(target=target)
        analysis = analyzer.analyze(scan_result)

        if target == "gateway-api":
            migrator = GatewayAPIMigrator()
        else:
            migrator = TraefikMigrator()
        files = migrator.migrate(scan_result, analysis)

        return generate_migration_report(scan_result, analysis, files=files)

    async def migrate(
        self,
        namespace: Optional[str] = None,
        target: str = "traefik",
        apply: bool = False,
        switch: bool = False,
        migration_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Scan → analyze → migrate → (optionally) apply.

        Args:
            namespace: Optional namespace filter.
            target: ``traefik`` or ``gateway-api``.
            apply: If True and ``target=traefik``, create Middleware CRDs and
                strategic-merge patch Ingress (metadata + spec). Requires
                MCP_ALLOW_WRITE=true.
            switch: If True, patch the `ingressClassName` to `traefik` for all
                ingresses in the namespace that have Traefik middlewares.
                supported in V1 — the server returns ``apply_result`` with
                ``status=skipped`` and a clear message (no cluster mutations).
            migration_plan: Optional per-Ingress overrides from the agent: map ingress
                name (or ``namespace/name``) to ``{"ignore_annotations": [...],
                "inject_middlewares": [...]}``. Ignored keys are excluded from
                analysis/middleware generation; inject refs append to router middlewares.

        Returns:
            Migration bundle dict with files, summary, and apply_result if applicable.
        """
        if target not in ("traefik", "gateway-api"):
            return {
                "status": "error",
                "error": f"Target '{target}' is not supported. Use 'traefik' or 'gateway-api'.",
            }

        self._ensure_clients()

        # 1. Scan
        scanner = NginxMigrationScanner(
            networking_api=self.networking_api,
            core_api=self.core_api,
            cluster_name=self._get_cluster_name(),
        )
        scan_result = scanner.scan(namespace=namespace)

        # 2. Analyze
        analyzer = NginxMigrationAnalyzer(target=target)
        analysis = analyzer.analyze(scan_result)

        parsed_plan = parse_migration_plan(migration_plan)
        if parsed_plan:
            analysis = apply_plan_to_analysis(analysis, parsed_plan)

        # 3. Migrate (generate files) — select migrator based on target
        if target == "gateway-api":
            migrator = GatewayAPIMigrator()
        else:
            migrator = TraefikMigrator()
        files = migrator.migrate(scan_result, analysis, migration_plan=migration_plan)

        # 4. Bundle as runbook (migration output); analysis at root with analyze()
        analysis_dict = analysis_report_to_dict(analysis)
        bundle = bundle_migration_output(files, scan_result, analysis, migration_plan=migration_plan)
        bundle["status"] = "success"

        out: Dict[str, Any] = {**analysis_dict, **bundle}
        
        # 5. Switch if requested
        if switch:
            if not self.config.allow_write:
                out["switch_result"] = {
                    "status": "blocked",
                    "error": "switch=True requires MCP_ALLOW_WRITE=true. Set the variable and restart.",
                }
            elif target == "gateway-api":
                out["switch_result"] = {
                    "status": "skipped",
                    "reason": "gateway_api_switch_not_supported",
                    "message": "switch=True is not supported for Gateway API."
                }
            else:
                out["switch_result"] = await self._apply_switch(scan_result)

        # 6. Apply if requested (Traefik-Ingress path only; Gateway API is generate-only in V1)
        if apply and not switch:
            if not self.config.allow_write:
                out["apply_result"] = {
                    "status": "blocked",
                    "error": (
                        "apply=True requires MCP_ALLOW_WRITE=true. "
                        "Set the environment variable and restart the server."
                    ),
                }
            elif target == "gateway-api":
                out["apply_result"] = {
                    "status": "skipped",
                    "reason": "gateway_api_apply_not_supported",
                    "message": (
                        "apply=True is not supported for target=gateway-api in V1. "
                        "This server only applies Traefik Middleware CRDs and "
                        "strategic-merge patches to Ingress resources. "
                        "Apply Gateway, HTTPRoute, and optional TraefikService "
                        "(shadow) YAML from the bundle using kubectl, GitOps, or CI."
                    ),
                }
            else:
                apply_result = await self._apply_migration(scan_result, files)
                out["apply_result"] = apply_result

        return out

    # ── Cluster apply ──────────────────────────────────────────────────────
    
    async def _apply_switch(self, scan_result: ScanResult) -> Dict[str, Any]:
        """Perform a hard cutover by patching ingressClassName to traefik."""
        results = []
        for ing in scan_result.ingresses:
            try:
                # Retrieve live ingress as Any to suppress kubernetes union type stubs
                live: Any = self.networking_api.read_namespaced_ingress(
                    name=ing.name, namespace=ing.namespace
                )
                
                # Check if it has been migrated (has the router.middlewares annotation)
                annotations = live.metadata.annotations or {}
                has_traefik_middlewares = any(k.startswith("traefik.ingress.kubernetes.io") for k in annotations.keys())
                
                if not has_traefik_middlewares:
                    results.append({"name": ing.name, "namespace": ing.namespace, "status": "skipped", "reason": "No Traefik annotations found"})
                    continue
                
                patch_body = {"spec": {"ingressClassName": "traefik"}}
                self.networking_api.patch_namespaced_ingress(
                    name=ing.name,
                    namespace=ing.namespace,
                    body=patch_body,
                )
                results.append({"name": ing.name, "namespace": ing.namespace, "status": "applied", "action": "switched"})
            except ApiException as e:
                results.append({"name": ing.name, "namespace": ing.namespace, "status": "error", "error": str(e)})

        return {
            "status": "success",
            "results": results,
            "summary": {
                "switched": sum(1 for r in results if r.get("status") == "applied"),
                "errors": sum(1 for r in results if r.get("status") == "error"),
            }
        }

    async def _apply_migration(
        self,
        scan_result: ScanResult,
        files: List[GeneratedFile],
    ) -> Dict[str, Any]:
        """Apply generated Middleware CRDs and strategic-merge patch Ingresses.

        Ingress patch includes metadata.annotations and spec when present in the
        generated manifest.

        Returns:
            Dict with middleware_results and ingress_results.
        """
        # Cache original annotations for rollback before patching
        await self._cache_original_annotations(scan_result)

        middleware_results = []
        ingress_results = []
        serverstransport_results = []
        service_patch_results = []

        # Apply middleware files
        for f in files:
            if f.category != "middleware":
                continue
            results = await self._apply_middleware_file(f)
            middleware_results.extend(results)

        # Apply ServersTransport files
        for f in files:
            if f.category != "serverstransport":
                continue
            results = await self._apply_serverstransport_file(f)
            serverstransport_results.extend(results)

        # Apply Service sticky session patches
        for f in files:
            if f.category != "service_patch":
                continue
            # Derive ingress key from file path for rollback tracking
            ingress_key = self._ingress_key_from_service_patch(f, scan_result)
            result = await self._apply_service_patch_file(f, ingress_key=ingress_key)
            service_patch_results.append(result)

        # Apply updated ingress files
        for f in files:
            if f.category != "ingress":
                continue
            result = await self._apply_ingress_file(f)
            ingress_results.append(result)

        all_results = middleware_results + serverstransport_results + service_patch_results + ingress_results
        applied_count = sum(1 for r in all_results if r.get("status") == "applied")
        error_count = sum(1 for r in all_results if r.get("status") == "error")

        return {
            "middleware_results": middleware_results,
            "serverstransport_results": serverstransport_results,
            "service_patch_results": service_patch_results,
            "ingress_results": ingress_results,
            "summary": {
                "applied": applied_count,
                "errors": error_count,
            },
        }

    async def _apply_middleware_file(self, gf: GeneratedFile) -> List[Dict[str, Any]]:
        """Parse multi-doc YAML and create/update each Middleware CRD."""
        results = []
        docs = gf.content.split("---")

        for doc in docs:
            doc = doc.strip()
            if not doc:
                continue
            try:
                obj = pyyaml.safe_load(doc)
                if not obj or obj.get("kind") != "Middleware":
                    continue

                name = obj["metadata"]["name"]
                namespace = obj["metadata"].get("namespace", "default")

                try:
                    # Try create first
                    self.custom_api.create_namespaced_custom_object(
                        group=self.TRAEFIK_CRD_GROUP,
                        version=self.TRAEFIK_CRD_VERSION,
                        namespace=namespace,
                        plural=self.TRAEFIK_MIDDLEWARE_PLURAL,
                        body=obj,
                    )
                    results.append({
                        "name": name,
                        "namespace": namespace,
                        "status": "applied",
                        "action": "created",
                    })
                except ApiException as e:
                    if e.status == 409:
                        # Already exists — update
                        self.custom_api.patch_namespaced_custom_object(
                            group=self.TRAEFIK_CRD_GROUP,
                            version=self.TRAEFIK_CRD_VERSION,
                            namespace=namespace,
                            plural=self.TRAEFIK_MIDDLEWARE_PLURAL,
                            name=name,
                            body=obj,
                        )
                        results.append({
                            "name": name,
                            "namespace": namespace,
                            "status": "applied",
                            "action": "updated",
                        })
                    else:
                        results.append({
                            "name": name,
                            "namespace": namespace,
                            "status": "error",
                            "error": str(e),
                        })
            except Exception as e:
                results.append({
                    "file": gf.rel_path,
                    "status": "error",
                    "error": f"YAML parse error: {e}",
                })

        return results

    async def _apply_ingress_file(self, gf: GeneratedFile) -> Dict[str, Any]:
        """Parse and patch a single Ingress manifest (annotations + spec)."""
        try:
            obj = pyyaml.safe_load(gf.content)
            if not obj or obj.get("kind") != "Ingress":
                return {"file": gf.rel_path, "status": "skipped", "reason": "Not an Ingress"}

            name = obj["metadata"]["name"]
            namespace = obj["metadata"].get("namespace", "default")
            key = f"{namespace}/{name}"

            original_annotations = self._rollback_cache.get(key, {})
            new_annotations = obj["metadata"].get("annotations", {})
            patch_annotations = new_annotations.copy()

            # Ensure stripped NGINX annotations are actually deleted during patch
            for k in original_annotations.keys():
                if k not in new_annotations and (
                    k.startswith("nginx.ingress.kubernetes.io/") or
                    k.startswith("traefik.ingress.kubernetes.io/")
                ):
                    patch_annotations[k] = None

            # Strategic merge patch: annotations + spec (ingressClassName, rules, tls)
            patch_body = {
                "metadata": {
                    "annotations": patch_annotations,
                },
            }
            if "spec" in obj:
                patch_body["spec"] = obj["spec"]

            self.networking_api.patch_namespaced_ingress(
                name=name,
                namespace=namespace,
                body=patch_body,
            )
            return {
                "name": name,
                "namespace": namespace,
                "status": "applied",
                "action": "patched",
            }
        except ApiException as e:
            return {
                "file": gf.rel_path,
                "status": "error",
                "error": str(e),
            }
        except Exception as e:
            return {
                "file": gf.rel_path,
                "status": "error",
                "error": f"Parse error: {e}",
            }

    async def _apply_serverstransport_file(self, gf: GeneratedFile) -> List[Dict[str, Any]]:
        """Parse and create/update ServersTransport CRDs via TraefikService."""
        results: List[Dict[str, Any]] = []
        for obj in parse_multidoc_yaml_objects(gf.content):
            if obj.get("kind") != "ServersTransport":
                continue
            try:
                r = await self._traefik.upsert_servers_transport(obj)
                results.append(
                    {
                        "name": r.get("name"),
                        "namespace": r.get("namespace"),
                        "status": "applied",
                        "action": r.get("action", "created"),
                        "kind": "ServersTransport",
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "file": gf.rel_path,
                        "status": "error",
                        "error": str(e),
                    }
                )
        return results

    async def _apply_service_patch_file(
        self,
        gf: GeneratedFile,
        ingress_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse and patch a Kubernetes Service with sticky session annotations."""
        try:
            obj = None
            for o in parse_multidoc_yaml_objects(gf.content):
                if o.get("kind") == "Service":
                    obj = o
                    break
            if not obj:
                return {"file": gf.rel_path, "status": "skipped", "reason": "Not a Service"}

            name = obj["metadata"]["name"]
            namespace = obj["metadata"].get("namespace", "default")
            annotations = obj["metadata"].get("annotations", {}) or {}
            if not annotations:
                return {
                    "file": gf.rel_path,
                    "status": "skipped",
                    "reason": "Service has no annotations",
                }

            await self._traefik.merge_service_annotations(
                name=name,
                namespace=namespace,
                annotations=dict(annotations),
            )

            if ingress_key:
                self._service_patch_cache.setdefault(ingress_key, []).append(
                    (namespace, name, list(annotations.keys()))
                )

            return {
                "name": name,
                "namespace": namespace,
                "status": "applied",
                "action": "patched",
                "kind": "Service",
            }
        except ApiException as e:
            return {
                "file": gf.rel_path,
                "status": "error",
                "error": str(e),
            }
        except Exception as e:
            return {
                "file": gf.rel_path,
                "status": "error",
                "error": f"Parse error: {e}",
            }

    # ── Rollback support ────────────────────────────────────────────────────

    async def _cache_original_annotations(
        self, scan_result: ScanResult,
    ) -> None:
        """Read live Ingress annotations and cache them for rollback."""
        for ing in scan_result.ingresses:
            key = f"{ing.namespace}/{ing.name}"
            try:
                live = self.networking_api.read_namespaced_ingress(
                    name=ing.name, namespace=ing.namespace,
                )
                self._rollback_cache[key] = dict(
                    live.metadata.annotations or {}  # type: ignore[union-attr]
                )
            except Exception:
                pass

    async def revert_migration(
        self,
        namespace: str,
        ingress_name: str,
    ) -> Dict[str, Any]:
        """Revert a previously applied migration on a single Ingress.

        1. Strip all ``traefik.ingress.kubernetes.io/*`` annotations.
        2. Restore original NGINX annotations from cache.
        3. Delete generated Middleware CRDs (labelled ``migration.source: <ingress_name>``).

        Args:
            namespace: Kubernetes namespace of the Ingress.
            ingress_name: Name of the Ingress to revert.

        Returns:
            Dict with revert results.
        """
        self._ensure_clients()
        key = f"{namespace}/{ingress_name}"

        # 1. Read the live Ingress
        try:
            live: Any = self.networking_api.read_namespaced_ingress(
                name=ingress_name, namespace=namespace,
            )
        except ApiException as e:
            return {
                "status": "error",
                "error": f"Ingress {key} not found: {e}",
            }

        live_annotations = dict(live.metadata.annotations or {})  # type: ignore[union-attr]

        # 2. Build patched annotations: drop Traefik, restore NGINX from cache
        restored_annotations: Dict[str, str] = {}
        traefik_prefix = "traefik.ingress.kubernetes.io/"
        stripped_keys: List[str] = []

        for k, v in live_annotations.items():
            if k.startswith(traefik_prefix):
                stripped_keys.append(k)
            else:
                restored_annotations[k] = v

        # Merge cached original annotations — full replace of nginx keys from
        # the snapshot.  This restores mutated values, not just missing keys.
        cached = self._rollback_cache.get(key)
        restored_nginx_keys: List[str] = []
        if cached:
            nginx_prefix = "nginx.ingress.kubernetes.io/"
            for k, v in cached.items():
                if k.startswith(nginx_prefix):
                    restored_annotations[k] = v
                    restored_nginx_keys.append(k)

        # 3. Patch the Ingress
        restored_ingress_class = False
        try:
            # We must null-out the removed Traefik annotations explicitly
            patch_annotations = dict(restored_annotations)
            for sk in stripped_keys:
                patch_annotations[sk] = None  # type: ignore[assignment]

            patch_body: Dict[str, Any] = {"metadata": {"annotations": patch_annotations}}
            if getattr(live.spec, "ingress_class_name", None) == "traefik":
                patch_body["spec"] = {"ingressClassName": "nginx"}
                restored_ingress_class = True

            self.networking_api.patch_namespaced_ingress(
                name=ingress_name,
                namespace=namespace,
                body=patch_body,
            )
        except ApiException as e:
            return {
                "status": "error",
                "error": f"Failed to patch Ingress {key}: {e}",
            }

        # 4. Delete migration-generated Middleware CRDs
        deleted_middlewares: List[str] = []
        try:
            mw_list = self.custom_api.list_namespaced_custom_object(
                group=self.TRAEFIK_CRD_GROUP,
                version=self.TRAEFIK_CRD_VERSION,
                namespace=namespace,
                plural=self.TRAEFIK_MIDDLEWARE_PLURAL,
                label_selector=f"migration.source={ingress_name}",
            )
            for mw in mw_list.get("items", []):
                mw_name = mw["metadata"]["name"]
                try:
                    self.custom_api.delete_namespaced_custom_object(
                        group=self.TRAEFIK_CRD_GROUP,
                        version=self.TRAEFIK_CRD_VERSION,
                        namespace=namespace,
                        plural=self.TRAEFIK_MIDDLEWARE_PLURAL,
                        name=mw_name,
                    )
                    deleted_middlewares.append(mw_name)
                except Exception:
                    pass
        except Exception:
            pass

        # 5. Delete migration-generated ServersTransport CRDs
        deleted_serverstransports: List[str] = []
        try:
            st_list = self.custom_api.list_namespaced_custom_object(
                group=self.TRAEFIK_CRD_GROUP,
                version=self.TRAEFIK_CRD_VERSION,
                namespace=namespace,
                plural=self.TRAEFIK_SERVERSTRANSPORT_PLURAL,
                label_selector=f"migration.source={ingress_name}",
            )
            for st in st_list.get("items", []):
                st_name = st["metadata"]["name"]
                try:
                    await self._traefik.delete_servers_transport(
                        name=st_name,
                        namespace=namespace,
                    )
                    deleted_serverstransports.append(st_name)
                except Exception:
                    pass
        except Exception:
            pass

        # 6. Revert Service sticky session patches
        reverted_services: List[str] = []
        svc_patches = self._service_patch_cache.get(key, [])
        for svc_ns, svc_name, ann_keys in svc_patches:
            try:
                # Null-out each annotation that was added during migration
                null_annotations = {k: None for k in ann_keys}  # type: ignore[misc]
                self.core_api.patch_namespaced_service(
                    name=svc_name,
                    namespace=svc_ns,
                    body={"metadata": {"annotations": null_annotations}},
                )
                reverted_services.append(f"{svc_ns}/{svc_name}")
            except Exception:
                pass

        # Clean up cache entries
        self._rollback_cache.pop(key, None)
        self._service_patch_cache.pop(key, None)

        msg_parts = [
            f"Reverted {key}: stripped {len(stripped_keys)} Traefik annotation(s)",
            f"restored {len(restored_nginx_keys)} NGINX annotation(s)",
            f"deleted {len(deleted_middlewares)} Middleware CRD(s)",
            f"deleted {len(deleted_serverstransports)} ServersTransport CRD(s)",
        ]
        if reverted_services:
            msg_parts.append(f"reverted sticky annotations on {len(reverted_services)} Service(s)")
        if restored_ingress_class:
            msg_parts.append('restored ingressClassName to "nginx"')

        return {
            "status": "success",
            "ingress": key,
            "stripped_traefik_annotations": stripped_keys,
            "restored_nginx_annotations": restored_nginx_keys,
            "deleted_middlewares": deleted_middlewares,
            "deleted_serverstransports": deleted_serverstransports,
            "reverted_services": reverted_services,
            "had_cache": cached is not None,
            "restored_ingress_class": restored_ingress_class,
            "message": ", ".join(msg_parts) + ".",
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    def _ingress_key_from_service_patch(
        self,
        gf: GeneratedFile,
        scan_result: ScanResult,
    ) -> Optional[str]:
        """Derive the Ingress rollback cache key from a service_patch GeneratedFile.

        The file path is ``02-middlewares/{ns}-{ing_name}-{svc_name}-service-patch.yaml``.
        We match against known ingresses to find the right ``namespace/name`` key.
        """
        for ing in scan_result.ingresses:
            prefix = f"{ing.namespace}-{ing.name}-"
            if prefix in gf.rel_path:
                return f"{ing.namespace}/{ing.name}"
        return None

    def _get_cluster_name(self) -> str:
        """Derive cluster name from kubeconfig context."""
        assert self.config.kubernetes is not None
        try:
            ctx = self.config.kubernetes.context_name
            if ctx:
                return ctx
        except Exception:
            pass
        # Fallback: try reading current-context from kubeconfig
        try:
            _, active_context = k8s_config.list_kube_config_contexts(
                config_file=self.config.kubernetes.kubeconfig,
            )
            if active_context and active_context.get("name"):
                return active_context["name"]
        except Exception:
            pass
        return "cluster"
