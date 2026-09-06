# Phase 27 — Voice HERMES + NVIDIA-powered rendering/simulation

**Date:** 2026-09-06  
**Status:** Planning  
**Goal:** Give HERMES a real-time voice, harden complex-design rendering, and wire NVIDIA NIM models into design inspection, voice, and simulation testing.

---

## 1. What the user asked for

1. **Voice for HERMES** — real-time two-way voice conversation. User can speak or type; HERMES always replies with both text and voice. Use LiveKit.
2. **Render complex designs properly** — the viewer must handle multi-part assemblies, materials, lighting, and advanced inspection modes.
3. **Use NVIDIA models** from `https://build.nvidia.com/models` to make rendering, simulation, and testing "perfect and to the point" for real-world scenarios.
4. **Keep the full test suite green** and the frontend build passing.

**Secrets to store in `.env` (user must add these; do not commit):**

```env
NVIDIA_API_KEY=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
LIVEKIT_URL=wss://assure-uc093wdg.livekit.cloud
LIVEKIT_API_KEY=APIJtMvhwRf2w4L
LIVEKIT_API_SECRET=DySp9UwP9PV53qhbhnVnuhYyrElk7PAaO6dyYeKfa2g
```

> The keys pasted in chat are exposed in conversation history. Rotate them after this session.

---

## 2. Proposed architecture

### 2.1 Voice HERMES with LiveKit

```
┌─────────────────────────────────────┐
│  Browser (React)                     │
│  - HermesPanel chat thread           │
│  - Voice connect button              │
│  - @livekit/components-react room    │
└──────────┬──────────────────────────┘
           │ WebRTC (WSS)
┌──────────▼──────────────────────────┐
│  LiveKit Cloud room                  │
│  (user's wss://assure-uc093wdg...)   │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│  LiveKit Agent worker (Python)       │
│  - STT: NVIDIA nemotron-asr-streaming│
│  - LLM/function layer: HERMES        │
│  - TTS: NVIDIA chatterbox-multilingual│
│  - Publishes transcript events       │
└─────────────────────────────────────┘
```

The existing FastAPI backend stays the source of truth for HERMES sessions. The LiveKit Agent worker calls the backend over local HTTP (`POST /hermes/session/{id}/message`) so all tool execution, approval gating, and persistence remain unchanged. The worker also emits room-data messages containing the transcript and HERMES text reply, which the React frontend displays in the chat panel.

### 2.2 Rendering hardening

Current `STLViewer.jsx` loads a single STL with flat `meshStandardMaterial`. Upgrades:

- **Multi-part assembly viewer**: load all STL/STEP parts from a bundle and color them by part family.
- **Material system**: differentiate PLA/AL6061/steel/PCB/enclosure with roughness/metalness and optional transparency.
- **Studio lighting + environment**: ambient + 3-point directional lights, soft shadows, contact shadows.
- **Inspection modes**: wireframe, section cut, exploded view, auto-fit camera.
- **Screenshot API**: capture the canvas so vision models can critique the render.
- **Progressive loading + error states**: show loading skeletons and mesh errors.

### 2.3 NVIDIA-powered simulation/testing intelligence

NVIDIA models useful to RoboCAD (from `build.nvidia.com/models`):

| Model | Role in RoboCAD |
|---|---|
| `nemotron-asr-streaming` | Real-time English STT for voice HERMES |
| `chatterbox-multilingual-tts` | Expressive TTS for HERMES voice replies |
| `nemotron-3-super-120b-a12b` / `ultra` | Optional LLM backend for HERMES (agentic coding/planning) |
| `llama-3.2-11b-vision-instruct` | Analyze screenshots of renders for design flaws |
| `cosmos-transfer1-7b` / `cosmos3-nano` | Generate physics-aware videos/scenarios from prompts; compare with MuJoCo rollouts |
| `fidelity` / `fluent` / `star-ccm` | CFD simulation stubs (where API access permits) |
| `trellis` | Text/image → 3D asset generation for reference parts |

