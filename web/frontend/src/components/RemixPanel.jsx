import { useState } from 'react'

export default function RemixPanel({ designId, onRemix, loading }) {
  const [prompt, setPrompt] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    onRemix({ prompt: prompt.trim(), max_retries: 2, model: null })
  }

  return (
    <div className="panel">
      <h3>Remix</h3>
      <p style={{ fontSize: '0.85rem', color: '#666' }}>
        Generate a new design based on Design #{designId.slice(0, 8)}.
      </p>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Make it thicker and add two more holes"
          style={{ width: '100%' }}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !prompt.trim()} style={{ marginTop: '0.5rem' }}>
          {loading ? 'Remixing...' : 'Remix'}
        </button>
      </form>
    </div>
  )
}
