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

import os
import tempfile
import requests
import csv
import re
from requests.adapters import HTTPAdapter, Retry
from typing import List, Dict, Any
from terraform_mcp_server.core.ingestion.ingestion_pipeline import IngestionPipeline
from terraform_mcp_server.core.extraction.pipeline import ChunkExtractionPipeline
from terraform_mcp_server.core.ingestion.neo4j_ingestion import Neo4jIngestion
from terraform_mcp_server.core.ingestion.structured_chunker import StructuredChunker
from terraform_mcp_server.core.loaders.terraform_structured_loader import TerraformMarkdownStructuredLoader
from terraform_mcp_server.core.llm.llm_provider import AIProvider
from terraform_mcp_server.config import Config
from terraform_mcp_server.utils.logging import get_logger
import glob

logger = get_logger(__name__)

DEFAULT_INGESTION_CONFIG = {
    "resource": ["embedding"],
    "datasource": ["embedding"],
    "data_source": ["embedding"],
    "best_practice": ["embedding", "llm"],
    "readme": ["embedding", "llm"]
}

LOG_FILE = Config().INGESTION_LOG_FILE
VALID_ASSET_RE = re.compile(r'^aws_[a-zA-Z0-9_]+$')
GITHUB_RAW_BASE_URL = Config().GITHUB_RAW_BASE_URL

# --- Asset Discovery Logic (from ingestion_web_markdown.py) ---
def construct_github_markdown_url(asset_name, asset_type):
    if asset_name.startswith("aws_"):
        resource_name = asset_name[4:]
    else:
        resource_name = asset_name
    doc_type = "r" if asset_type == "resource" else "d"
    return f"{GITHUB_RAW_BASE_URL}/{doc_type}/{resource_name}.html.markdown"

