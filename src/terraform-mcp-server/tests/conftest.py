"""Shared test fixtures for Terraform MCP Server tests."""

import pytest
from unittest.mock import MagicMock, patch
from terraform_mcp_server.server_config import ServerConfig


@pytest.fixture
def mock_config():
    """Create a mock domain Config instance."""
    config = MagicMock()
    config.NEO4J_URI = 'bolt://localhost:7687'
    config.NEO4J_USERNAME = 'neo4j'
    config.NEO4J_PASSWORD = 'test-password'
    config.NEO4J_DATABASE = 'neo4j'
    config.EMBEDDING_MODEL = 'text-embedding-ada-002'
    config.EMBEDDING_DIMENSIONS = 1536
    config.EMBEDDING_PROVIDER = 'openai'
    config.LLM_PROVIDER = 'openai'
    config.LLM_MODEL = 'gpt-4o'
    config.LLM_TEMPERATURE = 0.0
    config.LLM_MAX_TOKENS = 1000
    config.TERRAFORM_BINARY_PATH = 'terraform'
    config.TERRAFORM_ALLOWED_COMMANDS = ['init', 'plan', 'validate', 'apply', 'destroy']
    config.TERRAFORM_DEFAULT_TIMEOUT = 300
    config.TERRAFORM_MAX_TIMEOUT = 1800
    config.TERRAFORM_SECURITY_ENABLED = True
    config.TERRAFORM_DANGEROUS_PATTERNS_ENABLED = True
    config.TERRAFORM_WORKING_DIRECTORY_VALIDATION = True
    config.TERRAFORM_MAX_WORKING_DIRECTORY_DEPTH = 10
    config.TERRAFORM_BLOCKED_WORKING_DIRECTORIES = ['/etc', '/usr']
    config.TERRAFORM_ALLOWED_WORKING_DIRECTORIES = ['/tmp']
    config.TERRAFORM_AUTO_APPROVE_COMMANDS = ['apply', 'destroy']
    config.TERRAFORM_VARIABLE_COMMANDS = ['plan', 'apply', 'destroy']
    config.TERRAFORM_OUTPUT_COMMANDS = ['apply']
    config.TERRAFORM_MAX_OUTPUT_LENGTH = 10000
    config.TERRAFORM_MAX_VARIABLES = 100
    config.OPENAI_API_KEY = 'test-api-key'
    
    # Support dict-style access for config summary
    config._config = {
        'NEO4J_URI': 'bolt://localhost:7687',
        'NEO4J_USERNAME': 'neo4j',
        'NEO4J_PASSWORD': 'test-password',
        'OPENAI_API_KEY': 'test-api-key',
        'EMBEDDING_MODEL': 'text-embedding-ada-002',
    }
    
    return config


@pytest.fixture
def mock_server_config():
    """Create a ServerConfig instance for testing."""
    return ServerConfig(
        name='terraform-mcp-server-test',
        version='0.1.0-test',
        transport='stdio',
        host='127.0.0.1',
        port=9000,
        path='/mcp',
        debug=True,
        allow_dangerous_execution=False,
    )


@pytest.fixture
def mock_neo4j_graph():
    """Create a mock Neo4jGraph instance."""
    graph = MagicMock()
    graph.query.return_value = [{'cnt': 42}]
    return graph


@pytest.fixture
def service_locator(mock_config, mock_server_config, mock_neo4j_graph):
    """Create a complete service locator for dependency injection."""
    return {
        'config': mock_config,
        'server_config': mock_server_config,
        'neo4j_graph': mock_neo4j_graph,
    }
