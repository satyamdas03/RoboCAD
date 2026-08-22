import { useEffect, useRef, useState } from 'react'

export default function ParameterList({ parameters, selectedParameter, onRegenerate, loading, nudge }) {
  const [edits, setEdits] = useState({})
  const inputRefs = useRef({})

  // Apply a nudge from the viewer (Ctrl-drag) to the selected parameter.
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

  // Scroll to and focus the selected parameter when it changes.
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
    <div className="panel">
      <h3>Parameters</h3>
      <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '-0.5rem' }}>
        Edit values and click Regenerate, or click a face in the viewer to select its parameter.
      </p>
      <table style={{ width: '100%', fontSize: '0.9rem' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>Name</th>
            <th style={{ textAlign: 'left' }}>Value</th>
            <th style={{ textAlign: 'left' }}>Unit</th>
            <th style={{ textAlign: 'left' }}>Description</th>
          </tr>
        </thead>
        <tbody>
          {parameters.map((p) => (
            <tr key={p.name} style={{ background: selectedParameter === p.name ? '#fffbeb' : undefined }}>
              <td><code>{p.name}</code></td>
              <td>
                <input
                  ref={(el) => { inputRefs.current[p.name] = el }}
                  type="number"
                  value={edits[p.name] ?? p.value}
                  onChange={(e) => handleChange(p.name, e.target.value)}
                  disabled={loading}
                  style={{ width: '80px' }}
                />
              </td>
              <td>{p.unit || 'mm'}</td>
              <td>{p.description || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={handleRegenerate}
        disabled={loading || !hasChanges}
        style={{ marginTop: '0.5rem' }}
      >
        {loading ? 'Regenerating...' : 'Regenerate from parameters'}
      </button>
    </div>
  )
}
