"""LiveKit STT/TTS plugin adapters backed by NVIDIA NIM REST APIs.

These adapters wrap :mod:`ai_cad.hermes.nvidia_voice` so the LiveKit
``AgentSession`` can use NVIDIA speech models without requiring Deepgram,
Cartesia, or ElevenLabs keys.
"""
from __future__ import annotations

import asyncio
import uuid
import wave
import io
from typing import Any

from livekit import rtc
from livekit.agents import stt, tts
from livekit.agents.tts import AudioEmitter
from livekit.agents.types import (
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    NotGivenOr,
)
from livekit.agents.utils import AudioBuffer

from ai_cad.hermes.nvidia_voice import NvidiaSTT, NvidiaTTS, NvidiaVoiceError


class NvidiaSTTPlugin(stt.STT):
    """LiveKit STT plugin that transcribes audio using NVIDIA NIM ASR."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._client = NvidiaSTT(api_key=api_key, model=model, base_url=base_url)
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
            ),
        )

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        """Synchronize audio frames and call the NVIDIA REST ASR endpoint."""
        request_id = uuid.uuid4().hex[:12]
        audio_bytes = self._buffer_to_wav(buffer)

        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(None, self._client.transcribe, audio_bytes)
        except NvidiaVoiceError as exc:
            raise stt.STTError(str(exc)) from exc

        alternatives = [stt.SpeechData(text=text or "", language="")]
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=request_id,
            alternatives=alternatives,
        )

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """Streaming STT is not implemented; raise a clear error."""
        raise stt.STTError("NvidiaSTTPlugin does not support streaming. Use AgentSession turn-based mode.")

    @staticmethod
    def _buffer_to_wav(buffer: AudioBuffer) -> bytes:
        """Convert one or more LiveKit AudioFrames into a WAV blob."""
        frames: list[rtc.AudioFrame] = buffer if isinstance(buffer, list) else [buffer]
        if not frames:
            return b""
        sample_rate = frames[0].sample_rate
        num_channels = frames[0].num_channels
        pcm = b"".join(frame.data for frame in frames)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm)
        return wav_buffer.getvalue()


class NvidiaTTSPlugin(tts.TTS):
    """LiveKit TTS plugin that synthesizes speech using NVIDIA NIM TTS."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        voice: str | None = None,
        sample_rate: int = 24000,
        num_channels: int = 1,
    ) -> None:
        self._client = NvidiaTTS(api_key=api_key, model=model, base_url=base_url, voice=voice)
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=num_channels,
        )

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _NvidiaTTSStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
            client=self._client,
        )


class _NvidiaTTSStream(tts.ChunkedStream):
    """Single-shot TTS stream that returns the full synthesized audio as one chunk."""

    def __init__(
        self,
        *,
        tts: NvidiaTTSPlugin,
        input_text: str,
        conn_options: tts.APIConnectOptions,
        client: NvidiaTTS,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._client = client
        self._request_id = uuid.uuid4().hex[:12]

    async def _run(self, output_emitter: AudioEmitter) -> None:
        loop = asyncio.get_event_loop()
        try:
            wav_bytes: bytes = await loop.run_in_executor(
                None, self._client.synthesize, self.input_text
            )
        except NvidiaVoiceError as exc:
            raise tts.TTSError(str(exc)) from exc
        except Exception as exc:
            raise tts.TTSError(f"TTS synthesis failed: {exc}") from exc

        frame = _wav_bytes_to_audio_frame(wav_bytes)
        output_emitter.initialize(
            request_id=self._request_id,
            sample_rate=frame.sample_rate,
            num_channels=frame.num_channels,
            mime_type="audio/pcm",
        )
        output_emitter.push(frame.data)
        output_emitter.flush()


def _wav_bytes_to_audio_frame(wav_bytes: bytes) -> rtc.AudioFrame:
    """Decode a WAV blob into a LiveKit AudioFrame."""
    wav_buffer = io.BytesIO(wav_bytes)
    with wave.open(wav_buffer, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        num_channels = wav_file.getnchannels()
        sampwidth = wav_file.getsampwidth()
        pcm = wav_file.readframes(wav_file.getnframes())
        if sampwidth == 1:
            # 8-bit unsigned -> 16-bit signed
            import array

            arr = array.array("B", pcm)
            pcm = array.array("h", [(v - 128) * 256 for v in arr]).tobytes()
            sampwidth = 2
        elif sampwidth == 4:
            # 32-bit -> 16-bit (drop lower bytes)
            pcm = bytes(b for i, b in enumerate(pcm) if i % 4 < 2)
            sampwidth = 2
        if sampwidth != 2:
            raise ValueError(f"Unsupported sample width: {sampwidth}")
        samples_per_channel = len(pcm) // (num_channels * 2)
        return rtc.AudioFrame(
            data=pcm,
            sample_rate=sample_rate,
            num_channels=num_channels,
            samples_per_channel=samples_per_channel,
        )
