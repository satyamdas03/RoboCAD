import { useEffect, useRef, useState } from 'react'

export default function ParameterList({ parameters, selectedParameter, onRegenerate, loading, nudge }) {
  const [edits, setEdits] = useState({})
  const inputRefs = useRef({})

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

  useEffect(() => {
    if (!selectedParameter || !inputRefs.current[selectedParameter]) return
    const input = inputRefs.current[selectedParameter]
    input.scrollIntoView({ behavior: 'smooth', block: 'center' })
    input.focus()
    input.select()
  }, [selectedParameter])

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
    <section className="rc-panel" aria-labelledby="parameters-heading">
      <div className="rc-panel-header">
        <h3 id="parameters-heading" className="rc-panel-title">Parameters</h3>
        {selectedParameter && <span className="rc-badge rc-badge-accent">Selected: {selectedParameter}</span>}
      </div>
      <p className="rc-panel-subtitle">
        Edit values and regenerate, or click a face in the viewer to select its parameter.
      </p>

      <div style={{ overflowX: 'auto' }}>
        <table className="rc-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Unit</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {parameters.map((p) => (
              <tr key={p.name} className={selectedParameter === p.name ? 'selected' : ''}>
                <td className="rc-mono">{p.name}</td>
                <td>
                  <input
                    ref={(el) => { inputRefs.current[p.name] = el }}
                    className="rc-input"
                    type="number"
                    value={edits[p.name] ?? p.value}
                    onChange={(e) => handleChange(p.name, e.target.value)}
                    disabled={loading}
                    style={{ width: '100px' }}
                  />
                </td>
                <td className="rc-text-muted">{p.unit || 'mm'}</td>
                <td className="rc-text-muted">{p.description || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        onClick={handleRegenerate}
        disabled={loading || !hasChanges}
        className="rc-button rc-button-primary rc-mt-3"
      >
        {loading ? 'Regenerating…' : 'Regenerate from parameters'}
      </button>
    </section>
  )
}
