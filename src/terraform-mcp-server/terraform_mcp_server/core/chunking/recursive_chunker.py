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

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema import Document
from typing import List
from .base import BaseChunker

class RecursiveCharacterChunker(BaseChunker):
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, separators: List[str] = None):
        if separators is None:
            separators = ["\n\n", "\n", " ", ""]
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators
        )

    def chunk(self, documents: List[Document]) -> List[dict]:
        all_chunks = []
        for doc in documents:
            # Split and propagate metadata
            chunks = self.splitter.create_documents(
                [doc.page_content],
                metadatas=[doc.metadata]
            )
            source_id = doc.metadata.get('source', 'doc')
            for idx, chunk in enumerate(chunks):
                chunk.metadata["chunk_index"] = idx
                chunk.metadata["chunking_method"] = "RecursiveCharacterTextSplitter"
                chunk.metadata["chunk_size"] = self.chunk_size
                chunk.metadata["chunk_overlap"] = self.chunk_overlap
                chunk_id = f"{source_id}-{idx}"
                all_chunks.append({
                    "id": chunk_id,
                    "text": chunk.page_content,
                    "metadata": chunk.metadata
                })
        return all_chunks 