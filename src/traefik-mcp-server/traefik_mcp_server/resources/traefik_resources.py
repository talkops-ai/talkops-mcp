"""12 Read-Only traefik:// MCP Resources (R1–R12)."""

import json
from fastmcp import FastMCP

from traefik_mcp_server.resources.base import BaseResource
from traefik_mcp_server.tools.base import translate_error


class TraefikResources(BaseResource):
    """Registers the 12 read-only traefik:// resources (4 static + 8 templates)."""

    def register(self, mcp: FastMCP) -> None:
        svc = self.traefik_service

        # ── R1: traefik://server/capabilities ─────────────────────────────────
        @mcp.resource(
            "traefik://server/capabilities",
            name="traefik_server_capabilities",
            description=(
                "Server readiness, allow_write flag, active toolsets, Traefik version, "
                "installed CRDs (traefik.io and gateway.networking.k8s.io), enabled providers, "
                "Prometheus reachability, and namespace policies."
            ),
            mime_type="application/json",
        )
        async def get_server_capabilities() -> str:
            try:
                return json.dumps(svc.get_server_capabilities(), indent=2)
            except Exception as e:
                raise translate_error(e, "traefik://server/capabilities")

        # ── R2: traefik://cluster/contexts ────────────────────────────────────
        @mcp.resource(
            "traefik://cluster/contexts",
            name="traefik_cluster_contexts",
            description="Available kubeconfig contexts, active context, and cluster connection mode.",
            mime_type="application/json",
        )
        async def get_cluster_contexts() -> str:
            try:
                return json.dumps(svc.get_kube_contexts(), indent=2)
            except Exception as e:
                raise translate_error(e, "traefik://cluster/contexts")

        # ── R3: traefik://instance/static-config ──────────────────────────────
        @mcp.resource(
            "traefik://instance/static-config",
            name="traefik_instance_static_config",
            description=(
                "Redacted Traefik static configuration including entryPoints, providers "
                "(kubernetesCRD, kubernetesIngress, kubernetesIngressNGINX, kubernetesGateway), "
                "certificatesResolvers, metrics, accessLog, and plugins."
            ),
            mime_type="application/json",
        )
        async def get_instance_static_config() -> str:
            try:
                return json.dumps(svc.get_static_config(), indent=2)
            except Exception as e:
                raise translate_error(e, "traefik://instance/static-config")

        # ── R4: traefik://runtime/health ──────────────────────────────────────
        @mcp.resource(
            "traefik://runtime/health",
            name="traefik_runtime_health",
            description=(
                "Live Traefik runtime overview (/api/overview + /api/entrypoints): router, "
                "service, and middleware error/warning counts per protocol plus entryPoint "
                "listener status."
            ),
            mime_type="application/json",
        )
        async def get_runtime_health() -> str:
            try:
                return json.dumps(svc.get_runtime_health(), indent=2)
            except Exception as e:
                raise translate_error(e, "traefik://runtime/health")

        # ── R5: traefik://runtime/{protocol} ──────────────────────────────────
        @mcp.resource(
            "traefik://runtime/{protocol}",
            name="traefik_runtime_protocol",
            description=(
                "Active Traefik runtime routers, services (with backend serverStatus UP/DOWN), "
                "and middlewares for protocol ('http', 'tcp', or 'udp')."
            ),
            mime_type="application/json",
        )
        async def get_runtime_protocol(protocol: str) -> str:
            try:
                return json.dumps(svc.get_runtime_protocol(protocol), indent=2)
            except Exception as e:
                raise translate_error(e, f"traefik://runtime/{protocol}")

        # ── R6: traefik://routes/{namespace} ──────────────────────────────────
        @mcp.resource(
            "traefik://routes/{namespace}",
            name="traefik_routes_inventory",
            description=(
                "Unified route inventory (IngressRoute, IngressRouteTCP, IngressRouteUDP, "
                "TraefikService, and Ingress) in a namespace (or '_all'), enriched with "
                "hosts, entryPoints, weights, mirror percentages, and ownership metadata."
            ),
            mime_type="application/json",
        )
        async def get_routes_inventory(namespace: str) -> str:
            try:
                return json.dumps(svc.list_routes(namespace), indent=2)
            except Exception as e:
                raise translate_error(e, f"traefik://routes/{namespace}", namespace=namespace)

        # ── R7: traefik://manifests/{kind}/{namespace}/{name} ─────────────────
        @mcp.resource(
            "traefik://manifests/{kind}/{namespace}/{name}",
            name="traefik_resource_manifest",
            description=(
                "Sanitized Kubernetes manifest (managedFields and applied-configuration bloat "
                "stripped, Secret data redacted) with resourceVersion for optimistic concurrency."
            ),
            mime_type="application/json",
        )
        async def get_resource_manifest(kind: str, namespace: str, name: str) -> str:
            try:
                return json.dumps(svc.get_sanitized_manifest(kind, namespace, name), indent=2)
            except Exception as e:
                raise translate_error(
                    e,
                    f"traefik://manifests/{kind}/{namespace}/{name}",
                    namespace=namespace,
                    resource_name=name,
                )

        # ── R8: traefik://policies/{namespace} ────────────────────────────────
        @mcp.resource(
            "traefik://policies/{namespace}",
            name="traefik_policies_inventory",
            description=(
                "Unified policy inventory (Middleware, MiddlewareTCP, TLSOption, TLSStore, "
                "ServersTransport, ServersTransportTCP) in a namespace (or '_all') with "
                "referenced-by route counts."
            ),
            mime_type="application/json",
        )
        async def get_policies_inventory(namespace: str) -> str:
            try:
                return json.dumps(svc.list_policies(namespace), indent=2)
            except Exception as e:
                raise translate_error(e, f"traefik://policies/{namespace}", namespace=namespace)

        # ── R9: traefik://certificates/{namespace} ────────────────────────────
        @mcp.resource(
            "traefik://certificates/{namespace}",
            name="traefik_certificates_inventory",
            description=(
                "Sanitized X.509 certificate metadata (Subject, Issuer, SANs, NotBefore, "
                "NotAfter, days_remaining, cert-manager Certificate status) in a namespace "
                "(or '_all'). Never exposes private key material."
            ),
            mime_type="application/json",
        )
        async def get_certificates_inventory(namespace: str) -> str:
            try:
                return json.dumps(svc.list_certificates(namespace), indent=2)
            except Exception as e:
                raise translate_error(e, f"traefik://certificates/{namespace}", namespace=namespace)

        # ── R10: traefik://gateway/{namespace} ────────────────────────────────
        @mcp.resource(
            "traefik://gateway/{namespace}",
            name="traefik_gateway_inventory",
            description=(
                "Read-only Kubernetes Gateway API inventory (GatewayClass, Gateway, HTTPRoute, "
                "GRPCRoute, TLSRoute, TCPRoute, ReferenceGrant) with listener & parent status "
                "conditions (Accepted, Programmed, ResolvedRefs)."
            ),
            mime_type="application/json",
        )
        async def get_gateway_inventory(namespace: str) -> str:
            try:
                return json.dumps(svc.list_gateway_resources(namespace), indent=2)
            except Exception as e:
                raise translate_error(e, f"traefik://gateway/{namespace}", namespace=namespace)

        # ── R11: traefik://metrics/{namespace}/{service}/summary ──────────────
        @mcp.resource(
            "traefik://metrics/{namespace}/{service}/summary",
            name="traefik_service_metrics_summary",
            description=(
                "5-minute Prometheus GOLDEN metrics snapshot (RPS, 2xx/4xx/5xx error rates, "
                "P50/P95/P99 latency, open connections) for a Traefik service."
            ),
            mime_type="application/json",
        )
        async def get_service_metrics_summary(namespace: str, service: str) -> str:
            try:
                return json.dumps(svc.get_service_metrics_summary(namespace, service), indent=2)
            except Exception as e:
                raise translate_error(
                    e,
                    f"traefik://metrics/{namespace}/{service}/summary",
                    namespace=namespace,
                    resource_name=service,
                )

        # ── R12: traefik://schema/{kind} ──────────────────────────────────────
        @mcp.resource(
            "traefik://schema/{kind}",
            name="traefik_crd_schema",
            description=(
                "Cluster-installed CRD OpenAPI v3 spec schema and supported field names for "
                "a Traefik or Gateway API resource kind."
            ),
            mime_type="application/json",
        )
        async def get_crd_schema(kind: str) -> str:
            try:
                return json.dumps(svc.get_crd_schema(kind), indent=2)
            except Exception as e:
                raise translate_error(e, f"traefik://schema/{kind}", resource_name=kind)
