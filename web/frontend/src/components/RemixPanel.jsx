import { useState } from 'react'

export default function RemixPanel({ designId, onRemix, loading }) {
  const [prompt, setPrompt] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    onRemix({ prompt: prompt.trim(), max_retries: 2, model: null })
  }

  return (
    <section className="kp-panel" aria-labelledby="remix-heading">
      <div className="kp-panel-header">
        <h3 id="remix-heading" className="kp-panel-title">Remix</h3>
      </div>
      <p className="kp-panel-subtitle">
        Generate a new design based on #{designId.slice(0, 8)}.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="kp-field">
          <label htmlFor="remix-prompt" className="kp-label">Variation prompt</label>
          <input
            id="remix-prompt"
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Make it thicker and add two more holes"
            className="kp-input"
            disabled={loading}
          />
        </div>
        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="kp-button kp-button-primary kp-mt-3"
        >
          {loading ? 'Remixing…' : 'Remix'}
        </button>
      </form>
    </section>
  )
}
