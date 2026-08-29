import { useEffect, useState } from 'react'
import { runElectronicsAnalysis, getElectronicsReport, exportIDF, exportUrl } from '../api.js'

export default function ElectronicsPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [idfLoading, setIdfLoading] = useState(false)
  const [idfResult, setIdfResult] = useState(null)
  const [boardName, setBoardName] = useState('ROBOCAD_PCB')

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setIdfResult(null)
    setError(null)
    setLoading(true)
    getElectronicsReport(designId)
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
      const data = await runElectronicsAnalysis(designId)
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleExportIDF() {
    if (!designId) return
    setIdfLoading(true)
    setError(null)
    try {
      const data = await exportIDF(designId, { boardName })
      setIdfResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setIdfLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="electronics-heading">
      <div className="kp-panel-header">
        <h3 id="electronics-heading" className="kp-panel-title">Electronics / Mechatronics</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Board name (for IDF export)</label>
        <input
          className="kp-input"
          type="text"
          value={boardName}
          onChange={(e) => setBoardName(e.target.value)}
          disabled={loading || idfLoading}
        />

        <div className="kp-flex kp-gap-2">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleRun}
            disabled={loading}
            style={{ flex: 1 }}
          >
            {loading ? 'Analysing…' : 'Run electronics analysis'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleExportIDF}
            disabled={idfLoading}
            style={{ flex: 1 }}
          >
            {idfLoading ? 'Exporting…' : 'Export IDF'}
          </button>
        </div>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Components placed</span>
            <span className="kp-mono">{report.component_count}</span>
          </div>

          {report.pcb && (
            <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">PCB area</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.pcb.board_area_mm2?.toFixed(1) ?? '—'} mm²
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Thickness</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.pcb.board_thickness_mm?.toFixed(2) ?? '—'} mm
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Mounting holes</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.pcb.mounting_hole_count ?? '—'}
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Layers</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.pcb.layer_count ?? '—'}
                </span>
              </div>
            </div>
          )}

          <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
            <span className="kp-label">Estimated cable run</span>
            <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
              {report.estimated_cable_length_mm?.toFixed(1) ?? '—'} mm
            </span>
          </div>

          {report.warnings?.length > 0 && (
            <ul className="kp-list">
              {report.warnings.map((w, i) => (
                <li key={i} className="kp-tag kp-badge-warning" style={{ width: 'fit-content' }}>
                  {w}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {idfResult && (
        <div className="kp-flex-col kp-gap-2 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">IDF export</span>
            <span className="kp-badge kp-badge-success">Exported</span>
          </div>
          <div className="kp-flex-col kp-gap-1">
            {Object.entries(idfResult.files ?? {}).map(([key, path]) => (
              <a
                key={key}
                href={exportUrl(`/exports/${designId}/${path}`)}
                download
                className="kp-button kp-button-secondary"
                style={{ width: 'fit-content' }}
              >
                Download {key} ({idfResult.download_urls?.[key]?.split('/').pop()})
              </a>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
