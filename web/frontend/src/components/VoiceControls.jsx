import { useEffect, useRef, useState } from 'react'
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useDataChannel,
  useLocalParticipant,
  useRoomContext,
} from '@livekit/components-react'
import '@livekit/components-styles'
import { getHermesLiveKitToken } from '../api.js'

const STATUS_LABELS = {
  disconnected: 'Voice off',
  connecting: 'Connecting…',
  connected: 'Voice on',
  reconnecting: 'Reconnecting…',
}

const STATUS_COLORS = {
  disconnected: 'kp-badge-secondary',
  connecting: 'kp-badge-warning',
  connected: 'kp-badge-success',
  reconnecting: 'kp-badge-warning',
}

function InnerVoiceRoom({ onTranscript, onStatus, onError }) {
  const room = useRoomContext()
  const connectionState = useConnectionState()
  const { localParticipant } = useLocalParticipant()
  const micTrackRef = useRef(null)
  const [isMuted, setIsMuted] = useState(false)

  useDataChannel({
    topic: 'hermes_voice',
    onMessage: (msg) => {
      try {
        const payload = JSON.parse(msg.payload)
        if (payload.type === 'transcript' && onTranscript) {
          onTranscript(payload.role, payload.text)
        } else if (payload.type === 'agent_status' && onStatus) {
          onStatus(payload.status)
        } else if (payload.type === 'error' && onError) {
          onError(payload.message)
        }
      } catch {
        // Ignore non-JSON data messages.
      }
    },
  })

  useEffect(() => {
    async function publishMic() {
      try {
        const tracks = await room.localParticipant.createTracks({ audio: true })
        const audioTrack = tracks.find((t) => t.kind === 'audio')
        if (audioTrack) {
          await room.localParticipant.publishTrack(audioTrack)
          micTrackRef.current = audioTrack
        }
      } catch (err) {
        if (onError) onError(err.message || 'Failed to publish microphone')
      }
    }
    if (connectionState === 'connected' && !micTrackRef.current) {
      publishMic()
    }
  }, [connectionState, room, onError])

  const toggleMute = () => {
    if (micTrackRef.current) {
      micTrackRef.current.mute(!isMuted)
      setIsMuted(!isMuted)
    }
  }

  return (
    <div className="kp-flex kp-gap-2 kp-align-center kp-flex-wrap">
      <span className={`kp-badge ${STATUS_COLORS[connectionState] || 'kp-badge-secondary'}`}>
        {STATUS_LABELS[connectionState] || connectionState}
      </span>
      <button
        type="button"
        className="kp-button kp-button-sm kp-button-secondary"
        onClick={toggleMute}
        disabled={connectionState !== 'connected'}
      >
        {isMuted ? 'Unmute' : 'Mute'}
      </button>
      <RoomAudioRenderer />
    </div>
  )
}

export default function VoiceControls({ sessionId, onTranscript, onStatus, onError }) {
  const [tokenInfo, setTokenInfo] = useState(null)
  const [connecting, setConnecting] = useState(false)

  async function connect() {
    setConnecting(true)
    try {
      const data = await getHermesLiveKitToken(sessionId)
      setTokenInfo(data)
      if (onStatus) onStatus('connecting')
    } catch (err) {
      if (onError) onError(err.message || 'Failed to get LiveKit token')
    } finally {
      setConnecting(false)
    }
  }

  function disconnect() {
    setTokenInfo(null)
    if (onStatus) onStatus('disconnected')
  }

  if (!tokenInfo) {
    return (
      <button
        type="button"
        className="kp-button kp-button-sm kp-button-primary"
        onClick={connect}
        disabled={connecting}
      >
        {connecting ? 'Connecting…' : '🎙 Talk to HERMES'}
      </button>
    )
  }

  return (
    <LiveKitRoom
      serverUrl={tokenInfo.url}
      token={tokenInfo.token}
      connect={true}
      options={{ adaptiveStream: true }}
      audio={true}
      video={false}
      onDisconnected={disconnect}
      onError={(err) => onError && onError(err.message)}
    >
      <InnerVoiceRoom onTranscript={onTranscript} onStatus={onStatus} onError={onError} />
    </LiveKitRoom>
  )
}
