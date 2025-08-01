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

from typing import Optional
from langchain_neo4j import Neo4jGraph
from dotenv import load_dotenv
from terraform_mcp_server.config import Config
from terraform_mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

load_dotenv()

config = Config()

def filter_primitives(d):
    return {
        k: v for k, v in d.items()
        if isinstance(v, (str, int, float, bool, type(None)))
        or (isinstance(v, list) and all(isinstance(i, (str, int, float, bool, type(None))) for i in v))
    }

def flatten_provenance(prov: dict) -> dict:
    """
    Flattens provenance dict to provenance_<key>: value fields for Neo4j.
    """
    return {f"provenance_{k}": v for k, v in prov.items()}

class Neo4jIngestion:
    """
    Neo4jIngestion handles all database operations using langchain_neo4j.
    It does NOT perform document loading, chunking, embedding, or extraction.
    
    Interface:
        - apply_constraints_and_indexes(): Set up schema constraints and indexes.
        - ingest_chunks(chunks: List[dict], embeddings: Optional[List[List[float]]]): Ingest chunk nodes and embeddings.
        - close(): Close the Neo4j connection.
    
    To swap or extend the backend, subclass Neo4jIngestion or implement a compatible interface for another graph database.
    """
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or config.NEO4J_URI
        self.user = user or config.NEO4J_USERNAME
        self.password = password or config.NEO4J_PASSWORD
        self.graph = Neo4jGraph(
            url=self.uri,
            username=self.user,
            password=self.password
        )

    def close(self) -> None:
        # langchain_neo4j handles connection cleanup automatically
        pass

    def apply_constraints_and_indexes(self) -> None:
        """
        Create vector indexes for the three chunk node types used in the simplified approach.
        """
        # Create HNSW vector indexes for all chunk types
        vector_index_cyphers = [
            f"""CREATE VECTOR INDEX docchunk_embedding_hnsw IF NOT EXISTS FOR (d:DocChunk) ON (d.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`: {config.VECTOR_DIMENSIONS}, `vector.similarity_function`: '{config.VECTOR_SIMILARITY_FUNCTION}'}}}};""",
            f"""CREATE VECTOR INDEX docchunk_resource_embedding_hnsw IF NOT EXISTS FOR (d:DocChunk_Resource) ON (d.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`: {config.VECTOR_DIMENSIONS}, `vector.similarity_function`: '{config.VECTOR_SIMILARITY_FUNCTION}'}}}};""",
            f"""CREATE VECTOR INDEX docchunk_datasource_embedding_hnsw IF NOT EXISTS FOR (d:DocChunk_DataSource) ON (d.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`: {config.VECTOR_DIMENSIONS}, `vector.similarity_function`: '{config.VECTOR_SIMILARITY_FUNCTION}'}}}};""",
            f"""CREATE VECTOR INDEX docchunk_bestpractice_embedding_hnsw IF NOT EXISTS FOR (d:DocChunk_BestPractice) ON (d.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`: {config.VECTOR_DIMENSIONS}, `vector.similarity_function`: '{config.VECTOR_SIMILARITY_FUNCTION}'}}}};"""
        ]
        
        for cypher in vector_index_cyphers:
            try:
                self.graph.query(cypher)
                logger.info(f"Created vector index: {cypher.split('FOR')[1].split('ON')[0].strip()}")
            except Exception as index_error:
                logger.warning(f"Failed to create vector index: {index_error}")

    def ingest_chunks(self, chunks: list[dict], embeddings: Optional[list[list[float]]] = None, batch_size: int = 100, node_label: str = "DocChunk") -> None:
        """
        Ingest document chunks as DocChunk nodes with optimized batch processing for embeddings.
        For each chunk, create an EXTRACTED_FROM relationship to its parent resource/data source if possible.
        
        :param chunks: List of chunk dicts (should have 'id', 'text', 'metadata', etc.)
        :param embeddings: Optional list of embedding vectors (same order as chunks)
        :param batch_size: Number of chunks to process in each batch (default: 100)
        """
        # Use the existing graph connection
        graph = self.graph
        
        # Validate embeddings if provided
        if embeddings is not None:
            if len(embeddings) != len(chunks):
                raise ValueError(f"Number of embeddings ({len(embeddings)}) must match number of chunks ({len(chunks)})")
            
            # Validate embedding dimensions
            expected_dimensions = config.VECTOR_DIMENSIONS
            for i, embedding in enumerate(embeddings):
                if len(embedding) != expected_dimensions:
                    raise ValueError(f"Embedding {i} has {len(embedding)} dimensions, expected {expected_dimensions}")
        
        # Process chunks in batches for better performance
        for batch_start in range(0, len(chunks), batch_size):
            batch_end = min(batch_start + batch_size, len(chunks))
            batch_chunks = chunks[batch_start:batch_end]
            batch_embeddings = embeddings[batch_start:batch_end] if embeddings else None
            
            # Prepare batch data
            batch_data = []
            for i, chunk in enumerate(batch_chunks):
                props = {
                    "id": chunk["id"],
                    "content": chunk["text"],
                    "chunk_index": chunk["metadata"].get("chunk_index", batch_start + i),
                }
                # Flatten and add primitive metadata fields
                if "metadata" in chunk and isinstance(chunk["metadata"], dict):
                    for k, v in chunk["metadata"].items():
                        if isinstance(v, (str, int, float, bool, type(None))):
                            props[k] = v
                
                # Add embedding if provided
                if batch_embeddings is not None and i < len(batch_embeddings):
                    props["embedding"] = batch_embeddings[i]
                
                batch_data.append(props)
            
            # Batch create DocChunk nodes
            try:
                # Use UNWIND for efficient batch creation
                cypher_batch = f"""
                UNWIND $batch AS chunk
                CREATE (c:{node_label})
                SET c += chunk
                """
                graph.query(cypher_batch, params={"batch": batch_data})
                
                # No relationships needed in simplified approach - metadata is stored on chunks
                
                logger.info(f"Successfully ingested batch of {len(batch_data)} chunks")
                
            except Exception as e:
                logger.error(f"Failed to ingest batch starting at index {batch_start}: {e}")
                # Fallback to individual creation for better error isolation
                for i, props in enumerate(batch_data):
                    try:
                        graph.query(
                            f"""
                            CREATE (c:{node_label} $props)
                            """,
                            params={"props": props}
                        )
                        # No relationships needed in simplified approach
                    except Exception as chunk_error:
                        logger.error(f"Failed to ingest chunk {props.get('id', 'unknown')}: {chunk_error}")
                        continue
    
    # Relationship creation methods removed - not needed in simplified chunk-based approach

    # ingest_structured_entities method removed - no longer needed with chunk-based approach

    def deduplicate(self) -> None:
        """
        Optionally run Cypher to clean up duplicates (constraints should prevent most duplicates).
        """
        # TODO: Implement deduplication logic if needed
        pass 

    def verify_embedding_storage(self, sample_size: int = 10) -> dict:
        """
        Verify that embeddings are properly stored and can be retrieved efficiently.
        
        :param sample_size: Number of DocChunk nodes to sample for verification
        :return: Dictionary with verification results and performance metrics
        """
        # Use the existing graph connection
        graph = self.graph
        
        import time
        
        # Check total number of chunk nodes across all types
        total_count_result = graph.query("MATCH (c:DocChunk) RETURN count(c) as total")
        total_chunks = total_count_result[0]["total"]
        
        # Add counts for resource and datasource chunks
        resource_count_result = graph.query("MATCH (c:DocChunk_Resource) RETURN count(c) as total")
        resource_chunks = resource_count_result[0]["total"]
        
        datasource_count_result = graph.query("MATCH (c:DocChunk_DataSource) RETURN count(c) as total")
        datasource_chunks = datasource_count_result[0]["total"]
        
        total_all_chunks = total_chunks + resource_chunks + datasource_chunks
        
        # Check how many have embeddings across all types
        embedding_count_result = graph.query("MATCH (c:DocChunk) WHERE c.embedding IS NOT NULL RETURN count(c) as with_embeddings")
        chunks_with_embeddings = embedding_count_result[0]["with_embeddings"]
        
        resource_embedding_count = graph.query("MATCH (c:DocChunk_Resource) WHERE c.embedding IS NOT NULL RETURN count(c) as with_embeddings")
        resource_chunks_with_embeddings = resource_embedding_count[0]["with_embeddings"]
        
        datasource_embedding_count = graph.query("MATCH (c:DocChunk_DataSource) WHERE c.embedding IS NOT NULL RETURN count(c) as with_embeddings")
        datasource_chunks_with_embeddings = datasource_embedding_count[0]["with_embeddings"]
        
        total_chunks_with_embeddings = chunks_with_embeddings + resource_chunks_with_embeddings + datasource_chunks_with_embeddings
        
        # Sample some DocChunk nodes and verify their embeddings
        sample_result = graph.query(
            """
            MATCH (c:DocChunk)
            WHERE c.embedding IS NOT NULL
            RETURN c.id, c.content, c.embedding, size(c.embedding) as embedding_size
            LIMIT $sample_size
            """,
            params={"sample_size": sample_size}
        )
        
        verification_results = {
            "total_chunks": total_all_chunks,
            "chunks_with_embeddings": total_chunks_with_embeddings,
            "embedding_coverage": total_chunks_with_embeddings / total_all_chunks if total_all_chunks > 0 else 0,
            "chunk_breakdown": {
                "DocChunk": {"total": total_chunks, "with_embeddings": chunks_with_embeddings},
                "DocChunk_Resource": {"total": resource_chunks, "with_embeddings": resource_chunks_with_embeddings},
                "DocChunk_DataSource": {"total": datasource_chunks, "with_embeddings": datasource_chunks_with_embeddings}
            },
            "sample_size": len(sample_result),
            "embedding_dimensions": [],
            "sample_chunks": []
        }
        
        expected_dimensions = config.VECTOR_DIMENSIONS
        
        for record in sample_result:
            chunk_id = record["c.id"]
            content = record["c.content"]
            embedding = record["c.embedding"]
            embedding_size = record["embedding_size"]
            
            verification_results["embedding_dimensions"].append(embedding_size)
            verification_results["sample_chunks"].append({
                "id": chunk_id,
                "content_preview": content[:100] + "..." if len(content) > 100 else content,
                "embedding_size": embedding_size,
                "dimensions_match": embedding_size == expected_dimensions
            })
        
        # Test vector similarity search performance
        if sample_result:
            # Use the first sample's embedding for a similarity search
            test_embedding = sample_result[0]["c.embedding"]
            
            start_time = time.time()
            similarity_result = graph.query(
                """
                CALL db.index.vector.queryNodes('docchunk_embedding_hnsw', 5, $embedding)
                YIELD node, score
                RETURN node.id, score
                ORDER BY score DESC
                """,
                params={"embedding": test_embedding}
            )
            search_time = time.time() - start_time
            
            verification_results["similarity_search"] = {
                "query_time_ms": round(search_time * 1000, 2),
                "results_count": len(similarity_result),
                "top_score": similarity_result[0]["score"] if similarity_result else None
            }
        
        # Check vector index status
        try:
            index_status_result = graph.query(
                """
                SHOW INDEXES
                YIELD name, type, labelsOrTypes, properties, state
                WHERE name = 'docchunk_embedding_hnsw'
                """
            )
            if index_status_result:
                verification_results["vector_index"] = {
                    "name": index_status_result[0]["name"],
                    "type": index_status_result[0]["type"],
                    "state": index_status_result[0]["state"],
                    "labels": index_status_result[0]["labelsOrTypes"],
                    "properties": index_status_result[0]["properties"]
                }
        except Exception as e:
            verification_results["vector_index"] = {"error": str(e)}
        
        return verification_results 