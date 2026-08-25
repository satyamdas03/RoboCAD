import { useEffect, useState } from 'react'
import { runFitCheck } from '../api.js'

export default function ToleranceReport({ designId, designs = [] }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [otherId, setOtherId] = useState('')
  const [name, setName] = useState('fit_check')

  useEffect(() => {
    setReport(null)
    setError(null)
  }, [designId])

  async function handleRun() {
    if (!designId || !otherId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await runFitCheck(designId, { otherDesignId: otherId, name })
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  const others = designs.filter((d) => d.id !== designId)

  return (
    <section className="kp-panel" aria-labelledby="tol-heading">
      <div className="kp-panel-header">
        <h3 id="tol-heading" className="kp-panel-title">Tolerance / Fit Check</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Compare with design</label>
        <select
          className="kp-input"
          value={otherId}
          onChange={(e) => setOtherId(e.target.value)}
          disabled={loading}
        >
          <option value="">Select a design…</option>
          {others.map((d) => (
            <option key={d.id} value={d.id}>
              #{d.id.slice(0, 8)} — {d.prompt?.slice(0, 40) || 'Untitled'}
            </option>
          ))}
        </select>

        <label className="kp-label">Check name</label>
        <input
          className="kp-input"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={loading}
        />

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleRun}
          disabled={!otherId || loading}
        >
          {loading ? 'Running…' : 'Run fit check'}
        </button>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Classification</span>
            <span
              className={`kp-badge ${
                report.classification === 'clearance'
                  ? 'kp-badge-success'
                  : report.classification === 'interference'
                  ? 'kp-badge-error'
                  : 'kp-badge-warning'
              }`}
            >
              {report.classification}
            </span>
          </div>

          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Min clearance</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.min_clearance_mm.toFixed(3)} mm
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Max clearance</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.max_clearance_mm.toFixed(3)} mm
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Mean clearance</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.mean_clearance_mm.toFixed(3)} mm
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Interference vol</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.interference_volume_mm3 != null ? report.interference_volume_mm3.toFixed(3) + ' mm³' : '—'}
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
