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

from abc import ABC, abstractmethod
from typing import List, Any, Dict

class BaseDocumentLoader(ABC):
    """
    Abstract base class for all document loaders.
    Enforces a consistent interface and metadata handling.
    
    To add a new loader, subclass BaseDocumentLoader and implement load() and extract_metadata().
    """
    def __init__(self, source_path: str):
        self.source_path = source_path
        self.metadata: Dict[str, Any] = {}

    @abstractmethod
    def load(self) -> List[Any]:
        """
        Extracts and returns a list of document chunks (e.g., LangChain Document objects)
        with content and metadata.
        """
        pass

    @abstractmethod
    def extract_metadata(self) -> Dict[str, Any]:
        """
        Extracts and returns provenance and document-level metadata.
        """
        pass 