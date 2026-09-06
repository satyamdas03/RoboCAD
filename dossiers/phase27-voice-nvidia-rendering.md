# Phase 27 — Voice, NVIDIA Intelligence, and Professional Rendering

**Date:** 2026-09-01  
**Status:** Phases 27A, 27B, and 27C complete; 27D is future work blocked on hardware access.  
**Related:** [`robocad-end-to-end-roadmap.md`](robocad-end-to-end-roadmap.md), [`PATH1_PATH2_analysis.md`](PATH1_PATH2_analysis.md), [`PLAN.md`](../PLAN.md)

---

## Why Phase 27 matters

After Phases 0–26 turned RoboCAD into a multi-domain generative engineering platform with a conversational supervisor (HERMES), the next user-experience jump is making the supervisor *feel* present and making the designs *look* credible. Phase 27 addresses three parallel tracks:

- **27A — Voice:** Users should be able to talk to HERMES while their hands are on hardware or a sketch tablet.
- **27B — Rendering:** Complex parametric assemblies must render cleanly in the browser, with proper camera framing, lighting, and inspection tools.
- **27C — NVIDIA Intelligence:** Cloud NVIDIA NIM models provide high-quality STT, TTS, vision-language critique, and physics-aware scenario generation without maintaining those models locally.

All three are prerequisite to public demos, marketplace screenshots, and eventually sim-to-real loops where a human operator and HERMES converse around live telemetry.

---

## Phase 27A — HERMES voice interface

### Approach

We chose **LiveKit Cloud** for WebRTC rooms and a **manual room-based agent** (`livekit.rtc.Room`) rather than LiveKit's high-level `AgentSession`. The manual path gives full control over:

- audio buffering and VAD,
- HERMES backend HTTP calls between speech turns,
- transcript mirroring over LiveKit data channels,
- fallback behavior when NVIDIA STT/TTS latency spikes.

### Components

| File | Responsibility |
|---|---|
| `ai_cad/hermes/livekit_token.py` | User/agent token generation using `livekit.api.AccessToken` + `VideoGrants`. |
| `ai_cad/hermes/nvidia_voice.py` | Raw NVIDIA NIM clients: `NvidiaSTT.transcribe(audio_bytes)` and `NvidiaTTS.synthesize(text)`. |
| `ai_cad/hermes/voice_plugins.py` | LiveKit plugin subclasses: `NvidiaSTTPlugin(stt.STT)` and `NvidiaTTSPlugin(tts.TTS)`. |
| `ai_cad/hermes/voice_agent.py` | `HermesVoiceRoomAgent` joins the room, publishes a `LocalAudioTrack`, subscribes to user audio, runs VAD buffering, transcribes, calls HERMES, and publishes synthesized replies. |
| `web/backend/main.py` | `POST /hermes/session/{id}/livekit-token`. |
| `web/frontend/src/components/VoiceControls.jsx` | React/LiveKit room connection, mic publish, data-channel transcript display, status/errors. |
| `web/frontend/src/components/HermesPanel.jsx` | Embeds `VoiceControls` and merges voice transcripts into the text chat history. |

### Test coverage

`tests/test_hermes_voice.py` — 15 tests:

- token generation and structure,
- backend endpoint returns a valid LiveKit URL + token,
- NVIDIA STT client accepts PCM and returns transcript,
- NVIDIA TTS client returns PCM bytes,
- LiveKit plugin adapters construct without error.

---

## Phase 27B — Professional rendering

### Approach

The previous `STLViewer` loaded meshes but let the camera sit at a fixed position, which caused clipping, poor lighting, and unprofessional screenshots. The new viewer uses `@react-three/drei` helpers to auto-frame, light, and ground the scene.

### Components

| Feature | Implementation |
|---|---|
| Auto-fit camera | `Bounds` + `useBounds().fit()` on first load and after model change. |
| Lighting | `hemisphereLight` + 3 directional lights (key, fill, rim). |
| Ground contact | `ContactShadows` for object grounding. |
| Grid | Toggleable `Grid` helper. |
| Wireframe | Material toggle for inspection. |
| Screenshot | `preserveDrawingBuffer: true` + `CaptureBridge` reads the canvas. |
| AI critique | Toolbar button sends screenshot to `POST /designs/{id}/render-critique`. |

### File

`web/frontend/src/components/STLViewer.jsx` was rebuilt in place. The public API (`STLViewer` component props) remains backward-compatible with existing callers.

---

## Phase 27C — NVIDIA model intelligence

### Approach

Instead of wiring each NVIDIA model ad-hoc, we built one generic client (`NvidiaClient`) that handles NIM REST conventions: base URL `https://integrate.api.nvidia.com/v1`, `nvidia-` model IDs, bearer auth, and provider-specific payload shapes for chat, vision, and Cosmos scenario generation.

### Components

| File | Responsibility |
|---|---|
| `ai_cad/nvidia_client.py` | `NvidiaClient.chat()`, `.vision()`, `.generate_scenario()`; model constants for Nemotron Lightning, Llama 3.2 11B Vision, Cosmos Nano, and default STT/TTS. |
| `ai_cad/render_critique.py` | `critique_render(image_bytes)` sends a screenshot to the vision model and returns a structured JSON report (score, issues, suggestions, safe-to-show-user summary). |
| `ai_cad/hermes/llm.py` | `_looks_like_nvidia_model()` + `build_nvidia_caller()` lets HERMES route to NVIDIA chat models when `ROBOCAD_MODEL` is set to a NVIDIA ID. |
| `web/backend/main.py` | `POST /designs/{id}/render-critique`, `POST /world/scenario`, `GET /nvidia/models`. |
| `web/frontend/src/api.js` | `critiqueRender`, `generateScenario`, `listNvidiaModels`. |

### Test coverage

`tests/test_nvidia_client.py` — 15 tests:

- client chat and vision request shaping,
- HERMES caller construction and routing,
- render critique parsing and safe-output filtering,
- backend endpoint mocks.

---

## Phase 27D — Sim-to-real (future)

Hardware-in-the-loop remains the next milestone once a real robot, sensors, and a safe test environment are available. The software prerequisites are in place:

- verified MJCF/URDF bundles (Phase 14A),
- world-model scene builder (Phase 24),
- attention-based brain training harness (Phase 25),
- HERMES supervisor with voice interface (Phases 26–27A).

Phase 27D will add a ROS 2 / micro-ROS bridge, real-trajectory logger, sim-parameter calibration, and a retraining loop.

---

## Configuration

Required `.env` entries:

```bash
ANTHROPIC_API_KEY=...            # generation + HERMES
NVIDIA_API_KEY=...               # STT, TTS, chat, vision, Cosmos
LIVEKIT_URL=wss://...            # WebRTC room URL
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

Optional:

```bash
ROBOCAD_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b   # route HERMES through NVIDIA
```

---

## Acceptance criteria

- [x] User can start a voice session from `HermesPanel`.
- [x] Spoken HERMES replies are synthesized and played.
- [x] Text transcripts from voice appear in the chat history.
- [x] Complex assemblies auto-fit and render with shadows + ground grid.
- [x] AI render critique returns a structured report for any design.
- [x] NVIDIA model catalog endpoint lists supported models.
- [x] Full pytest suite passes: 263 default + 222 heavy/slow tests.
- [x] Frontend production build passes.

---

*Phase 27A/B/C acceptance verified 2026-09-01. Phase 27D blocked on hardware access.*
