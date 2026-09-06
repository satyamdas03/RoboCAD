"""HERMES voice agent worker using LiveKit.

Connects to a LiveKit room associated with a HERMES session, listens to the
user's microphone, transcribes speech with NVIDIA STT, sends the transcript to
the HERMES backend, and plays the HERMES text response through NVIDIA TTS.
Transcripts are also mirrored to the room as data messages so the React
HermesPanel can display them alongside the text chat.

Run as a separate worker process:

    python -m ai_cad.hermes.voice_agent_worker --session-id <id>

For day-to-day use the FastAPI backend can spawn a worker task per voice
session; the CLI entrypoint is useful for local debugging and scaling out.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import time
import wave
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import inference, JobContext, WorkerOptions, cli

from ai_cad.hermes.livekit_token import create_agent_token
from ai_cad.hermes.nvidia_voice import NvidiaSTT, NvidiaTTS, NvidiaVoiceError

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env", override=True)

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
TTS_SAMPLE_RATE = 24000
STT_SAMPLE_RATE = 16000
AUDIO_FRAME_MS = 20


class HermesVoiceRoomAgent:
    """Room-based voice agent that bridges LiveKit audio with HERMES text."""

    def __init__(
        self,
        session_id: str,
        backend_url: str = DEFAULT_BACKEND_URL,
        design_id: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.design_id = design_id
        self.backend_url = backend_url.rstrip("/")
        self.room = rtc.Room()
        self._audio_source: rtc.AudioSource | None = None
        self._audio_track: rtc.LocalAudioTrack | None = None
        self._http = httpx.AsyncClient(timeout=120.0)
        self._stt = NvidiaSTT()
        self._tts = NvidiaTTS()
        self._vad = inference.VAD()
        self._running = False
        self._user_track_task: asyncio.Task | None = None
        self._publish_options: rtc.TrackPublishOptions | None = None

        self.room.on("track_subscribed", self._on_track_subscribed)
        self.room.on("track_unsubscribed", self._on_track_unsubscribed)

    async def connect(self) -> None:
        """Generate an agent token and connect to the HERMES voice room."""
        token_info = create_agent_token(self.session_id)
        await self.room.connect(token_info["url"], token_info["token"])
        self._running = True
        await self._publish_audio_source()
        await self._send_data({
            "type": "agent_status",
            "status": "connected",
            "session_id": self.session_id,
        })

    async def disconnect(self) -> None:
        self._running = False
        if self._user_track_task and not self._user_track_task.done():
            self._user_track_task.cancel()
            try:
                await self._user_track_task
            except asyncio.CancelledError:
                pass
        await self._http.aclose()
        await self.room.disconnect()

    async def _publish_audio_source(self) -> None:
        """Set up a local audio track so we can play TTS responses."""
        self._audio_source = rtc.AudioSource(TTS_SAMPLE_RATE, 1)
        self._audio_track = rtc.LocalAudioTrack.create_audio_source(
            "hermes-agent-audio", self._audio_source
        )
        self._publish_options = rtc.TrackPublishOptions()
        self._publish_options.audio_encoding = rtc.AudioEncoding.ACM_OPUS
        await self.room.local_participant.publish_track(
            self._audio_track, self._publish_options
        )

    async def _on_track_subscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        await self._send_data({
            "type": "agent_status",
            "status": "listening",
            "participant": participant.identity,
        })
        stream = rtc.AudioStream(
            track,
            sample_rate=STT_SAMPLE_RATE,
            num_channels=1,
        )
        self._user_track_task = asyncio.create_task(
            self._process_user_audio(stream, participant.identity)
        )

    async def _on_track_unsubscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        await self._send_data({
            "type": "agent_status",
            "status": "idle",
            "participant": participant.identity,
        })
        if self._user_track_task and not self._user_track_task.done():
            self._user_track_task.cancel()

    async def _process_user_audio(
        self,
        stream: rtc.AudioStream,
        participant_identity: str,
    ) -> None:
        """Buffer user audio, run VAD, and call HERMES at end of utterance."""
        vad_stream = self._vad.stream()
        speech_buffer: list[rtc.AudioFrame] = []
        in_speech = False

        async def _drain_vad() -> None:
            """Read VAD events and finalize speech segments."""
            nonlocal in_speech, speech_buffer
            try:
                async for event in vad_stream:
                    if event.type.value == "start_of_speech":
                        in_speech = True
                        speech_buffer = []
                        await self._send_data({
                            "type": "agent_status",
                            "status": "listening",
                            "speaking": True,
                        })
                    elif event.type.value == "end_of_speech":
                        in_speech = False
                        if speech_buffer:
                            wav_bytes = self._frames_to_wav(speech_buffer)
                            speech_buffer = []
                            await self._handle_final_utterance(wav_bytes, participant_identity)
            except Exception as exc:
                await self._send_data({"type": "error", "message": f"VAD error: {exc}"})

        vad_task = asyncio.create_task(_drain_vad())

        try:
            async for frame in stream:
                if not self._running:
                    break
                try:
                    vad_stream.push_frame(frame)
                except Exception:
                    pass
                if in_speech:
                    speech_buffer.append(frame)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await vad_stream.aclose()
            except Exception:
                pass
            if not vad_task.done():
                vad_task.cancel()
                try:
                    await vad_task
                except asyncio.CancelledError:
                    pass

    async def _handle_final_utterance(
        self,
        wav_bytes: bytes,
        participant_identity: str,
    ) -> None:
        """Transcribe an utterance, ask HERMES, and speak the reply."""
        await self._send_data({"type": "agent_status", "status": "thinking"})
        try:
            user_text = await self._transcribe(wav_bytes)
        except NvidiaVoiceError as exc:
            await self._send_data({"type": "error", "message": f"STT failed: {exc}"})
            return

        if not user_text.strip():
            return

        await self._send_data({
            "type": "transcript",
            "role": "user",
            "text": user_text,
        })

        try:
            hermes_reply = await self._ask_hermes(user_text)
        except Exception as exc:
            await self._send_data({"type": "error", "message": f"HERMES failed: {exc}"})
            return

        await self._send_data({
            "type": "transcript",
            "role": "assistant",
            "text": hermes_reply,
        })
        await self._speak(hermes_reply)

    @staticmethod
    def _frames_to_wav(frames: list[rtc.AudioFrame]) -> bytes:
        """Convert a list of AudioFrames to a 16-bit mono WAV blob."""
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

    async def _transcribe(self, wav_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._stt.transcribe, wav_bytes)

    async def _speak(self, text: str) -> None:
        await self._send_data({"type": "agent_status", "status": "speaking"})
        try:
            loop = asyncio.get_event_loop()
            wav_bytes: bytes = await loop.run_in_executor(None, self._tts.synthesize, text)
        except NvidiaVoiceError as exc:
            await self._send_data({"type": "error", "message": f"TTS failed: {exc}"})
            return

        await self._publish_wav(wav_bytes)
        await self._send_data({"type": "agent_status", "status": "listening"})

    async def _publish_wav(self, wav_bytes: bytes) -> None:
        """Decode a WAV blob and push frames to the published audio source."""
        wav_buffer = io.BytesIO(wav_bytes)
        with wave.open(wav_buffer, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            num_channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            n_frames = wav_file.getnframes()
            pcm = wav_file.readframes(n_frames)
            if sampwidth == 1:
                pcm = _convert_8bit_to_16bit(pcm)
            elif sampwidth == 4:
                pcm = _convert_32bit_to_16bit(pcm)
            samples_per_channel = n_frames

        # Push audio in 20 ms chunks to keep latency low.
        bytes_per_frame = num_channels * 2
        samples_per_chunk = int(sample_rate * AUDIO_FRAME_MS / 1000)
        chunk_size = samples_per_chunk * bytes_per_frame
        for offset in range(0, len(pcm), chunk_size):
            chunk = pcm[offset : offset + chunk_size]
            if len(chunk) < bytes_per_frame:
                break
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=sample_rate,
                num_channels=num_channels,
                samples_per_channel=len(chunk) // bytes_per_frame,
            )
            await self._audio_source.capture_frame(frame)
            await asyncio.sleep(0)

    async def _ask_hermes(self, message: str) -> str:
        """Send the user's speech transcript to the HERMES text endpoint."""
        url = f"{self.backend_url}/hermes/session/{self.session_id}/message"
        response = await self._http.post(
            url,
            json={"session_id": self.session_id, "message": message},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("reply") or data.get("content") or ""

    async def _send_data(self, payload: dict[str, Any]) -> None:
        try:
            await self.room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"),
                topic="hermes_voice",
            )
        except Exception:
            # Data-channel publishing is best-effort; do not crash the agent.
            pass


