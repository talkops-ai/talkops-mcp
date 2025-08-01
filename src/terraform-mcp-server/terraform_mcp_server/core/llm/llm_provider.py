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
from typing import Optional, Dict, Any, Callable, List
from langchain_core.runnables import Runnable
from terraform_mcp_server.utils.errors import UnsupportedProviderError, LLMConfigurationError, EmbeddingConfigurationError
from .base_llm_provider import BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    """
    Unified provider for OpenAI models (LLMs and Embeddings).
    Implements the BaseAIProvider interface.
    """
    
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_openai", "OpenAI")
        from langchain_openai import ChatOpenAI
        api_key = kwargs.pop('api_key', None) or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise LLMConfigurationError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        config = {
            "model": model,
            "temperature": temperature,
            "openai_api_key": api_key,
        }
        if max_tokens is not None:
            config["max_tokens"] = max_tokens
        if kwargs.get('base_url'):
            config["openai_api_base"] = kwargs.pop('base_url')
        if kwargs.get('organization'):
            config["openai_organization"] = kwargs.pop('organization')
        config.update(kwargs)
        return ChatOpenAI(**config)
    
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_openai", "OpenAI")
        from langchain_openai import OpenAIEmbeddings
        
        api_key = kwargs.pop('api_key', None) or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise EmbeddingConfigurationError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        config = {
            "model": model,
            "openai_api_key": api_key,
        }
        
        if dimensions is not None:
            config["dimensions"] = dimensions
            
        if kwargs.get('base_url'):
            config["openai_api_base"] = kwargs.pop('base_url')
        if kwargs.get('organization'):
            config["openai_organization"] = kwargs.pop('organization')
            
        config.update(kwargs)
        return OpenAIEmbeddings(**config)
    
    def get_provider_name(self) -> str:
        return "openai"
    
    def get_supported_llm_models(self) -> List[str]:
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k"
        ]
    
    def get_supported_embedding_models(self) -> List[str]:
        return [
            "text-embedding-3-large",
            "text-embedding-3-small", 
            "text-embedding-ada-002"
        ]
    
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        validation = {"valid": True, "missing": []}
        
        if not os.getenv('OPENAI_API_KEY') and not kwargs.get('api_key'):
            validation["valid"] = False
            validation["missing"].append("OPENAI_API_KEY")
        
        return validation


class AnthropicProvider(BaseAIProvider):
    """
    Unified provider for Anthropic models (LLMs only, no embeddings).
    Implements the BaseAIProvider interface.
    """
    
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_anthropic", "Anthropic")
        from langchain_anthropic import ChatAnthropic  # type: ignore
        api_key = kwargs.pop('api_key', None) or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise LLMConfigurationError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )
        config = {
            "model": model,
            "temperature": temperature,
            "anthropic_api_key": api_key,
        }
        if max_tokens is not None:
            config["max_tokens"] = max_tokens
        config.update(kwargs)
        return ChatAnthropic(**config)
    
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        raise NotImplementedError("Anthropic does not currently support embeddings")
    
    def get_provider_name(self) -> str:
        return "anthropic"
    
    def get_supported_llm_models(self) -> List[str]:
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0"
        ]
    
    def get_supported_embedding_models(self) -> List[str]:
        return []
    
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        validation = {"valid": True, "missing": []}
        
        if not os.getenv('ANTHROPIC_API_KEY') and not kwargs.get('api_key'):
            validation["valid"] = False
            validation["missing"].append("ANTHROPIC_API_KEY")
        
        return validation


