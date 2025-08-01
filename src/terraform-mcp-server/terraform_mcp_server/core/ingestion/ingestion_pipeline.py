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
import csv
from datetime import datetime, timezone
from terraform_mcp_server.core.loaders.registry import get_loader
from terraform_mcp_server.utils.errors import LoaderError, UnsupportedFormatError
from terraform_mcp_server.core.chunking.recursive_chunker import RecursiveCharacterChunker
from terraform_mcp_server.config import Config
from terraform_mcp_server.utils.logging import get_logger
from terraform_mcp_server.core.llm.llm_provider import AIProvider

logger = get_logger(__name__)

# Explicitly import all loader modules to ensure registration
import terraform_mcp_server.core.loaders.html_loader
import terraform_mcp_server.core.loaders.pdf_loader
import terraform_mcp_server.core.loaders.markdown_loader

SUPPORTED_EXTENSIONS = {
    '.html': 'html',
    '.htm': 'html',
    '.pdf': 'pdf',
    '.md': 'md',
}

config = Config()
LOG_FILE = config.INGESTION_LOG_FILE


def get_file_type(file_path: str) -> str:
    if file_path.startswith("http://") or file_path.startswith("https://"):
        return "html"
    ext = os.path.splitext(file_path)[1].lower()
    return SUPPORTED_EXTENSIONS.get(ext)


def log_ingestion(entry: dict):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            "timestamp", "file_path", "loader", "status", "error", "num_chunks", "chunking_method"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


class IngestionPipeline:
    """
    IngestionPipeline handles document loading, chunking, embedding generation, and ingestion logging.
    It does NOT perform extraction or database operations. Output is a list of standardized chunk dicts and embeddings.
    Interface:
        - run() -> Tuple[List[dict], List[List[float]]]: Loads, chunks, and embeds a single file.
        - batch_run(directory, ...): Batch process all supported files in a directory.
        - batch_run_urls(url_list, ...): Batch process a list of URLs.
    """
    def __init__(self, file_path: str, chunk_size: int = None, chunk_overlap: int = None):
        self.file_path = file_path
        self.file_type = get_file_type(file_path)
        if not self.file_type:
            raise UnsupportedFormatError(f"Unsupported file extension: {file_path}")
        self.loader_cls = get_loader(self.file_type)
        if not self.loader_cls:
            raise UnsupportedFormatError(f"No loader registered for file type: {self.file_type}")
        self.loader = self.loader_cls(file_path)
        self.chunker = RecursiveCharacterChunker(
            chunk_size=chunk_size or config.CHUNK_SIZE,
            chunk_overlap=chunk_overlap or config.CHUNK_OVERLAP
        )
        # Initialize embedding service using the new AIProvider system
        embedding_config = config.get_embedding_config()
        
        # Only pass dimensions for models that support it
        embedding_kwargs = {
            "provider": embedding_config['provider'],
            "model": embedding_config['model']
        }
        
        # text-embedding-ada-002 doesn't support dimensions parameter
        if embedding_config['model'] not in ['text-embedding-ada-002']:
            embedding_kwargs["dimensions"] = embedding_config['dimensions']
        
        self.embedding_service = AIProvider.create_embeddings(**embedding_kwargs)

    def run(self) -> tuple[list[dict], list[list[float]]]:
        """
        Loads the file, chunks it, generates embeddings, and logs the ingestion.
        Returns:
            chunks: List of chunk dicts (id, text, metadata)
            embeddings: List of embedding vectors (aligned with chunks)
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_path": self.file_path,
            "loader": self.loader.__class__.__name__,
            "status": "pending",
            "error": None,
            "num_chunks": 0,
            "chunking_method": self.chunker.__class__.__name__,
        }
        try:
            docs = self.loader.load()
            logger.info(f"Loaded {len(docs)} document(s) from {self.file_path}")
            for i, doc in enumerate(docs):
                logger.debug(f"--- Document {i+1} ---")
                logger.debug(f"Content: {doc.page_content}")
                logger.debug(f"Metadata: {doc.metadata}")
            # Chunking stage
            chunks = self.chunker.chunk(docs)
            logger.info(f"Chunked into {len(chunks)} chunk(s)")
            for i, chunk in enumerate(chunks):
                logger.debug(f"--- Chunk {i+1} ---")
                logger.debug(f"ID: {chunk['id']}")
                logger.debug(f"Text: {chunk['text']}")
                logger.debug(f"Metadata: {chunk['metadata']}")
            # Embedding stage
            chunk_texts = [chunk["text"] for chunk in chunks]
            embeddings = self.embedding_service.embed_documents(chunk_texts)
            entry["status"] = "success"
            entry["num_chunks"] = len(chunks)
            log_ingestion(entry)
            return chunks, embeddings
        except LoaderError as e:
            logger.error(f"LoaderError: {e}")
            entry["status"] = "failure"
            entry["error"] = str(e)
            log_ingestion(entry)
            return [], []

    @staticmethod
    def batch_run(directory: str, chunk_size: int = None, chunk_overlap: int = None) -> None:
        """
        Batch process all supported files in a directory.
        """
        files = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f)) and get_file_type(f)
        ]
        logger.info(f"Found {len(files)} supported files in {directory}")
        for file_path in files:
            logger.info(f"Processing: {file_path}")
            pipeline = IngestionPipeline(file_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            pipeline.run()

    @staticmethod
    def batch_run_urls(url_list: list[str], chunk_size: int = None, chunk_overlap: int = None) -> None:
        """
        Batch process a list of URLs.
        """
        logger.info(f"Found {len(url_list)} URLs to process")
        for url in url_list:
            logger.info(f"Processing: {url}")
            pipeline = IngestionPipeline(url, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            pipeline.run()

# if __name__ == "__main__":
#     import sys
#     if len(sys.argv) < 2:
#         print("Usage: python -m tf_knowledge_graph.ingestion_pipeline <file_path|directory> [chunk_size] [chunk_overlap]")
#         exit(1)
#     path = sys.argv[1]
#     chunk_size = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
#     chunk_overlap = int(sys.argv[3]) if len(sys.argv) > 3 else 200
#     if os.path.isdir(path):
#         IngestionPipeline.batch_run(path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
#     else:
#         pipeline = IngestionPipeline(path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
#         pipeline.run() 