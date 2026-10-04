import { useEffect, useRef, useState } from 'react'
import {
  approveHermesStep,
  createHermesSession,
  explainWithHermes,
  getHermesAudit,
  getHermesSession,
  getHermesStatus,
  rejectHermesStep,
  sendHermesMessage,
  startHermesAuto,
} from '../api.js'
import VoiceControls from './VoiceControls.jsx'

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

export default function HermesPanel({ designId, onDesignCreated, focus, onFocusAck }) {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [activePlan, setActivePlan] = useState(null)
  const [pending, setPending] = useState([])
  const [status, setStatus] = useState('idle')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(true)
  const [voiceStatus, setVoiceStatus] = useState('disconnected')
  const [autoOpen, setAutoOpen] = useState(false)
  const [autoPrompt, setAutoPrompt] = useState('')
  const [autoMaxRetries, setAutoMaxRetries] = useState(3)
  const [autoCertThreshold, setAutoCertThreshold] = useState(0.7)
  const [autoTimeoutSeconds, setAutoTimeoutSeconds] = useState(600)
  const [autoLoading, setAutoLoading] = useState(false)
  const [autoStatus, setAutoStatus] = useState('idle')
  const [auditAttempts, setAuditAttempts] = useState([])
  const [autoResult, setAutoResult] = useState(null)
  const messagesEndRef = useRef(null)
  const autoSectionRef = useRef(null)

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
          if (full.context?.design_summary) {
            const summary = full.context.design_summary
            const ctxText = [
              summary.prompt,
              summary.domain,
              summary.success ? 'success' : 'failed',
              `${(summary.parameters || []).length} editable params`,
            ].filter(Boolean).join(' · ')
            setMessages((prev) => {
              const existing = prev.find((m) => m.role === 'context_summary')
              if (existing) return prev
              return [{ role: 'context_summary', content: ctxText }, ...prev]
            })
          }
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

  // Poll auto-design audit while running or awaiting approval.
  useEffect(() => {
    if (!sessionId) return
    if (autoStatus !== 'running' && autoStatus !== 'awaiting_approval' && autoStatus !== 'certified' && autoStatus !== 'failed') return
    const interval = setInterval(async () => {
      try {
        const data = await getHermesAudit(sessionId)
        setAuditAttempts(data.audit || [])
        setAutoStatus(data.status || 'idle')
        if (data.result) {
          setAutoResult(data.result)
        }
      } catch {
        // Ignore polling errors.
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [sessionId, autoStatus])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // When App routes focus to HERMES, expand the panel and surface the auto-design form.
  useEffect(() => {
    if (!focus) return
    setExpanded(true)
    setAutoOpen(true)
    setTimeout(() => {
      autoSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
    if (onFocusAck) onFocusAck()
  }, [focus, onFocusAck])

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

  async function handleStartAuto() {
    if (!sessionId || !autoPrompt.trim()) return
    setAutoLoading(true)
    setError(null)
    setAuditAttempts([])
    setAutoResult(null)
    try {
      const data = await startHermesAuto(sessionId, autoPrompt.trim(), {
        maxRetries: Number(autoMaxRetries),
        certThreshold: Number(autoCertThreshold),
        timeoutSeconds: Number(autoTimeoutSeconds),
      })
      setAutoStatus(data.status || 'running')
      setAuditAttempts(data.audit || [])
      setAutoResult({
        design_id: data.design_id,
        search_id: data.search_id,
        candidate_id: data.candidate_id,
        success: data.success,
        message: data.message,
      })
    } catch (err) {
      setError(err.message)
      setAutoStatus('error')
    } finally {
      setAutoLoading(false)
    }
  }

  function handleOpenAutoResult() {
    const id = autoResult?.design_id || autoResult?.search_id
    if (id && onDesignCreated) {
      onDesignCreated(id)
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

  function handleVoiceTranscript(role, text) {
    setMessages((prev) => [
      ...prev,
      { role, content: text, source: 'voice' },
    ])
  }

  function handleVoiceStatus(newStatus) {
    setVoiceStatus(newStatus)
  }

  if (!designId) return null

  const contextSummary = messages.find((m) => m.role === 'context_summary')?.content

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
            className={`kp-button kp-button-small ${autoOpen ? 'kp-button-primary' : 'kp-button-secondary'}`}
            onClick={() => setAutoOpen(!autoOpen)}
            disabled={loading || autoLoading}
          >
            Auto-design
          </button>
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

          <div ref={autoSectionRef} className="kp-flex-col kp-gap-2">
            <div className="kp-flex kp-gap-2 kp-align-center kp-flex-wrap">
              <button
                type="button"
                className={`kp-button kp-button-small ${autoOpen ? 'kp-button-primary' : 'kp-button-secondary'}`}
                onClick={() => setAutoOpen(!autoOpen)}
                disabled={loading || autoLoading}
              >
                {autoOpen ? 'Close auto-design' : 'Auto-design'}
              </button>
              {autoStatus !== 'idle' && (
                <span className={`kp-badge ${autoStatus === 'done' || autoStatus === 'certified' ? 'kp-badge-success' : autoStatus === 'error' || autoStatus === 'failed' ? 'kp-badge-error' : 'kp-badge-warning'}`}>
                  {autoStatus}
                </span>
              )}
            </div>

            {autoOpen && (
              <div
                className="kp-flex-col kp-gap-2"
                style={{
                  padding: '0.5rem',
                  border: '1px solid var(--kp-outline-variant)',
                  borderRadius: '4px',
                  background: 'var(--kp-surface-container-lowest)',
                }}
              >
                <div className="kp-field">
                  <label htmlFor="auto-prompt" className="kp-label">Auto-design prompt</label>
                  <input
                    id="auto-prompt"
                    type="text"
                    className="kp-input"
                    placeholder="e.g. robot arm with gripper"
                    value={autoPrompt}
                    onChange={(e) => setAutoPrompt(e.target.value)}
                    disabled={autoLoading}
                  />
                </div>

                <div className="kp-flex kp-gap-2 kp-flex-wrap">
                  <div className="kp-field" style={{ flex: 1, minWidth: '100px' }}>
                    <label htmlFor="auto-retries" className="kp-label">Max retries</label>
                    <input
                      id="auto-retries"
                      type="number"
                      className="kp-input"
                      min={1}
                      max={10}
                      value={autoMaxRetries}
                      onChange={(e) => setAutoMaxRetries(e.target.value)}
                      disabled={autoLoading}
                    />
                  </div>
                  <div className="kp-field" style={{ flex: 1, minWidth: '100px' }}>
                    <label htmlFor="auto-cert" className="kp-label">Cert threshold</label>
                    <input
                      id="auto-cert"
                      type="number"
                      className="kp-input"
                      min={0}
                      max={1}
                      step={0.05}
                      value={autoCertThreshold}
                      onChange={(e) => setAutoCertThreshold(e.target.value)}
                      disabled={autoLoading}
                    />
                  </div>
                  <div className="kp-field" style={{ flex: 1, minWidth: '100px' }}>
                    <label htmlFor="auto-timeout" className="kp-label">Timeout (s)</label>
                    <input
                      id="auto-timeout"
                      type="number"
                      className="kp-input"
                      min={30}
                      step={30}
                      value={autoTimeoutSeconds}
                      onChange={(e) => setAutoTimeoutSeconds(e.target.value)}
                      disabled={autoLoading}
                    />
                  </div>
                </div>

                <button
                  type="button"
                  className="kp-button kp-button-primary"
                  onClick={handleStartAuto}
                  disabled={autoLoading || !autoPrompt.trim()}
                >
                  {autoLoading ? 'Starting pipeline…' : 'Run full pipeline'}
                </button>

                {auditAttempts.length > 0 && (
                  <div className="kp-flex-col kp-gap-1">
                    <span className="kp-label">Pipeline audit</span>
                    {auditAttempts.map((attempt) => (
                      <div
                        key={attempt.attempt_number || attempt.attempt || attempt.id || attempt.action}
                        className="kp-flex kp-gap-2 kp-align-center kp-small"
                        style={{
                          padding: '0.35rem 0.5rem',
                          borderRadius: '4px',
                          background: 'var(--kp-surface-container)',
                          border: '1px solid var(--kp-border)',
                        }}
                      >
                        <span className="kp-mono">Attempt {attempt.attempt_number ?? attempt.attempt ?? '?'}</span>
                        <span className="kp-text-subtle">·</span>
                        <span>{attempt.action || '—'}</span>
                        <span className="kp-text-subtle">·</span>
                        <span className="kp-mono">{attempt.duration_seconds != null ? `${attempt.duration_seconds.toFixed(1)}s` : '—'}</span>
                        <span className={`kp-badge ${attempt.passed ? 'kp-badge-success' : 'kp-badge-error'}`}>
                          {attempt.passed ? 'PASS' : 'FAIL'}
                        </span>
                        {!attempt.passed && attempt.retry_reason && (
                          <span className="kp-small" style={{ color: 'var(--kp-error)' }}>{attempt.retry_reason}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {autoResult && (
                  <div className="kp-flex-col kp-gap-1">
                    <span className="kp-label">Result</span>
                    <div className="kp-flex kp-gap-2 kp-align-center kp-small">
                      <span className="kp-mono">
                        {autoResult.design_id ? `Design #${autoResult.design_id.slice(0, 8)}` : autoResult.search_id ? `Search #${autoResult.search_id.slice(0, 8)}` : 'Done'}
                      </span>
                      {(autoResult.design_id || autoResult.search_id) && onDesignCreated && (
                        <button
                          type="button"
                          className="kp-button kp-button-small kp-button-primary"
                          onClick={handleOpenAutoResult}
                        >
                          Open result
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {contextSummary && (
            <div
              className="kp-small"
              style={{
                padding: '0.5rem',
                border: '1px solid var(--kp-outline-variant)',
                borderRadius: '4px',
                background: 'var(--kp-surface-container-lowest)',
              }}
            >
              <strong>Design context:</strong> {contextSummary}
            </div>
          )}

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
            <button
              type="button"
              className="kp-button kp-button-sm kp-button-primary"
              onClick={() => setInput('Propose a redesign from the latest report')}
              disabled={loading}
            >
              Propose redesign
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
                {msg.role === 'context_summary' ? (
                  <div
                    className="kp-small"
                    style={{
                      padding: '0.35rem 0.6rem',
                      borderRadius: '4px',
                      maxWidth: '90%',
                      background: 'var(--kp-surface-container)',
                      color: 'var(--kp-on-surface-variant)',
                      fontStyle: 'italic',
                    }}
                  >
                    {msg.content}
                  </div>
                ) : (
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
                )}
                {msg.tool_results?.length > 0 && (
                  <div className="kp-flex-col kp-gap-1" style={{ maxWidth: '90%' }}>
                    {msg.tool_results.map((tr, tidx) => (
                      <div
                        key={tidx}
                        className="kp-small"
                        style={{
                          padding: '0.35rem 0.5rem',
                          borderRadius: '4px',
                          background:
                            tr.status === 'success'
                              ? 'var(--kp-success-container)'
                              : tr.status === 'error'
                              ? 'var(--kp-error-container)'
                              : 'var(--kp-surface-container-high)',
                          color: 'var(--kp-on-surface)',
                        }}
                      >
                        <strong>{tr.tool}</strong>: {tr.status}
                        {tr.message && <span> — {tr.message}</span>}
                      </div>
                    ))}
                  </div>
                )}
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
                    className="kp-flex-col kp-gap-1 kp-small"
                    style={{ paddingLeft: '0.5rem' }}
                  >
                    <div className="kp-flex kp-gap-2 kp-align-center">
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
                    {step.status === 'failed' && step.error && (
                      <div className="kp-error kp-small">{step.error}</div>
                    )}
                    {step.tool === 'propose_redesign' && step.result?.parameter_updates && (
                      <div
                        className="kp-flex-col kp-gap-1"
                        style={{
                          padding: '0.5rem',
                          border: '1px solid var(--kp-outline-variant)',
                          borderRadius: '4px',
                          background: 'var(--kp-surface-container-lowest)',
                        }}
                      >
                        <div className="kp-small"><strong>Redesign proposal</strong>: {step.result.rationale}</div>
                        <pre className="kp-mono kp-small">{JSON.stringify(step.result.parameter_updates, null, 2)}</pre>
                        {step.result.confidence && (
                          <span className="kp-small kp-text-subtle">Confidence: {step.result.confidence}</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <div className="kp-error">{error}</div>}

          <div className="kp-flex kp-gap-2 kp-align-center kp-flex-wrap">
            <VoiceControls
              sessionId={sessionId}
              onTranscript={handleVoiceTranscript}
              onStatus={handleVoiceStatus}
              onError={(msg) => setError(msg)}
            />
            {voiceStatus && voiceStatus !== 'disconnected' && (
              <span className="kp-small kp-text-subtle">Voice: {voiceStatus}</span>
            )}
          </div>

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
