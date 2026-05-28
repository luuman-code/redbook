"""
TTS (Text-to-Speech) Gateway

Handles speech synthesis using MiniMax API.
Models: speech-2.8-hd, speech-2.8-turbo

Converts text to speech with customizable voice settings.
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
class TTSRequest:
    """Request object for TTS gateway."""

    input: str = ""  # Text to synthesize
    model: Optional[str] = None
    voice_id: str = "male-qn-qingse"  # Voice identifier
    speed: float = 1.0  # Speech speed (0.5-2.0)
    vol: float = 1.0  # Volume (0-2.0)
    pitch: float = 0  # Pitch adjustment
    emotion: str = "happy"  # Emotion: happy, sad, angry, neutral
    sample_rate: int = 32000  # Audio sample rate
    bitrate: int = 128000  # Audio bitrate
    format: str = "mp3"  # Audio format: mp3, aac, wav
    channel: int = 1  # Audio channel: 1 (mono), 2 (stereo)
    stream: bool = False  # Whether to stream audio
    pronunciation_dict: List[tuple] = field(default_factory=list)  # [(word, pronunciation), ...]
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.input:
            raise ValueError("input (text) cannot be empty")


class MiniMaxTTSProvider(BaseProvider):
    """MiniMax TTS API provider."""

    async def chat_completions(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Not used for TTS."""
        raise NotImplementedError("Use synthesize_speech instead")

    async def chat_completions_stream(self, messages: list, **kwargs) -> AsyncIterator[str]:
        """Not used for TTS."""
        raise NotImplementedError("TTS does not support chat completions streaming")

    async def synthesize_speech(
        self,
        input_text: str,
        model: str = None,
        voice_id: str = "male-qn-qingse",
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: float = 0,
        emotion: str = "happy",
        sample_rate: int = 32000,
        bitrate: int = 128000,
        format: str = "mp3",
        channel: int = 1,
        stream: bool = False,
        pronunciation_dict: List[tuple] = None,
        **kwargs,
    ) -> bytes:
        """
        Call MiniMax TTS endpoint.

        Args:
            input_text: Text to synthesize
            model: Model name (speech-2.8-hd or speech-2.8-turbo)
            voice_id: Voice identifier
            speed: Speech speed
            vol: Volume level
            pitch: Pitch adjustment
            emotion: Emotion setting
            sample_rate: Audio sample rate
            bitrate: Audio bitrate
            format: Audio format
            channel: Audio channel
            stream: Whether to stream
            pronunciation_dict: Custom pronunciation dictionary

        Returns:
            Raw audio bytes
        """
        # Build voice settings
        voice_setting = {
            "voice_id": voice_id,
            "speed": speed,
            "vol": vol,
            "pitch": pitch,
            "emotion": emotion,
            **self.default_params.get("voice_setting", {}),
        }

        # Build audio settings
        audio_setting = {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": format,
            "channel": channel,
            **self.default_params.get("audio_setting", {}),
        }

        # Build pronunciation dictionary
        pronunciation_dict_data = None
        if pronunciation_dict:
            pronunciation_dict_data = {
                "tone": [
                    {"text": word, "pronunciation": pron}
                    for word, pron in pronunciation_dict
                ]
            }

        data = {
            "model": model or self.model_name,
            "text": input_text,
            "stream": stream,
            "voice_setting": voice_setting,
            "audio_setting": audio_setting,
        }

        if pronunciation_dict_data:
            data["pronunciation_dict"] = pronunciation_dict_data

        data.update(kwargs)

        url = self.api_url
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=data, headers=headers)

            if response.status_code == 200:
                self._record_success()
                return response.content
            elif response.status_code == 401:
                from ..exceptions import AuthenticationError
                raise AuthenticationError("Authentication failed. Check your API key.")
            elif response.status_code == 429:
                from ..exceptions import RateLimitError
                raise RateLimitError("Rate limit exceeded")
            else:
                error_msg = response.text
                raise APIError(
                    f"TTS API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=error_msg
                )


class TTSGateway(BaseGateway):
    """
    Gateway for Text-to-Speech models.

    Supports:
    - MiniMax TTS API (speech-2.8-hd, speech-2.8-turbo)
    - Customizable voice settings
    - Multiple audio formats and sample rates
    - Emotion control
    - Custom pronunciation dictionary
    """

    def _create_provider(self, config: Dict[str, Any]) -> BaseProvider:
        """Create MiniMax TTS provider from configuration."""
        return MiniMaxTTSProvider(config)

    async def invoke(self, request: TTSRequest, **kwargs) -> GatewayResponse:
        """
        Invoke TTS model with the given request.

        Args:
            request: TTSRequest object with text and parameters
            **kwargs: Additional parameters

        Returns:
            GatewayResponse with audio data in data field
        """
        self._check_circuit_breaker()
        start_time = time.time()

        async def do_invoke(
            provider: MiniMaxTTSProvider, request: TTSRequest, **kw
        ) -> GatewayResponse:
            # Build parameters
            params = {**request.kwargs}
            if request.model:
                params["model"] = request.model
            if request.voice_id:
                params["voice_id"] = request.voice_id
            if request.speed:
                params["speed"] = request.speed
            if request.vol:
                params["vol"] = request.vol
            if request.pitch:
                params["pitch"] = request.pitch
            if request.emotion:
                params["emotion"] = request.emotion
            if request.sample_rate:
                params["sample_rate"] = request.sample_rate
            if request.bitrate:
                params["bitrate"] = request.bitrate
            if request.format:
                params["format"] = request.format
            if request.channel:
                params["channel"] = request.channel
            if request.pronunciation_dict:
                params["pronunciation_dict"] = request.pronunciation_dict

            try:
                audio_data = await provider.synthesize_speech(
                    input_text=request.input,
                    **params,
                )

                return GatewayResponse(
                    success=True,
                    data={
                        "audio": audio_data,
                        "format": params.get("format", "mp3"),
                        "sample_rate": params.get("sample_rate", 32000),
                    },
                    model_used=params.get("model", provider.model_name),
                    provider=type(provider).__name__,
                    latency_ms=(time.time() - start_time) * 1000,
                )

            except Exception as e:
                raise GatewayError(f"TTS synthesis failed: {str(e)}")

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
                    return self._error_response("TTS synthesis failed", start_time)

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

    async def stream(self, request: TTSRequest, **kwargs) -> AsyncIterator[StreamChunk]:
        """Streaming not supported for TTS (returns all audio at once)."""
        response = await self.invoke(request, **kwargs)
        if response.success:
            yield StreamChunk(
                content=f"[Audio data: {len(response.data.get('audio', b''))} bytes]",
                done=True,
            )
        else:
            yield StreamChunk(content=f"Error: {response.error}", done=True)
