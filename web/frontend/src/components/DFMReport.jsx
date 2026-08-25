import { useEffect, useState } from 'react'
import { getDFMReport } from '../api.js'

export default function DFMReport({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    getDFMReport(designId)
      .then((data) => setReport(data.report))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [designId])

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="dfm-heading">
      <div className="kp-panel-header">
        <h3 id="dfm-heading" className="kp-panel-title">DFM Report</h3>
      </div>

      {loading && <p className="kp-text-muted kp-small">Analyzing…</p>}
      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Overall</span>
            <span className={`kp-badge ${report.valid ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.valid ? 'PASS' : 'FAIL'}
            </span>
          </div>

          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Min wall</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.min_wall_thickness_mm != null ? report.min_wall_thickness_mm.toFixed(2) + ' mm' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Min hole</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.min_hole_diameter_mm != null ? report.min_hole_diameter_mm.toFixed(2) + ' mm' : '—'}
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
                    background: report.overhang_ratio > 0.05 ? 'var(--kp-warning)' : 'var(--kp-primary-container)',
                    transition: 'width 250ms ease-out',
                  }}
                />
              </div>
            </div>
          )}

          {report.rules?.length > 0 && (
            <ul className="kp-list">
              {report.rules.map((rule, i) => (
                <li
                  key={i}
                  className={`kp-tag ${rule.severity === 'error' ? 'kp-badge-error' : rule.severity === 'warning' ? 'kp-badge-warning' : ''}`}
                  style={{ width: 'fit-content' }}
                >
                  {rule.name}: {rule.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
