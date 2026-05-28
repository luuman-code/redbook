"""
Image Generation Gateway

Handles text-to-image generation using DashScope API.
Models: qwen-image-2.0-pro-2026-04-22, qwen-image-2.0-pro

Generates images from text prompts.
"""

import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from ..config.config_service import AgentConfigService
from ..providers.base_provider import BaseProvider
from ..exceptions import APIError, GatewayError
from .base import BaseGateway, GatewayResponse, GatewayStatus, StreamChunk


@dataclass
class ImageGenerationRequest:
    """Request object for Image Generation gateway."""

    prompt: str = ""  # Text description of desired image
    model: Optional[str] = None
    negative_prompt: str = ""  # Things to avoid
    prompt_extend: bool = True  # Whether to extend the prompt
    size: str = "2048*2048"  # Output size
    n: int = 1  # Number of images to generate
    watermark: bool = False
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.prompt:
            raise ValueError("prompt cannot be empty")


class DashScopeImageProvider(BaseProvider):
    """DashScope Image Generation API provider."""

    async def chat_completions(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Not used for image generation."""
        raise NotImplementedError("Use generate_image instead")

    async def chat_completions_stream(self, messages: list, **kwargs) -> AsyncIterator[str]:
        """Not used for image generation."""
        raise NotImplementedError("Image generation does not support streaming")

    async def generate_image(
        self,
        prompt: str,
        model: str = None,
        negative_prompt: str = "",
        prompt_extend: bool = True,
        size: str = "2048*2048",
        n: int = 1,
        watermark: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Call DashScope image generation endpoint.

        Args:
            prompt: Text description of desired image
            model: Model name (qwen-image-2.0-pro)
            negative_prompt: Things to avoid in the image
            prompt_extend: Whether to auto-extend the prompt
            size: Output image size
            n: Number of images to generate
            watermark: Whether to add watermark

        Returns:
            API response with generated image URLs
        """
        # Build parameters - only include negative_prompt if it has content
        parameters = {
            "prompt_extend": prompt_extend,
            "watermark": watermark,
            "size": size,
            "n": n,
            **self.default_params,
            **kwargs,
        }
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt

        data = {
            "model": model or self.model_name,
            "input": {
                "messages": [{
                    "role": "user",
                    "content": [{"text": prompt}]
                }]
            },
            "parameters": parameters
        }

        url = self.api_url
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=data, headers=headers)

            if response.status_code == 200:
                result = response.json()
                self._record_success()
                return result
            elif response.status_code == 401:
                from ..exceptions import AuthenticationError
                raise AuthenticationError("Authentication failed. Check your API key.")
            elif response.status_code == 429:
                from ..exceptions import RateLimitError
                raise RateLimitError("Rate limit exceeded")
            else:
                error_msg = response.text
                raise APIError(
                    f"Image Generation API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=error_msg
                )


class ImageGenerationGateway(BaseGateway):
    """
    Gateway for Image Generation models.

    Supports:
    - Text-to-image generation
    - DashScope API (qwen-image-2.0-pro)
    - Negative prompts and prompt extension
    - Multiple output sizes
    - Primary/Fallback provider switching
    """

    def _create_provider(self, config: Dict[str, Any]) -> BaseProvider:
        """Create DashScope image generation provider from configuration."""
        return DashScopeImageProvider(config)

    async def invoke(
        self, request: ImageGenerationRequest, **kwargs
    ) -> GatewayResponse:
        """
        Invoke Image Generation model with the given request.

        Args:
            request: ImageGenerationRequest object with prompt and parameters
            **kwargs: Additional parameters

        Returns:
            GatewayResponse with generated images in data field
        """
        self._check_circuit_breaker()
        start_time = time.time()

        async def do_invoke(
            provider: DashScopeImageProvider, request: ImageGenerationRequest, **kw
        ) -> GatewayResponse:
            # Build parameters
            params = {**request.kwargs}
            if request.model:
                params["model"] = request.model
            if request.negative_prompt:
                params["negative_prompt"] = request.negative_prompt
            if request.prompt_extend is not None:
                params["prompt_extend"] = request.prompt_extend
            if request.size:
                params["size"] = request.size
            if request.n:
                params["n"] = request.n
            if request.watermark is not None:
                params["watermark"] = request.watermark

            try:
                result = await provider.generate_image(
                    prompt=request.prompt,
                    **params,
                )

                # Extract image URLs from response
                if "output" in result and "results" in result["output"]:
                    images = []
                    for item in result["output"]["results"]:
                        images.append({
                            "url": item.get("image_url"),
                            "revised_prompt": item.get("revised_prompt"),
                        })
                    return GatewayResponse(
                        success=True,
                        data={"images": images, "raw_response": result},
                        model_used=params.get("model", provider.model_name),
                        provider=type(provider).__name__,
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                elif "output" in result and "image_url" in result["output"]:
                    return GatewayResponse(
                        success=True,
                        data={"images": [{"url": result["output"]["image_url"]}], "raw_response": result},
                        model_used=params.get("model", provider.model_name),
                        provider=type(provider).__name__,
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                elif "output" in result and "choices" in result["output"]:
                    # Handle DashScope multimodal API response format
                    choices = result["output"]["choices"]
                    if choices and "message" in choices[0] and "content" in choices[0]["message"]:
                        images = []
                        for msg_content in choices[0]["message"]["content"]:
                            if "image" in msg_content:
                                images.append({
                                    "url": msg_content["image"],
                                })
                        if images:
                            return GatewayResponse(
                                success=True,
                                data={"images": images, "raw_response": result},
                                model_used=params.get("model", provider.model_name),
                                provider=type(provider).__name__,
                                latency_ms=(time.time() - start_time) * 1000,
                            )
                    return GatewayResponse(
                        success=False,
                        error="Invalid response format from image generation API",
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                else:
                    return GatewayResponse(
                        success=False,
                        error="Invalid response format from image generation API",
                        latency_ms=(time.time() - start_time) * 1000,
                    )

            except Exception as e:
                raise GatewayError(f"Image generation failed: {str(e)}")

        # Try primary first
        if self._primary_provider and not self._using_fallback:
            try:
                response = await do_invoke(self._primary_provider, request, **kwargs)
                if response.success:
                    self._record_success()
                return response
            except GatewayError:
                self._record_failure()
                if self._fallback_provider:
                    self._using_fallback = True
                else:
                    return self._error_response("Image generation failed", start_time)

        # Try fallback
        if self._fallback_provider:
            try:
                response = await do_invoke(self._fallback_provider, request, **kwargs)
                self._record_success()
                return response
            except GatewayError as e:
                self._record_failure()
                return self._error_response(str(e), start_time)

        return self._error_response("No available providers", start_time)

    async def stream(
        self, request: ImageGenerationRequest, **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Streaming not supported for image generation."""
        yield StreamChunk(
            content="Image generation does not support streaming",
            done=True,
        )
