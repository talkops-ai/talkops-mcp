# Terraform MCP Server

A comprehensive Model Context Protocol (MCP) server for Terraform operations, featuring secure command execution, semantic document search, and intelligent document ingestion with vector embeddings and Neo4j integration.

## 🚀 Key Features

- **Secure Terraform Execution**: Execute Terraform commands with comprehensive validation, security checks, and configurable parameters
- **Semantic Document Search**: Vector similarity search over Terraform documentation using LangChain Neo4j integration
- **Intelligent Document Ingestion**: Process Terraform resources, data sources, and best practices with structured chunking
- **MCP Server Integration**: Full Model Context Protocol support for AI agent integration
- **Multi-Provider AI Support**: OpenAI, Anthropic, Azure OpenAI, HuggingFace, Cohere, Ollama
- **Neo4j Vector Database**: HNSW-based similarity search with comprehensive metadata tracking

## 🏗️ Architecture

### Core Tools

The server provides three main MCP tools that work together to provide comprehensive Terraform support:

#### 1. Terraform Execution Tool (`terraform_execute`)

Secure execution of Terraform commands with enterprise-grade security and validation:

**User Query**: "Can you run terraform plan in /path/to/terraform/config with environment=production, AWS region us-west-2, and a 5-minute timeout?"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
await terraform_execute(
    command="plan",
    working_directory="/path/to/terraform/config",
    variables={"environment": "production"},
    aws_region="us-west-2",
    timeout=300
)
```

**User Query**: "Apply the terraform configuration in /path/to/terraform/config with instance_type=t3.micro and clean up the output"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
await terraform_execute(
    command="apply",
    working_directory="/path/to/terraform/config",
    variables={"instance_type": "t3.micro"},
    strip_ansi=True
)
```

**Features:**
- **🔒 Security Validation**: Directory traversal protection, dangerous pattern detection, command whitelisting
- **⚡ Command Processing**: Auto-approval for apply/destroy, variable injection, AWS region support
- **📊 Output Processing**: ANSI code removal, Unicode normalization, output truncation (10K chars)
- **⏱️ Timeout Management**: Configurable timeouts (1-1800 seconds), automatic process termination
- **📈 Metadata Collection**: Execution timing, Terraform version detection, return code tracking
- **🛡️ Comprehensive Security**: 100+ dangerous patterns detected, directory depth limiting, blocked system paths

**Supported Commands**: `init`, `plan`, `validate`, `apply`, `destroy`

**Security Features**:
- Whitelisted commands only
- Directory traversal protection (`..` blocked)
- Dangerous pattern detection (command injection, system commands)
- Working directory validation (only `/tmp`, `/var/tmp` allowed by default)
- Maximum 100 variables per execution
- Cross-platform security (Unix + Windows patterns)

📖 **[Detailed Documentation](docs/terraform_execution_tool.md)** - Complete API reference, security patterns, configuration options, and troubleshooting guide

#### 2. Terraform Document Search Tool (`terraform_doc_search`)

Semantic similarity search over ingested Terraform documentation:

**User Query**: "Find AWS EC2 instance configuration and best practices"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
await terraform_doc_search(
    query="AWS EC2 instance configuration and best practices",
    top_k=5,
    similarity_threshold=0.7,
    node_types=["resource", "best_practice"]
)
```

**User Query**: "Search for VPC data source configuration"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_doc_search tool
await terraform_doc_search(
    query="VPC data source configuration",
    top_k=3,
    node_types=["data_source"]
)
```

**Features:**
- **🔍 Vector Similarity Search**: HNSW index with cosine similarity scoring, 1536-dimensional embeddings
- **📚 Multi-Type Search**: Resources, data sources, and best practices with separate optimized indexes
- **🎯 Advanced Filtering**: Node type filtering, similarity thresholds (0.0-1.0), result count control (1-50)
- **⚡ Performance Optimized**: Lazy initialization, connection reuse, 10-100ms query times
- **🔄 Result Distribution**: Even distribution across node types with global ranking
- **📊 Rich Metadata**: Comprehensive result metadata with similarity scores and node types

**Search Capabilities**:
- Three dedicated HNSW indexes for different document types
- Configurable similarity thresholds for precision/recall tuning
- Natural language query processing with 1000 character limit
- Concurrent search support with graceful error handling

