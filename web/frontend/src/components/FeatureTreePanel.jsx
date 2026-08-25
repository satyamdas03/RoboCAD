import { useEffect, useState } from 'react'
import { loadFeatureTree, regenerateFromFeatureTree } from '../api.js'

export default function FeatureTreePanel({ designId, parameters, onRegenerate, loading }) {
  const [tree, setTree] = useState(null)
  const [error, setError] = useState(null)
  const [edits, setEdits] = useState({})

  useEffect(() => {
    if (!designId) {
      setTree(null)
      setEdits({})
      return
    }
    loadFeatureTree(designId)
      .then((data) => {
        setTree(data.feature_tree)
        setEdits({})
      })
      .catch((err) => {
        setError(err.message)
        setTree(null)
      })
  }, [designId])

  useEffect(() => {
    const next = {}
    for (const p of parameters || []) {
      next[p.name] = String(p.value)
    }
    setEdits(next)
  }, [parameters])

  if (!designId) return null
  if (error) return null
  if (!tree) {
    return (
      <section className="kp-panel" aria-labelledby="feature-tree-heading">
        <div className="kp-panel-header">
          <h3 id="feature-tree-heading" className="kp-panel-title">Feature tree</h3>
        </div>
        <p className="kp-text-muted kp-small">No feature tree available for this design.</p>
      </section>
    )
  }

  const handleChange = (name, raw) => {
    setEdits((prev) => ({ ...prev, [name]: raw }))
  }

  const handleRegenerate = () => {
    const updates = {}
    for (const p of parameters || []) {
      const raw = edits[p.name]
      if (raw !== undefined && raw !== '' && raw !== String(p.value)) {
        const num = Number(raw)
        if (!Number.isNaN(num)) {
          updates[p.name] = num
        }
      }
    }
    if (Object.keys(updates).length > 0) {
      onRegenerate(updates)
    }
  }

  const hasChanges = parameters?.some((p) => String(edits[p.name]) !== String(p.value)) ?? false

  return (
    <section className="kp-panel" aria-labelledby="feature-tree-heading">
      <div className="kp-panel-header">
        <h3 id="feature-tree-heading" className="kp-panel-title">Feature tree</h3>
        <span className="kp-badge kp-badge-accent">{tree.parts?.length || 0} part(s)</span>
      </div>
      <p className="kp-panel-subtitle">
        Edit parameters and regenerate directly from the structured feature tree.
      </p>

      <div style={{ overflowX: 'auto' }}>
        <table className="kp-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Unit</th>
            </tr>
          </thead>
          <tbody>
            {parameters?.map((p) => {
              const isChanged = String(edits[p.name]) !== String(p.value)
              return (
                <tr key={p.name} className={isChanged ? 'changed' : ''}>
                  <td className="kp-mono">{p.name}</td>
                  <td>
                    <input
                      className="kp-input kp-mono"
                      type="number"
                      value={edits[p.name] ?? p.value}
                      onChange={(e) => handleChange(p.name, e.target.value)}
                      disabled={loading}
                      style={{ width: '120px' }}
                    />
                  </td>
                  <td className="kp-text-muted kp-mono">{p.unit || 'mm'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <button
        onClick={handleRegenerate}
        disabled={loading || !hasChanges}
        className="kp-button kp-button-primary kp-mt-3"
      >
        {loading ? 'Regenerating…' : 'Regenerate from feature tree'}
      </button>
    </section>
  )
}