A new `ai_cad/nvidia_nim.py` client will centralize authentication, endpoint discovery, retries, and test-mode fallbacks.

---

## 3. Phase breakdown

### Phase 27A — Voice HERMES (MVP, ~2 weeks)

**Backend**
- Add `livekit-agents`, `livekit-api`, and NVIDIA-specific STT/TTS packages to `requirements.txt`.
- Create `ai_cad/hermes/voice_agent.py` implementing a LiveKit `VoicePipelineAgent`:
  - `EntryJob` joins room, streams user audio to STT.
  - On final transcript, calls HERMES backend (`/hermes/session/{id}/message`).
  - Speaks the HERMES text reply via TTS.
  - Emits data messages: `{type: "transcript", role: "user", text: ...}` and `{type: "transcript", role: "assistant", text: ...}`.
- Add FastAPI token endpoint `POST /hermes/session/{session_id}/livekit-token`.
- Add `ai_cad/hermes/nvidia_voice.py` adapters for STT/TTS using the NVIDIA API key.
- Add tests in `tests/test_hermes_voice.py` using mocked LiveKit rooms and deterministic audio buffers.

**Frontend**
- Add `@livekit/components-react` to `package.json`.
- Add `VoiceControls.jsx` sub-component inside `HermesPanel.jsx`:
  - microphone/connect button, mute, disconnect, voice status badge.
  - Display incoming user transcript and assistant transcript inline in the chat.
- Add `getLiveKitToken(sessionId)` helper in `api.js`.
- Add voice-specific quick action: "Talk to HERMES".

**Integration test**
- A mocked LiveKit agent emits a user transcript, backend responds via HERMES, agent receives text, TTS fallback returns audio metadata, frontend shows both transcripts.

### Phase 27B — Rendering hardening (~1.5 weeks)

**Frontend**
- Refactor `STLViewer.jsx` into:
  - `SceneContainer` (Canvas, lights, controls).
  - `AssemblyModel` (load multiple STLs from `/designs/{id}/bundle` parts list).
  - `PartMaterial` (family-based material mapping).
- Add viewer toolbar: wireframe, section cut (clipping plane), exploded view slider, fit view, screenshot.
- Add screenshot endpoint `POST /designs/{id}/screenshot` that the frontend can trigger; backend stores image for vision-model analysis.
- Add loading/error states for large meshes.

**Backend**
- Add `GET /designs/{id}/bundle-parts` returning part URLs + family tags + colors.
- Optional: add `POST /designs/{id}/render-analysis` using `llama-3.2-11b-vision-instruct` to critique a screenshot.

**Tests**
- `tests/test_viewer_api.py` for bundle-parts and screenshot endpoints.
- Frontend build must pass.

### Phase 27C — NVIDIA simulation intelligence (~1.5 weeks)

**Backend**
- Create `ai_cad/nvidia_nim.py` with:
  - `NvidiaNimClient(api_key)`.
  - `chat_completion(model, messages)` for LLMs.
  - `text_to_speech(text, voice)` using `chatterbox-multilingual-tts`.
  - `speech_to_text(audio_bytes)` using `nemotron-asr-streaming`.
  - `generate_scenario_video(prompt, image)` using Cosmos for real-world scenario generation.
  - `analyze_image(prompt, image_bytes)` using vision models.
- Add HERMES tools:
  - `analyze_render`: send current design screenshot to vision model for feedback.
  - `generate_real_world_scenario`: use Cosmos/LLM to produce a MuJoCo world variant.
- Add an optional `NVIDIA_MODEL` env var to `ai_cad/hermes/llm.py` so HERMES can use `nemotron-3-super-120b-a12b`.

**Tests**
- `tests/test_nvidia_nim.py` with mocked HTTP responses.
- `tests/test_hermes_nvidia_tools.py` for the new HERMES tools.

---

## 4. Key decisions for the user