def extract_doc_assets(md_path):
    assets = []
    seen_assets = set()  # Use (name, type) tuple to distinguish
    current_type = None  # 'resource' or 'data_source'
    current_service = None
    with open(md_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            service_match = re.match(r'^##\s+(.+)$', line)
            if service_match:
                current_service = service_match.group(1).strip()
                continue
            if line.startswith('### Resources'):
                current_type = 'resource'
                continue
            elif line.startswith('### Data Sources'):
                current_type = 'data_source'
                continue
            elif line.startswith('- ['):
                match = re.match(r'- \[([^\]]+)\]\((https://registry\.terraform\.io[^)]+)\)', line)
                if match:
                    asset_name, _ = match.groups()
                    asset_name = asset_name.strip()
                    asset_key = (asset_name, current_type)
                    if not VALID_ASSET_RE.match(asset_name):
                        logger.warning(f"Skipping invalid asset name: {asset_name}")
                        continue
                    if asset_key in seen_assets:
                        logger.info(f"Skipping duplicate: {asset_name} ({current_type})")
                        continue
                    seen_assets.add(asset_key)
                    github_url = construct_github_markdown_url(asset_name, current_type)
                    assets.append({
                        'name': asset_name,
                        'type': current_type,
                        'service': current_service,
                        'url': github_url
                    })
    return assets

# --- Existing Orchestrator Logic ---
def get_already_ingested(log_file=LOG_FILE):
    ingested = set()
    if not os.path.isfile(log_file):
        return ingested
    with open(log_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row.get("status") == "success":
                ingested.add(row.get("file_path"))
    return ingested

def log_ingestion(entry: dict, log_file=LOG_FILE):
    file_exists = os.path.isfile(log_file)
    with open(log_file, mode='a', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            "timestamp", "file_path", "doc_type", "status", "error", "strategies"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)

def download_to_temp(url: str) -> str:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.warning(f"Failed to download {url}: {e}")
        return None
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout when downloading {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="w", encoding="utf-8")
    tmp.write(resp.text)
    tmp_path = tmp.name
    tmp.close()
    return tmp_path

# Rule-based parser removed - now using structured chunking approach

# --- Directory Scanning Utilities ---
def scan_for_best_practices(scan_dirs):
    """Scan directories for best practice docs (e.g., *_best_practices.pdf, *_best_practices.md)"""
    docs = []
    for d in scan_dirs:
        for ext in ["pdf", "md"]:
            for path in glob.glob(os.path.join(d, f"*best_practice*.{ext}")):
                docs.append({"path": path, "type": "best_practice"})
    return docs

def scan_for_readmes(scan_dirs):
    """Scan directories for README files (README.md, readme.md, etc.)"""
    docs = []
    for d in scan_dirs:
        for name in ["README.md", "readme.md", "README.MD"]:
            for path in glob.glob(os.path.join(d, "**", name), recursive=True):
                docs.append({"path": path, "type": "readme"})
    return docs

def scan_for_custom_patterns(scan_dirs, pattern, doc_type):
    """Scan directories for custom patterns and assign doc_type."""
    docs = []
    for d in scan_dirs:
        for path in glob.glob(os.path.join(d, pattern), recursive=True):
            docs.append({"path": path, "type": doc_type})
    return docs

class IngestionOrchestrator:
    def __init__(self, config: Dict[str, List[str]] = None, log_file: str = LOG_FILE):
        self.config = config or DEFAULT_INGESTION_CONFIG
        self.neo4j = Neo4jIngestion()
        self.extraction_pipeline = ChunkExtractionPipeline()
        self.structured_chunker = StructuredChunker()
        self.log_file = log_file
        self.already_ingested = get_already_ingested(log_file)
        # Filtering config from global Config
        cfg = Config()
        self.filter_types = getattr(cfg, 'INGESTION_FILTER_TYPES', None)
        self.filter_services = getattr(cfg, 'INGESTION_FILTER_SERVICES', None)
        
        # Create vector indexes before ingestion
        logger.info("Creating vector indexes for document chunks...")
        self.neo4j.apply_constraints_and_indexes()
        logger.info("Vector indexes created successfully")

    def ingest_document(self, doc_path: str, doc_type: str):
        is_temp = False
        local_path = doc_path
        if doc_path.startswith('http://') or doc_path.startswith('https://'):
            local_path = download_to_temp(doc_path)
            is_temp = True
            if not local_path:
                logger.warning(f"Skipping {doc_path} (download failed)")
                return
        if local_path in self.already_ingested:
            logger.info(f"[SKIP] Already ingested: {local_path}")
            if is_temp and os.path.exists(local_path):
                os.unlink(local_path)
            return
        logger.info(f"Ingesting {doc_type} document: {local_path}")
        strategies = self.config.get(doc_type, [])
        entry = {
            "timestamp": Config().now_utc(),
            "file_path": local_path,
            "doc_type": doc_type,
            "status": "pending",
            "error": None,
            "strategies": ",".join(strategies)
        }
        try:
            # Strategy: Embedding (for resources, datasources, and best practices, use structured chunking)
            if "embedding" in strategies and doc_type in ["resource", "datasource", "data_source", "best_practice"]:
                logger.info(f"Applying structured embedding strategy for Terraform {doc_type}")
                
                if doc_type == "best_practice":
                    # For best practices, use LLM extraction first, then chunk the structured data
                    logger.info("Processing best practice document with LLM extraction (sequential to avoid rate limiting)")
                    pipeline = IngestionPipeline(local_path)
                    chunks, _ = pipeline.run()
                    logger.info(f"Processing {len(chunks)} chunks sequentially with 1-second delays between LLM calls")
                    results, errors = self.extraction_pipeline.process_chunks_sequential(
                        chunks, schema="best_practice", delay_between_calls=1.0)
                    
                    if not results:
                        logger.warning(f"No best practice entities extracted from {local_path}")
                        return
                    
                    logger.info(f"Extracted {len(results)} best practice entities from {len(chunks)} chunks")
                    
                    # Process ALL extracted best practices, not just the first one
                    all_structured_chunks = []
                    for i, structured_data in enumerate(results):
                        # Create structured chunks with preserved metadata for each best practice
                        best_practice_chunks = self.structured_chunker.chunk_best_practice(structured_data)
                        all_structured_chunks.extend(best_practice_chunks)
                    
                    structured_chunks = all_structured_chunks
                else:
                    # For resources and datasources, use structured loader
                    structured_loader = TerraformMarkdownStructuredLoader(local_path)
                    structured_data = structured_loader._extract_structured_data()
                    
                    # Create structured chunks with preserved metadata
                    structured_chunks = self.structured_chunker.chunk_terraform_resource(structured_data)
                
                # Convert to standard chunk format for embedding
                chunks_for_embedding = []
                for i, chunk in enumerate(structured_chunks):
                    chunks_for_embedding.append({
                        "id": f"{chunk['name']}_{chunk['chunk_type']}_{i}",
                        "text": chunk["content"],
                        "metadata": {
                            "provider": chunk["provider"],
                            "service": chunk["service"],
                            "name": chunk["name"],
                            "type": chunk["type"],
                            "chunk_type": chunk["chunk_type"],
                            "source_file": local_path
                        }
                    })
                
                # Generate embeddings for structured chunks
                chunk_texts = [chunk["content"] for chunk in structured_chunks]
                
                # Create embedding service with proper dimension handling
                cfg = Config()
                embedding_kwargs = {
                    "provider": cfg.EMBEDDING_PROVIDER,
                    "model": cfg.EMBEDDING_MODEL
                }
                
                # Only pass dimensions for models that support it
                if cfg.EMBEDDING_MODEL not in ['text-embedding-ada-002']:
                    embedding_kwargs["dimensions"] = cfg.EMBEDDING_DIMENSIONS
                
                embedding_service = AIProvider.create_embeddings(**embedding_kwargs)
                embeddings = embedding_service.embed_documents(chunk_texts)
                
                # Determine node label based on document type
                if doc_type in ["datasource", "data_source"]:
                    node_label = "DocChunk_DataSource"
                elif doc_type == "best_practice":
                    node_label = "DocChunk_BestPractice"
                else:
                    node_label = "DocChunk_Resource"
                
                # Ingest with appropriate node label
                self.neo4j.ingest_chunks(chunks_for_embedding, embeddings, node_label=node_label)
                
            elif "embedding" in strategies:
                # Standard embedding for other document types
                logger.info("Applying standard embedding strategy")
                pipeline = IngestionPipeline(local_path)
                chunks, embeddings = pipeline.run()
                self.neo4j.ingest_chunks(chunks, embeddings)
            
            # Strategy: LLM Extraction (only for non-resource/datasource/best_practice types)
            if "llm" in strategies and doc_type not in ["resource", "datasource", "data_source", "best_practice"]:
                logger.info("Applying LLM extraction strategy")
                pipeline = IngestionPipeline(local_path)
                chunks, _ = pipeline.run()
                results, errors = self.extraction_pipeline.process_chunks_batch(
                    chunks, schema="best_practice")
                if results:
                    # Note: ingest_structured_entities was removed, so this is now handled in the embedding strategy
                    logger.warning("LLM extraction for non-best_practice types is not currently supported")
            entry["status"] = "success"
        except Exception as e:
            logger.error(f"Error during ingestion of {local_path}: {e}")
            entry["status"] = "failure"
            entry["error"] = str(e)
        finally:
            log_ingestion(entry, self.log_file)
            if is_temp and os.path.exists(local_path):
                os.unlink(local_path)

    def batch_ingest(self, doc_list: List[Dict[str, str]]):
        for doc in doc_list:
            self.ingest_document(doc["path"], doc["type"])

    def parse_index_and_ingest(self, md_path: str, filter_types: List[str] = None, filter_services: List[str] = None):
        """
        Parse a Markdown index file to discover all resource/data source docs and ingest them.
        Filtering can be configured globally via Config (INGESTION_FILTER_TYPES, INGESTION_FILTER_SERVICES),
        or overridden per call.
        Args:
            md_path (str): Path to the Markdown index file.
            filter_types (List[str], optional): List of asset types to ingest (e.g., ['resource'], ['data_source'], or both). If None, uses config.
            filter_services (List[str], optional): List of service names to ingest (e.g., ['S3', 'EC2']). If None, uses config.
        """
        # Use config defaults if not overridden
        if filter_types is None:
            filter_types = self.filter_types
        if filter_services is None:
            filter_services = self.filter_services
        assets = extract_doc_assets(md_path)
        if filter_types is not None:
            assets = [a for a in assets if a["type"] in filter_types]
        if filter_services is not None:
            assets = [a for a in assets if a["service"] in filter_services]
        doc_list = []
        for asset in assets:
            doc_list.append({"path": asset["url"], "type": asset["type"]})
        logger.info(f"Discovered {len(doc_list)} assets to ingest (types={filter_types}, services={filter_services})")
        self.batch_ingest(doc_list)

    def unified_ingest(self, index_path=None, scan_dirs=None, extra_docs=None, filter_types=None, filter_services=None):
        """
        Unified ingestion: discovers docs from index, directory scan, and extra list, applies config-driven filtering, and ingests all.
        Args:
            index_path (str, optional): Markdown index file for resources/data sources.
            scan_dirs (List[str], optional): Directories to scan for best practices, READMEs, etc.
            extra_docs (List[dict], optional): Additional docs to include (each dict: {"path": ..., "type": ...}).
            filter_types (List[str], optional): Override config for types.
            filter_services (List[str], optional): Override config for services.
        """
        doc_list = []
        # 1. Index-based discovery
        if index_path:
            assets = extract_doc_assets(index_path)
            doc_list.extend({"path": a["url"], "type": a["type"], "service": a.get("service")} for a in assets)
        # 2. Directory scan for best practices and READMEs
        if scan_dirs:
            doc_list.extend(scan_for_best_practices(scan_dirs))
            doc_list.extend(scan_for_readmes(scan_dirs))
        # 3. Extra docs
        if extra_docs:
            doc_list.extend(extra_docs)
        # 4. Filtering (by type/service)
        types = filter_types if filter_types is not None else self.filter_types
        services = filter_services if filter_services is not None else self.filter_services
        filtered = []
        for doc in doc_list:
            if types is not None and doc.get("type") not in types:
                continue
            if services is not None and doc.get("service") and doc["service"] not in services:
                continue
            filtered.append(doc)
        logger.info(f"Unified ingest: {len(filtered)} docs after filtering (types={types}, services={services})")
        self.batch_ingest(filtered)

# if __name__ == "__main__":
#     orchestrator = IngestionOrchestrator()
#     # Unified ingest: index, directory scan, and extra docs, all filtered by config
#     # orchestrator.unified_ingest(
#     #     index_path="tf_knowledge_graph/docs/AWS_PROVIDER_TEST.md",
#     #     # scan_dirs=["docs/", "modules/"],
#     #     # extra_docs=[{"path": "https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/s3_bucket.html.markdown", "type": "resource"}],
#     #     filter_types=["resource", "data_source"]
#     # )
#     # To override config filtering:
#     orchestrator.unified_ingest(
#       extra_docs=[{"path": "docs/terraform-aws-provider-best-practices.pdf", "type": "best_practice"}],
#       filter_types=["best_practice"]
#     )