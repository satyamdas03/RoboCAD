import { useEffect, useState } from 'react'
import { runFEA } from '../api.js'

const MATERIALS = ['PLA', 'PETG', 'ABS', 'aluminum', 'steel']
const FACES = ['+x', '-x', '+y', '-y', '+z', '-z']

export default function FEAPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [fixedFace, setFixedFace] = useState('-x')
  const [loadMagnitude, setLoadMagnitude] = useState(100)
  const [material, setMaterial] = useState('PLA')

  useEffect(() => {
    setReport(null)
    setError(null)
  }, [designId])

  async function handleRun() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await runFEA(designId, { fixedFace, loadMagnitudeN: loadMagnitude, material })
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="fea-heading">
      <div className="kp-panel-header">
        <h3 id="fea-heading" className="kp-panel-title">FEA / Stress Check</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Fixed face</label>
        <select
          className="kp-input"
          value={fixedFace}
          onChange={(e) => setFixedFace(e.target.value)}
          disabled={loading}
        >
          {FACES.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>

        <label className="kp-label">Material</label>
        <select
          className="kp-input"
          value={material}
          onChange={(e) => setMaterial(e.target.value)}
          disabled={loading}
        >
          {MATERIALS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        <label className="kp-label">Load (N)</label>
        <input
          className="kp-input"
          type="number"
          min={1}
          step={10}
          value={loadMagnitude}
          onChange={(e) => setLoadMagnitude(Number(e.target.value))}
          disabled={loading}
        />

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? 'Running…' : 'Run analysis'}
        </button>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Status</span>
            <span className={`kp-badge ${report.success ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.success ? 'OK' : 'FAIL'}
            </span>
          </div>

          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Max stress</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.max_stress_mpa != null ? report.max_stress_mpa.toFixed(2) + ' MPa' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Max displacement</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.max_displacement_mm != null ? report.max_displacement_mm.toFixed(3) + ' mm' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Safety factor</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.safety_factor != null ? report.safety_factor.toFixed(2) : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Solver</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.solver || '—'}
              </span>
            </div>
          </div>

          {report.errors?.length > 0 && (
            <ul className="kp-list">
              {report.errors.map((err, i) => (
                <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>
                  {err}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