1. **LiveKit Agent deployment model**
   - **Option A (recommended)**: Run the LiveKit Agent as a separate worker process (`python -m ai_cad.hermes.voice_agent_worker`). Simpler, scales independently, matches LiveKit docs.
   - **Option B**: Spawn the agent inside the FastAPI process as a background task. Simpler to start locally but couples voice to the web server.

2. **Voice STT/TTS provider**
   - **Option A (recommended)**: Use NVIDIA `nemotron-asr-streaming` + `chatterbox-multilingual-tts` via custom LiveKit plugins. Fits the user's NVIDIA key and "use the power of this" request.
   - **Option B**: Use LiveKit's default plugin examples (e.g., OpenAI Whisper + OpenAI TTS). Requires an OpenAI key.
   - **Option C**: Use a local open-source pipeline (whisper.cpp + piper). No cloud cost but lower quality.

3. **Scope order**
   - **Option A (recommended)**: Ship 27A (voice) first because it has the clearest user-facing win and uses the keys provided.
   - **Option B**: Ship 27B (rendering) first if the user thinks the current viewer is the biggest blocker.
   - **Option C**: Parallel 27A+27B using workflows, then 27C.

4. **NVIDIA LLM for HERMES**
   - Add as an optional model (`ROBOCAD_MODEL=nemotron-3-super-120b-a12b`) without removing Anthropic/Ollama support. Default stays Anthropic for now unless the user wants to switch.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| NVIDIA API key is rate-limited / costly | Add caching, test-mode mocks, and budget-aware defaults (low max_tokens, no streaming unless needed). |
| LiveKit Cloud free tier limits concurrent agents | Document limits; fallback to "push-to-talk" mode that records short audio clips instead of persistent room. |
| Real-time STT latency hurts conversation | Use streaming partial transcripts for UI feedback and final transcript only for HERMES calls; keep TTS responses concise. |
| Browser mic permissions / WebRTC blocked | Provide clear copy-paste fallback; keep text chat always available. |
| Multi-part viewer performance | Use instancing, lazy part loading, and LOD for very large assemblies. |
| Vision model hallucinates design critiques | Always return raw vision output as a suggestion, not an executed change; route real changes through HERMES approval gates. |

---

## 6. Test strategy

- **Unit**: mock LiveKit, NVIDIA, and vision APIs; assert transcripts and tool calls.
- **Integration**: mocked-LLM voice flow `audio → STT → HERMES → TTS` in one pytest.
- **Frontend**: `npm run build` after adding LiveKit components; React component smoke tests if feasible.
- **End-to-end**: token endpoint returns a valid JWT-looking string; agent connects to a local LiveKit dev server (optional, heavy tier).
- **Target**: maintain 450/451 passing baseline; add ~30–40 new tests for 27A, ~15 for 27B, ~15 for 27C.

---

## 7. Timeline

- **27A (Voice HERMES)**: 2 weeks → immediate user-visible win.
- **27B (Rendering hardening)**: 1.5 weeks.
- **27C (NVIDIA simulation intelligence)**: 1.5 weeks.
- **Total**: ~5 weeks, but 27A can be demoed independently after 2 weeks.

---

## 8. Superpowers to use

- `/workflows` — parallel agents for NVIDIA model exploration, LiveKit adapter design, and frontend voice UI options.
- `/frontend-design:frontend-design` — design the voice control UI inside HermesPanel.
- `/brainstorming` — architecture for real-time voice + approval gates + text synchronization.
- `/qa` — test the voice pipeline and NVIDIA integrations.
- `/loop` — iterative validation of the full voice → HERMES → render → simulation loop.

---

## 9. First step after approval

1. Add the provided secrets to `.env` (user action).
2. Add `livekit-agents`, `livekit-api`, and frontend LiveKit dependencies.
3. Implement `ai_cad/hermes/voice_agent.py` and `ai_cad/hermes/nvidia_voice.py` with mocked fallbacks.
4. Add the LiveKit token endpoint.
5. Add `VoiceControls.jsx` and wire it into `HermesPanel.jsx`.
6. Run tests and frontend build; iterate.
