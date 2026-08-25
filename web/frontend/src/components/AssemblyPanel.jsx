import { useEffect, useState } from 'react'
import { loadAssembly } from '../api.js'

export default function AssemblyPanel({ designId }) {
  const [assembly, setAssembly] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!designId) {
      setAssembly(null)
      return
    }
    loadAssembly(designId)
      .then((data) => setAssembly(data.assembly))
      .catch((err) => setError(err.message))
  }, [designId])

  if (!designId) return null
  if (error) return null
  if (!assembly) {
    return (
      <section className="kp-panel" aria-labelledby="assembly-heading">
        <div className="kp-panel-header">
          <h3 id="assembly-heading" className="kp-panel-title">Assembly</h3>
        </div>
        <p className="kp-text-muted kp-small">No assembly data for this design.</p>
      </section>
    )
  }

  return (
    <section className="kp-panel" aria-labelledby="assembly-heading">
      <div className="kp-panel-header">
        <h3 id="assembly-heading" className="kp-panel-title">Assembly</h3>
        <span className="kp-badge kp-badge-accent">
          {assembly.instances?.length || 0} instance(s)
        </span>
      </div>
      <p className="kp-panel-subtitle">Part instances and mates in this design.</p>

      <div className="kp-flex-col kp-gap-2" style={{ fontSize: '0.8rem' }}>
        <div>
          <span className="kp-text-muted">Instances</span>
          <ul className="kp-mono kp-mt-1" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {assembly.instances?.map((inst) => (
              <li key={inst.id} className="kp-flex kp-justify-between" style={{ borderBottom: '1px solid var(--kp-outline-variant)', padding: '0.25rem 0' }}>
                <span>{inst.id}</span>
                <span className="kp-text-primary">{inst.part_id}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <span className="kp-text-muted">Mates</span>
          <ul className="kp-mono kp-mt-1" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {(assembly.mates || []).length === 0 && (
              <li className="kp-text-muted kp-small">No mates defined.</li>
            )}
            {assembly.mates?.map((mate) => (
              <li key={mate.id} className="kp-flex kp-justify-between" style={{ borderBottom: '1px solid var(--kp-outline-variant)', padding: '0.25rem 0' }}>
                <span>{mate.id}</span>
                <span className="kp-text-accent">{mate.type}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
