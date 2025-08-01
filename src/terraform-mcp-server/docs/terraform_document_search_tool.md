# Terraform Document Search Tool Documentation

## Overview

The Terraform Document Search Tool (`terraform_doc_search`) is a sophisticated semantic search engine that provides vector similarity search capabilities over Terraform documentation using LangChain Neo4j integration. It enables users to find relevant Terraform resources, data sources, and best practices through natural language queries with configurable similarity thresholds and filtering options.

## Tool Information

- **MCP Tool Name**: `terraform_doc_search`
- **Description**: Perform semantic similarity search over terraform document chunks using vector embeddings with LangChain Neo4j integration
- **Base Class**: `TFSearchTool` extends `BaseMCPTool`

## Core Features

### 🔍 Semantic Search Capabilities

#### Vector Similarity Search
- **HNSW Index**: Uses Hierarchical Navigable Small World (HNSW) vector index for fast similarity search
- **Multi-Dimensional Embeddings**: Supports high-dimensional vector embeddings (default: 1536 dimensions)
- **Cosine Similarity**: Implements cosine similarity scoring for semantic matching
- **Configurable Thresholds**: Adjustable similarity score thresholds (0.0 to 1.0)

#### Multi-Type Document Search
- **Resource Documentation**: Search Terraform aws resource documentation and examples
- **Data Source Documentation**: Search Terraform aws data source documentation
- **Best Practices**: Search Terraform aws best practices and guidelines
- **Combined Search**: Search across all document types simultaneously

#### Advanced Filtering
- **Node Type Filtering**: Filter results by specific document types
- **Similarity Threshold Filtering**: Filter results by minimum similarity score
- **Result Count Control**: Configurable number of results (1-50)
- **Score-Based Ranking**: Results automatically ranked by similarity score

### 🏗️ Architecture Components

#### LangChain Neo4j Integration
- **Neo4jGraph**: Direct connection to Neo4j database for graph operations
- **Neo4jVector**: Vector store implementation for similarity search

#### Embedding System
- **OpenAI Embeddings**: Primary embedding provider (configurable)
- **Multi-Provider Support**: Extensible to other embedding providers
- **Dimension Management**: Automatic dimension handling and validation
- **Model Configuration**: Configurable embedding models and parameters

#### Vector Index Management
- **Separate Indexes**: Dedicated HNSW indexes for each document type:
  - `docchunk_resource_embedding_hnsw` for resources
  - `docchunk_datasource_embedding_hnsw` for data sources
  - `docchunk_bestpractice_embedding_hnsw` for best practices
- **Index Optimization**: Optimized for fast similarity search
- **Metadata Preservation**: Rich metadata storage and retrieval

## Input Parameters

### Required Parameters

| Parameter | Type | Description | Validation |
|-----------|------|-------------|------------|
| `query` | string | Search query to find similar document chunks | 1-1000 characters, non-empty |

### Optional Parameters

| Parameter | Type | Default | Description | Validation |
|-----------|------|---------|-------------|------------|
| `top_k` | integer | 5 | Number of top results to return | 1-50 range |
| `similarity_threshold` | float | 0.7 | Minimum similarity score threshold | 0.0-1.0 range |
| `node_types` | list | None | Node types to search | Valid types: 'resource', 'data_source', 'best_practice' |

## Output Structure

### Success Response

```json
{
  "success": true,
  "data": {
    "query": "AWS EC2 instance configuration",
    "results_count": 3,
    "results": [
      {
        "content": "resource \"aws_instance\" \"example\" {\n  ami           = data.aws_ami.ubuntu.id\n  instance_type = \"t3.micro\"\n\n  tags = {\n    Name = \"ExampleInstance\"\n  }\n}",
        "similarity_score": 0.89,
        "node_type": "resource",
        "id": "docchunk_001",
        "chunk_index": null,
        "source_path": null,
        "file_name": null,
        "loader": null,
        "ingested_at": null
      },
      {
        "content": "Best practices for EC2 instance configuration include using data sources for AMI selection, implementing proper tagging, and following the principle of least privilege.",
        "similarity_score": 0.76,
        "node_type": "best_practice",
        "id": "docchunk_002",
        "chunk_index": null,
        "source_path": null,
        "file_name": null,
        "loader": null,
        "ingested_at": null
      }
    ],
    "search_parameters": {
      "top_k": 5,
      "similarity_threshold": 0.7
    },
    "service_info": {
      "provider": "openai",
      "model": "text-embedding-ada-002",
      "dimensions": 1536,
      "index_name": "docchunk_resource_embedding_hnsw, docchunk_bestpractice_embedding_hnsw",
      "integration": "langchain_neo4j"
    }
  },
  "metadata": {
    "timestamp": "2025-08-01T13:21:14.246401",
    "tool": "terraform_doc_search",
    "execution_id": "terraform_doc_search_0",
    "version": "1.0.0"
  }
}
```

