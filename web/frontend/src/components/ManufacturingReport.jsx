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
    <section className="rc-panel" aria-labelledby="mfg-heading">
      <h3 id="mfg-heading" className="rc-panel-title">Manufacturing Report</h3>

      {loading && <p className="rc-text-muted">Analyzing…</p>}
      {error && <div className="rc-alert rc-alert-error rc-mt-2">{error}</div>}

      {report && (
        <div className="rc-flex-col rc-gap-3">
          <div className="rc-flex rc-flex-wrap rc-gap-4 rc-text-muted">
            {report.bounds_mm && (
              <span>
                <strong className="rc-text-muted">Bounds:</strong>{' '}
                {report.bounds_mm.map((v) => v.toFixed(1)).join(' × ')} mm
              </span>
            )}
            {report.volume_cm3 != null && (
              <span>
                <strong>Volume:</strong> {report.volume_cm3.toFixed(2)} cm³
              </span>
            )}
            {report.surface_area_cm2 != null && (
              <span>
                <strong>Surface area:</strong> {report.surface_area_cm2.toFixed(2)} cm²
              </span>
            )}
            {report.estimated_print_time_min != null && (
              <span>
                <strong>Est. print time:</strong> {report.estimated_print_time_min.toFixed(1)} min
              </span>
            )}
          </div>

          {report.overhang_ratio > 0 && (
            <div className="rc-alert rc-alert-warning">
              <strong>Overhang:</strong> {Math.round(report.overhang_ratio * 100)}% of surface area — supports likely needed.
            </div>
          )}

          {report.min_hole_diameter_mm && report.min_hole_diameter_mm < 2.0 && (
            <div className="rc-alert rc-alert-warning">
              <strong>Small hole:</strong> ~{report.min_hole_diameter_mm.toFixed(2)} mm — verify fastener clearance.
            </div>
          )}

          {report.issues?.length > 0 && (
            <ul className="rc-list rc-text-muted">
              {report.issues.map((issue, i) => (
                <li key={i} className="rc-tag">{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
