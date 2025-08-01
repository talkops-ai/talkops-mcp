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

import json
from typing import List, Dict, Any, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import ValidationError
from terraform_mcp_server.config import Config
from terraform_mcp_server.core.llm.llm_provider import AIProvider
from .schemas import TFResourceSchema, BestPracticeSchema
from .prompt_manager import PromptManager
import re
import asyncio
from datetime import datetime, timezone
from terraform_mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

class ChunkExtractionPipeline:
    """
    ChunkExtractionPipeline handles LLM/rule-based extraction, validation, merging, and provenance tracking.
    It does NOT perform document loading, chunking, embedding, or database operations.
    
    Interface:
        - process_chunk(chunk: dict, schema: str) -> Tuple[Optional[dict], Optional[dict]]
        - process_chunk_async(chunk: dict, schema: str) -> Tuple[Optional[dict], Optional[dict]]
        - process_chunks_sequential(chunks: List[dict], schema: str) -> Tuple[List[dict], List[dict]]
        - process_chunks_batch(chunks: List[dict], schema: str) -> Tuple[List[dict], List[dict]]
        - process_chunks_batch_async(chunks: List[dict], schema: str) -> Tuple[List[dict], List[dict]]
        - process_chunk_unified(...): Hybrid LLM/rule extraction
        - merge_extractions(...): Merge LLM and rule-based results
    
    To add a new AI provider, subclass BaseAIProvider and register it in AIProvider.
    To add a new rule-based extractor, pass a callable to process_chunk_unified().
    """
    def __init__(self, config: Optional[Config] = None, max_workers: int = 4, confidence_threshold: float = 0.7, pipeline_version: str = "v1.0.0"):
        self.config = config or Config()
        self.llm_config = self.config.get_llm_config()
        self.llm = AIProvider.create_llm(
            provider=self.llm_config["provider"],
            model=self.llm_config["model"],
            temperature=self.llm_config["temperature"],
            max_tokens=self.llm_config["max_tokens"]
        )
        self.max_workers = max_workers
        self.confidence_threshold = confidence_threshold
        self.pipeline_version = pipeline_version

    @staticmethod
    def parse_and_validate_response(
        llm_response: str,
        schema: str = "resource"
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Parse and validate LLM output against the expected schema.
        Handles JSON decode errors, Pydantic validation errors, and can be extended for repair attempts.
        Args:
            llm_response: Raw LLM output (string)
            schema: 'resource' or 'best_practice'
        Returns:
            (validated_result, error_message)
        """
        def extract_json(text: str) -> str:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            return match.group(0) if match else text

        try:
            json_str = extract_json(llm_response)
            data = json.loads(json_str)
            if schema == "resource":
                validated = TFResourceSchema(**data)
            else:
                validated = BestPracticeSchema(**data)
            return validated, None
        except json.JSONDecodeError as e:
            return None, f"JSON decode error: {e}"
        except ValidationError as e:
            return None, f"Schema validation error: {e}"
        except Exception as e:
            return None, f"Unexpected error: {e}"

    def _build_provenance(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a provenance dictionary for a given chunk.
        """
        return {
            "source": chunk["metadata"].get("source"),
            "chunk_id": chunk["id"],
            "extraction_time": datetime.now(timezone.utc).isoformat(),
            "llm_model": self.llm_config["model"],
            "llm_provider": self.llm_config["provider"],
            "pipeline_version": self.pipeline_version
        }

    def process_chunk(self, chunk: Dict[str, Any], schema: str = "resource") -> Tuple[Optional[dict], Optional[dict]]:
        """
        Process a single chunk with the LLM and validate the output.
        Returns (validated_result, error_info).
        """
        prompt = self._build_prompt(chunk["text"], schema)
        try:
            llm_response = self.llm.invoke(prompt)
            validated, error = self.parse_and_validate_response(llm_response.content, schema)
            if validated:
                if getattr(validated, "confidence", 0.0) >= self.confidence_threshold:
                    # Attach provenance as a field in the validated schema
                    validated.provenance = self._build_provenance(chunk)
                    return validated.dict(), None
                else:
                    return None, {"error": f"Low confidence ({getattr(validated, 'confidence', 0.0)})", "chunk": chunk, "raw_result": validated.dict()}
            else:
                return None, {"error": error, "chunk": chunk}
        except Exception as e:
            return None, {"error": f"LLM or pipeline error: {e}", "chunk": chunk}

    async def process_chunk_async(self, chunk: Dict[str, Any], schema: str = "resource") -> Tuple[Optional[dict], Optional[dict]]:
        """
        Async: Process a single chunk with the LLM and validate the output.
        Returns (validated_result, error_info).
        """
        prompt = self._build_prompt(chunk["text"], schema)
        try:
            llm_response = await self.llm.ainvoke(prompt)
            validated, error = self.parse_and_validate_response(llm_response.content, schema)
            if validated:
                if getattr(validated, "confidence", 0.0) >= self.confidence_threshold:
                    validated.provenance = self._build_provenance(chunk)
                    return validated.dict(), None
                else:
                    return None, {"error": f"Low confidence ({getattr(validated, 'confidence', 0.0)})", "chunk": chunk, "raw_result": validated.dict()}
            else:
                return None, {"error": error, "chunk": chunk}
        except Exception as e:
            return None, {"error": f"LLM or pipeline error: {e}", "chunk": chunk}

    def process_chunks_sequential(self, chunks: List[Dict[str, Any]], schema: str = "resource", delay_between_calls: float = 0.0) -> Tuple[List[dict], List[dict]]:
        """
        Synchronous: Process chunks sequentially.
        Returns (results, errors)
        """
        import time
        results, errors = [], []
        for i, chunk in enumerate(chunks):
            result, error = self.process_chunk(chunk, schema)
            if result:
                results.append(result)
            else:
                errors.append(error)
            
            # Add a delay between LLM calls to avoid rate limiting (except for the last chunk)
            if delay_between_calls > 0 and i < len(chunks) - 1:
                time.sleep(delay_between_calls)
        return results, errors

    def process_chunks_batch(self, chunks: List[Dict[str, Any]], schema: str = "resource") -> Tuple[List[dict], List[dict]]:
        """
        Synchronous: Process chunks in parallel using ThreadPoolExecutor.
        Returns (results, errors)
        """
        results, errors = [], []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.process_chunk, chunk, schema): chunk for chunk in chunks}
            for future in as_completed(futures):
                result, error = future.result()
                if result:
                    results.append(result)
                else:
                    errors.append(error)
        return results, errors

    async def process_chunks_batch_async(self, chunks: List[Dict[str, Any]], schema: str = "resource") -> Tuple[List[dict], List[dict]]:
        """
        Async: Process chunks concurrently using asyncio.gather.
        Returns (results, errors)
        """
        tasks = [self.process_chunk_async(chunk, schema) for chunk in chunks]
        results = await asyncio.gather(*tasks)
        return ([r for r, e in results if r], [e for r, e in results if e])

    def process_chunk_unified(
        self,
        chunk: Dict[str, Any],
        schema: str = "resource",
        rule_extraction_func: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a chunk with both LLM-based and rule-based extraction.
        Returns a unified dict with both results, provenance, and source.
        Args:
            chunk: The document chunk (with 'id', 'text', 'metadata', etc.)
            schema: 'resource' or 'best_practice'
            rule_extraction_func: Optional callable for rule-based extraction
        Returns:
            dict with keys: 'llm_extraction', 'rule_extraction', 'provenance', 'source'
        """
        # LLM extraction (with confidence thresholding and provenance)
        llm_result, llm_error = self.process_chunk(chunk, schema)
        # Rule-based extraction (if function provided)
        rule_result = None
        if rule_extraction_func is not None:
            try:
                rule_result = rule_extraction_func(chunk)
            except Exception as e:
                rule_result = {"error": f"Rule-based extraction error: {e}"}
        # Provenance (always present)
        provenance = self._build_provenance(chunk)
        return {
            "llm_extraction": llm_result,
            "llm_error": llm_error,
            "rule_extraction": rule_result,
            "provenance": provenance,
            "source": chunk["metadata"].get("source"),
            "chunk_id": chunk["id"]
        }

    @staticmethod
    def merge_extractions(
        llm_result: Optional[Dict[str, Any]],
        rule_result: Optional[Dict[str, Any]],
        confidence_threshold: float = 0.7
    ) -> Optional[Dict[str, Any]]:
        """
        Merge LLM and rule-based extraction results.
        Prefer LLM if confidence is high, otherwise fallback to rule-based.
        If both are present, fill missing fields from rule-based.
        Adds 'extraction_method' field.
        """
        if llm_result and llm_result.get("confidence", 0.0) >= confidence_threshold:
            merged = llm_result.copy()
            if rule_result:
                for k, v in rule_result.items():
                    if k not in merged or merged[k] in (None, [], "", {}):
                        merged[k] = v
            merged["extraction_method"] = "llm"
            return merged
        elif rule_result:
            rule_result = rule_result.copy()
            rule_result["extraction_method"] = "rule"
            return rule_result
        else:
            return None

    def _build_prompt(self, text: str, schema: str) -> str:
        """
        Build the prompt for the LLM based on the schema type.
        """
        if schema == "resource":
            return PromptManager.get_resource_prompt(text)
        else:
            return PromptManager.get_best_practice_prompt(text) 