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
    <div className="panel">
      <h3>Manufacturing Report</h3>
      {loading && <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Analyzing...</p>}
      {error && <p style={{ color: '#b00000', fontSize: '0.9rem' }}>Error: {error}</p>}
      {report && (
        <div style={{ fontSize: '0.9rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <div><strong>Bounds:</strong> {report.bounds_mm?.map((v) => v.toFixed(1)).join(' × ')} mm</div>
            <div><strong>Volume:</strong> {report.volume_cm3?.toFixed(2)} cm³</div>
            <div><strong>Surface area:</strong> {report.surface_area_cm2?.toFixed(2)} cm²</div>
            <div><strong>Est. print time:</strong> {report.estimated_print_time_min?.toFixed(1)} min</div>
          </div>

          {report.overhang_ratio > 0 && (
            <p style={{ color: '#92400e', background: '#fef3c7', padding: '0.4rem', borderRadius: '4px' }}>
              ⚠️ {Math.round(report.overhang_ratio * 100)}% overhang area — supports likely needed.
            </p>
          )}

          {report.min_hole_diameter_mm && report.min_hole_diameter_mm < 2.0 && (
            <p style={{ color: '#92400e', background: '#fef3c7', padding: '0.4rem', borderRadius: '4px', marginTop: '0.25rem' }}>
              ⚠️ Smallest detected hole ~{report.min_hole_diameter_mm.toFixed(2)} mm — verify clearance.
            </p>
          )}

          {report.issues.length > 0 && (
            <ul style={{ margin: '0.5rem 0', paddingLeft: '1.2rem', color: '#64748b' }}>
              {report.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
