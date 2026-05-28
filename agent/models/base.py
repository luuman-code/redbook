"""
Base Gateway Abstract Class

Provides common functionality for all model gateways including:
- Primary/Fallback provider switching
- Circuit breaker pattern
- Request/Response typing
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from ..config.config_service import AgentConfigService
from ..exceptions import (
    APIError,
    AuthenticationError,
    CircuitBreakerOpenError,
    GatewayError,
    RateLimitError,
    TimeoutError,
)
from ..providers.base_provider import BaseProvider


class GatewayStatus(Enum):
    """Gateway health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FALLBACK_ACTIVE = "fallback_active"
    UNAVAILABLE = "unavailable"


@dataclass
class GatewayResponse:
    """Standard response from gateway operations."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    model_used: Optional[str] = None
    provider: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class StreamChunk:
    """Chunk of data from streaming response."""

    content: str
    done: bool = False
    model_used: Optional[str] = None


class BaseGateway(ABC):
    """
    Abstract base class for all model gateways.

    Provides:
    - Configuration loading from AgentConfigService
    - Primary/Fallback provider switching
    - Circuit breaker pattern
    - Retry logic
    """

    # Circuit breaker thresholds
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 60  # seconds

    def __init__(self, config_service: AgentConfigService, model_type: str):
        """
        Initialize gateway.

        Args:
            config_service: Configuration service instance
            model_type: Model type identifier (llm, vision, image_generation, tts, video)
        """
        self.config_service = config_service
        self.model_type = model_type
        self._model_config: Dict[str, Any] = {}
        self._primary_provider: Optional[BaseProvider] = None
        self._fallback_provider: Optional[BaseProvider] = None
        self._using_fallback = False
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._circuit_open_until: Optional[float] = None

        self._load_config()

    def _load_config(self) -> None:
        """Load model configuration from config service."""
        self._model_config = self.config_service.get_model_config(self.model_type)

        primary_config = self._model_config.get("primary")
        if primary_config and primary_config.get("enabled"):
            self._primary_provider = self._create_provider(primary_config)

        fallback_config = self._model_config.get("fallback")
        if fallback_config and fallback_config.get("enabled"):
            self._fallback_provider = self._create_provider(fallback_config)

    @abstractmethod
    def _create_provider(self, config: Dict[str, Any]) -> BaseProvider:
        """Create provider instance from configuration. Override in subclass."""
        pass

    @property
    def status(self) -> GatewayStatus:
        """Get current gateway status."""
        if self._circuit_open_until and time.time() < self._circuit_open_until:
            return GatewayStatus.UNAVAILABLE

        if not self._primary_provider and not self._fallback_provider:
            return GatewayStatus.UNAVAILABLE

        if self._using_fallback or (self._primary_provider and not self._primary_provider.is_healthy):
            if self._fallback_provider and self._fallback_provider.is_healthy:
                return GatewayStatus.FALLBACK_ACTIVE
            return GatewayStatus.DEGRADED

        if self._primary_provider and not self._primary_provider.is_healthy:
            if self._fallback_provider and self._fallback_provider.is_healthy:
                return GatewayStatus.FALLBACK_ACTIVE
            return GatewayStatus.DEGRADED

        return GatewayStatus.HEALTHY

    def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker should open."""
        if self._circuit_open_until and time.time() < self._circuit_open_until:
            raise CircuitBreakerOpenError(
                "Circuit breaker is open",
                failure_count=self._failure_count,
                next_attempt_time=self._circuit_open_until,
            )

        if self._failure_count >= self.FAILURE_THRESHOLD:
            self._circuit_open_until = time.time() + self.RECOVERY_TIMEOUT
            raise CircuitBreakerOpenError(
                "Circuit breaker opened due to repeated failures",
                failure_count=self._failure_count,
                next_attempt_time=self._circuit_open_until,
            )

    def _record_success(self) -> None:
        """Record successful operation."""
        self._failure_count = 0
        self._circuit_open_until = None
        self._using_fallback = False

    def _record_failure(self) -> None:
        """Record failed operation."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        # If primary is failing, switch to fallback
        if self._primary_provider and not self._primary_provider.is_healthy:
            if self._fallback_provider and self._fallback_provider.is_healthy:
                self._using_fallback = True

    async def _invoke_with_fallback(
        self,
        request: Any,
        invoke_func,
        **kwargs
    ) -> GatewayResponse:
        """
        Invoke request with automatic fallback on failure.

        Args:
            request: The request object
            invoke_func: Callable that takes (provider, request, **kwargs) and returns GatewayResponse
        """
        self._check_circuit_breaker()

        start_time = time.time()

        # Try primary first
        if self._primary_provider and not self._using_fallback:
            try:
                response = await invoke_func(self._primary_provider, request, **kwargs)
                self._record_success()
                return response
            except CircuitBreakerOpenError:
                raise
            except (GatewayError, httpx.HTTPError) as e:
                self._record_failure()
                if self._fallback_provider:
                    self._using_fallback = True
                else:
                    return self._error_response(str(e), start_time)

        # Try fallback
        if self._fallback_provider:
            try:
                response = await invoke_func(self._fallback_provider, request, **kwargs)
                self._record_success()
                return response
            except (GatewayError, httpx.HTTPError) as e:
                self._record_failure()
                return self._error_response(str(e), start_time)

        return self._error_response("No available providers", start_time)

    def _error_response(self, error: str, start_time: float) -> GatewayResponse:
        """Create error response."""
        return GatewayResponse(
            success=False,
            error=error,
            latency_ms=(time.time() - start_time) * 1000,
        )

    @abstractmethod
    async def invoke(self, request: Any, **kwargs) -> GatewayResponse:
        """
        Main invocation method. Must be implemented by subclass.

        Args:
            request: Request object specific to the gateway type
            **kwargs: Additional arguments

        Returns:
            GatewayResponse
        """
        pass

    @abstractmethod
    async def stream(self, request: Any, **kwargs) -> AsyncIterator[StreamChunk]:
        """
        Streaming invocation method. Must be implemented by subclass.

        Args:
            request: Request object specific to the gateway type
            **kwargs: Additional arguments

        Yields:
            StreamChunk objects
        """
        pass

    def _get_provider_for_request(self, request: Any) -> tuple:
        """
        Determine which provider to use based on request and current state.

        Returns:
            Tuple of (provider, is_fallback)
        """
        if self._using_fallback and self._fallback_provider:
            return self._fallback_provider, True
        if self._primary_provider:
            return self._primary_provider, False
        if self._fallback_provider:
            return self._fallback_provider, True
        raise GatewayError("No available providers")
