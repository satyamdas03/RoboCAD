import { useState } from 'react'

export default function RemixPanel({ designId, onRemix, loading }) {
  const [prompt, setPrompt] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    onRemix({ prompt: prompt.trim(), max_retries: 2, model: null })
  }

  return (
    <section className="rc-panel" aria-labelledby="remix-heading">
      <h3 id="remix-heading" className="rc-panel-title">Remix</h3>
      <p className="rc-panel-subtitle">
        Generate a new design based on #{designId.slice(0, 8)}.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="rc-field">
          <label htmlFor="remix-prompt" className="rc-label">Variation prompt</label>
          <input
            id="remix-prompt"
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Make it thicker and add two more holes"
            className="rc-input"
            disabled={loading}
          />
        </div>
        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="rc-button rc-button-primary rc-mt-3"
        >
          {loading ? 'Remixing…' : 'Remix'}
        </button>
      </form>
    </section>
  )
}
