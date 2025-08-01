import json
import os
import warnings
from typing import Dict, Any, List, Union, Type, get_origin, get_args, Optional, Tuple
from terraform_mcp_server.config.default import DefaultConfig
from terraform_mcp_server.utils.errors import ConfigError
from datetime import datetime, timezone

# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, continue without it
    pass


class Config:
    """
    Configuration class for Terraform MCP Server.

    Precedence order for config values:
    1. Defaults from DefaultConfig
    2. Environment variables (including .env)
    3. Runtime/programmatic overrides (via config dict)

    All config keys are available as attributes and in the internal _config dict.
    """

    def __init__(self, config: Dict[str, Any] = {}) -> None:
        """
        Initialize the configuration.
        Args:
            config: Optional configuration dictionary to override defaults (highest precedence)
        """
        # Start with default configuration
        default_config = {key: getattr(DefaultConfig, key) for key in dir(DefaultConfig) if not key.startswith('_')}
        
        # Merge with provided config
        self._config = default_config.copy()
        self._config.update(config)
        
        # Set attributes from configuration and environment variables
        self._set_attributes(self._config)

    def _set_attributes(self, config: Dict[str, Any]) -> None:
        """
        Set attributes from configuration and environment variables.
        Environment variables take precedence over defaults and runtime config.
        Updates both attributes and the internal _config dict.
        Args:
            config: Configuration dictionary
        """
        for key, value in config.items():
            env_value = os.getenv(key)
            if env_value is not None:
                value = self.convert_env_value(key, env_value, DefaultConfig.__annotations__[key])
            setattr(self, key.lower(), value)
            self._config[key] = value  # Ensure internal dict reflects env override

    def __getattr__(self, item: str) -> Any:
        """
        Allow attribute-style access to config keys.
        Raises AttributeError if the key is missing.
        """
        if item in self._config:
            return self._config[item]
        raise AttributeError(f"'Config' object has no attribute '{item}'")

    def __getitem__(self, key: str) -> Any:
        """
        Allow dictionary-style access to config keys.
        """
        return self._config.get(key)

    def __contains__(self, key: str) -> bool:
        """
        Check if a config key exists.
        """
        return key in self._config

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a config value with a default fallback.
        """
        return self._config.get(key, default)

    @property
    def llm_config(self) -> Dict[str, Any]:
        """Get the LLM configuration."""
        return {
            'provider': self._config.get('LLM_PROVIDER'),
            'model': self._config.get('LLM_MODEL'),
            'temperature': self._config.get('LLM_TEMPERATURE'),
            'max_tokens': self._config.get('LLM_MAX_TOKENS')
        }

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration.
        
        Returns:
            LLM configuration dictionary
        """
        return self.llm_config

    def set_llm_config(self, config: Dict[str, Any]) -> None:
        """Set the LLM configuration.
        
        Args:
            config: LLM configuration dictionary
        """
        for key, value in config.items():
            if key == 'provider':
                self._config['LLM_PROVIDER'] = value
            elif key == 'model':
                self._config['LLM_MODEL'] = value
            elif key == 'temperature':
                self._config['LLM_TEMPERATURE'] = value
            elif key == 'max_tokens':
                self._config['LLM_MAX_TOKENS'] = value

    @property
    def embedding_config(self) -> Dict[str, Any]:
        """Get the embedding configuration."""
        return {
            'provider': self._config.get('EMBEDDING_PROVIDER'),
            'model': self._config.get('EMBEDDING_MODEL'),
            'dimensions': self._config.get('EMBEDDING_DIMENSIONS'),
            'cache_enabled': self._config.get('EMBEDDING_CACHE_ENABLED'),
            'cache_ttl': self._config.get('EMBEDDING_CACHE_TTL'),
            'cache_max_size': self._config.get('EMBEDDING_CACHE_MAX_SIZE')
        }

    def get_embedding_config(self) -> Dict[str, Any]:
        """Get embedding configuration.
        
        Returns:
            Embedding configuration dictionary
        """
        return self.embedding_config

    def set_embedding_config(self, config: Dict[str, Any]) -> None:
        """Set the embedding configuration.
        
        Args:
            config: Embedding configuration dictionary
        """
        for key, value in config.items():
            if key == 'provider':
                self._config['EMBEDDING_PROVIDER'] = value
            elif key == 'model':
                self._config['EMBEDDING_MODEL'] = value
            elif key == 'dimensions':
                self._config['EMBEDDING_DIMENSIONS'] = value
            elif key == 'cache_enabled':
                self._config['EMBEDDING_CACHE_ENABLED'] = value
            elif key == 'cache_ttl':
                self._config['EMBEDDING_CACHE_TTL'] = value
            elif key == 'cache_max_size':
                self._config['EMBEDDING_CACHE_MAX_SIZE'] = value

    def get_config_group(self, prefix: str) -> Dict[str, Any]:
        """
        Get a group of configuration values by prefix.
        
        Args:
            prefix: Prefix to filter config keys (e.g., 'LLM_', 'EMBEDDING_', 'NEO4J_')
            
        Returns:
            Dictionary of config values with the given prefix
        """
        return {
            key: value for key, value in self._config.items() 
            if key.startswith(prefix)
        }

    def set_config_group(self, prefix: str, config: Dict[str, Any]) -> None:
        """
        Set a group of configuration values by prefix.
        
        Args:
            prefix: Prefix for the config keys
            config: Dictionary of config values to set
        """
        for key, value in config.items():
            full_key = f"{prefix}_{key.upper()}" if not key.startswith(prefix) else key
            self._config[full_key] = value

    @staticmethod
    def convert_env_value(key: str, env_value: str, type_hint: Type) -> Any:
        """Convert environment variable to the appropriate type.
        
        Args:
            key: Configuration key
            env_value: Environment variable value
            type_hint: Type hint for the value
            
        Returns:
            Converted value
        """
        origin = get_origin(type_hint)
        args = get_args(type_hint)

        if origin is Union:
            for arg in args:
                if arg is type(None):
                    if env_value.lower() in ("none", "null", ""):
                        return None
                else:
                    try:
                        return Config.convert_env_value(key, env_value, arg)
                    except Exception:
                        continue
            raise ConfigError(f"Cannot convert {env_value} to any of {args}")

        if type_hint is bool:
            return env_value.lower() in ("true", "1", "yes", "on")
        elif type_hint is int:
            return int(env_value)
        elif type_hint is float:
            return float(env_value)
        elif type_hint in (str, Any):
            return env_value
        elif origin is list or origin is List:
            return json.loads(env_value)
        else:
            raise ConfigError(f"Unsupported type {type_hint} for key {key}")

    @classmethod
    def load_config(cls, config_path: str) -> Dict[str, Any]:
        """Load configuration from file or use defaults.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Configuration dictionary
        """
        if not os.path.exists(config_path):
            print(f"Warning: Configuration not found at '{config_path}'. Using default configuration.")
            return {}

        with open(config_path, "r") as f:
            custom_config = json.load(f)

        # Merge with default config
        merged_config = {key: getattr(DefaultConfig, key) for key in dir(DefaultConfig) if not key.startswith('_')}
        merged_config.update(custom_config)
        return merged_config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary with lowercase keys."""
        return {key.lower(): value for key, value in self._config.items()}

    def to_dict_original_case(self) -> Dict[str, Any]:
        """Convert configuration to dictionary with original case keys."""
        return self._config.copy()

    def keys(self) -> List[str]:
        """Get all configuration keys."""
        return list(self._config.keys())

    def values(self) -> List[Any]:
        """Get all configuration values."""
        return list(self._config.values())

    def items(self) -> List[Tuple[str, Any]]:
        """Get all configuration key-value pairs."""
        return list(self._config.items())

    @staticmethod
    def now_utc():
        """Get current UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()