"""
LLM Gateway

Handles text generation requests using DashScope SDK.
Supports multimodal models (qwen3.6-plus, qwen3.6-flash) that can accept
text, images, videos, and audio inputs.
"""

import asyncio
import logging
import ssl
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp
import certifi
import dashscope
from dashscope import Generation, MultiModalConversation

from ..config.config_service import AgentConfigService
from ..exceptions import APIError, GatewayError, RateLimitError, TimeoutError
from ..providers.base_provider import BaseProvider
from .base import BaseGateway, GatewayResponse, GatewayStatus, StreamChunk

# 获取日志记录器
logger = logging.getLogger("studio.llm_gateway")


@dataclass
class LLMRequest:
    """Request object for LLM gateway."""

    messages: List[Dict[str, Any]] = field(
        default_factory=list
    )
    # messages format: [{"role": "user", "content": "text"}] or
    # [{"role": "user", "content": [{"image": "url"}, {"text": "prompt"}]}]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: bool = False
    tools: Optional[List[Any]] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.messages:
            raise ValueError("messages cannot be empty")

    def _is_multimodal(self) -> bool:
        """Check if any message contains multimodal content (images, video, audio)."""
        for msg in self.messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                return True
            if isinstance(content, dict):
                return True
        return False

    def _is_multimodal_model(self) -> bool:
        """
        Check if model is a multimodal model requiring MultiModalConversation API.

        Note: This method only checks message content. For accurate multimodal detection,
        use LLMGateway._get_multimodal_models_from_config() which reads from config.
        """
        # Just check if messages contain multimodal content
        return self._is_multimodal()