class AzureOpenAIProvider(BaseAIProvider):
    """
    Unified provider for Azure OpenAI models (LLMs and Embeddings).
    Implements the BaseAIProvider interface.
    """
    
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_openai", "Azure OpenAI")
        from langchain_openai import ChatOpenAI
        api_key = kwargs.pop('api_key', None) or os.getenv('AZURE_OPENAI_API_KEY')
        endpoint = kwargs.pop('endpoint', None) or os.getenv('AZURE_OPENAI_ENDPOINT')
        if not api_key or not endpoint:
            raise LLMConfigurationError(
                "Azure OpenAI API key or endpoint not found. Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT "
                "environment variables or pass api_key and endpoint parameters."
            )
        config = {
            "model": model,
            "temperature": temperature,
            "openai_api_key": api_key,
            "openai_api_base": endpoint,
        }
        if max_tokens is not None:
            config["max_tokens"] = max_tokens
        if kwargs.get('api_version'):
            config["openai_api_version"] = kwargs.pop('api_version')
        if kwargs.get('deployment_name'):
            config["azure_deployment"] = kwargs.pop('deployment_name')
        config.update(kwargs)
        return ChatOpenAI(**config)
    
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_openai", "Azure OpenAI")
        from langchain_openai import OpenAIEmbeddings
        
        api_key = kwargs.pop('api_key', None) or os.getenv('AZURE_OPENAI_API_KEY')
        endpoint = kwargs.pop('endpoint', None) or os.getenv('AZURE_OPENAI_ENDPOINT')
        if not api_key or not endpoint:
            raise EmbeddingConfigurationError(
                "Azure OpenAI API key or endpoint not found. Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT "
                "environment variables or pass api_key and endpoint parameters."
            )
        
        config = {
            "model": model,
            "openai_api_key": api_key,
            "openai_api_base": endpoint,
        }
        
        if dimensions is not None:
            config["dimensions"] = dimensions
            
        if kwargs.get('api_version'):
            config["openai_api_version"] = kwargs.pop('api_version')
        if kwargs.get('deployment_name'):
            config["azure_deployment"] = kwargs.pop('deployment_name')
            
        config.update(kwargs)
        return OpenAIEmbeddings(**config)
    
    def get_provider_name(self) -> str:
        return "azure_openai"
    
    def get_supported_llm_models(self) -> List[str]:
        return [
            "gpt-4",
            "gpt-35-turbo",
            "gpt-35-turbo-16k"
        ]
    
    def get_supported_embedding_models(self) -> List[str]:
        return [
            "text-embedding-ada-002",
            "text-embedding-3-large",
            "text-embedding-3-small"
        ]
    
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        validation = {"valid": True, "missing": []}
        
        if not os.getenv('AZURE_OPENAI_API_KEY') and not kwargs.get('api_key'):
            validation["valid"] = False
            validation["missing"].append("AZURE_OPENAI_API_KEY")
        if not os.getenv('AZURE_OPENAI_ENDPOINT') and not kwargs.get('endpoint'):
            validation["valid"] = False
            validation["missing"].append("AZURE_OPENAI_ENDPOINT")
        
        return validation


class HuggingFaceProvider(BaseAIProvider):
    """
    Unified provider for HuggingFace models (Embeddings only, LLMs via different interface).
    Implements the BaseAIProvider interface.
    """
    
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        raise NotImplementedError("HuggingFace LLM support requires different interface. Use embeddings only.")
    
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_community", "HuggingFace")
        from langchain_community.embeddings import HuggingFaceEmbeddings
        
        config = {
            "model_name": model,
        }
        
        if kwargs.get('device'):
            config["device"] = kwargs.pop('device')
        if kwargs.get('trust_remote_code'):
            config["trust_remote_code"] = kwargs.pop('trust_remote_code')
            
        config.update(kwargs)
        return HuggingFaceEmbeddings(**config)
    
    def get_provider_name(self) -> str:
        return "huggingface"
    
    def get_supported_llm_models(self) -> List[str]:
        return []
    
    def get_supported_embedding_models(self) -> List[str]:
        return [
            "sentence-transformers/all-MiniLM-L6-v2",
            "sentence-transformers/all-mpnet-base-v2",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "intfloat/multilingual-e5-large"
        ]
    
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        # HuggingFace models are typically local, so no API key validation needed
        return {"valid": True, "missing": []}


class CohereProvider(BaseAIProvider):
    """
    Unified provider for Cohere models (Embeddings only).
    Implements the BaseAIProvider interface.
    """
    
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        raise NotImplementedError("Cohere LLM support not implemented. Use embeddings only.")
    
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_community", "Cohere")
        from langchain_community.embeddings import CohereEmbeddings
        
        api_key = kwargs.pop('api_key', None) or os.getenv('COHERE_API_KEY')
        if not api_key:
            raise EmbeddingConfigurationError(
                "Cohere API key not found. Set COHERE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        config = {
            "model": model,
            "cohere_api_key": api_key,
        }
        
        config.update(kwargs)
        return CohereEmbeddings(**config)
    
    def get_provider_name(self) -> str:
        return "cohere"
    
    def get_supported_llm_models(self) -> List[str]:
        return []
    
    def get_supported_embedding_models(self) -> List[str]:
        return [
            "embed-english-v3.0",
            "embed-multilingual-v3.0",
            "embed-english-light-v3.0",
            "embed-multilingual-light-v3.0"
        ]
    
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        validation = {"valid": True, "missing": []}
        
        if not os.getenv('COHERE_API_KEY') and not kwargs.get('api_key'):
            validation["valid"] = False
            validation["missing"].append("COHERE_API_KEY")
        
        return validation


