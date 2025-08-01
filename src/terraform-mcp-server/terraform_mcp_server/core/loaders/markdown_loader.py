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

from langchain_community.document_loaders import UnstructuredMarkdownLoader
from typing import List, Any, Dict
from .base import BaseDocumentLoader
from .registry import register_loader
from terraform_mcp_server.utils.metadata import generate_base_metadata, validate_metadata
from terraform_mcp_server.utils.errors import LoaderError, MetadataValidationError

@register_loader
class MarkdownDocumentLoader(BaseDocumentLoader):
    """
    Loader for Markdown files using LangChain's UnstructuredMarkdownLoader.
    """
    def load(self) -> List[Any]:
        try:
            loader = UnstructuredMarkdownLoader(self.source_path)
            docs = loader.load()
            base_meta = generate_base_metadata(self.source_path, self.__class__.__name__)
            for doc in docs:
                doc.metadata = {**base_meta, **getattr(doc, 'metadata', {})}
                if not validate_metadata(doc.metadata):
                    raise MetadataValidationError(f"Metadata missing required fields for {self.source_path}")
            return docs
        except Exception as e:
            raise LoaderError(f"Failed to load Markdown file {self.source_path}: {e}")

    def extract_metadata(self) -> Dict[str, Any]:
        return generate_base_metadata(self.source_path, self.__class__.__name__)

register_loader('md', MarkdownDocumentLoader) 