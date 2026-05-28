"""
Base Provider Class

Common interface for all AI providers (OpenAI, Anthropic, etc.)
"""

import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from ..exceptions import APIError, AuthenticationError, RateLimitError, TimeoutError


class BaseProvider(ABC):
    """Abstract base class for AI service providers."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration.

        Args:
            config: Provider configuration dict containing:
                - api_url: Base API URL
                - api_key: API key
                - model_name: Model identifier
                - timeout: Request timeout in seconds
                - retry_count: Number of retries on failure
                - default_params: Default request parameters
                - status_url_template: URL template for status checks (e.g., "https://api.example.com/status/{task_id}")
        """
        self.api_url = config.get("api_url", "").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.model_name = config.get("model_name", "")
        self.timeout = config.get("timeout", 60)
        self.retry_count = config.get("retry_count", 3)
        self.default_params = config.get("default_params", {})
        self.status_url_template = config.get("status_url_template", "")
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None

    @abstractmethod
    async def chat_completions(
        self, messages: list, **kwargs
    ) -> Dict[str, Any]:
        """Call chat completions endpoint."""
        pass

    @abstractmethod
    async def chat_completions_stream(
        self, messages: list, **kwargs
    ) -> AsyncIterator[str]:
        """Call chat completions endpoint with streaming."""
        pass

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers. Override in subclass for provider-specific headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic (non-streaming).

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data

        Returns:
            Response JSON data
        """
        url = f"{self.api_url}{endpoint}"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.retry_count + 1):
                try:
                    if method.upper() == "POST":
                        response = await client.post(url, json=data, headers=headers)
                    else:
                        response = await client.get(url, headers=headers)

                    return await self._handle_response(response)

                except httpx.TimeoutException:
                    if attempt < self.retry_count:
                        await self._maybe_backoff(attempt)
                        continue
                    raise TimeoutError(f"Request to {url} timed out after {self.retry_count} retries")

                except httpx.HTTPStatusError as e:
                    self._handle_http_error(e)
                    # If we get here, error was re-raised, continue to retry
                    if attempt < self.retry_count:
                        await self._maybe_backoff(attempt)
                        continue
                    raise

                except httpx.HTTPError as e:
                    if attempt < self.retry_count:
                        await self._maybe_backoff(attempt)
                        continue
                    raise APIError(f"HTTP error: {str(e)}")

    async def _stream_request(
        self,
        method: str,
        endpoint: str,
        data: Dict[str, Any] = None,
    ) -> AsyncIterator[str]:
        """
        Make HTTP request with streaming (async generator).

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data

        Yields:
            Lines from the streaming response
        """
        url = f"{self.api_url}{endpoint}"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.retry_count + 1):
                try:
                    async with client.stream(method, url, json=data, headers=headers) as response:
                        await self._handle_stream_response(response)
                        async for line in response.aiter_lines():
                            if line:
                                yield line
                        return

                except httpx.TimeoutException:
                    if attempt < self.retry_count:
                        await self._maybe_backoff(attempt)
                        continue
                    raise TimeoutError(f"Request to {url} timed out after {self.retry_count} retries")

                except httpx.HTTPStatusError as e:
                    self._handle_http_error(e)
                    if attempt < self.retry_count:
                        await self._maybe_backoff(attempt)
                        continue
                    raise

                except httpx.HTTPError as e:
                    if attempt < self.retry_count:
                        await self._maybe_backoff(attempt)
                        continue
                    raise APIError(f"HTTP error: {str(e)}")

    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle non-streaming HTTP response."""
        if response.status_code == 401:
            raise AuthenticationError("Authentication failed. Check your API key.")
        elif response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(
                f"Rate limit exceeded. Retry after {retry_after}s" if retry_after else "Rate limit exceeded.",
                retry_after=int(retry_after) if retry_after else None,
            )
        elif response.status_code >= 400:
            raise APIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )

        self._record_success()
        return response.json()

    async def _handle_stream_response(self, response: httpx.Response) -> None:
        """Handle streaming HTTP response (check status only)."""
        if response.status_code == 401:
            raise AuthenticationError("Authentication failed. Check your API key.")
        elif response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(
                f"Rate limit exceeded." if not retry_after else f"Rate limit exceeded. Retry after {retry_after}s",
                retry_after=int(retry_after) if retry_after else None,
            )
        elif response.status_code >= 400:
            raise APIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )

        self._record_success()

    def _record_success(self) -> None:
        """Record successful request for circuit breaker."""
        self._failure_count = 0
        self._last_failure_time = None

    def _record_failure(self) -> None:
        """Record failed request for circuit breaker."""
        self._failure_count += 1
        self._last_failure_time = time.time()

    async def _maybe_backoff(self, attempt: int) -> None:
        """Exponential backoff between retries."""
        import asyncio

        backoff = min(2**attempt, 30)  # Max 30 seconds
        await asyncio.sleep(backoff)

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP status errors."""
        status_code = error.response.status_code
        if status_code == 401:
            raise AuthenticationError("Authentication failed. Check your API key.")
        elif status_code == 429:
            retry_after = error.response.headers.get("retry-after")
            raise RateLimitError(
                f"Rate limit exceeded",
                retry_after=int(retry_after) if retry_after else None,
            )
        else:
            self._record_failure()
            raise APIError(
                f"API error: {status_code}",
                status_code=status_code,
                response_body=error.response.text,
            )

    @property
    def failure_count(self) -> int:
        """Get current failure count for circuit breaker."""
        return self._failure_count

    @property
    def is_healthy(self) -> bool:
        """Check if provider is considered healthy."""
        return self._failure_count < 5  # Threshold for unhealthy status
