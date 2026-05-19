"""Terraform MCP resources — knowledge graph stats and server config summary.

Provides terraform:// URI resources for MCP clients:
- terraform://knowledge-graph/stats — Neo4j graph statistics
- terraform://server/config-summary — server configuration (secrets redacted)
"""

import json
import logging
from typing import Any, Dict

from terraform_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)

# Fields whose values must be redacted in config-summary
_SECRET_FIELDS = frozenset({
    'NEO4J_PASSWORD',
    'OPENAI_API_KEY',
    'API_KEY',
    'neo4j_password',
    'openai_api_key',
    'api_key',
})


def _redact(key: str, value: Any) -> Any:
    """Redact sensitive values.
    
    Args:
        key: Configuration key name
        value: Configuration value
    
    Returns:
        '***REDACTED***' if key is sensitive, else original value
    """
    if key.upper() in {f.upper() for f in _SECRET_FIELDS}:
        return '***REDACTED***'
    # Also redact any key containing PASSWORD, SECRET, or TOKEN
    key_upper = key.upper()
    for pattern in ('PASSWORD', 'SECRET', 'TOKEN', 'API_KEY'):
        if pattern in key_upper:
            return '***REDACTED***'
    return value


class TerraformResources(BaseResource):
    """MCP resources for Terraform knowledge graph and server info."""
    
    def register(self, mcp_instance) -> None:
        """Register terraform:// resources."""
        config = self.config
        server_config = self.server_config
        neo4j_graph = self.neo4j_graph
        
        @mcp_instance.resource("terraform://knowledge-graph/stats")
        async def knowledge_graph_stats() -> str:
            """Aggregate Neo4j knowledge graph statistics.
            
            Returns chunk counts, embedding coverage, and index health
            for the Terraform documentation knowledge graph.
            """
            try:
                if neo4j_graph is None:
                    return json.dumps({
                        "status": "unavailable",
                        "error": "Neo4j connection not established",
                    }, indent=2)
                
                # Query aggregate stats
                stats = {}
                
                # Count chunks by type
                for label, key in [
                    ('DocChunk_Resource', 'resource_chunks'),
                    ('DocChunk_DataSource', 'datasource_chunks'),
                    ('DocChunk_BestPractice', 'bestpractice_chunks'),
                ]:
                    try:
                        result = neo4j_graph.query(
                            f"MATCH (n:{label}) RETURN count(n) AS cnt"
                        )
                        stats[key] = result[0]['cnt'] if result else 0
                    except Exception:
                        stats[key] = 'query_failed'
                
                # Total chunks
                try:
                    result = neo4j_graph.query(
                        "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'DocChunk') "
                        "RETURN count(n) AS cnt"
                    )
                    stats['total_chunks'] = result[0]['cnt'] if result else 0
                except Exception:
                    stats['total_chunks'] = 'query_failed'
                
                # Embedding coverage (chunks with embeddings)
                try:
                    result = neo4j_graph.query(
                        "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'DocChunk') "
                        "AND n.embedding IS NOT NULL "
                        "RETURN count(n) AS cnt"
                    )
                    stats['chunks_with_embeddings'] = result[0]['cnt'] if result else 0
                except Exception:
                    stats['chunks_with_embeddings'] = 'query_failed'
                
                stats['status'] = 'connected'
                return json.dumps(stats, indent=2, default=str)
                
            except Exception as e:
                logger.error("knowledge-graph/stats failed: %s", e)
                return json.dumps({
                    "status": "error",
                    "error": str(e),
                }, indent=2)
        
        @mcp_instance.resource("terraform://server/config-summary")
        async def server_config_summary() -> str:
            """Operator-facing server configuration summary.
            
            Returns current configuration with secrets redacted.
            Never echoes NEO4J_PASSWORD, API keys, or other sensitive values.
            """
            try:
                summary: Dict[str, Any] = {}
                
                # MCP server config
                if server_config is not None:
                    summary['mcp_server'] = {
                        'name': server_config.name,
                        'version': server_config.version,
                        'transport': server_config.transport,
                        'host': server_config.host,
                        'port': server_config.port,
                        'path': server_config.path,
                        'debug': server_config.debug,
                        'allow_dangerous_execution': server_config.allow_dangerous_execution,
                    }
                
                # Domain config (with redaction)
                if config is not None:
                    domain: Dict[str, Any] = {}
                    
                    # Iterate through config items
                    if hasattr(config, '_config'):
                        for key, value in config._config.items():
                            domain[key] = _redact(key, value)
                    elif hasattr(config, 'to_dict_original_case'):
                        for key, value in config.to_dict_original_case().items():
                            domain[key] = _redact(key, value)
                    
                    summary['domain_config'] = domain
                
                summary['status'] = 'ok'
                return json.dumps(summary, indent=2, default=str)
                
            except Exception as e:
                logger.error("server/config-summary failed: %s", e)
                return json.dumps({
                    "status": "error",
                    "error": str(e),
                }, indent=2)
