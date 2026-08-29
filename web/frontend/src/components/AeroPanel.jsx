import { useEffect, useState } from 'react'
import { runAeroAnalysis, getAeroReport, exportCFDMesh, exportUrl } from '../api.js'

const NACA_CODES = ['0006', '0009', '0012', '0015', '0021', '2412', '2415', '4412', '6412']

export default function AeroPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [naca, setNaca] = useState('0012')
  const [angleOfAttack, setAngleOfAttack] = useState(5)
  const [flowVelocity, setFlowVelocity] = useState(10)
  const [cfdLoading, setCfdLoading] = useState(false)
  const [cfdReport, setCfdReport] = useState(null)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setCfdReport(null)
    setError(null)
    setLoading(true)
    getAeroReport(designId)
      .then((data) => setReport(data.report))
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }, [designId])

  async function handleRun() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await runAeroAnalysis(designId, {
        naca,
        angleOfAttackDeg: angleOfAttack,
        flowVelocityMs: flowVelocity,
      })
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleExportCFD() {
    if (!designId) return
    setCfdLoading(true)
    setError(null)
    try {
      const data = await exportCFDMesh(designId, {
        solver: 'su2_stub',
        angleOfAttackDeg: angleOfAttack,
        flowVelocityMs: flowVelocity,
        characteristicLengthM: 0.1,
      })
      setCfdReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setCfdLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="aero-heading">
      <div className="kp-panel-header">
        <h3 id="aero-heading" className="kp-panel-title">Aero / CFD</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">NACA airfoil</label>
        <select
          className="kp-input"
          value={naca}
          onChange={(e) => setNaca(e.target.value)}
          disabled={loading}
        >
          {NACA_CODES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <label className="kp-label">Angle of attack (°)</label>
        <input
          className="kp-input"
          type="number"
          min={-20}
          max={20}
          step={0.5}
          value={angleOfAttack}
          onChange={(e) => setAngleOfAttack(Number(e.target.value))}
          disabled={loading}
        />

        <label className="kp-label">Flow velocity (m/s)</label>
        <input
          className="kp-input"
          type="number"
          min={0.1}
          step={0.5}
          value={flowVelocity}
          onChange={(e) => setFlowVelocity(Number(e.target.value))}
          disabled={loading}
        />

        <div className="kp-flex kp-gap-2">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleRun}
            disabled={loading}
            style={{ flex: 1 }}
          >
            {loading ? 'Running…' : 'Run aero'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleExportCFD}
            disabled={cfdLoading}
            style={{ flex: 1 }}
          >
            {cfdLoading ? 'Exporting…' : 'Export CFD mesh'}
          </button>
        </div>
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
              <span className="kp-label">Lift coefficient</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.lift_coefficient != null ? report.lift_coefficient.toFixed(3) : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Drag coefficient</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.drag_coefficient != null ? report.drag_coefficient.toFixed(4) : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">L/D</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.lift_to_drag_ratio != null ? report.lift_to_drag_ratio.toFixed(2) : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Reference area</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.reference_area_mm2 != null ? report.reference_area_mm2.toFixed(1) + ' mm²' : '—'}
              </span>
            </div>
          </div>

          {report.stall_warning && (
            <div className="kp-alert kp-alert-warning" style={{ fontSize: '0.8rem' }}>
              Stall warning: angle of attack exceeds thin-airfoil stall estimate.
            </div>
          )}

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

      {cfdReport && (
        <div className="kp-flex-col kp-gap-2 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">CFD mesh</span>
            <span className={`kp-badge ${cfdReport.success ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {cfdReport.success ? 'Exported' : 'Failed'}
            </span>
          </div>
          {cfdReport.success && cfdReport.mesh_path && (
            <a
              href={exportUrl(`/exports/${designId}/cfd/surface_mesh.stl`)}
              download
              className="kp-button kp-button-secondary"
              style={{ width: 'fit-content' }}
            >
              Download surface_mesh.stl
            </a>
          )}
          {cfdReport.success && cfdReport.solver === 'su2_stub' && (
            <a
              href={exportUrl(`/exports/${designId}/cfd/config.cfg`)}
              download
              className="kp-button kp-button-secondary"
              style={{ width: 'fit-content' }}
            >
              Download SU2 config
            </a>
          )}
        </div>
      )}
    </section>
  )
}
