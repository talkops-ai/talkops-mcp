"""Native NGINX-to-Traefik migration pipeline.

Provides scan → analyze → migrate capabilities for bulk Ingress migration.
Ported from the reference project: https://github.com/saiyam1814/ing-switch (MIT license).

Modules:
  scanner            – List Ingress resources, detect controller, classify complexity
  analyzer           – Map nginx annotations to Traefik/Gateway API equivalents
  migrator_traefik   – Generate Middleware CRDs + updated Ingress manifests
  migrator_gateway_api – Generate HTTPRoute + Gateway manifests (Gateway API)
  generator          – Bundle files and produce migration report
"""

from traefik_mcp_server.migration_nginx.scanner import NginxMigrationScanner
from traefik_mcp_server.migration_nginx.analyzer import NginxMigrationAnalyzer
from traefik_mcp_server.migration_nginx.migrator_traefik import TraefikMigrator
from traefik_mcp_server.migration_nginx.migrator_gateway_api import GatewayAPIMigrator

__all__ = [
    "NginxMigrationScanner",
    "NginxMigrationAnalyzer",
    "TraefikMigrator",
    "GatewayAPIMigrator",
]

