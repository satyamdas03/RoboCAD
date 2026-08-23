import { useEffect, useState } from 'react'
import { getManufacturingReport } from '../api.js'

export default function ManufacturingReport({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    getManufacturingReport(designId)
      .then((data) => setReport(data.report))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [designId])

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="mfg-heading">
      <div className="kp-panel-header">
        <h3 id="mfg-heading" className="kp-panel-title">Manufacturing Report</h3>
      </div>

      {loading && <p className="kp-text-muted kp-small">Analyzing…</p>}
      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3">
          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Bounds</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.bounds_mm ? report.bounds_mm.map((v) => v.toFixed(1)).join(' × ') + ' mm' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Volume</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.volume_cm3 != null ? report.volume_cm3.toFixed(2) + ' cm³' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Surface area</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.surface_area_cm2 != null ? report.surface_area_cm2.toFixed(2) + ' cm²' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Est. print time</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.estimated_print_time_min != null ? report.estimated_print_time_min.toFixed(1) + ' min' : '—'}
              </span>
            </div>
          </div>

          {report.overhang_ratio > 0 && (
            <div className="kp-flex-col kp-gap-1">
              <div className="kp-flex kp-justify-between">
                <span className="kp-label">Overhang ratio</span>
                <span className="kp-mono">{Math.round(report.overhang_ratio * 100)}%</span>
              </div>
              <div style={{ height: '6px', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${Math.min(report.overhang_ratio * 100, 100)}%`,
                    height: '100%',
                    background: report.overhang_ratio > 0.25 ? 'var(--kp-warning)' : 'var(--kp-primary-container)',
                    transition: 'width 250ms ease-out',
                  }}
                />
              </div>
            </div>
          )}

          {report.min_hole_diameter_mm && (
            <div className="kp-flex kp-justify-between kp-align-center">
              <span className="kp-label">Min hole diameter</span>
              <span className={`kp-badge ${report.min_hole_diameter_mm < 2.0 ? 'kp-badge-warning' : 'kp-badge-success'}`}>
                ~{report.min_hole_diameter_mm.toFixed(2)} mm
              </span>
            </div>
          )}

          {report.issues?.length > 0 && (
            <ul className="kp-list">
              {report.issues.map((issue, i) => (
                <li key={i} className="kp-tag" style={{ width: 'fit-content' }}>
                  {typeof issue === 'string' ? issue : issue.message || JSON.stringify(issue)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