class DashScopeProvider(BaseProvider):
    """DashScope SDK provider implementation using native async HTTP."""

    # Connection-related errors that should trigger a retry
    CONNECTION_ERRORS = (
        ConnectionResetError,
        ConnectionAbortedError,
        ConnectionRefusedError,
        BrokenPipeError,
        TimeoutError,
        aiohttp.ClientError,
    )

    def __init__(self, config: Dict[str, Any]):
        """Initialize provider with configuration."""
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session with proper SSL configuration."""
        if self._session is None or self._session.closed:
            # Create SSL context with proper certificates
            ssl_context = ssl.create_default_context(cafile=certifi.where())

            # Create connector with connection limits
            self._connector = aiohttp.TCPConnector(
                limit=100,           # Total connection limit
                limit_per_host=30,   # Per-host connection limit
                ssl=ssl_context,
            )

            # Create session
            self._session = aiohttp.ClientSession(connector=self._connector)

        return self._session

    async def _close_session(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        if self._connector:
            self._connector = None

    async def _call_with_retry(
        self,
        sdk_call_func,
        params: Dict[str, Any],
        max_retries: int = 3,
    ) -> Any:
        """
        Call DashScope SDK with retry logic for connection errors.

        Args:
            sdk_call_func: The SDK call function (e.g., Generation.call)
            params: Parameters to pass to the SDK call
            max_retries: Maximum number of retry attempts

        Returns:
            SDK response object

        Raises:
            APIError: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                # Pass session to SDK for proper connection management
                params_with_session = {**params, "session": session}
                response = await sdk_call_func(**params_with_session)
                return response

            except self.CONNECTION_ERRORS as e:
                last_error = e
                # Close and recreate session on connection error
                await self._close_session()
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    backoff = 2 ** attempt
                    await asyncio.sleep(backoff)
                    continue
                raise APIError(
                    f"DashScope connection error after {max_retries} attempts: {str(e)}",
                    status_code=None,
                    response_body=str(e)
                )

            except Exception as e:
                # Re-raise other exceptions immediately (don't retry)
                raise

        # This should not happen, but handle it just in case
        if last_error:
            raise APIError(
                f"DashScope SDK call failed: {str(last_error)}",
                status_code=None,
                response_body=str(last_error)
            )

    async def chat_completions(self, messages: list, tools: list = None, **kwargs) -> Dict[str, Any]:
        """Call DashScope Generation API for text-only requests using thread pool."""
        # Build parameters
        params = {
            "model": kwargs.get("model", self.model_name),
            "messages": messages,
            "result_format": "message",
            **self.default_params,
            **kwargs,
        }

        if "model" in kwargs:
            del kwargs["model"]

        if "temperature" in kwargs and kwargs["temperature"] is not None:
            params["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            params["max_tokens"] = kwargs["max_tokens"]
        if "top_p" in kwargs and kwargs["top_p"] is not None:
            params["top_p"] = kwargs["top_p"]
        if tools:
            params["tools"] = tools

        # Use thread pool with retry for synchronous Generation.call
        response = await self._call_with_retry_threadpool(Generation.call, params)

        if response.status_code == 200:
            message = response.output.choices[0].message
            return {
                "choices": [{
                    "message": {
                        "content": message.content,
                        "tool_calls": message.tool_calls if 'tool_calls' in message else None
                    }
                }],
                "raw_response": response
            }
        else:
            raise APIError(
                f"DashScope API error: {response.message}",
                status_code=response.status_code,
                response_body=response.message
            )

    async def multimodal_conversation(self, messages: list, tools: list = None, **kwargs) -> Dict[str, Any]:
        """Call DashScope MultiModalConversation API using thread pool with retry."""
        params = {
            "model": kwargs.get("model", self.model_name),
            "messages": messages,
            **self.default_params,
            **kwargs,
        }

        if "model" in kwargs:
            del kwargs["model"]

        if tools:
            params["tools"] = tools

        # Use thread pool with retry for multimodal
        response = await self._call_with_retry_threadpool(MultiModalConversation.call, params)

        if response.status_code == 200:
            message = response.output.choices[0].message
            return {
                "choices": [{
                    "message": {
                        "content": message.content,
                        "tool_calls": message.tool_calls if 'tool_calls' in message else None
                    }
                }],
                "raw_response": response
            }
        else:
            raise APIError(
                f"DashScope MultiModal API error: {response.message}",
                status_code=response.status_code,
                response_body=response.message
            )

    async def _call_with_retry_threadpool(
        self,
        sdk_call_func,
        params: Dict[str, Any],
        max_retries: int = 3,
    ) -> Any:
        """
        Call synchronous SDK function in thread pool with retry logic.

        Args:
            sdk_call_func: The synchronous SDK call function
            params: Parameters to pass to the SDK call
            max_retries: Maximum number of retry attempts

        Returns:
            SDK response object
        """
        last_error = None
        loop = asyncio.get_event_loop()

        for attempt in range(max_retries):
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: sdk_call_func(**params)
                )
                return response

            except self.CONNECTION_ERRORS as e:
                last_error = e
                if attempt < max_retries - 1:
                    backoff = 2 ** attempt
                    await asyncio.sleep(backoff)
                    continue
                raise APIError(
                    f"DashScope connection error after {max_retries} attempts: {str(e)}",
                    status_code=None,
                    response_body=str(e)
                )

            except Exception as e:
                # Re-raise other exceptions immediately
                raise

        if last_error:
            raise APIError(
                f"DashScope SDK call failed: {str(last_error)}",
                status_code=None,
                response_body=str(last_error)
            )

    def _is_multimodal_messages(self, messages: list) -> bool:
        """Check if messages contain multimodal content."""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if any(k in item for k in ["image", "video", "audio"]):
                            return True
            elif isinstance(content, dict):
                if any(k in content for k in ["image", "video", "audio"]):
                    return True
        return False

    async def chat_completions_stream(
        self, messages: list, **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream chat completions using DashScope SDK.
        For multimodal models, uses MultiModalConversation.call with stream=True.
        For text-only models, uses Generation.call with stream=True.
        """
        # Extract multimodal models from kwargs before building params
        multimodal_models = kwargs.pop("_multimodal_models", set())

        params = {
            "model": kwargs.pop("model", self.model_name),
            "messages": messages,
            "result_format": "message",
            "stream": True,
            "incremental_output": True,
            **self.default_params,
            **kwargs,
        }

        if "temperature" in kwargs and kwargs["temperature"] is not None:
            params["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            params["max_tokens"] = kwargs["max_tokens"]
        if "top_p" in kwargs and kwargs["top_p"] is not None:
            params["top_p"] = kwargs["top_p"]

        loop = asyncio.get_event_loop()

        # For multimodal models, use MultiModalConversation
        model = params.get("model", "")
        # multimodal_models was already popped from kwargs at line 328
        if model.lower() in multimodal_models or self._is_multimodal_messages(messages):
            # Use thread pool for streaming multimodal
            responses = await loop.run_in_executor(
                None,
                lambda: MultiModalConversation.call(**params)
            )
            for response in responses:
                if response.status_code == 200:
                    message = response.output.choices[0].message
                    # Try content field first, then reasoning_content (for reasoning models)
                    content = message.content
                    if not content or (isinstance(content, list) and len(content) == 0):
                        content = getattr(message, 'reasoning_content', None)

                    if content and len(content) > 0:
                        # Content is a list of text chunks or a string
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and 'text' in item:
                                    yield item['text']
                                elif isinstance(item, str):
                                    yield item
                        elif isinstance(content, str):
                            yield content
        else:
            # For text-only models, check if AioGeneration supports streaming
            # If not, fall back to non-streaming
            try:
                from dashscope import Generation
                responses_gen = await loop.run_in_executor(
                    None,
                    lambda: Generation.call(**params)
                )
                for response in responses_gen:
                    if response.status_code == 200:
                        message = response.output.choices[0].message
                        # Try content field first, then reasoning_content
                        content = message.content
                        if not content or (isinstance(content, list) and len(content) == 0):
                            content = getattr(message, 'reasoning_content', None)

                        if content:
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and 'text' in item:
                                        yield item['text']
                                    elif isinstance(item, str):
                                        yield item
                            elif isinstance(content, str):
                                yield content
            except Exception as e:
                logger.warning(f"Generation streaming failed, falling back to non-streaming: {e}")
                # Fall back to non-streaming
                response = await self.chat_completions(messages, **kwargs)
                if "choices" in response and len(response["choices"]) > 0:
                    content = response["choices"][0]["message"].get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and 'text' in item:
                                yield item['text']
                    elif isinstance(content, str):
                        yield content


class LLMGateway(BaseGateway):
    """
    Gateway for LLM/Text generation models.

    Supports:
    - Primary/Fallback provider switching
    - Text-only input via Generation.call() (sync, via thread pool)
    - Multimodal input (images, video, audio) via MultiModalConversation.call()
    - Configurable parameters
    - Connection pooling with aiohttp
    """

    def _create_provider(self, config: Dict[str, Any]) -> BaseProvider:
        """Create DashScope provider from configuration."""
        # Set the API key from config
        if config.get("api_key"):
            dashscope.api_key = config["api_key"]
        return DashScopeProvider(config)

    async def close(self) -> None:
        """Close all provider sessions."""
        for provider in [self._primary_provider, self._fallback_provider]:
            if isinstance(provider, DashScopeProvider):
                await provider._close_session()

    async def invoke(self, request: LLMRequest, **kwargs) -> GatewayResponse:
        """
        Invoke LLM with the given request.

        Args:
            request: LLMRequest object with messages and parameters
            **kwargs: Additional parameters to override request

        Returns:
            GatewayResponse with generated text in data field
        """
        logger.debug(f"LLM invoke called with {len(request.messages)} messages")

        async def do_invoke(provider: DashScopeProvider, req: LLMRequest, **kw) -> GatewayResponse:
            start_time = time.time()

            # Set API key if provided
            if provider.api_key:
                dashscope.api_key = provider.api_key

            # Build parameters
            params = {**req.kwargs}
            if req.temperature is not None:
                params["temperature"] = req.temperature
            if req.max_tokens is not None:
                params["max_tokens"] = req.max_tokens
            if req.top_p is not None:
                params["top_p"] = req.top_p
            if req.model:
                params["model"] = req.model
            else:
                params["model"] = provider.model_name
            if req.tools:
                params["tools"] = req.tools

            model = params.get("model", "")
            logger.debug(f"Using model: {model}")

            try:
                # Check if model is multimodal or if request has multimodal content
                # qwen3.6-plus requires MultiModalConversation API even for text-only
                multimodal_models = self._get_multimodal_models_from_config()
                is_multimodal_model = model.lower() in multimodal_models

                # Determine which API to use based on tools and multimodal status
                if req.tools and not (is_multimodal_model or req._is_multimodal()):
                    # Has tools and is NOT multimodal - use chat_completions
                    logger.debug("Using chat_completions API with tools")
                    result = await provider.chat_completions(req.messages, tools=req.tools, **params)
                elif is_multimodal_model or req._is_multimodal():
                    # Multimodal (may or may not have tools)
                    logger.debug("Using multimodal_conversation API")
                    result = await provider.multimodal_conversation(req.messages, **params)
                else:
                    # Regular text, no tools
                    logger.debug("Using chat_completions API")
                    result = await provider.chat_completions(req.messages, **params)

                # Extract content and tool_calls from response
                if "choices" in result and len(result["choices"]) > 0:
                    raw_message = result["choices"][0]["message"]
                    raw_content = raw_message.get("content", "")
                    tool_calls_data = raw_message.get("tool_calls")

                    # Handle both string and list formats from multimodal API
                    # Multimodal returns: [{"text": "..."}] or just "string"
                    if isinstance(raw_content, list):
                        content = "".join(item.get("text", "") for item in raw_content if isinstance(item, dict))
                    else:
                        content = raw_content

                    latency = (time.time() - start_time) * 1000
                    logger.debug(f"LLM invoke successful: latency={latency:.2f}ms, content_len={len(content)}")
                    return GatewayResponse(
                        success=True,
                        data={
                            "content": content,
                            "tool_calls": tool_calls_data,
                            "raw_response": result.get("raw_response")
                        },
                        model_used=params.get("model"),
                        provider=type(provider).__name__,
                        latency_ms=latency,
                    )
                else:
                    latency = (time.time() - start_time) * 1000
                    logger.warning(f"Invalid response format from provider: latency={latency:.2f}ms")
                    return GatewayResponse(
                        success=False,
                        error="Invalid response format from provider",
                        latency_ms=latency,
                    )

            except APIError as e:
                latency = (time.time() - start_time) * 1000
                logger.warning(f"APIError during LLM invoke: {e}, latency={latency:.2f}ms")
                # Re-raise the exception so _invoke_with_fallback can catch it and switch to fallback
                raise

        return await self._invoke_with_fallback(request, do_invoke, **kwargs)

    async def stream(self, request: LLMRequest, **kwargs) -> AsyncIterator[StreamChunk]:
        """
        Stream LLM response using DashScope SDK streaming support.

        Yields chunks of content as they become available from the API.
        Implements automatic primary/fallback switching on failure.
        """
        logger.debug(f"LLM stream called with {len(request.messages)} messages, stream={request.stream}")

        # Build parameters
        params = {**request.kwargs}
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            params["top_p"] = request.top_p

        # Dynamically get multimodal models from config
        multimodal_models = self._get_multimodal_models_from_config()
        params["_multimodal_models"] = multimodal_models

        # Try primary provider first
        primary_error = None
        if self._primary_provider and not self._using_fallback:
            try:
                provider = self._primary_provider
                if provider.api_key:
                    dashscope.api_key = provider.api_key
                if request.model:
                    params["model"] = request.model
                else:
                    params["model"] = provider.model_name
                model = params.get("model", "")

                logger.debug(f"Trying primary provider with model: {model}")

                # Use streaming API
                full_content = ""
                first_chunk = True
                async for chunk in provider.chat_completions_stream(request.messages, **params):
                    if first_chunk:
                        # Successfully started streaming, record this
                        self._record_success()
                        first_chunk = False
                    full_content += chunk
                    yield StreamChunk(
                        content=chunk,
                        done=False,
                        model_used=model,
                    )

                yield StreamChunk(
                    content="",
                    done=True,
                    model_used=model,
                )
                logger.debug(f"LLM stream completed: total_content_len={len(full_content)}")
                return  # Success, return normally

            except Exception as e:
                primary_error = e
                logger.warning(f"Primary provider streaming failed: {e}")
                self._record_failure()
                if self._fallback_provider:
                    self._using_fallback = True
                    logger.debug("Switching to fallback provider")

        # Try fallback provider if primary failed or _using_fallback is set
        if self._fallback_provider:
            try:
                provider = self._fallback_provider
                if provider.api_key:
                    dashscope.api_key = provider.api_key
                if request.model:
                    params["model"] = request.model
                else:
                    params["model"] = provider.model_name
                model = params.get("model", "")

                logger.debug(f"Using fallback provider with model: {model}")

                # Use streaming API
                full_content = ""
                first_chunk = True
                async for chunk in provider.chat_completions_stream(request.messages, **params):
                    if first_chunk:
                        # Successfully started streaming with fallback
                        self._record_success()
                        first_chunk = False
                    full_content += chunk
                    yield StreamChunk(
                        content=chunk,
                        done=False,
                        model_used=model,
                    )

                yield StreamChunk(
                    content="",
                    done=True,
                    model_used=model,
                )
                logger.debug(f"LLM fallback stream completed: total_content_len={len(full_content)}")
                return  # Success, return normally

            except Exception as e:
                logger.error(f"Fallback provider streaming also failed: {e}")
                self._record_failure()
                # Both primary and fallback failed
                error_msg = f"Error: {str(e)}"
                if primary_error:
                    error_msg = f"Primary failed: {str(primary_error)}. Fallback also failed: {str(e)}"
                yield StreamChunk(content=error_msg, done=True)
                return

        # No providers available
        yield StreamChunk(content="Error: No DashScope provider available", done=True)

    def _get_multimodal_models_from_config(self) -> set:
        """
        Get multimodal model names from configuration.

        Returns a set of model names that are multimodal (supporting images/videos).
        """
        try:
            from agent.config.config_service import AgentConfigService
            config_service = AgentConfigService()

            multimodal_models = set()

            # Get LLM models (primary and fallback)
            llm_config = config_service.get_model_config("llm")
            for provider_type in ["primary", "fallback"]:
                if provider_type in llm_config:
                    model_name = llm_config[provider_type].get("model_name", "")
                    if model_name:
                        multimodal_models.add(model_name.lower())

            # Get vision models
            vision_config = config_service.get_model_config("vision")
            for provider_type in ["primary", "fallback"]:
                if provider_type in vision_config:
                    model_name = vision_config[provider_type].get("model_name", "")
                    if model_name:
                        multimodal_models.add(model_name.lower())

            logger.debug(f"Multimodal models from config: {multimodal_models}")
            return multimodal_models
        except Exception as e:
            logger.warning(f"Failed to get multimodal models from config: {e}")
            # Return a default set if config is not available
            return {"qwen3.6-plus", "qwen3.6-plus-2026-04-02", "qwen3.6-35b-a3b", "qwen-v1.5-plus", "qwen-v1.5-turbo"}
