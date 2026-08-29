import { useEffect, useState } from 'react'
import { getAssemblyCollision } from '../api.js'

export default function AssemblyCollisionPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!designId) {
      setReport(null)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    getAssemblyCollision(designId)
      .then((data) => setReport(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [designId])

  if (!designId) return null
  if (loading) {
    return (
      <section className="kp-panel" aria-labelledby="collision-heading">
        <div className="kp-panel-header">
          <h3 id="collision-heading" className="kp-panel-title">Assembly collision</h3>
        </div>
        <p className="kp-text-muted kp-small">Running pairwise clearance checks…</p>
      </section>
    )
  }
  if (error) {
    return (
      <section className="kp-panel" aria-labelledby="collision-heading">
        <div className="kp-panel-header">
          <h3 id="collision-heading" className="kp-panel-title">Assembly collision</h3>
        </div>
        <p className="kp-text-error kp-small">{error}</p>
      </section>
    )
  }
  if (!report?.pairs?.length) {
    return (
      <section className="kp-panel" aria-labelledby="collision-heading">
        <div className="kp-panel-header">
          <h3 id="collision-heading" className="kp-panel-title">Assembly collision</h3>
        </div>
        <p className="kp-text-muted kp-small">No collision data available.</p>
      </section>
    )
  }

  const worst = report.pairs.reduce((acc, p) =>
    p.min_clearance_mm < acc.min_clearance_mm ? p : acc, report.pairs[0])

  return (
    <section className="kp-panel" aria-labelledby="collision-heading">
      <div className="kp-panel-header">
        <h3 id="collision-heading" className="kp-panel-title">Assembly collision</h3>
        <span className={`kp-badge ${worst.classification === 'interference' ? 'kp-badge-error' : 'kp-badge-success'}`}>
          {worst.classification === 'interference' ? 'Interference' : 'OK'}
        </span>
      </div>
      <p className="kp-panel-subtitle">Pairwise clearance between placed instances.</p>

      <ul className="kp-mono kp-small" style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: '14rem', overflow: 'auto' }}>
        {report.pairs.map((p, idx) => (
          <li
            key={idx}
            className="kp-flex kp-justify-between"
            style={{ borderBottom: '1px solid var(--kp-outline-variant)', padding: '0.25rem 0' }}
          >
            <span>{p.instance_a} ↔ {p.instance_b}</span>
            <span className={p.classification === 'interference' ? 'kp-text-error' : 'kp-text-primary'}>
              {p.min_clearance_mm.toFixed(3)} mm
            </span>
          </li>
        ))}
      </ul>

      {report.overconstrained && (
        <div className="kp-badge kp-badge-error" style={{ marginTop: '0.5rem' }}>
          Overconstrained assembly
        </div>
      )}
    </section>
  )
}
