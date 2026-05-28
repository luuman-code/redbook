"""
Vision Gateway

Handles image understanding and editing using DashScope API.
Models: wan2.7-image-pro, wan2.7-image

For image editing: takes reference images + text prompt to edit images.
For image understanding: analyzes images and returns descriptions.
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
class VisionRequest:
    """Request object for Vision gateway."""

    # For image editing: list of image URLs and text prompt
    images: List[str] = field(default_factory=list)  # URLs of reference images
    prompt: str = ""  # Text instruction for editing/understanding
    model: Optional[str] = None
    size: str = "2K"  # Output size: 2K, 1080P, 720P, etc.
    n: int = 1  # Number of outputs
    watermark: bool = False
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.prompt:
            raise ValueError("prompt cannot be empty")
        if not self.images:
            raise ValueError("images cannot be empty")


class DashScopeVisionProvider(BaseProvider):
    """DashScope Vision API provider for image editing."""

    async def chat_completions(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Not used for vision."""
        raise NotImplementedError("Use image_editing instead")

    async def chat_completions_stream(self, messages: list, **kwargs) -> AsyncIterator[str]:
        """Not used for vision."""
        raise NotImplementedError("Vision does not support streaming")

    async def image_editing(
        self,
        images: List[str],
        prompt: str,
        model: str = None,
        size: str = "2K",
        n: int = 1,
        watermark: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Call DashScope image editing endpoint.

        Args:
            images: List of image URLs for editing
            prompt: Text instruction for the editing
            model: Model name (wan2.7-image-pro or wan2.7-image)
            size: Output image size
            n: Number of images to generate
            watermark: Whether to add watermark

        Returns:
            API response with edited image URLs
        """
        # Build content array with images and text
        content = []
        for img_url in images:
            content.append({"image": img_url})
        content.append({"text": prompt})

        data = {
            "model": model or self.model_name,
            "input": {
                "messages": [{
                    "role": "user",
                    "content": content
                }]
            },
            "parameters": {
                "size": size,
                "n": n,
                "watermark": watermark,
                **self.default_params,
                **kwargs,
            }
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
                    f"Vision API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=error_msg
                )


class VisionGateway(BaseGateway):
    """
    Gateway for Vision/Image Editing models.

    Supports:
    - Image editing with reference images + text prompt
    - DashScope API (wan2.7-image-pro, wan2.7-image)
    - Primary/Fallback provider switching
    """

    def _create_provider(self, config: Dict[str, Any]) -> BaseProvider:
        """Create DashScope vision provider from configuration."""
        return DashScopeVisionProvider(config)

    async def invoke(self, request: VisionRequest, **kwargs) -> GatewayResponse:
        """
        Invoke Vision model with the given request.

        Args:
            request: VisionRequest object with images and prompt
            **kwargs: Additional parameters

        Returns:
            GatewayResponse with edited images in data field
        """
        self._check_circuit_breaker()
        start_time = time.time()

        async def do_invoke(
            provider: DashScopeVisionProvider, req: VisionRequest, **kw
        ) -> GatewayResponse:
            # Build parameters
            params = {**req.kwargs}
            if req.model:
                params["model"] = req.model
            if req.size:
                params["size"] = req.size
            if req.n:
                params["n"] = req.n
            params["watermark"] = req.watermark

            try:
                result = await provider.image_editing(
                    images=req.images,
                    prompt=req.prompt,
                    **params,
                )

                # Extract image URLs from response
                # Format 1: {"output": {"results": [{"image_url": "...", "revised_prompt": "..."}]}}
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
                # Format 3: DashScope multimodal-generation API format
                elif "output" in result and "choices" in result["output"]:
                    choices = result["output"].get("choices", [])
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", [])
                        images = []
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "image" and item.get("image"):
                                images.append({
                                    "url": item.get("image"),
                                    "revised_prompt": req.prompt,
                                })
                        if images:
                            return GatewayResponse(
                                success=True,
                                data={"images": images, "raw_response": result},
                                model_used=params.get("model", provider.model_name),
                                provider=type(provider).__name__,
                                latency_ms=(time.time() - start_time) * 1000,
                            )
                else:
                    return GatewayResponse(
                        success=False,
                        error="Invalid response format from vision API",
                        latency_ms=(time.time() - start_time) * 1000,
                    )

            except Exception as e:
                raise GatewayError(f"Vision processing failed: {str(e)}")

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
                    return self._error_response("Vision processing failed", start_time)

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

    async def stream(self, request: VisionRequest, **kwargs) -> AsyncIterator[StreamChunk]:
        """Streaming not supported for vision."""
        response = await self.invoke(request, **kwargs)
        if response.success:
            yield StreamChunk(
                content=f"Vision processed: {len(response.data.get('images', []))} images",
                done=True,
            )
        else:
            yield StreamChunk(content=f"Error: {response.error}", done=True)
