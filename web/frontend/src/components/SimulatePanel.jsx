import { useEffect, useState } from 'react'
import { simulateDesign, getSimulationReport, getBundleUrl, exportUrl } from '../api.js'

const MATERIALS = ['PLA', 'PETG', 'ABS', 'aluminum', 'steel']

export default function SimulatePanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [material, setMaterial] = useState('PLA')
  const [tolerance, setTolerance] = useState(0.1)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setError(null)
    setLoading(true)
    getSimulationReport(designId)
      .then((data) => setReport(data))
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }, [designId])

  async function handleSimulate() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await simulateDesign(designId, { material, tolerance })
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const totalMass = report?.manifest?.parts?.reduce((sum, p) => sum + (p.inertial?.mass_kg || 0), 0)
  const bundleUrl = report?.bundle_url ? exportUrl(report.bundle_url) : null

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="sim-heading">
      <div className="kp-panel-header">
        <h3 id="sim-heading" className="kp-panel-title">Simulation / GEDA Bridge</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
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

        <label className="kp-label">Mesh tolerance (mm)</label>
        <input
          className="kp-input"
          type="number"
          min={0.01}
          max={1.0}
          step={0.01}
          value={tolerance}
          onChange={(e) => setTolerance(Number(e.target.value))}
          disabled={loading}
        />

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleSimulate}
          disabled={loading}
        >
          {loading ? 'Building bundle…' : 'Generate simulation bundle'}
        </button>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Bundle status</span>
            <span className={`kp-badge ${report.valid ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.valid ? 'Verified' : 'Failed'}
            </span>
          </div>

          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Bodies</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.manifest?.parts?.length ?? '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Total mass</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {totalMass != null ? totalMass.toFixed(4) + ' kg' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Watertight</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.verification?.all_watertight ? 'Yes' : 'No'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Inertia valid</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.verification?.all_inertia_positive_definite ? 'Yes' : 'No'}
              </span>
            </div>
          </div>

          {report.verification?.errors?.length > 0 && (
            <ul className="kp-list">
              {report.verification.errors.map((err, i) => (
                <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>
                  {err}
                </li>
              ))}
            </ul>
          )}

          {bundleUrl && (
            <a
              href={bundleUrl}
              download
              className="kp-button kp-button-secondary"
              style={{ width: 'fit-content' }}
            >
              Download bundle (.zip)
            </a>
          )}
        </div>
      )}
    </section>
  )
}
