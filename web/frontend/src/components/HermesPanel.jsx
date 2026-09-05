import { useEffect, useRef, useState } from 'react'
import {
  approveHermesStep,
  createHermesSession,
  explainWithHermes,
  getHermesSession,
  getHermesStatus,
  rejectHermesStep,
  sendHermesMessage,
} from '../api.js'

const STATUS_COLORS = {
  idle: 'kp-badge-secondary',
  running: 'kp-badge-warning',
  awaiting_approval: 'kp-badge-error',
  error: 'kp-badge-error',
  done: 'kp-badge-success',
}

const STATUS_LABELS = {
  idle: 'Idle',
  running: 'Running',
  awaiting_approval: 'Awaiting approval',
  error: 'Error',
  done: 'Done',
}

export default function HermesPanel({ designId }) {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [activePlan, setActivePlan] = useState(null)
  const [pending, setPending] = useState([])
  const [status, setStatus] = useState('idle')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(true)
  const messagesEndRef = useRef(null)

  // Create or load a session for this design.
  useEffect(() => {
    let cancelled = false
    async function init() {
      setSessionId(null)
      setMessages([])
      setActivePlan(null)
      setPending([])
      setStatus('idle')
      try {
        const data = await createHermesSession(designId)
        if (cancelled) return
        setSessionId(data.session_id)
        const full = await getHermesSession(data.session_id, designId)
        if (!cancelled) {
          setMessages(full.messages || [])
          setActivePlan(full.active_plan)
          setStatus(full.status || 'idle')
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    init()
    return () => { cancelled = true }
  }, [designId])

  // Poll status while running or awaiting approval.
  useEffect(() => {
    if (!sessionId) return
    if (status !== 'running' && status !== 'awaiting_approval') return
    const interval = setInterval(async () => {
      try {
        const data = await getHermesStatus(sessionId)
        setStatus(data.status)
        setPending(data.pending_approvals || [])
      } catch {
        // Ignore polling errors.
      }
    }, 1500)
    return () => clearInterval(interval)
  }, [sessionId, status])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    if (!sessionId || !input.trim()) return
    setLoading(true)
    setError(null)
    const text = input.trim()
    setInput('')
    try {
      const data = await sendHermesMessage(sessionId, text)
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: text },
        { role: 'assistant', content: data.reply },
      ])
      setActivePlan(data.active_plan)
      setPending(data.pending_approvals || [])
      setStatus(data.status)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove(step) {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      const data = await approveHermesStep(sessionId, step.step_id)
      setActivePlan(data.active_plan)
      setPending((data.active_plan?.steps || [])
        .filter((s) => s.status === 'awaiting_approval')
        .map((s) => ({ step_id: s.id, description: s.description, tool: s.tool, parameters: s.parameters })))
      setStatus(data.status)
      if (data.results?.length) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Executed ${step.tool}. Status: ${data.status}.` },
        ])
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleReject(step) {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      const data = await rejectHermesStep(sessionId, step.step_id, 'Rejected by user from UI')
      setActivePlan(data.active_plan)
      setPending([])
      setStatus(data.status)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Rejected step ${step.description}.` },
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleExplain(target) {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      const data = await explainWithHermes(sessionId, target)
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: `Explain ${target}` },
        { role: 'assistant', content: data.explanation },
      ])
      setStatus(data.status)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="hermes-heading">
      <div className="kp-panel-header">
        <h3 id="hermes-heading" className="kp-panel-title">🧿 HERMES supervisor</h3>
        <div className="kp-flex kp-gap-2 kp-align-center">
          <span className={`kp-badge ${STATUS_COLORS[status] || 'kp-badge-secondary'}`}>
            {STATUS_LABELS[status] || status}
          </span>
          <button
            type="button"
            className="kp-button kp-button-icon kp-button-ghost"
            onClick={() => setExpanded(!expanded)}
            aria-label={expanded ? 'Collapse HERMES panel' : 'Expand HERMES panel'}
          >
            {expanded ? '−' : '+'}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="kp-flex-col kp-gap-2 kp-mt-2">
          <p className="kp-help-text">
            Conversational supervisor across design, simulation, and training.
            Expensive actions require your approval.
          </p>

          <div className="kp-flex kp-gap-2 kp-flex-wrap">
            <button
              type="button"
              className="kp-button kp-button-sm kp-button-secondary"
              onClick={() => handleExplain('dfm')}
              disabled={loading}
            >
              Explain DFM
            </button>
            <button
              type="button"
              className="kp-button kp-button-sm kp-button-secondary"
              onClick={() => handleExplain('brain')}
              disabled={loading}
            >
              Explain brain
            </button>
            <button
              type="button"
              className="kp-button kp-button-sm kp-button-secondary"
              onClick={() => handleExplain('world_replay')}
              disabled={loading}
            >
              Explain replay
            </button>
          </div>

          <div
            className="kp-flex-col kp-gap-2"
            style={{
              maxHeight: '240px',
              overflowY: 'auto',
              border: '1px solid var(--kp-outline-variant)',
              borderRadius: '4px',
              padding: '0.5rem',
              background: 'var(--kp-surface-container-lowest)',
            }}
          >
            {messages.length === 0 && (
              <p className="kp-text-subtle kp-small">Ask HERMES to design, simulate, train, or explain.</p>
            )}
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className="kp-flex-col kp-gap-1"
                style={{
                  alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  className="kp-small"
                  style={{
                    padding: '0.35rem 0.6rem',
                    borderRadius: '4px',
                    maxWidth: '90%',
                    background:
                      msg.role === 'user'
                        ? 'var(--kp-primary-container)'
                        : 'var(--kp-surface-container)',
                    color:
                      msg.role === 'user'
                        ? 'var(--kp-on-primary-container)'
                        : 'var(--kp-on-surface)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {pending.length > 0 && (
            <div className="kp-flex-col kp-gap-2">
              <strong className="kp-small">Pending approvals</strong>
              {pending.map((step) => (
                <div
                  key={step.step_id}
                  className="kp-flex-col kp-gap-1"
                  style={{
                    padding: '0.5rem',
                    border: '1px solid var(--kp-error)',
                    borderRadius: '4px',
                    background: 'var(--kp-error-container)',
                  }}
                >
                  <div className="kp-flex kp-justify-between kp-align-center">
                    <span className="kp-small" style={{ color: 'var(--kp-on-error-container)' }}>
                      {step.description} <span className="kp-mono">({step.tool})</span>
                    </span>
                    <div className="kp-flex kp-gap-1">
                      <button
                        type="button"
                        className="kp-button kp-button-sm kp-button-primary"
                        onClick={() => handleApprove(step)}
                        disabled={loading}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="kp-button kp-button-sm kp-button-secondary"
                        onClick={() => handleReject(step)}
                        disabled={loading}
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                  {Object.keys(step.parameters || {}).length > 0 && (
                    <pre
                      className="kp-mono kp-small"
                      style={{
                        background: 'var(--kp-surface-container-lowest)',
                        padding: '0.25rem',
                        borderRadius: '2px',
                        overflowX: 'auto',
                      }}
                    >
                      {JSON.stringify(step.parameters, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}

          {activePlan && (
            <div className="kp-flex-col kp-gap-1">
              <strong className="kp-small">Active plan: {activePlan.goal}</strong>
              <div className="kp-flex-col kp-gap-1">
                {activePlan.steps.map((step) => (
                  <div
                    key={step.id}
                    className="kp-flex kp-gap-2 kp-align-center kp-small"
                    style={{ paddingLeft: '0.5rem' }}
                  >
                    <span
                      className={`kp-badge ${
                        step.status === 'completed'
                          ? 'kp-badge-success'
                          : step.status === 'awaiting_approval'
                          ? 'kp-badge-error'
                          : step.status === 'failed' || step.status === 'rejected'
                          ? 'kp-badge-error'
                          : 'kp-badge-secondary'
                      }`}
                    >
                      {step.status}
                    </span>
                    <span className="kp-text-subtle">{step.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <div className="kp-error">{error}</div>}

          <div className="kp-flex kp-gap-2 kp-align-center">
            <input
              type="text"
              className="kp-input"
              placeholder="Ask HERMES…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={loading}
            />
            <button
              type="button"
              className="kp-button kp-button-primary"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              {loading ? '…' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
