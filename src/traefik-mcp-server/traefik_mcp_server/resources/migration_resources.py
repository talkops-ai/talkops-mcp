"""Migration guidance resources.

Provides programmatic access to migration phase guides and commands.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from traefik_mcp_server.resources.base import BaseResource



def _nginx_scan_agent_digest(scan: Dict[str, Any], scoped_namespace: Optional[str]) -> Dict[str, Any]:
    """Shape a raw scan dict into an agent-friendly payload: paths + nginx values per Ingress."""
    ingresses_raw = scan.get("ingresses") or []
    by_complexity: Dict[str, int] = {}
    by_namespace: Dict[str, int] = {}
    with_nginx = 0
    with_tls = 0
    brief: List[Dict[str, Any]] = []

    for ing in ingresses_raw:
        ns = ing.get("namespace") or ""
        c = ing.get("complexity") or "simple"
        by_complexity[c] = by_complexity.get(c, 0) + 1
        by_namespace[ns] = by_namespace.get(ns, 0) + 1
        na = ing.get("nginxAnnotations") or {}
        if na:
            with_nginx += 1
        if ing.get("tlsEnabled"):
            with_tls += 1

        paths = ing.get("paths") or []
        path_rows = [
            {
                "host": p.get("host") or "",
                "path": p.get("path") or "",
                "pathType": p.get("pathType") or "Prefix",
                "serviceName": p.get("serviceName") or "",
                "servicePort": p.get("servicePort") or 0,
            }
            for p in paths
        ]
        svc_brief: List[str] = []
        for s in ing.get("services") or []:
            sn = s.get("name") or ""
            sp = s.get("port") or 0
            sns = s.get("namespace") or ""
            if sns and sns != ns:
                svc_brief.append(f"{sns}/{sn}:{sp}")
            else:
                svc_brief.append(f"{sn}:{sp}")

        brief.append(
            {
                "ref": f"{ns}/{ing.get('name', '')}",
                "ingressClass": ing.get("ingressClass") or "",
                "complexity": c,
                "hosts": ing.get("hosts") or [],
                "paths": path_rows,
                "pathCount": len(path_rows),
                "tlsEnabled": bool(ing.get("tlsEnabled")),
                "nginxAnnotations": dict(na),
                "backends": svc_brief,
            }
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scope: Dict[str, Any] = (
        {"allNamespaces": True} if scoped_namespace is None else {"namespace": scoped_namespace}
    )

    return {
        "schema": "traefik.mcp/nginx-ingress-scan/2",
        "fetchedAt": now,
        "scope": scope,
        "clusterName": scan.get("clusterName") or "",
        "controller": scan.get("controller") or {},
        "summary": {
            "totalIngresses": len(ingresses_raw),
            "byComplexity": by_complexity,
            "byNamespace": dict(sorted(by_namespace.items())),
            "namespaces": scan.get("namespaces") or [],
            "ingressesWithNginxAnnotations": with_nginx,
            "ingressesWithTls": with_tls,
        },
        "ingresses": brief,
        "howToGoDeeper": [
            "Per-annotation Traefik compatibility: read_resource traefik://migration/nginx-ingress-analyze or .../nginx-ingress-analyze/{namespace}.",
            "Generate migration runbook (read-only): read_resource traefik://migration/nginx-runbook or .../nginx-runbook/{namespace}.",
            "Apply migration or use migration_plan overrides: tool traefik_nginx_migration (action=apply or generate); action=apply requires MCP_ALLOW_WRITE=true.",
        ],
    }


def _nginx_analyze_resource_body(
    analysis: Dict[str, Any],
    scoped_namespace: Optional[str],
) -> Dict[str, Any]:
    """Wrap analyzer output for MCP resource (schema + scope + analysis fields)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scope: Dict[str, Any] = (
        {"allNamespaces": True} if scoped_namespace is None else {"namespace": scoped_namespace}
    )
    body: Dict[str, Any] = {
        "schema": "traefik.mcp/nginx-ingress-analyze/1",
        "fetchedAt": now,
        "scope": scope,
    }
    body.update(analysis)
    return body


