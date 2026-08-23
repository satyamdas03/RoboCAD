import { useEffect, useState } from 'react'

const SUGGESTIONS = [
  'A 120 mm x 80 mm x 3 mm base plate with four M3 holes on a 100 mm x 60 mm grid.',
  'A NEMA-17 motor mount bracket with two M3 holes and a 22 mm motor boss.',
  'A wheel hub with a 6 mm D-shaft bore and four M3 holes on a 30 mm PCD.',
]

export default function PromptInput({ onGenerate, loading, seedPrompt }) {
  const [prompt, setPrompt] = useState('')
  const [maxRetries, setMaxRetries] = useState(2)
  const [model, setModel] = useState('')

  useEffect(() => {
    if (seedPrompt) {
      setPrompt(seedPrompt)
    }
  }, [seedPrompt])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    onGenerate({ prompt: prompt.trim(), max_retries: maxRetries, model: model || null })
  }

  return (
    <section className="rc-panel" aria-labelledby="prompt-heading">
      <div className="rc-panel-header">
        <h2 id="prompt-heading" className="rc-panel-title">Specimen prompt</h2>
        <span className="rc-badge rc-badge-accent">{loading ? 'Running…' : 'Ready'}</span>
      </div>
      <p className="rc-panel-subtitle">
        Describe the robot part in plain language. RoboCAD writes parametric build123d code and validates the geometry.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="rc-field rc-mt-2">
          <label htmlFor="prompt" className="rc-label">Part description</label>
          <textarea
            id="prompt"
            className="rc-textarea"
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes..."
            disabled={loading}
          />
        </div>

        <div className="rc-flex rc-align-center rc-gap-4 rc-mt-3 rc-flex-wrap">
          <div className="rc-field" style={{ minWidth: '160px', flex: '1 1 160px' }}>
            <label htmlFor="retries" className="rc-label">Retries: {maxRetries}</label>
            <input
              id="retries"
              className="rc-range"
              type="range"
              min={0}
              max={5}
              value={maxRetries}
              onChange={(e) => setMaxRetries(Number(e.target.value))}
              disabled={loading}
            />
          </div>

          <div className="rc-field" style={{ minWidth: '180px', flex: '1 1 180px' }}>
            <label htmlFor="model" className="rc-label">Model override</label>
            <input
              id="model"
              className="rc-input"
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="default"
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            disabled={loading || !prompt.trim()}
            className="rc-button rc-button-primary rc-mt-3"
            style={{ marginLeft: 'auto', minWidth: '140px' }}
          >
            {loading ? 'Generating…' : 'Generate'}
          </button>
        </div>
      </form>

      <div className="rc-flex rc-align-center rc-gap-2 rc-mt-3 rc-flex-wrap">
        <span className="rc-small rc-text-muted">Try:</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setPrompt(s)}
            disabled={loading}
            className="rc-button rc-button-small rc-button-ghost"
          >
            {s.length > 55 ? s.slice(0, 55) + '…' : s}
          </button>
        ))}
      </div>
    </section>
  )
}