class OllamaProvider(BaseAIProvider):
    """
    Unified provider for Ollama models (LLMs and Embeddings).
    Implements the BaseAIProvider interface.
    """
    
    def create_llm(
        self,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_community", "Ollama")
        from langchain_community.llms import Ollama
        
        base_url = kwargs.pop('base_url', None) or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        
        config = {
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
        }
        
        if max_tokens is not None:
            config["num_predict"] = max_tokens
            
        config.update(kwargs)
        return Ollama(**config)
    
    def create_embeddings(
        self,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        AIProvider._check_package("langchain_community", "Ollama")
        from langchain_community.embeddings import OllamaEmbeddings
        
        base_url = kwargs.pop('base_url', None) or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        
        config = {
            "model": model,
            "base_url": base_url,
        }
        
        config.update(kwargs)
        return OllamaEmbeddings(**config)
    
    def get_provider_name(self) -> str:
        return "ollama"
    
    def get_supported_llm_models(self) -> List[str]:
        return [
            "llama2",
            "mistral",
            "codellama",
            "qwen",
            "gemma"
        ]
    
    def get_supported_embedding_models(self) -> List[str]:
        return [
            "nomic-embed-text",
            "llama2",
            "mistral",
            "codellama"
        ]
    
    def validate_configuration(self, **kwargs: Any) -> Dict[str, bool]:
        # Ollama is typically local, so minimal validation needed
        return {"valid": True, "missing": []}


class AIProvider:
    """Unified factory for creating LangChain-compatible AI instances (LLMs and Embeddings)."""
    
    # Supported providers registry
    _SUPPORTED_PROVIDERS = {
        "openai", 
        "anthropic", 
        "azure_openai",
        "huggingface",
        "cohere",
        "ollama"
    }
    
    @staticmethod
    def create_llm(
        provider: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        """
        Create a LangChain LLM instance that implements the Runnable interface.
        
        Args:
            provider: AI provider name ('openai', 'anthropic', 'azure_openai', 'ollama')
            model: Model name (e.g., 'gpt-4', 'claude-3-sonnet-20240229')
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Configured LangChain LLM instance (guaranteed to be a Runnable)
            
        Raises:
            UnsupportedProviderError: If provider is not supported
            LLMConfigurationError: If configuration is invalid
        """
        provider = provider.lower().strip()
        
        if provider not in AIProvider._SUPPORTED_PROVIDERS:
            supported = ", ".join(AIProvider._SUPPORTED_PROVIDERS)
            raise UnsupportedProviderError(
                f"Unsupported provider: '{provider}'. "
                f"Supported providers: {supported}"
            )
        
        try:
            return AIProvider._create_provider_instance(provider).create_llm(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs
            )
        except LLMConfigurationError as e:
            raise e
        except Exception as e:
            raise LLMConfigurationError(
                f"Failed to create LLM for provider '{provider}': {e}"
            )
    
    @staticmethod
    def create_embeddings(
        provider: str,
        model: str,
        dimensions: Optional[int] = None,
        **kwargs: Any
    ) -> Runnable:
        """
        Create a LangChain embedding instance that implements the Runnable interface.
        
        Args:
            provider: AI provider name ('openai', 'azure_openai', 'huggingface', 'cohere', 'ollama')
            model: Model name/identifier
            dimensions: Embedding dimensions (if applicable)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Configured LangChain embedding instance (guaranteed to be a Runnable)
            
        Raises:
            UnsupportedProviderError: If provider is not supported
            EmbeddingConfigurationError: If configuration is invalid
        """
        provider = provider.lower().strip()
        
        if provider not in AIProvider._SUPPORTED_PROVIDERS:
            supported = ", ".join(AIProvider._SUPPORTED_PROVIDERS)
            raise UnsupportedProviderError(
                f"Unsupported provider: '{provider}'. "
                f"Supported providers: {supported}"
            )
        
        try:
            return AIProvider._create_provider_instance(provider).create_embeddings(
                model=model,
                dimensions=dimensions,
                **kwargs
            )
        except EmbeddingConfigurationError as e:
            raise e
        except Exception as e:
            raise EmbeddingConfigurationError(
                f"Failed to create embedding model for provider '{provider}': {e}"
            )
    
    @staticmethod
    def _check_package(package_name: str, provider_name: str) -> None:
        """Check if required package is installed."""
        try:
            __import__(package_name)
        except ImportError:
            raise LLMConfigurationError(
                f"{package_name} package is required for {provider_name} provider. "
                f"Install with: pip install {package_name}"
            )
    
    @staticmethod
    def _create_provider_instance(provider: str) -> BaseAIProvider:
        """Create the actual provider instance using the factory pattern."""
        if provider == "openai":
            return OpenAIProvider()
        elif provider == "anthropic":
            return AnthropicProvider()
        elif provider == "azure_openai":
            return AzureOpenAIProvider()
        elif provider == "huggingface":
            return HuggingFaceProvider()
        elif provider == "cohere":
            return CohereProvider()
        elif provider == "ollama":
            return OllamaProvider()
        else:
            # This should never happen due to validation above
            raise UnsupportedProviderError(f"Provider '{provider}' not implemented")
    
    @staticmethod
    def get_supported_providers() -> Dict[str, Dict[str, str]]:
        """Get information about supported providers and their capabilities."""
        return {
            "openai": {
                "description": "OpenAI GPT models and embeddings",
                "capabilities": "LLM, Embeddings",
                "required_env": "OPENAI_API_KEY",
                "package": "langchain-openai",
                "example_llm_models": "gpt-4, gpt-4-turbo, gpt-3.5-turbo",
                "example_embedding_models": "text-embedding-3-large, text-embedding-3-small"
            },
            "anthropic": {
                "description": "Anthropic Claude models", 
                "capabilities": "LLM only",
                "required_env": "ANTHROPIC_API_KEY",
                "package": "langchain-anthropic",
                "example_llm_models": "claude-3-opus-20240229, claude-3-sonnet-20240229",
                "example_embedding_models": "None"
            },
            "azure_openai": {
                "description": "Azure OpenAI Service",
                "capabilities": "LLM, Embeddings",
                "required_env": "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT",
                "package": "langchain-openai", 
                "example_llm_models": "gpt-4, gpt-35-turbo (deployment names)",
                "example_embedding_models": "text-embedding-ada-002, text-embedding-3-large"
            },
            "huggingface": {
                "description": "HuggingFace sentence transformers and models",
                "capabilities": "Embeddings only",
                "required_env": "None (local models)",
                "package": "langchain-community",
                "example_llm_models": "None",
                "example_embedding_models": "sentence-transformers/all-MiniLM-L6-v2"
            },
            "cohere": {
                "description": "Cohere embedding models",
                "capabilities": "Embeddings only",
                "required_env": "COHERE_API_KEY",
                "package": "langchain-community",
                "example_llm_models": "None",
                "example_embedding_models": "embed-english-v3.0, embed-multilingual-v3.0"
            },
            "ollama": {
                "description": "Ollama local models",
                "capabilities": "LLM, Embeddings",
                "required_env": "OLLAMA_BASE_URL (optional)",
                "package": "langchain-community",
                "example_llm_models": "llama2, mistral, codellama",
                "example_embedding_models": "nomic-embed-text, llama2"
            }
        }
    
    @staticmethod
    def validate_environment(provider: str) -> Dict[str, bool]:
        """
        Validate that required environment variables are set for a provider.
        
        Args:
            provider: Provider name to validate
            
        Returns:
            Dictionary with validation results
        """
        provider = provider.lower().strip()
        return AIProvider._create_provider_instance(provider).validate_configuration()


# Keep the old class for backward compatibility
class LLMProvider:
    """Legacy factory for LLM-only creation. Deprecated: Use AIProvider instead."""
    
    @staticmethod
    def create_llm(
        provider: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        **kwargs: Any
    ) -> Runnable:
        """Legacy method. Use AIProvider.create_llm() instead."""
        return AIProvider.create_llm(
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs
        )
    
    @staticmethod
    def get_supported_providers() -> Dict[str, Dict[str, str]]:
        """Legacy method. Use AIProvider.get_supported_providers() instead."""
        return AIProvider.get_supported_providers()
    
    @staticmethod
    def validate_environment(provider: str) -> Dict[str, bool]:
        """Legacy method. Use AIProvider.validate_environment() instead."""
        return AIProvider.validate_environment(provider)


# Convenience functions for quick creation
def create_llm_from_env(
    provider: str = "openai", 
    model: str = "gpt-4",
    **kwargs: Any
) -> Runnable:
    """
    Convenience function to create an LLM using environment variables.
    
    Args:
        provider: AI provider name (default: 'openai')
        model: Model name (default: 'gpt-4')
        **kwargs: Additional parameters for LLM configuration
        
    Returns:
        Configured LangChain LLM instance (guaranteed to be a Runnable)
    """
    return AIProvider.create_llm(provider=provider, model=model, **kwargs)


def create_embeddings_from_env(
    provider: str = "openai", 
    model: str = "text-embedding-3-large",
    **kwargs: Any
) -> Runnable:
    """
    Convenience function to create an embedding model using environment variables.
    
    Args:
        provider: AI provider name (default: 'openai')
        model: Model name (default: 'text-embedding-3-large')
        **kwargs: Additional parameters for embedding configuration
        
    Returns:
        Configured LangChain embedding instance (guaranteed to be a Runnable)
    """
    return AIProvider.create_embeddings(provider=provider, model=model, **kwargs) 