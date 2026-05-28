"""
Video Generation Gateway

Handles video generation and editing using DashScope and MiniMax APIs.
Models:
- happyhorse-1.0-video-edit (DashScope) - Video editing with reference images
- MiniMax-Hailuo-2.3 (MiniMax) - Video generation from character images

Video generation is typically async - this gateway handles polling for completion.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

import httpx

from ..config.config_service import AgentConfigService
from ..providers.base_provider import BaseProvider
from ..exceptions import APIError, GatewayError
from .base import BaseGateway, GatewayResponse, GatewayStatus, StreamChunk


@dataclass
class VideoGenerationRequest:
    """Request object for Video Generation gateway."""

    # For happyhorse (video editing):
    prompt: str = ""  # Text instruction for video editing
    video_url: str = ""  # Source video URL
    reference_images: List[str] = field(default_factory=list)  # Reference image URLs

    # For MiniMax (video generation):
    subject_reference: List[Dict] = field(default_factory=list)  # Subject reference images

    # Common parameters:
    model: Optional[str] = None
    resolution: str = "720P"  # 480P, 720P, 1080P
    duration: Optional[int] = None  # Video duration in seconds
    ratio: str = "16:9"  # Video aspect ratio: 16:9, 9:16, 1:1
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.prompt and not self.subject_reference:
            raise ValueError("prompt or subject_reference is required")


class DashScopeVideoProvider(BaseProvider):
    """DashScope Video Generation API provider for happyhorse model."""

    async def chat_completions(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Not used for video."""
        raise NotImplementedError("Use generate_video instead")

    async def chat_completions_stream(self, messages: list, **kwargs) -> AsyncIterator[str]:
        """Not used for video."""
        raise NotImplementedError("Video generation does not support streaming")

    async def generate_video(
        self,
        prompt: str,
        video_url: str = "",
        reference_images: List[str] = None,
        model: str = None,
        resolution: str = "720P",
        duration: int = 5,
        ratio: str = "16:9",
        model_type: str = "i2v",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Call DashScope video generation endpoint.

        Args:
            prompt: Text instruction for video editing
            video_url: Source video URL (for editing)
            reference_images: Reference image URLs
            model: Model name (happyhorse-1.0-t2v, happyhorse-1.0-i2v, etc.)
            resolution: Output resolution
            duration: Video duration in seconds
            ratio: Video aspect ratio (e.g., "16:9", "9:16")
            model_type: Type of video model (t2v, i2v, r2v, video-edit)

        Returns:
            API response with task_id for polling
        """
        if reference_images is None:
            reference_images = []

        model_name = model or self.model_name

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"DashScope generate_video: model={model}, self.model_name={self.model_name}, using model_name={model_name}, model_type={model_type}, default_params={self.default_params}, kwargs={kwargs}")

        # Determine model type from model name or explicit model_type
        effective_model_type = model_type
        if effective_model_type == "i2v" and "r2v" in model_name.lower():
            effective_model_type = "r2v"
        elif effective_model_type == "r2v" and "i2v" in model_name.lower():
            effective_model_type = "r2v"

        if "t2v" in model_name.lower():
            # Text-to-video: only prompt in input
            data = {
                "model": model_name,
                "input": {
                    "prompt": prompt,
                },
                "parameters": {
                    "resolution": resolution,
                    "duration": duration,
                    "ratio": ratio,
                    **self.default_params,
                    **kwargs,
                }
            }
        elif effective_model_type == "i2v":
            # Image-to-video: first frame image
            media = []
            for img_url in reference_images:
                media.append({"type": "first_frame", "url": img_url})

            data = {
                "model": model_name,
                "input": {
                    "prompt": prompt,
                    "media": media,
                },
                "parameters": {
                    "resolution": resolution,
                    "duration": duration,
                    **self.default_params,
                    **kwargs,
                }
            }
        elif effective_model_type == "r2v":
            # Reference-to-video: prompt with [Image N] placeholders + reference images
            # Replace [Image N] placeholders in prompt with actual image references
            processed_prompt = prompt
            for i, img_url in enumerate(reference_images, 1):
                processed_prompt = processed_prompt.replace(f"[Image {i}]", img_url)
                processed_prompt = processed_prompt.replace(f"[image {i}]", img_url)

            media = []
            for img_url in reference_images:
                media.append({"type": "reference_image", "url": img_url})

            data = {
                "model": model_name,
                "input": {
                    "prompt": processed_prompt,
                    "media": media,
                },
                "parameters": {
                    "resolution": resolution,
                    "ratio": ratio,
                    "duration": duration,
                    **self.default_params,
                    **kwargs,
                }
            }
        else:
            # video-edit: video + reference image (only one video and one reference image)
            media = []
            if video_url:
                media.append({"type": "video", "url": video_url})
            for img_url in reference_images:
                media.append({"type": "reference_image", "url": img_url})

            data = {
                "model": model_name,
                "input": {
                    "prompt": prompt,
                    "media": media,
                },
                "parameters": {
                    "resolution": resolution,
                    **self.default_params,
                    **kwargs,
                }
            }

        url = self.api_url
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",  # Enable async mode
        }

        # Debug: log the exact request data
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"DashScope video API request: url={url}, data={data}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=data, headers=headers)

            if response.status_code == 200:
                result = response.json()
                self._record_success()
                logger.debug(f"DashScope video API response: {result}")
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
                    f"Video Generation API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=error_msg
                )

    async def get_video_status(self, task_id: str) -> Dict[str, Any]:
        """
        Poll for video generation status.

        Args:
            task_id: Task ID from generate_video response

        Returns:
            Status response with video URL when complete
        """
        status_url_template = getattr(self, 'status_url_template', None)
        if status_url_template:
            url = status_url_template.format(task_id=task_id)
        else:
            url = f"{self.api_url}/tasks/{task_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                raise APIError(
                    f"Video status check error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text
                )


class MiniMaxVideoProvider(BaseProvider):
    """MiniMax Video Generation API provider for MiniMax-Hailuo-2.3 model."""

    async def chat_completions(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Not used for video."""
        raise NotImplementedError("Use generate_video instead")

    async def chat_completions_stream(self, messages: list, **kwargs) -> AsyncIterator[str]:
        """Not used for video."""
        raise NotImplementedError("Video generation does not support streaming")

    async def generate_video(
        self,
        prompt: str,
        subject_reference: List[Dict] = None,
        model: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Call MiniMax video generation endpoint.

        Args:
            prompt: Text description of desired video
            subject_reference: Subject reference images [{"type": "character", "image": ["url"]}]
            model: Model name (S2V-01 or similar)

        Returns:
            API response with task_id for polling
        """
        if subject_reference is None:
            subject_reference = []

        data = {
            "prompt": prompt,
            "model": model or self.model_name,
            **self.default_params,
            **kwargs,
        }

        if subject_reference:
            data["subject_reference"] = subject_reference

        url = f"{self.api_url}/v1/video_generation"
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
                    f"Video Generation API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=error_msg
                )

    async def get_video_status(self, task_id: str) -> Dict[str, Any]:
        """
        Poll for video generation status.

        Args:
            task_id: Task ID from generate_video response

        Returns:
            Status response with video URL when complete
        """
        status_url_template = getattr(self, 'status_url_template', None)
        if status_url_template:
            url = status_url_template.format(task_id=task_id)
        else:
            url = f"{self.api_url}/v1/video_generation/{task_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                raise APIError(
                    f"Video status check error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text
                )


class VideoGateway(BaseGateway):
    """
    Gateway for Video Generation models.

    Supports:
    - DashScope happyhorse-1.0-t2v (text-to-video)
    - DashScope happyhorse-1.0-i2v (image-to-video)
    - DashScope happyhorse-1.0-r2v (reference-to-video)
    - DashScope happyhorse-1.0-video-edit (video editing)
    - MiniMax-Hailuo-2.3 (video generation from character images)
    - Async video generation with polling
    - Primary/Fallback provider switching
    """

    # Polling configuration
    POLLING_INTERVAL = 5  # seconds between status checks
    MAX_POLLING_TIME = 600  # 10 minutes max wait

    def __init__(self, config_service, model_type: str, model_subtype: str = None):
        """
        Initialize Video Gateway.

        Args:
            config_service: Configuration service instance
            model_type: Model type identifier (video)
            model_subtype: Video model subtype (t2v, i2v, r2v, video-edit)
        """
        self._model_subtype = model_subtype
        super().__init__(config_service, model_type)

    def _load_config(self) -> None:
        """Load model configuration from config service."""
        self._model_config = self.config_service.get_model_config(self.model_type)

        if self._model_subtype and self._model_subtype != "default":
            # Map model_subtype to config key (e.g., "t2v" -> "video_t2v")
            subtype_key = f"video_{self._model_subtype}" if not self._model_subtype.startswith("video_") else self._model_subtype

            # Try to find the specific model config at top level first (flattened structure)
            if subtype_key in self._model_config:
                specific_config = self._model_config[subtype_key]
                # Replace primary with the specific model config
                self._model_config["primary"] = specific_config
                # Remove fallback since we're using specific model
                self._model_config["fallback"] = None
            # Fallback to nested models structure
            elif "models" in self._model_config and self._model_subtype in self._model_config["models"]:
                specific_config = self._model_config["models"][self._model_subtype]
                self._model_config["primary"] = specific_config
                self._model_config["fallback"] = None

        primary_config = self._model_config.get("primary")
        if primary_config and primary_config.get("enabled"):
            self._primary_provider = self._create_provider(primary_config)

        fallback_config = self._model_config.get("fallback")
        if fallback_config and fallback_config.get("enabled"):
            self._fallback_provider = self._create_provider(fallback_config)

    def _create_provider(self, config: Dict[str, Any]) -> BaseProvider:
        """Create video generation provider based on model type."""
        model_name = config.get("model_name", "")
        # Use MiniMax provider for MiniMax models, DashScope for others
        if "minimax" in model_name.lower() or "hailuo" in model_name.lower():
            return MiniMaxVideoProvider(config)
        return DashScopeVideoProvider(config)

    async def invoke(
        self, request: VideoGenerationRequest, **kwargs
    ) -> GatewayResponse:
        """
        Invoke Video Generation model with the given request.

        This is an async operation - the gateway will poll for completion.

        Args:
            request: VideoGenerationRequest object with prompt and parameters
            **kwargs: Additional parameters

        Returns:
            GatewayResponse with video URL in data field
        """
        self._check_circuit_breaker()
        start_time = time.time()

        async def do_invoke_dashscope(
            provider: DashScopeVideoProvider, request: VideoGenerationRequest, **kw
        ) -> GatewayResponse:
            params = {**request.kwargs}
            if request.model:
                params["model"] = request.model
            if request.resolution:
                params["resolution"] = request.resolution
            if request.duration:
                params["duration"] = request.duration
            if request.ratio:
                params["ratio"] = request.ratio
            # Get model_type from kwargs but DON'T pass it to API - only use internally
            model_type = kw.get("model_type", "i2v")

            try:
                result = await provider.generate_video(
                    prompt=request.prompt,
                    video_url=request.video_url,
                    reference_images=request.reference_images,
                    model_type=model_type,
                    **params,
                )

                # Extract task_id from response
                # API returns: {"output": {"task_id": "...", "task_status": "PENDING"}}
                task_id = result.get("output", {}).get("task_id") or result.get("task_id") or result.get("id")
                if not task_id:
                    return GatewayResponse(
                        success=False,
                        error=f"No task_id returned from video generation API. Response: {result}",
                        latency_ms=(time.time() - start_time) * 1000,
                    )

                # Poll for completion
                video_url = await self._poll_for_completion_dashscope(provider, task_id)

                return GatewayResponse(
                    success=True,
                    data={
                        "video_url": video_url,
                        "task_id": task_id,
                        "raw_response": result,
                    },
                    model_used=params.get("model", provider.model_name),
                    provider=type(provider).__name__,
                    latency_ms=(time.time() - start_time) * 1000,
                )

            except Exception as e:
                raise GatewayError(f"Video generation failed: {str(e)}")

        async def do_invoke_minimax(
            provider: MiniMaxVideoProvider, request: VideoGenerationRequest, **kw
        ) -> GatewayResponse:
            params = {**request.kwargs}
            if request.model:
                params["model"] = request.model

            try:
                result = await provider.generate_video(
                    prompt=request.prompt,
                    subject_reference=request.subject_reference,
                    **params,
                )

                # Extract task_id from response
                # API returns: {"output": {"task_id": "...", "task_status": "PENDING"}}
                task_id = result.get("output", {}).get("task_id") or result.get("task_id") or result.get("id")
                if not task_id:
                    return GatewayResponse(
                        success=False,
                        error=f"No task_id returned from video generation API. Response: {result}",
                        latency_ms=(time.time() - start_time) * 1000,
                    )

                # Poll for completion
                video_url = await self._poll_for_completion_minimax(provider, task_id)

                return GatewayResponse(
                    success=True,
                    data={
                        "video_url": video_url,
                        "task_id": task_id,
                        "raw_response": result,
                    },
                    model_used=params.get("model", provider.model_name),
                    provider=type(provider).__name__,
                    latency_ms=(time.time() - start_time) * 1000,
                )

            except Exception as e:
                raise GatewayError(f"Video generation failed: {str(e)}")

        # Try primary first
        if self._primary_provider and not self._using_fallback:
            try:
                if isinstance(self._primary_provider, MiniMaxVideoProvider):
                    response = await do_invoke_minimax(self._primary_provider, request, **kwargs)
                else:
                    response = await do_invoke_dashscope(self._primary_provider, request, **kwargs)
                if response.success:
                    self._record_success()
                return response
            except GatewayError:
                self._record_failure()
                if self._fallback_provider:
                    self._using_fallback = True
                else:
                    return self._error_response("Video generation failed", start_time)

        # Try fallback
        if self._fallback_provider:
            try:
                if isinstance(self._fallback_provider, MiniMaxVideoProvider):
                    response = await do_invoke_minimax(self._fallback_provider, request, **kwargs)
                else:
                    response = await do_invoke_dashscope(self._fallback_provider, request, **kwargs)
                self._record_success()
                return response
            except GatewayError as e:
                self._record_failure()
                return self._error_response(str(e), start_time)

        return self._error_response("No available providers", start_time)

    async def _poll_for_completion_dashscope(
        self, provider: DashScopeVideoProvider, task_id: str
    ) -> Optional[str]:
        """
        Poll DashScope video generation status until complete or timeout.
        """
        elapsed = 0
        while elapsed < self.MAX_POLLING_TIME:
            await asyncio.sleep(self.POLLING_INTERVAL)
            elapsed += self.POLLING_INTERVAL

            try:
                status = await provider.get_video_status(task_id)
                # Status is in output.task_status: PENDING, RUNNING, SUCCEEDED, FAILED
                status_value = status.get("output", {}).get("task_status", "").lower()

                if status_value == "succeeded" or status_value == "completed":
                    return status.get("output", {}).get("video_url") or status.get("video_url")
                elif status_value in ("failed", "error"):
                    raise GatewayError(
                        f"Video generation failed: {status.get('output', {}).get('error', status.get('error', 'Unknown error'))}"
                    )
                # else: still processing, continue polling

            except GatewayError:
                raise
            except Exception as e:
                if "failed" in str(e).lower():
                    raise
                # Transient error, continue polling

        raise GatewayError(f"Video generation timed out after {self.MAX_POLLING_TIME}s")

    async def _poll_for_completion_minimax(
        self, provider: MiniMaxVideoProvider, task_id: str
    ) -> Optional[str]:
        """
        Poll MiniMax video generation status until complete or timeout.
        """
        elapsed = 0
        while elapsed < self.MAX_POLLING_TIME:
            await asyncio.sleep(self.POLLING_INTERVAL)
            elapsed += self.POLLING_INTERVAL

            try:
                status = await provider.get_video_status(task_id)
                status_value = status.get("status", "").lower()

                if status_value == "success" or status_value == "completed":
                    return status.get("video_url") or status.get("data", {}).get("video_url")
                elif status_value in ("failed", "error"):
                    raise GatewayError(
                        f"Video generation failed: {status.get('error', 'Unknown error')}"
                    )
                # else: still processing, continue polling

            except Exception as e:
                if "failed" in str(e).lower():
                    raise
                # Transient error, continue polling

        raise GatewayError(f"Video generation timed out after {self.MAX_POLLING_TIME}s")

    async def stream(
        self, request: VideoGenerationRequest, **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream video generation progress.
        """
        yield StreamChunk(
            content="Starting video generation...",
            done=False,
        )

        response = await self.invoke(request, **kwargs)

        if response.success:
            yield StreamChunk(
                content=f"Video ready: {response.data.get('video_url')}",
                done=True,
            )
        else:
            yield StreamChunk(
                content=f"Error: {response.error}",
                done=True,
            )
