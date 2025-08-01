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
from typing import Any, Optional, List, Dict
from langchain_core.runnables import Runnable

class BaseAIProvider(ABC):
    """
    Abstract base class for all AI providers (LLMs and Embeddings).
    Defines the unified interface for creating LangChain-compatible instances.
    """
    
    @abstractmethod
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        """
        Create a LangChain LLM instance that implements the Runnable interface.
        Args:
            model: Model name (e.g., 'gpt-4')
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific parameters
        Returns:
            Configured LangChain LLM instance (Runnable)
        """
        pass
    
    @abstractmethod
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        """
        Create a LangChain embedding instance that implements the Runnable interface.
        Args:
            model: Model name/identifier
            dimensions: Embedding dimensions (if applicable)
            **kwargs: Additional provider-specific parameters
        Returns:
            Configured LangChain embedding instance (Runnable)
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        pass
    
    @abstractmethod
    def get_supported_llm_models(self) -> List[str]:
        """Get list of supported LLM models for this provider."""
        pass
    
    @abstractmethod
    def get_supported_embedding_models(self) -> List[str]:
        """Get list of supported embedding models for this provider."""
        pass
    
    @abstractmethod
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        """
        Validate that required configuration is available.
        
        Args:
            **kwargs: Configuration parameters to validate
            
        Returns:
            Dictionary with validation results
        """
        pass


# Keep the old class for backward compatibility
class BaseLLMProvider(BaseAIProvider):
    """
    Legacy base class for LLM providers only.
    Deprecated: Use BaseAIProvider instead.
    """
    def create_embeddings(self, model: str, dimensions: Optional[int] = None, **kwargs: Any) -> Runnable:
        raise NotImplementedError("This provider does not support embeddings")
    
    def get_supported_embedding_models(self) -> List[str]:
        return [] 