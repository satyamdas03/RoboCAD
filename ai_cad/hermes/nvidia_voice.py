"""NVIDIA NIM speech adapters for HERMES voice.

Provides REST-based STT and TTS wrappers that the LiveKit voice agent can use.
Endpoints and model IDs default to NVIDIA's NIM catalog but can be overridden via
environment variables so the system remains testable when keys are absent.
"""
from __future__ import annotations

import os
import wave
import io
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_STT_MODEL = "nemotron-asr-streaming"
DEFAULT_TTS_MODEL = "chatterbox-multilingual-tts"
DEFAULT_TTS_VOICE = "English-US.Female-1"


class NvidiaVoiceError(Exception):
    """Raised when an NVIDIA voice API call fails."""


class NvidiaSTT:
    """Streaming-compatible speech-to-text using a NVIDIA NIM ASR model.

    The current implementation sends a complete audio buffer and returns the
    transcription. Future iterations can stream chunks for lower latency.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = (base_url or os.environ.get("NVIDIA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("NVIDIA_STT_MODEL", DEFAULT_STT_MODEL)

    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcribe 16-bit PCM or WAV audio to text.

        Args:
            audio_bytes: Raw bytes. If the bytes do not start with a WAV header,
                they are wrapped as 16-bit mono PCM at ``sample_rate`` before sending.
            sample_rate: Sample rate of the input audio.

        Returns:
            Transcribed text, or an empty string on failure.
        """
        if not self.available():
            raise NvidiaVoiceError("NVIDIA_API_KEY is not configured")

        payload = self._prepare_audio(audio_bytes, sample_rate)
        url = f"{self.base_url}/audio/transcriptions"
        try:
            response = httpx.post(
                url,
                headers=self._headers(),
                data={"model": self.model},
                files={"file": ("audio.wav", payload, "audio/wav")},
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                return data.get("text", "") or data.get("transcription", "")
            return ""
        except httpx.HTTPStatusError as exc:
            raise NvidiaVoiceError(f"STT API error: {exc.response.status_code} {exc.response.text[:200]}") from exc
        except Exception as exc:
            raise NvidiaVoiceError(f"STT request failed: {exc}") from exc

    @staticmethod
    def _prepare_audio(audio_bytes: bytes, sample_rate: int) -> bytes:
        if audio_bytes[:4] == b"RIFF":
            return audio_bytes
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)
        return wav_buffer.getvalue()


class NvidiaTTS:
    """Text-to-speech using a NVIDIA NIM TTS model."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        voice: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = (base_url or os.environ.get("NVIDIA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("NVIDIA_TTS_MODEL", DEFAULT_TTS_MODEL)
        self.voice = voice or os.environ.get("NVIDIA_TTS_VOICE", DEFAULT_TTS_VOICE)

    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        }

    def synthesize(
        self,
        text: str,
        sample_rate: int = 16000,
        speed: float = 1.0,
    ) -> bytes:
        """Synthesize text into WAV audio bytes.

        Args:
            text: Text to speak.
            sample_rate: Desired output sample rate.
            speed: Speech speed multiplier (model-dependent).

        Returns:
            WAV audio bytes.
        """
        if not self.available():
            raise NvidiaVoiceError("NVIDIA_API_KEY is not configured")

        url = f"{self.base_url}/audio/speech"
        body: dict[str, Any] = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
            "sample_rate": sample_rate,
        }
        if speed != 1.0:
            body["speed"] = speed

        try:
            response = httpx.post(
                url,
                headers=self._headers(),
                json=body,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            raise NvidiaVoiceError(f"TTS API error: {exc.response.status_code} {exc.response.text[:200]}") from exc
        except Exception as exc:
            raise NvidiaVoiceError(f"TTS request failed: {exc}") from exc
