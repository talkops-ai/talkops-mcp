# Terraform Document Ingestion Tool Documentation

## Overview

The Terraform Document Ingestion Tool (`ingest_terraform_docs`) is a sophisticated document processing system that automatically ingests, processes, and stores Terraform documentation into a knowledge graph using vector embeddings and structured chunking. It provides comprehensive ingestion capabilities for Terraform resources, data sources, best practices, and READMEs with intelligent processing strategies and LLM-powered extraction.

## Tool Information

- **MCP Tool Name**: `ingest_terraform_docs`
- **Description**: Ingest Terraform documentation (resources, data sources, best practices) into the knowledge graph using vector embeddings and structured chunking
- **Base Class**: `TFIngestionTool` extends `BaseMCPTool`

## Core Features

### 🔄 Ingestion Strategies

#### Automatic Document Discovery
- **Index-Based Discovery**: Parse Markdown index files to discover resources and data sources
- **Directory Scanning**: Scan directories for best practices and READMEs
- **URL Processing**: Download and process documents from GitHub and other sources
- **Incremental Processing**: Skip already ingested documents using CSV logging

#### Multi-Format Support
- **HTML Documents**: Process Terraform provider documentation from GitHub
- **Markdown Files**: Handle local and remote Markdown documentation
- **PDF Documents**: Extract content from PDF best practice guides
- **Mixed Content**: Support for various document formats in unified ingestion

#### Intelligent Processing Strategies
- **Structured Chunking**: Semantic chunking with metadata preservation
- **LLM Extraction**: AI-powered content extraction and structuring
- **Vector Embedding**: Automatic embedding generation for similarity search
- **Neo4j Storage**: Graph database storage with vector indexes

### 🏗️ Architecture Components

#### IngestionOrchestrator
- **Unified Ingestion**: Single interface for all ingestion operations
- **Strategy Management**: Configurable processing strategies per document type
- **Filtering System**: Service and type-based filtering
- **Progress Tracking**: CSV-based ingestion logging and progress tracking

#### Document Processing Pipeline
- **Loader System**: Format-specific document loaders (HTML, Markdown, PDF)
- **Chunking Engine**: Recursive character chunking with overlap
- **Embedding Service**: Multi-provider embedding generation
- **Neo4j Integration**: Graph database storage with constraints and indexes

#### LLM-Powered Extraction
- **ChunkExtractionPipeline**: LLM-based content extraction and structuring
- **Schema Validation**: Pydantic-based output validation
- **Sequential Processing**: Rate-limited LLM calls for best practices
- **Error Recovery**: Graceful handling of extraction failures

#### Structured Chunking
- **Semantic Segmentation**: Meaningful chunk creation based on document structure
- **Metadata Preservation**: Provider, service, and name metadata retention
- **Type-Specific Chunking**: Different strategies for resources, data sources, and best practices
- **Content Organization**: Logical grouping of related information

## Input Parameters

### Required Parameters

| Parameter | Type | Description | Validation |
|-----------|------|-------------|------------|
| `filter_types` | list | Document types to ingest | Valid types: 'resource', 'data_source', 'datasource', 'best_practice', 'terraform', 'readme' |

### Optional Parameters

| Parameter | Type | Default | Description | Validation |
|-----------|------|---------|-------------|------------|
| `filter_services` | list | None | Service names to filter by (e.g., ['S3', 'EC2']) | Non-empty if provided |
| `scan_dirs` | list | ["docs/", "terraform_mcp_server/docs/"] | Directories to scan for documents | None |


## Usage Examples

### Ingest AWS Resources and Data Sources

**User Query**: "Ingest AWS provider resources and data sources documents"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the ingest_terraform_docs tool
result = await ingest_terraform_docs(
    filter_types=["terraform"],  # Both resource and data_source
)
```

### Ingest Best Practices

**User Query**: "Ingest Terraform best practices documents"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the ingest_terraform_docs tool
result = await ingest_terraform_docs(
    filter_types=["best_practice"],
    scan_dirs=["docs/", "terraform_mcp_server/docs/"]
)
```

