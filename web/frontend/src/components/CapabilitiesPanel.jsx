import { useEffect, useState } from 'react'
import { getCapabilities, runHandshake, getHandshakeReport } from '../api.js'

export default function CapabilitiesPanel({ designId }) {
  const [caps, setCaps] = useState(null)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getCapabilities()
      .then((data) => setCaps(data))
      .catch((err) => console.error('Failed to load capabilities', err))
  }, [])

  useEffect(() => {
    if (!designId) return
    setReport(null)
    getHandshakeReport(designId, 'wedge_push_block')
      .then((data) => setReport(data))
      .catch(() => setReport(null))
  }, [designId])

  async function handleHandshake() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await runHandshake(designId, 'wedge_push_block')
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="caps-heading">
      <div className="kp-panel-header">
        <h3 id="caps-heading" className="kp-panel-title">LearningRobotics handshake</h3>
      </div>

      {caps && (
        <div className="kp-flex-col kp-gap-2 kp-mb-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Bundle schema</span>
            <span className="kp-mono kp-badge">{caps.bundle_schema_version}</span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Simulators</span>
            <span className="kp-mono">{caps.supported_simulators?.join(', ')}</span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Templates</span>
            <span className="kp-mono">{caps.supported_scene_templates?.length ?? 0}</span>
          </div>
        </div>
      )}

      <button
        type="button"
        className="kp-button kp-button-primary"
        onClick={handleHandshake}
        disabled={loading}
      >
        {loading ? 'Running 10 s stability…' : 'Run handshake (wedge push)'}
      </button>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Handshake</span>
            <span className={`kp-badge ${report.success || report.handshake?.success ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.success || report.handshake?.success ? 'Stable' : 'Failed'}
            </span>
          </div>

          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Bodies</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.nbody ?? report.handshake?.nbody ?? '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Steps</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.rollout?.steps ?? report.handshake?.rollout?.steps ?? '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Max pen. (mm)</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {(report.rollout?.max_penetration_mm ?? report.handshake?.rollout?.max_penetration_mm ?? null) != null
                  ? (report.rollout?.max_penetration_mm ?? report.handshake?.rollout?.max_penetration_mm).toFixed(3)
                  : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Energy drift</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {(report.rollout?.energy_drift ?? report.handshake?.rollout?.energy_drift ?? null) != null
                  ? (report.rollout?.energy_drift ?? report.handshake?.rollout?.energy_drift).toFixed(4)
                  : '—'}
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
