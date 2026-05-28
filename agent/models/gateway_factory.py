"""
Gateway Factory

Provides singleton instances of gateways for each model type.
"""

from typing import Dict, Type

from ..config.config_service import AgentConfigService
from .base import BaseGateway
from .llm_gateway import LLMGateway
from .vision_gateway import VisionGateway
from .image_gateway import ImageGenerationGateway
from .tts_gateway import TTSGateway
from .video_gateway import VideoGateway


class GatewayFactory:
    """
    Factory for creating and managing gateway instances.

    Implements singleton pattern - each gateway type has only one instance
    per config service.
    """

    _gateways: Dict[str, BaseGateway] = {}

    @classmethod
    def get_gateway(
        cls, gateway_type: str, config_service: AgentConfigService = None, model_subtype: str = None
    ) -> BaseGateway:
        """
        Get or create a gateway instance.

        Args:
            gateway_type: Type of gateway ("llm", "vision", "image_generation", "tts", "video")
            config_service: Configuration service instance (uses singleton if not provided)
            model_subtype: For video gateway, specify the video model type ("t2v", "i2v", "r2v", "video-edit")

        Returns:
            Gateway instance for the requested type

        Raises:
            ValueError: If gateway_type is not supported
        """
        if config_service is None:
            config_service = AgentConfigService()

        # For video gateway with specific model subtype
        if gateway_type == "video" and model_subtype:
            cache_key = f"{gateway_type}_{model_subtype}_{id(config_service)}"
            if cache_key in cls._gateways:
                return cls._gateways[cache_key]
            gateway = VideoGateway(config_service, gateway_type, model_subtype=model_subtype)
            cls._gateways[cache_key] = gateway
            return gateway

        # Return cached instance if exists
        cache_key = f"{gateway_type}_{id(config_service)}"
        if cache_key in cls._gateways:
            return cls._gateways[cache_key]

        # Create new instance based on type
        gateway_map: Dict[str, Type[BaseGateway]] = {
            "llm": LLMGateway,
            "vision": VisionGateway,
            "image_generation": ImageGenerationGateway,
            "tts": TTSGateway,
            "video": VideoGateway,
        }

        if gateway_type not in gateway_map:
            raise ValueError(
                f"Unsupported gateway type: {gateway_type}. "
                f"Supported types: {list(gateway_map.keys())}"
            )

        gateway = gateway_map[gateway_type](config_service, gateway_type)
        cls._gateways[cache_key] = gateway

        return gateway

    @classmethod
    def get_all_gateways(
        cls, config_service: AgentConfigService = None
    ) -> Dict[str, BaseGateway]:
        """
        Get all gateway instances.

        Args:
            config_service: Configuration service instance

        Returns:
            Dict mapping gateway types to their instances
        """
        if config_service is None:
            config_service = AgentConfigService()

        gateway_types = ["llm", "vision", "image_generation", "tts", "video"]
        return {gw_type: cls.get_gateway(gw_type, config_service) for gw_type in gateway_types}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached gateway instances."""
        cls._gateways.clear()

    @classmethod
    def remove_gateway(cls, gateway_type: str, config_service: AgentConfigService = None) -> None:
        """
        Remove a specific gateway from cache.

        Args:
            gateway_type: Type of gateway to remove
            config_service: Configuration service instance
        """
        if config_service is None:
            config_service = AgentConfigService()

        cache_key = f"{gateway_type}_{id(config_service)}"
        if cache_key in cls._gateways:
            del cls._gateways[cache_key]
