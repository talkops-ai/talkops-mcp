# Copyright (C) 2025 StructBinary
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Default configuration for the Knowledge Graph MCP Server.
Contains only default values - environment variable handling is in config.py
"""

from typing import List


class DefaultConfig:
    """Default configuration values."""
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "knowledge_graph.log"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Database Configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    NEO4J_DATABASE: str = "neo4j"
    
    # AI Configuration
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 1000
    
    # Embedding Configuration
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-ada-002"
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_CACHE_ENABLED: bool = True
    EMBEDDING_CACHE_TTL: int = 86400  # 24 hours
    EMBEDDING_CACHE_MAX_SIZE: int = 10000
    
    # HNSW Configuration
    HNSW_M: int = 32
    HNSW_EF_CONSTRUCTION: int = 400
    HNSW_EF_SEARCH: int = 64
    HNSW_INDEX_NAME: str = "docchunk_embedding_hnsw"
    VECTOR_SIMILARITY_FUNCTION: str = "cosine"
    VECTOR_DIMENSIONS: int = 1536  # Alias for EMBEDDING_DIMENSIONS
    
    # Document Processing Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_CHUNK_SIZE: int = 2000
    
    # Ingestion Configuration
    BATCH_SIZE: int = 100
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    INGESTION_LOG_FILE: str = "ingestion_log.csv"
    
    # API Configuration
    API_TIMEOUT: int = 60
    MAX_CONCURRENT_REQUESTS: int = 10
    
    # Security Configuration
    API_KEY_HEADER: str = "X-API-Key"
    CORS_ORIGINS: List[str] = ["*"]
    
    # Performance Configuration
    VECTOR_SEARCH_TIMEOUT: int = 30
    EMBEDDING_GENERATION_TIMEOUT: int = 60
    
    # GitHub Configuration
    GITHUB_RAW_BASE_URL: str = "https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs"
    
    # Terraform Execution Configuration
    TERRAFORM_BINARY_PATH: str = "terraform"
    TERRAFORM_ALLOWED_COMMANDS: List[str] = ["init", "plan", "validate", "apply", "destroy"]
    TERRAFORM_AUTO_APPROVE_COMMANDS: List[str] = ["apply", "destroy"]
    TERRAFORM_VARIABLE_COMMANDS: List[str] = ["plan", "apply", "destroy"]
    TERRAFORM_OUTPUT_COMMANDS: List[str] = ["apply"]
    TERRAFORM_DEFAULT_TIMEOUT: int = 300  # 5 minutes
    TERRAFORM_MAX_TIMEOUT: int = 1800  # 30 minutes
    TERRAFORM_DEFAULT_STRIP_ANSI: bool = True
    TERRAFORM_MAX_VARIABLES: int = 100
    TERRAFORM_MAX_OUTPUT_LENGTH: int = 10000  # Max length for stdout/stderr
    TERRAFORM_README_MAX_LENGTH: int = 8000  # Max length for README content
    TERRAFORM_DESCRIPTION_MAX_LENGTH: int = 200  # Max length for descriptions
    
    
    # Security Configuration for Terraform Execution
    TERRAFORM_SECURITY_ENABLED: bool = True
    TERRAFORM_DANGEROUS_PATTERNS_ENABLED: bool = True
    TERRAFORM_WORKING_DIRECTORY_VALIDATION: bool = True
    TERRAFORM_MAX_WORKING_DIRECTORY_DEPTH: int = 10  # Prevent directory traversal
    TERRAFORM_ALLOWED_WORKING_DIRECTORIES: List[str] = ["/tmp", "/var/tmp"]  # Explicitly allowed root directories
    TERRAFORM_BLOCKED_WORKING_DIRECTORIES: List[str] = ["/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys"]  # Blocked directories (removed / and /var to avoid conflicts)