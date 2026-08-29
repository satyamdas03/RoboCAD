import { useEffect, useState } from 'react'
import { runThermalAnalysis, getThermalReport } from '../api.js'

export default function ThermalPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [heatFlux, setHeatFlux] = useState(10)
  const [ambientTemp, setAmbientTemp] = useState(25)
  const [convectionCoeff, setConvectionCoeff] = useState(50)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setError(null)
    setLoading(true)
    getThermalReport(designId)
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
      const data = await runThermalAnalysis(designId, {
        heatFluxW: heatFlux,
        ambientTempC: ambientTemp,
        convectionCoefficientWPerM2K: convectionCoeff,
      })
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="thermal-heading">
      <div className="kp-panel-header">
        <h3 id="thermal-heading" className="kp-panel-title">Thermal / Heat Sink</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Heat flux (W)</label>
        <input
          className="kp-input"
          type="number"
          min={0}
          step={1}
          value={heatFlux}
          onChange={(e) => setHeatFlux(Number(e.target.value))}
          disabled={loading}
        />

        <label className="kp-label">Ambient temp (°C)</label>
        <input
          className="kp-input"
          type="number"
          min={-40}
          max={100}
          step={1}
          value={ambientTemp}
          onChange={(e) => setAmbientTemp(Number(e.target.value))}
          disabled={loading}
        />

        <label className="kp-label">Convection coefficient (W/m²·K)</label>
        <input
          className="kp-input"
          type="number"
          min={1}
          step={5}
          value={convectionCoeff}
          onChange={(e) => setConvectionCoeff(Number(e.target.value))}
          disabled={loading}
        />

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? 'Running…' : 'Run thermal check'}
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
              <span className="kp-label">Surface area</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.total_surface_area_mm2 != null ? report.total_surface_area_mm2.toFixed(1) + ' mm²' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Base area</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.base_area_mm2 != null ? report.base_area_mm2.toFixed(1) + ' mm²' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Fins counted</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.fin_count != null ? report.fin_count : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Thermal resistance</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.thermal_resistance_c_per_w != null ? report.thermal_resistance_c_per_w.toFixed(2) + ' °C/W' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Max temp</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.max_temperature_c != null ? report.max_temperature_c.toFixed(1) + ' °C' : '—'}
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