📖 **[Detailed Documentation](docs/terraform_document_search_tool.md)** - Complete MCP Tool reference, search algorithms, performance characteristics, and troubleshooting guide

#### 3. Terraform Document Ingestion Tool (`ingest_terraform_docs`)

Sophisticated document processing system with intelligent ingestion strategies:

**User Query**: "Ingest AWS provider resources and data sources"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the ingest_terraform_docs tool
await ingest_terraform_docs(
    filter_types=["terraform"]  # Both resource and data_source
)
```

**User Query**: "Ingest Terraform best practices from the docs directory"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the ingest_terraform_docs tool
await ingest_terraform_docs(
    filter_types=["best_practice"],
    scan_dirs=["docs/", "terraform_mcp_server/docs/"]
)
```

**Ingestion Capabilities**:
- **🔄 Multi-Format Support**: HTML, Markdown, PDF document processing
- **🔍 Intelligent Discovery**: Index-based and directory scanning
- **🤖 LLM-Powered Extraction**: AI-powered content structuring for best practices
- **📊 Structured Chunking**: Semantic chunking with metadata preservation
- **⚡ Incremental Processing**: Skip already ingested documents
- **🎯 Service Filtering**: Filter by specific AWS services
- **🗄️ Neo4j Integration**: Graph database storage with vector indexes

📖 **[Detailed Documentation](docs/terraform_document_ingestion_tool.md)** - Complete MCP Tool reference, ingestion strategies, LLM usage patterns, and troubleshooting guide

## 🚀 Installation

### Prerequisites
- Python 3.12 or higher
- Neo4j Database (4.4+ with vector search support)

#### Neo4j Database Setup

**Option 1: Using Docker (Recommended)**

1. **Pull the latest Neo4j Docker image:**
   ```bash
   docker pull neo4j
   ```

2. **Start Neo4j database:**
   ```bash
   docker run \
     --publish=7474:7474 --publish=7687:7687 \
     --volume=/path/to/your/neo4j_data:/data \
     --env NEO4J_AUTH=neo4j/your-password \
     --env NEO4J_PLUGINS='["apoc"]' \
     --env "NEO4J_dbms_security_procedures_unrestricted=apoc.*,apoc.meta.data" \
     --env "NEO4J_dbms_security_procedures_allowlist=apoc.*,apoc.meta.data" \
     neo4j
   ```

   **Important Notes:**
   - Replace `/path/to/your/neo4j_data` with your desired data directory path
   - Replace `your-password` with a secure password
   - Port 7474 is for Neo4j Browser (web interface)
   - Port 7687 is for Bolt protocol (used by the MCP server)

**Option 2: Direct Installation**

