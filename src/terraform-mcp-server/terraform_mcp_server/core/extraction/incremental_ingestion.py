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
from typing import List, Dict, Any, Set, Optional, Callable
from .pipeline import ChunkExtractionPipeline
from terraform_mcp_server.core.ingestion.neo4j_ingestion import Neo4jIngestion
import asyncio

INGESTION_LOG = "ingestion_log.csv"

class IncrementalIngestion:
    """
    Sample incremental ingestion mechanism for document chunks.
    Maintains a log of ingested chunk IDs and only processes new/changed chunks.
    Supports config-driven mode:
      - mode="llm": Use only LLM extraction
      - mode="rule": Use only rule-based extraction
      - mode="both": Use both and merge (LLM preferred, fallback to rule)
    """
    def __init__(self, pipeline: ChunkExtractionPipeline, log_file: str = INGESTION_LOG, mode: str = "llm"):
        self.pipeline = pipeline
        self.log_file = log_file
        self.mode = mode  # "llm", "rule", or "both"
        self.ingested_ids = self._load_ingested_ids()

    def _load_ingested_ids(self) -> Set[str]:
        if not os.path.isfile(self.log_file):
            return set()
        with open(self.log_file, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            return {row["chunk_id"] for row in reader if row.get("status") == "success"}

    def _append_log(self, chunk_id: str, status: str):
        file_exists = os.path.isfile(self.log_file)
        with open(self.log_file, "a", newline='', encoding='utf-8') as csvfile:
            fieldnames = ["chunk_id", "status"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({"chunk_id": chunk_id, "status": status})

    async def ingest_chunks_incremental(
        self,
        chunks: List[Dict[str, Any]],
        schema: str = "resource",
        rule_extraction_func: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        """
        Incrementally ingest chunks based on mode (llm, rule, both).
        Each chunk is a dict with 'id', 'text', and 'metadata'.
        """
        to_process = [chunk for chunk in chunks if chunk.get("id") not in self.ingested_ids]
        print(f"[IncrementalIngestion] {len(to_process)} new/changed chunks to process (out of {len(chunks)})")
        ingestion = Neo4jIngestion()
        results, errors = [], []
        if self.mode == "llm":
            results, errors = await self.pipeline.process_chunks_batch_async(to_process, schema=schema)
        elif self.mode == "rule":
            # Only use rule-based extraction
            for chunk in to_process:
                try:
                    rule_result = rule_extraction_func(chunk) if rule_extraction_func else None
                    if rule_result:
                        ingestion.ingest_structured_entities({"resources": [rule_result]})
                        self._append_log(chunk.get("id", "unknown"), "success")
                        results.append(rule_result)
                    else:
                        self._append_log(chunk.get("id", "unknown"), "error")
                        errors.append({"chunk": chunk, "error": "No rule-based result"})
                except Exception as e:
                    self._append_log(chunk.get("id", "unknown"), "error")
                    errors.append({"chunk": chunk, "error": str(e)})
        elif self.mode == "both":
            # Use unified extraction and merge
            for chunk in to_process:
                unified = self.pipeline.process_chunk_unified(chunk, schema=schema, rule_extraction_func=rule_extraction_func)
                merged = self.pipeline.merge_extractions(
                    unified["llm_extraction"], unified["rule_extraction"], confidence_threshold=self.pipeline.confidence_threshold
                )
                if merged:
                    ingestion.ingest_structured_entities({"resources": [merged]})
                    self._append_log(chunk.get("id", "unknown"), "success")
                    results.append(merged)
                else:
                    self._append_log(chunk.get("id", "unknown"), "error")
                    errors.append({"chunk": chunk, "error": "No valid extraction"})
        print(f"[IncrementalIngestion] Ingestion complete: {len(results)} succeeded, {len(errors)} failed.") 