**Response**: Scans directories for best practice documents and processes them with LLM extraction.

### Ingest READMEs

**User Query**: "Ingest README files from the project"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the ingest_terraform_docs tool
result = await ingest_terraform_docs(
    filter_types=["readme"],
    scan_dirs=["docs/", "examples/", "modules/"]
)
```

**Response**: Scans specified directories for README files and ingests them.

### Comprehensive Ingestion

**User Query**: "Ingest all Terraform documentation including resources, data sources, best practices, and READMEs"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the ingest_terraform_docs tool
result = await ingest_terraform_docs(
    filter_types=["resource", "data_source", "best_practice", "readme"],
    scan_dirs=["docs/", "terraform_mcp_server/docs/", "examples/"]
)
```

**Response**: Comprehensive ingestion of all document types with service filtering.

## Ingestion Pipeline Details

### Document Processing Flow

1. **Document Discovery**
   - Parse index files for resources/data sources
   - Scan directories for best practices and READMEs
   - Apply service and type filtering

2. **Document Loading**
   - Format detection (HTML, Markdown, PDF)
   - Loader selection and content extraction
   - URL downloading for remote documents

3. **Content Processing**
   - **Resources/Data Sources**: Structured loader with semantic chunking
   - **Best Practices**: LLM extraction with sequential processing
   - **READMEs**: Standard chunking with embedding generation

4. **Embedding Generation**
   - Multi-provider embedding service
   - Dimension handling for different models
   - Batch processing for efficiency

5. **Neo4j Storage**
   - Graph database ingestion with constraints
   - Vector index creation for similarity search
   - Metadata preservation and indexing

### LLM Usage Strategies

#### Best Practice Processing
- **Sequential LLM Calls**: Rate-limited processing to avoid API limits
- **Schema Validation**: Pydantic-based output validation
- **Structured Extraction**: Extract best practices, security guidelines, compliance info
- **Error Recovery**: Graceful handling of extraction failures

#### Content Structuring
- **Semantic Chunking**: Create meaningful chunks based on content structure
- **Metadata Preservation**: Maintain provider, service, and name information
- **Type-Specific Processing**: Different strategies for different document types

### Chunking Strategies

#### Resource/Data Source Chunking
```python
# Structured chunks created for Terraform resources
chunks = [
    {
        "content": "Resource overview and description...",
        "provider": "aws",
        "service": "S3",
        "name": "aws_s3_bucket",
        "type": "resource",
        "chunk_type": "overview"
    },
    {
        "content": "Arguments and parameters...",
        "provider": "aws",
        "service": "S3",
        "name": "aws_s3_bucket",
        "type": "resource",
        "chunk_type": "arguments"
    },
    {
        "content": "Attributes and outputs...",
        "provider": "aws",
        "service": "S3",
        "name": "aws_s3_bucket",
        "type": "resource",
        "chunk_type": "attributes"
    },
    {
        "content": "Usage examples...",
        "provider": "aws",
        "service": "S3",
        "name": "aws_s3_bucket",
        "type": "resource",
        "chunk_type": "examples"
    }
]
```

#### Best Practice Chunking
```python
# LLM-extracted best practices with structured chunks
chunks = [
    {
        "content": "Best practice overview...",
        "provider": "aws",
        "service": "general",
        "name": "terraform_best_practices",
        "type": "best_practice",
        "chunk_type": "overview"
    },
    {
        "content": "Security best practices...",
        "provider": "aws",
        "service": "security",
        "name": "terraform_best_practices",
        "type": "best_practice",
        "chunk_type": "security"
    },
    {
        "content": "Compliance guidelines...",
        "provider": "aws",
        "service": "compliance",
        "name": "terraform_best_practices",
        "type": "best_practice",
        "chunk_type": "compliance"
    }
]
```

## Configuration