Download and install Neo4j from [neo4j.com](https://neo4j.com/download/) following their official installation guide.


### Installation
1. **Install [uv](https://docs.astral.sh/uv/getting-started/installation/)** for dependency management
2. **Create and activate a virtual environment with Python 3.12:**
   ```sh
   uv venv --python=3.12
   source .venv/bin/activate  # On Unix/macOS
   # or
   .venv\Scripts\activate  # On Windows
   ```
3. **Install dependencies from pyproject.toml:**
   ```sh
   uv pip install -e .
   ```

### Set up environment variables

Create a `.env` file in the project root with the following configuration:

```bash
# Create .env file
touch .env
```

Add the following configuration to your `.env` file:

```env
# Required: Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

# Required: AI Provider Configuration (choose one)
OPENAI_API_KEY=sk-...                    # OpenAI
ANTHROPIC_API_KEY=sk-ant-...            # Anthropic
AZURE_OPENAI_API_KEY=your-key           # Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://...       # Azure OpenAI
```
```

### Additional Configuration (Optional)

For advanced configuration, you can also add these optional settings to your `.env` file:

```env
# Optional: Additional AI Providers
COHERE_API_KEY=your-key                 # Cohere
OLLAMA_BASE_URL=http://localhost:11434  # Ollama

# Optional: Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

## 🚀 Quick Start

### 1. Start the MCP Server

```bash
# Start the server
uv run terraform_mcp_server

# The server will be available for MCP client connections
```

#### Server Configuration

The server runs with the following default configuration:

- **Host**: `localhost`
- **Port**: `8000`
- **Transport**: `sse` (Server-Sent Events)

You can customize these settings using command-line options:

```bash
uv run terraform_mcp_server --host 0.0.0.0 --port 9000 --transport stdio
```

**Available Options:**
- `--host`: Host on which the server is started (default: localhost)
- `--port`: Port on which the server is started (default: 8080)
- `--transport`: MCP Transport protocol (default: sse)

#### MCP Client Configuration

To connect to the Terraform MCP Server from an MCP client (like Cursor), add the following configuration to your MCP client settings:

```json
{
  "terraform-mcp-server": {
    "url": "http://127.0.0.1:8000/sse",
    "transport": "sse",
    "disabled": false,
    "autoApprove": []
  }
}
```

**Configuration Parameters:**
- `url`: The SSE endpoint URL for the server (default: http://127.0.0.1:8000/sse)
- `transport`: Transport protocol (sse for Server-Sent Events)
- `disabled`: Set to `true` to disable this MCP server connection
- `autoApprove`: Array of tool names that should be auto-approved (empty for manual approval)

### 2. Ingest Terraform Documentation

**User Query**: "Ingest AWS provider resources and data sources"

**User Query**: "Ingest Terraform best practices documentation"

### 3. Search Documentation

**User Query**: "Search for S3 bucket configuration and best practices"

**User Query**: "Find VPC data source subnet information"
```

### 4. Execute Terraform Commands

**User Query**: "Initialize Terraform in /tmp/terraform-project"

**User Query**: "Plan Terraform changes with environment=production, instance_count=3, and AWS region us-west-2"

**User Query**: "Apply the Terraform configuration with auto-approve"

## 🔧 Configuration

### Default Configuration

The server uses a comprehensive configuration system with environment variable support:

```python
# Server Configuration
HOST = "0.0.0.0"
PORT = 8000
DEBUG = False

# Neo4j Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "password"

# AI Configuration
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4o"
EMBEDDING_PROVIDER = "openai"
EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_DIMENSIONS = 1536

# Terraform Execution Security
TERRAFORM_SECURITY_ENABLED = True
TERRAFORM_ALLOWED_COMMANDS = ["init", "plan", "validate", "apply", "destroy"]
TERRAFORM_ALLOWED_WORKING_DIRECTORIES = ["/tmp", "/var/tmp"]
TERRAFORM_MAX_TIMEOUT = 1800  # 30 minutes
```

### Security Features

The Terraform execution tool includes comprehensive security measures:

- **Command Whitelisting**: Only allowed Terraform commands can be executed
- **Directory Validation**: Working directory validation with traversal protection
- **Pattern Detection**: Dangerous pattern detection in variables and commands
- **Timeout Limits**: Configurable execution timeouts to prevent hanging processes
- **Output Sanitization**: ANSI code removal and output length limiting

## 📚 Examples

### Complete Workflow Example

**User Query**: "Ingest EC2 and VPC documentation and best practices"

**User Query**: "Search for EC2 instance with VPC configuration guidance"

**User Query**: "Initialize Terraform in /tmp/ec2-project"

**User Query**: "Plan Terraform changes with instance_type=t3.micro and vpc_id=vpc-12345678"

### Advanced Search Example

**User Query**: "Search for S3 bucket encryption and access control with high similarity threshold"

**User Query**: "Find best practices for S3 bucket security configuration"


## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

This project is licensed under the Apache License, Version 2.0 - see the LICENSE file for details.

## 🙏 Acknowledgments

- **AWS Labs**: For open-sourcing their Terraform MCP server implementation, which served as the foundational inspiration and base layer for this project. Several key ideas and architectural patterns were adapted from their excellent work.
- **HashiCorp**: For the excellent Terraform documentation
- **Neo4j**: For the powerful graph database and vector search capabilities
- **LangChain**: For the comprehensive AI framework integration
- **OpenAI, Anthropic, and other AI providers**: For their cutting-edge AI models
- **The open-source community**: For inspiration and tools

## 🔗 Related Projects

- [Terraform Registry](https://registry.terraform.io/)
- [Neo4j Vector Search](https://neo4j.com/docs/cypher-manual/current/indexes-for-vector-search/)
- [LangChain Neo4j Integration](https://python.langchain.com/docs/integrations/vectorstores/neo4j)
- [Model Context Protocol](https://modelcontextprotocol.io/)
