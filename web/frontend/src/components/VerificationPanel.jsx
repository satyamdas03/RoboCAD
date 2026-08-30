import { useEffect, useState } from 'react'
import { checkMeshQuality, runVerification } from '../api.js'

const LOAD_CASES = [
  { value: 'static_stress', label: 'Static stress' },
  { value: 'drop_test', label: 'Drop test' },
  { value: 'thermal_expansion', label: 'Thermal expansion' },
  { value: 'fatigue_cycles', label: 'Fatigue cycles' },
  { value: 'fastener_pull_out', label: 'Fastener pull-out' },
  { value: 'wind_tunnel_drag', label: 'Wind-tunnel drag' },
  { value: 'heat_sink_thermal_resistance', label: 'Heat-sink thermal resistance' },
  { value: 'joint_torque_check', label: 'Joint torque check' },
  { value: 'mesh_quality', label: 'Mesh quality' },
  { value: 'assembly_clearance', label: 'Assembly clearance' },
]

const MATERIALS = [
  'PLA',
  'PETG',
  'ABS',
  'Nylon 12',
  'Aluminum 6061',
  'Mild Steel',
  'Copper',
  'Brass',
  'Titanium 6Al-4V',
  'FR4',
  'CopperTrace',
]

export default function VerificationPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [loadCase, setLoadCase] = useState('static_stress')
  const [material, setMaterial] = useState('PLA')
  const [paramJson, setParamJson] = useState('{}')

  useEffect(() => {
    setReport(null)
    setError(null)
  }, [designId, loadCase])

  async function handleRun() {
    if (!designId) return
    let parameters = {}
    try {
      parameters = JSON.parse(paramJson || '{}')
    } catch (err) {
      setError('Parameters JSON is invalid: ' + err.message)
      return
    }
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await runVerification(designId, {
        loadCase,
        materials: { default: material },
        parameters: { ...parameters, material },
      })
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleMeshCheck() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await checkMeshQuality(designId)
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  const isMeshCase = loadCase === 'mesh_quality'

  return (
    <section className="kp-panel" aria-labelledby="verify-heading">
      <div className="kp-panel-header">
        <h3 id="verify-heading" className="kp-panel-title">Multi-physics verification</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Load case</label>
        <select
          className="kp-input"
          value={loadCase}
          onChange={(e) => setLoadCase(e.target.value)}
          disabled={loading}
        >
          {LOAD_CASES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>

        {!isMeshCase && (
          <>
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
          </>
        )}

        <label className="kp-label">Parameters (JSON)</label>
        <textarea
          className="kp-input"
          rows={3}
          value={paramJson}
          onChange={(e) => setParamJson(e.target.value)}
          disabled={loading}
          placeholder='{"load_magnitude_n": 100}'
        />

        <div className="kp-flex kp-gap-2">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleRun}
            disabled={loading}
          >
            {loading ? 'Running…' : 'Run verification'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleMeshCheck}
            disabled={loading}
          >
            Mesh quality
          </button>
        </div>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Status</span>
            <span className={`kp-badge ${report.passed ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.passed ? 'PASS' : 'FAIL'}
            </span>
          </div>

          {report.load_case && (
            <div className="kp-flex kp-justify-between kp-align-center">
              <span className="kp-label">Load case</span>
              <span className="kp-mono" style={{ fontSize: '0.85rem' }}>{report.load_case}</span>
            </div>
          )}

          {report.metrics && Object.keys(report.metrics).length > 0 && (
            <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
              {Object.entries(report.metrics).map(([key, value]) => (
                <div key={key} className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                  <span className="kp-label">{key}</span>
                  <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                    {typeof value === 'number' ? value.toFixed(4) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {report.mesh_report && (
            <div className="kp-flex-col kp-gap-2" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <div className="kp-flex kp-justify-between kp-align-center">
                <span className="kp-label">Mesh suitable for solver</span>
                <span className={`kp-badge ${report.mesh_report.is_suitable_for_solver ? 'kp-badge-success' : 'kp-badge-error'}`}>
                  {report.mesh_report.is_suitable_for_solver ? 'YES' : 'NO'}
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1">
                <span className="kp-label">Issues</span>
                {report.mesh_report.issues?.length > 0 ? (
                  <ul className="kp-list">
                    {report.mesh_report.issues.map((issue, i) => (
                      <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{issue}</li>
                    ))}
                  </ul>
                ) : (
                  <span className="kp-text-muted kp-small">No issues detected.</span>
                )}
              </div>
            </div>
          )}

          {report.failure_modes?.length > 0 && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Failure modes</span>
              <ul className="kp-list">
                {report.failure_modes.map((mode, i) => (
                  <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{mode}</li>
                ))}
              </ul>
            </div>
          )}

          {report.redesign_suggestions?.length > 0 && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Redesign suggestions</span>
              <ul className="kp-list">
                {report.redesign_suggestions.map((s, i) => (
                  <li key={i} className="kp-tag" style={{ width: 'fit-content' }}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {report.errors?.length > 0 && (
            <ul className="kp-list">
              {report.errors.map((err, i) => (
                <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{err}</li>
              ))}
            </ul>
          )}

          {report.warnings?.length > 0 && (
            <ul className="kp-list">
              {report.warnings.map((warn, i) => (
                <li key={i} className="kp-tag kp-badge-warning" style={{ width: 'fit-content' }}>{warn}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
