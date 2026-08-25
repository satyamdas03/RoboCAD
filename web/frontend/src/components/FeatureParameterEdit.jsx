import { useEffect, useState } from 'react'

export default function FeatureParameterEdit({ parameters, selectedParameter, onRegenerate, loading, nudge }) {
  const [edits, setEdits] = useState({})

  useEffect(() => {
    if (nudge == null || selectedParameter == null || !parameters) return
    const param = parameters.find((p) => p.name === selectedParameter)
    if (!param) return
    const currentRaw = edits[selectedParameter]
    const currentValue = currentRaw !== undefined && currentRaw !== '' ? Number(currentRaw) : param.value
    if (Number.isNaN(currentValue)) return
    const newValue = currentValue + nudge
    setEdits((prev) => ({ ...prev, [selectedParameter]: String(Number(newValue.toFixed(4))) }))
  }, [nudge, selectedParameter, parameters])

  if (!parameters || parameters.length === 0) return null

  const handleChange = (name, raw) => {
    setEdits((prev) => ({ ...prev, [name]: raw }))
  }

  const handleRegenerate = () => {
    const updates = {}
    for (const p of parameters) {
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

  const hasChanges = Object.keys(edits).some((name) => {
    const original = parameters.find((p) => p.name === name)?.value
    return String(edits[name]) !== String(original)
  })

  return (
    <section className="kp-panel" aria-labelledby="feature-params-heading">
      <div className="kp-panel-header">
        <h3 id="feature-params-heading" className="kp-panel-title">Feature parameters</h3>
        {selectedParameter && (
          <span className="kp-badge kp-badge-accent">Selected: {selectedParameter}</span>
        )}
      </div>
      <p className="kp-panel-subtitle">
        Edit parameter values and regenerate from the feature tree.
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
            {parameters.map((p) => {
              const isSelected = selectedParameter === p.name
              const isChanged = String(edits[p.name]) !== String(p.value) && edits[p.name] !== undefined
              return (
                <tr
                  key={p.name}
                  className={`${isSelected ? 'selected' : ''} ${isChanged ? 'changed' : ''}`}
                >
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