### Required Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `NEO4J_URI` | "bolt://localhost:7687" | Neo4j database connection URI |
| `NEO4J_USERNAME` | "neo4j" | Neo4j database username |
| `NEO4J_PASSWORD` | "password" | Neo4j database password |
| `EMBEDDING_MODEL` | "text-embedding-ada-002" | OpenAI embedding model |
| `EMBEDDING_DIMENSIONS` | 1536 | Embedding vector dimensions |
| `EMBEDDING_PROVIDER` | "openai" | Embedding provider |

### Ingestion Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `CHUNK_SIZE` | 1000 | Default chunk size in characters |
| `CHUNK_OVERLAP` | 200 | Default chunk overlap in characters |
| `BATCH_SIZE` | 100 | Batch size for processing |
| `MAX_RETRIES` | 3 | Maximum retry attempts |
| `RETRY_DELAY` | 1.0 | Delay between retries in seconds |

### Default Ingestion Strategies

| Document Type | Strategies | Description |
|---------------|------------|-------------|
| `resource` | ["embedding"] | Structured chunking with embedding generation |
| `data_source` | ["embedding"] | Structured chunking with embedding generation |
| `best_practice` | ["embedding", "llm"] | LLM extraction + embedding generation |
| `readme` | ["embedding", "llm"] | Standard chunking + LLM extraction |

## Performance Characteristics

### Processing Performance
- **Document Loading**: 1-5 seconds per document depending on size
- **LLM Extraction**: 2-10 seconds per chunk (rate-limited)
- **Embedding Generation**: 0.5-2 seconds per batch
- **Neo4j Storage**: 1-3 seconds per batch

### Scalability
- **Batch Processing**: Configurable batch sizes for efficiency
- **Incremental Updates**: Skip already processed documents
- **Parallel Processing**: Concurrent document processing where possible
- **Memory Management**: Efficient memory usage with streaming

### Optimization Features
- **Lazy Initialization**: Components initialized on first use
- **Connection Reuse**: Neo4j connections reused across operations
- **Rate Limiting**: LLM API rate limiting to avoid quotas
- **Error Recovery**: Graceful handling of processing failures

## Error Handling

### Common Error Scenarios

1. **Document Download Failed**
   ```
   Error: Failed to download document from URL
   ```

2. **LLM Extraction Failed**
   ```
   Error: LLM extraction failed for chunk
   ```

3. **Embedding Generation Failed**
   ```
   Error: Failed to generate embeddings
   ```

4. **Neo4j Connection Failed**
   ```
   Error: Failed to connect to Neo4j database
   ```

5. **Schema Validation Failed**
   ```
   Error: LLM output failed schema validation
   ```

### Error Recovery
- **Retry Logic**: Automatic retries for transient failures
- **Partial Success**: Continue processing other documents on failure
- **Detailed Logging**: Comprehensive error logging for debugging
- **Graceful Degradation**: Fallback strategies for failed operations


## Best Practices

### Ingestion Optimization
1. **Use Specific Filter Types**: Filter by document types to focus ingestion
2. **Service Filtering**: Use service filters to limit scope
3. **Incremental Updates**: Leverage existing ingestion logs
4. **Monitor Performance**: Track processing times and success rates

### Configuration Management
1. **Batch Size Tuning**: Adjust batch sizes based on system resources
2. **Rate Limiting**: Configure appropriate delays for LLM calls
3. **Memory Management**: Monitor memory usage during large ingestions
4. **Error Handling**: Implement appropriate retry strategies

### Quality Assurance
1. **Schema Validation**: Ensure LLM outputs meet expected schemas
2. **Content Verification**: Verify extracted content quality
3. **Metadata Preservation**: Ensure metadata is properly preserved
4. **Index Optimization**: Regular index maintenance and optimization

## Limitations

1. **Document Size**: Large documents may require significant processing time
2. **LLM Dependencies**: Best practice extraction requires LLM API access
3. **Rate Limits**: LLM API rate limits may slow processing
4. **Format Support**: Limited to HTML, Markdown, and PDF formats
5. **Neo4j Dependency**: Requires Neo4j database with vector search support
6. **Index Availability**: Depends on pre-built vector indexes