### Error Response

```json
{
  "success": false,
  "data": {
    "query": "AWS EC2 instance configuration",
    "results_count": 0,
    "results": [],
    "search_parameters": {
      "top_k": 5,
      "similarity_threshold": 0.7
    },
    "service_info": {
      "provider": "openai",
      "model": "text-embedding-ada-002",
      "dimensions": 1536,
      "index_name": "docchunk_resource_embedding_hnsw, docchunk_bestpractice_embedding_hnsw",
      "integration": "langchain_neo4j"
    }
  },
  "metadata": {
    "timestamp": "2025-08-01T13:21:14.246401",
    "tool": "terraform_doc_search",
    "execution_id": "terraform_doc_search_0",
    "version": "1.0.0"
  }
}
```

## Usage Examples

### Basic Resource Search

**User Query**: "Find AWS S3 bucket configuration examples"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
result = await terraform_doc_search(
    query="AWS S3 bucket configuration examples",
    top_k=5,
    similarity_threshold=0.7,
    node_types=["resource"]
)
```

**Response**: Returns S3 bucket resource configurations and examples from Terraform documentation.

### Multi-Type Search

**User Query**: "Search for VPC configuration in both resources and best practices"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
result = await terraform_doc_search(
    query="VPC configuration",
    top_k=10,
    similarity_threshold=0.6,
    node_types=["resource", "best_practice"]
)
```

**Response**: Returns VPC-related resources and best practices from Terraform documentation.

### High Precision Search

**User Query**: "Find exact matches for EC2 instance with encryption"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
result = await terraform_doc_search(
    query="EC2 instance with encryption",
    top_k=3,
    similarity_threshold=0.9,  # High threshold for precision
    node_types=["resource", "data_source"]
)
```

**Response**: Returns only highly relevant EC2 instance configurations with encryption.

### Data Source Search

**User Query**: "Find data sources for getting VPC information"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
result = await terraform_doc_search(
    query="search data sources for getting VPC information",
    top_k=5,
    node_types=["data_source"]
)
```

**Response**: Returns VPC-related data sources from Terraform documentation.

### Best Practices Search

**User Query**: "What are the best practices for Terraform state management?"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
result = await terraform_doc_search(
    query="best practices for Terraform state management",
    top_k=8,
    similarity_threshold=0.7,
    node_types=["best_practice"]
)
```

**Response**: Returns best practices and guidelines for Terraform state management.

## Search Algorithm Details

### Vector Similarity Search Process

1. **Query Embedding**: Convert natural language query to vector embedding
2. **Multi-Index Search**: Search across relevant HNSW indexes
3. **Score Calculation**: Calculate cosine similarity scores
4. **Threshold Filtering**: Filter results by similarity threshold
5. **Result Ranking**: Sort results by similarity score (highest first)
6. **Result Limiting**: Return top-k results

### Cypher Query Structure

The tool uses optimized Cypher queries for each node type:

```cypher
// Resource Search Query
MATCH (node:DocChunk_Resource)
RETURN 
    node.content AS text,
    score,
    {
        id: node.id,
        node_type: 'resource'
    } AS metadata
ORDER BY score DESC

// Data Source Search Query
MATCH (node:DocChunk_DataSource)
RETURN 
    node.content AS text,
    score,
    {
        id: node.id,
        node_type: 'data_source'
    } AS metadata
