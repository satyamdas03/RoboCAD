import { useEffect, useState } from 'react'
import { getAssemblyPoses } from '../api.js'

export default function AssemblyReplayPanel({ designId }) {
  const [poses, setPoses] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!designId) {
      setPoses(null)
      setError(null)
      setFrame(0)
      setPlaying(false)
      return
    }
    setLoading(true)
    setError(null)
    getAssemblyPoses(designId, { samplesPerJoint: 8 })
      .then((data) => {
        setPoses(data)
        setFrame(0)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [designId])

  useEffect(() => {
    if (!playing || !poses?.frames?.length) return
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % poses.frames.length)
    }, 600)
    return () => clearInterval(id)
  }, [playing, poses])

  if (!designId) return null
  if (loading) {
    return (
      <section className="kp-panel" aria-labelledby="replay-heading">
        <div className="kp-panel-header">
          <h3 id="replay-heading" className="kp-panel-title">Assembly replay</h3>
        </div>
        <p className="kp-text-muted kp-small">Loading range-of-motion poses…</p>
      </section>
    )
  }
  if (error) {
    return (
      <section className="kp-panel" aria-labelledby="replay-heading">
        <div className="kp-panel-header">
          <h3 id="replay-heading" className="kp-panel-title">Assembly replay</h3>
        </div>
        <p className="kp-text-error kp-small">{error}</p>
      </section>
    )
  }
  if (!poses?.frames?.length) {
    return (
      <section className="kp-panel" aria-labelledby="replay-heading">
        <div className="kp-panel-header">
          <h3 id="replay-heading" className="kp-panel-title">Assembly replay</h3>
        </div>
        <p className="kp-text-muted kp-small">No articulated poses available for this design.</p>
      </section>
    )
  }

  const current = poses.frames[frame]
  const total = poses.frames.length

  return (
    <section className="kp-panel" aria-labelledby="replay-heading">
      <div className="kp-panel-header">
        <h3 id="replay-heading" className="kp-panel-title">Assembly replay</h3>
        <span className="kp-badge kp-badge-accent">
          {poses.joint_count || 0} joint(s)
        </span>
      </div>
      <p className="kp-panel-subtitle">
        Lightweight range-of-motion preview ({frame + 1}/{total}).
      </p>

      <div className="kp-flex kp-gap-2 kp-align-center" style={{ marginBottom: '0.75rem' }}>
        <button
          type="button"
          className="kp-button kp-button-small"
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <input
          type="range"
          min={0}
          max={total - 1}
          value={frame}
          onChange={(e) => setFrame(Number(e.target.value))}
          style={{ flex: 1 }}
          aria-label="Pose frame"
        />
      </div>

      <div className="kp-mono kp-small" style={{ maxHeight: '12rem', overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--kp-outline-variant)' }}>
              <th>Instance</th>
              <th>Position (mm)</th>
              <th>Rotation (°)</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(current.transforms || {}).map(([id, t]) => {
              const pos = t.position || [0, 0, 0]
              const rot = t.rotation_deg || [0, 0, 0]
              return (
                <tr key={id} style={{ borderBottom: '1px solid var(--kp-outline-variant)' }}>
                  <td>{id}</td>
                  <td>{pos.map((n) => n.toFixed(1)).join(', ')}</td>
                  <td>{rot.map((n) => n.toFixed(1)).join(', ')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {poses.overconstrained && (
        <div className="kp-badge kp-badge-error" style={{ marginTop: '0.5rem' }}>
          Overconstrained assembly detected
        </div>
      )}
    </section>
  )
}
