import { useState } from 'react'

export default function ParameterList({ parameters, onRegenerate, loading }) {
  const [edits, setEdits] = useState({})

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
        Edit values and click Regenerate to re-run the build123d code.
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
            <tr key={p.name}>
              <td><code>{p.name}</code></td>
              <td>
                <input
                  type="number"
                  defaultValue={p.value}
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