def _convert_8bit_to_16bit(pcm: bytes) -> bytes:
    import array

    arr = array.array("B", pcm)
    return array.array("h", [(v - 128) * 256 for v in arr]).tobytes()


def _convert_32bit_to_16bit(pcm: bytes) -> bytes:
    import array

    arr = array.array("i", pcm)
    return array.array("h", [(v >> 16) for v in arr]).tobytes()


def _entrypoint(ctx: JobContext) -> None:
    """LiveKit worker entrypoint invoked by ``lk agent``."""
    session_id = ctx.userdata.get("session_id") if ctx.userdata else None
    backend_url = ctx.userdata.get("backend_url", DEFAULT_BACKEND_URL) if ctx.userdata else DEFAULT_BACKEND_URL
    design_id = ctx.userdata.get("design_id") if ctx.userdata else None
    if not session_id:
        # Fall back to room name stripping the "hermes-" prefix.
        session_id = ctx.room.name.removeprefix("hermes-")

    agent = HermesVoiceRoomAgent(session_id, backend_url=backend_url, design_id=design_id)

    async def _start() -> None:
        await agent.connect()

    ctx.add_shutdown_callback(agent.disconnect)
    asyncio.create_task(_start())


def main() -> None:
    parser = argparse.ArgumentParser(description="HERMES LiveKit voice agent worker")
    parser.add_argument("--session-id", required=True, help="HERMES session id to join")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="RoboCAD backend URL")
    parser.add_argument("--design-id", default=None, help="Optional design id")
    args = parser.parse_args()

    options = WorkerOptions(
        entrypoint_fnc=_entrypoint,
        userdata={
            "session_id": args.session_id,
            "backend_url": args.backend_url,
            "design_id": args.design_id,
        },
    )
    cli.run_app(options)


if __name__ == "__main__":
    main()
