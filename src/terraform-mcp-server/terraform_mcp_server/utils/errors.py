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
Custom exception classes for the knowledge graph system.
"""


class KnowledgeGraphError(Exception):
    """Base exception for knowledge graph errors."""
    pass


class UnsupportedProviderError(KnowledgeGraphError):
    """Raised when an unsupported provider is requested."""
    pass


class LLMConfigurationError(KnowledgeGraphError):
    """Raised when LLM configuration is invalid or missing."""
    pass


class EmbeddingConfigurationError(KnowledgeGraphError):
    """Raised when embedding configuration is invalid or missing."""
    pass


class ConfigurationError(KnowledgeGraphError):
    """Raised when general configuration is invalid or missing."""
    pass


class IngestionError(KnowledgeGraphError):
    """Raised when document ingestion fails."""
    pass


class VectorSearchError(KnowledgeGraphError):
    """Raised when vector search operations fail."""
    pass


class Neo4jError(KnowledgeGraphError):
    """Raised when Neo4j operations fail."""
    pass


class ValidationError(KnowledgeGraphError):
    """Raised when data validation fails."""
    pass


class ConfigError(KnowledgeGraphError):
    """Raised when configuration is invalid or missing."""
    pass


class QueryParsingError(KnowledgeGraphError):
    """Raised when natural language query parsing fails."""
    pass


class LoaderError(KnowledgeGraphError):
    """Raised when document loading fails."""
    pass


class UnsupportedFormatError(KnowledgeGraphError):
    """Raised when an unsupported document format is encountered."""
    pass


class MetadataValidationError(KnowledgeGraphError):
    """Raised when metadata validation fails."""
    pass