ORDER BY score DESC

// Best Practice Search Query
MATCH (node:DocChunk_BestPractice)
RETURN 
    node.content AS text,
    score,
    {
        id: node.id,
        node_type: 'best_practice'
    } AS metadata
ORDER BY score DESC
```

### Result Distribution Strategy

When searching multiple node types:
- **Even Distribution**: Results distributed evenly across node types
- **Per-Type Limit**: `top_k // number_of_node_types` results per type
- **Minimum Results**: At least 1 result per type if available
- **Global Ranking**: Final results ranked by similarity score across all types

## Configuration

### Required Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `NEO4J_URI` | "bolt://localhost:7687" | Neo4j database connection URI |
| `NEO4J_USERNAME` | "neo4j" | Neo4j database username |
| `NEO4J_PASSWORD` | "password" | Neo4j database password |
| `EMBEDDING_MODEL` | "text-embedding-ada-002" | OpenAI embedding model |
| `EMBEDDING_DIMENSIONS` | 1536 | Embedding vector dimensions |

### Vector Index Configuration

| Index Name | Node Type | Description |
|------------|-----------|-------------|
| `docchunk_resource_embedding_hnsw` | Resource | HNSW index for resource documentation |
| `docchunk_datasource_embedding_hnsw` | Data Source | HNSW index for data source documentation |
| `docchunk_bestpractice_embedding_hnsw` | Best Practice | HNSW index for best practices |

### Search Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `top_k` | 5 | 1-50 | Maximum number of results |
| `similarity_threshold` | 0.7 | 0.0-1.0 | Minimum similarity score |
| `query_max_length` | 1000 | 1-1000 | Maximum query length |

## Performance Characteristics

### Search Performance
- **Query Time**: Typically 10-100ms for most queries
- **Index Size**: Scales with document corpus size
- **Memory Usage**: Efficient memory usage with lazy loading
- **Concurrent Searches**: Supports multiple concurrent search requests

### Scalability
- **Document Count**: Scales to millions of document chunks
- **Index Performance**: HNSW index maintains performance with large datasets
- **Memory Efficiency**: Lazy initialization reduces memory footprint
- **Connection Pooling**: Efficient Neo4j connection management

### Optimization Features
- **Lazy Initialization**: Components initialized on first use
- **Connection Reuse**: Neo4j connections reused across requests
- **Query Optimization**: Optimized Cypher queries for each node type
- **Result Caching**: Built-in result caching for repeated queries

## Error Handling

### Common Error Scenarios

1. **No Results Found**
   ```
   Response: Empty results array with results_count: 0
   ```

2. **Invalid Node Types**
   ```
   Error: Node type must be one of: resource, data_source, best_practice
   ```

3. **Query Too Long**
   ```
   Error: Query length exceeds maximum of 1000 characters
   ```

4. **Neo4j Connection Failed**
   ```
   Error: Failed to connect to Neo4j database
   ```

5. **Embedding Model Error**
   ```
   Error: Failed to generate embeddings for query
   ```

## Health Check

The tool provides a comprehensive health check endpoint:

```python
health_info = tool.get_tool_health()
```

Returns:
- Tool status (healthy/unhealthy)
- Component status (Neo4j connection, embedding model, vector stores)
- Configuration details
- Validation status
- Index information

## Best Practices

### Search Optimization
1. **Use Specific Queries**: More specific queries yield better results
2. **Adjust Similarity Thresholds**: Higher thresholds for precision, lower for recall
3. **Filter by Node Types**: Use node type filtering to focus search
4. **Monitor Query Performance**: Track search times and result quality

### Query Design
1. **Natural Language**: Use natural language queries for best results
2. **Include Context**: Include relevant context in queries
3. **Use Keywords**: Include important keywords and concepts
4. **Iterative Refinement**: Refine queries based on initial results

## Limitations

1. **Query Length**: Maximum 1000 characters per query
2. **Result Count**: Maximum 50 results per search
3. **Node Type Restrictions**: Limited to predefined node types
5. **Neo4j Dependency**: Requires Neo4j database with vector search support
6. **Index Availability**: Depends on pre-built vector indexes