class MigrationResources(BaseResource):
    """Migration guide resources.
    
    Provides structured migration phases from NGINX to Traefik.
    Update frequency: Static content.
    """

    def __init__(self, service_locator: Dict[str, Any]):
        super().__init__(service_locator)
        self._nginx_migration = service_locator.get("nginx_migration_service")

    def register(self, mcp_instance) -> None:
        """Register migration resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("traefik://migration/nginx-to-traefik")
        async def full_migration_guide() -> str:
            """Get the full structured NGINX to Traefik migration guide.
            
            Returns:
                JSON string with the entire migration structured data.
            """
            guide_data = {
                "title": "NGINX to Traefik Migration Strategy",
                "strategy": "Side-by-side (Active-Active) with DNS cutover",
                "zeroDowntime": True,
                "phases": [
                    {
                        "phase": "phase1",
                        "title": "Install Traefik Side-by-Side",
                        "description": "Install Traefik with kubernetesIngressNginx provider enabled so it watches existing Ingress objects.",
                        "commands": [
                            "Use instructions from: read_resource traefik://migration/nginx-runbook/{namespace}",
                            "Install Traefik using helm (details in the runbook)"
                        ]
                    },
                    {
                        "phase": "phase2",
                        "title": "Apply Middlewares and Patches",
                        "description": "Create the corresponding Traefik Middlewares and patch Ingress objects with Traefik annotations side-by-side.",
                        "commands": [
                            "Call MCP Tool: traefik_nginx_migration",
                            "Args: {\"namespace\": \"<target_namespace>\", \"apply\": true}"
                        ]
                    },
                    {
                        "phase": "phase3",
                        "title": "Validate Traefik Routing & Traffic Cutover",
                        "description": "Test Traefik's load balancer IP. Then, shift live traffic from the NGINX LoadBalancer IP to the Traefik LoadBalancer IP via DNS changes.",
                        "commands": [
                            "Use the returned IP from the Traefik service to test: curl -v -H \"Host: <your-domain>\" http://<TRAEFIK_IP>/",
                            "Change DNS A-records to the Traefik IP"
                        ]
                    },
                    {
                        "phase": "phase4",
                        "title": "Clean Up NGINX",
                        "description": "Preserve the 'nginx' IngressClass object manually, then uninstall the NGINX controller.",
                        "commands": [
                            "Follow cleanup instructions in: read_resource traefik://migration/nginx-runbook/{namespace}"
                        ]
                    }
                ],
                "postMigration": {
                    "title": "Remove legacy Ingress objects (manual)",
                    "description": (
                        "After hostnames are fully served by Traefik-native resources (e.g. IngressRoute) and verified, "
                        "operators manually delete networking.k8s.io/v1 Ingress from Git or kubectl. "
                        "Not performed automatically—install styles (Helm vs manifest vs GitOps) differ."
                    ),
                    "whenNotToDelete": (
                        "If Traefik still relies solely on the kubernetesIngress(nginx) provider and no IngressRoute "
                        "exists for that hostname, deleting Ingress drops routing."
                    ),
                },
                "rollback": {
                    "description": "Rollback is instant by reverting DNS back to NGINX IP, provided NGINX has not been uninstalled yet. If annotations were applied and break things, use traefik_nginx_migration with action=revert (plus ingress_name) to strip Traefik annotations and delete Middlewares."
                }
            }
            return json.dumps(guide_data, indent=2)

        @mcp_instance.resource("traefik://migration/nginx-to-traefik/{phase}")
        async def phase_migration_guide(phase: str) -> str:
            """Get structured data for a specific NGINX to Traefik migration phase.
            
            Args:
                phase: Migration phase (e.g., 'phase1', 'phase2', 'phase3', 'phase4')
            
            Returns:
                JSON string with the requested phase data.
            """
            
            full_guide = json.loads(await full_migration_guide())
            phases = full_guide.get("phases", [])
            
            for p in phases:
                if p["phase"] == phase:
                    return json.dumps(p, indent=2)
            
            if phase == "rollback":
                return json.dumps(full_guide.get("rollback", {}), indent=2)
                
            return json.dumps({"error": f"Phase '{phase}' not found. Valid phases: phase1, phase2, phase3, phase4, rollback."}, indent=2)

        @mcp_instance.resource("traefik://migration/nginx-ingress-scan")
        async def nginx_ingress_scan_digest() -> str:
            """Live cluster digest: per-Ingress paths (host, path, pathType, service) and nginxAnnotations map.

            Schema ``traefik.mcp/nginx-ingress-scan/2``. Compatibility: read_resource
            ``traefik://migration/nginx-ingress-analyze`` (or ``.../{namespace}``).
            """
            if self._nginx_migration is None:
                return json.dumps(
                    {
                        "schema": "traefik.mcp/nginx-ingress-scan/2",
                        "error": "nginx_migration_service is not configured on this server.",
                    },
                    indent=2,
                )
            raw = await self._nginx_migration.scan(namespace=None)
            digest = _nginx_scan_agent_digest(raw, scoped_namespace=None)
            return json.dumps(digest, indent=2)

        @mcp_instance.resource("traefik://migration/nginx-ingress-scan/{namespace}")
        async def nginx_ingress_scan_digest_namespace(namespace: str) -> str:
            """Same as nginx-ingress-scan but scoped to one Kubernetes namespace."""
            if self._nginx_migration is None:
                return json.dumps(
                    {
                        "schema": "traefik.mcp/nginx-ingress-scan/2",
                        "error": "nginx_migration_service is not configured on this server.",
                    },
                    indent=2,
                )
            raw = await self._nginx_migration.scan(namespace=namespace)
            digest = _nginx_scan_agent_digest(raw, scoped_namespace=namespace)
            return json.dumps(digest, indent=2)

        @mcp_instance.resource("traefik://migration/nginx-ingress-analyze")
        async def nginx_ingress_analyze_all() -> str:
            """Full NGINX→Traefik compatibility analysis (cluster-wide).

            Schema ``traefik.mcp/nginx-ingress-analyze/1`` — same fields as the former
            tool analyze output: ``target``, ``ingressReports`` (with
            ``breakingAnnotations`` when breaking), ``summary``. Use **resources** for
            large reports so MCP clients do not truncate tool results.
            """
            if self._nginx_migration is None:
                return json.dumps(
                    {
                        "schema": "traefik.mcp/nginx-ingress-analyze/1",
                        "error": "nginx_migration_service is not configured on this server.",
                    },
                    indent=2,
                )
            analysis = await self._nginx_migration.analyze(namespace=None, target="traefik")
            body = _nginx_analyze_resource_body(analysis, scoped_namespace=None)
            return json.dumps(body, indent=2, default=str)

        @mcp_instance.resource("traefik://migration/nginx-ingress-analyze/{namespace}")
        async def nginx_ingress_analyze_namespace(namespace: str) -> str:
            """Compatibility analysis scoped to one Kubernetes namespace (Traefik target)."""
            if self._nginx_migration is None:
                return json.dumps(
                    {
                        "schema": "traefik.mcp/nginx-ingress-analyze/1",
                        "error": "nginx_migration_service is not configured on this server.",
                    },
                    indent=2,
                )
            analysis = await self._nginx_migration.analyze(namespace=namespace, target="traefik")
            body = _nginx_analyze_resource_body(analysis, scoped_namespace=namespace)
            return json.dumps(body, indent=2, default=str)

        @mcp_instance.resource("traefik://migration/nginx-runbook")
        async def nginx_runbook_all() -> str:
            """Generate the NGINX → Traefik migration runbook (cluster-wide, default settings).

            Returns a markdown runbook with inline YAML for Middleware CRDs,
            updated Ingresses, shadow TraefikService mirrors (if applicable),
            validation steps, DNS cutover, cleanup, and rollback instructions.

            This is read-only — no cluster mutations. For ``action=apply`` or
            ``migration_plan`` overrides, use the ``traefik_nginx_migration`` tool.
            """
            if self._nginx_migration is None:
                return json.dumps(
                    {"error": "nginx_migration_service is not configured on this server."},
                    indent=2,
                )
            runbook = await self._nginx_migration.generate_runbook(namespace=None, target="traefik")
            return runbook

        @mcp_instance.resource("traefik://migration/nginx-runbook/{namespace}")
        async def nginx_runbook_namespace(namespace: str) -> str:
            """Generate the NGINX → Traefik migration runbook for a specific namespace.

            Same as ``nginx-runbook`` but scoped to one Kubernetes namespace.
            Read-only — no cluster mutations.
            """
            if self._nginx_migration is None:
                return json.dumps(
                    {"error": "nginx_migration_service is not configured on this server."},
                    indent=2,
                )
            runbook = await self._nginx_migration.generate_runbook(namespace=namespace, target="traefik")
            return runbook

