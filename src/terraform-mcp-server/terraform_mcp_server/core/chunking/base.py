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
from typing import List
from langchain.schema import Document

class BaseChunker(ABC):
    """
    Abstract base class for all chunkers.
    Enforces a consistent interface for chunking documents.
    
    To add a new chunker, subclass BaseChunker and implement the chunk() method.
    """
    @abstractmethod
    def chunk(self, documents: List[Document]) -> List[Document]:
        """
        Splits input documents into smaller chunks, preserving and enriching metadata.
        """
        pass 