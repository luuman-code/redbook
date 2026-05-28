"""
Agent Configuration Service

Loads configuration from config.json (environments[env].models path).
Supports ${ENV_VAR} syntax for environment variable substitution.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentConfigService:
    """Configuration service for agent module, independent from config-ui."""

    _instance: Optional["AgentConfigService"] = None
    _config: Dict[str, Any] = {}

    # Pattern to match ${ENV_VAR} syntax
    _ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __new__(cls, config_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str = None):
        if self._initialized:
            return

        if config_path is None:
            # Default to config.json in project root
            config_path = Path(__file__).parent.parent.parent / "config.json"

        self._config_path = Path(config_path)
        self._load_config()
        self._initialized = True

    def _load_config(self) -> None:
        """Load and parse the configuration file."""
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self._config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")

    def _resolve_env_vars(self, value: Any) -> Any:
        """Recursively resolve ${ENV_VAR} placeholders in config values."""
        if isinstance(value, str):
            matches = self._ENV_VAR_PATTERN.findall(value)
            for var_name in matches:
                env_value = os.environ.get(var_name, "")
                value = value.replace(f"${{{var_name}}}", env_value)
            return value
        elif isinstance(value, dict):
            return {k: self._resolve_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_env_vars(item) for item in value]
        return value

    def get_active_environment(self) -> str:
        """Get the currently active environment name."""
        return self._config.get("activeEnvironment", "development")

    def get_environment_config(self, env: str = None) -> Dict[str, Any]:
        """Get the full configuration for an environment."""
        if env is None:
            env = self.get_active_environment()

        env_config = self._config.get("environments", {}).get(env)
        if env_config is None:
            raise ValueError(f"Environment '{env}' not found in configuration")

        return self._resolve_env_vars(env_config)

    def get_model_config(self, model_type: str, env: str = None) -> Dict[str, Any]:
        """
        Get the model configuration for a specific model type.

        Args:
            model_type: One of 'llm', 'vision', 'image_generation', 'tts', 'video'
            env: Environment name, defaults to active environment

        Returns:
            Dict with 'primary' and optionally 'fallback' keys
        """
        env_config = self.get_environment_config(env)
        models = env_config.get("models", {})

        if model_type not in models:
            raise ValueError(f"Model type '{model_type}' not found in configuration")

        return models[model_type]

    def get_provider_config(
        self, model_type: str, provider_type: str = "primary", env: str = None
    ) -> Dict[str, Any]:
        """
        Get a specific provider configuration.

        Args:
            model_type: Model type (llm, vision, etc.)
            provider_type: 'primary' or 'fallback'
            env: Environment name

        Returns:
            Provider configuration dict
        """
        model_config = self.get_model_config(model_type, env)
        provider_config = model_config.get(provider_type)

        if provider_config is None:
            raise ValueError(
                f"Provider type '{provider_type}' not configured for model '{model_type}'"
            )

        if not provider_config.get("enabled", False):
            raise ValueError(
                f"Provider type '{provider_type}' is disabled for model '{model_type}'"
            )

        return provider_config

    def get_all_model_types(self) -> List[str]:
        """Get list of all available model types."""
        env_config = self.get_environment_config()
        return list(env_config.get("models", {}).keys())

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()


# Singleton instance accessor
def get_config_service() -> AgentConfigService:
    """Get the singleton configuration service instance."""
    return AgentConfigService()
