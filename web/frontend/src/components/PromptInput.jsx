import { useState } from 'react'

const SUGGESTIONS = [
  'A 120 mm x 80 mm x 3 mm base plate with four M3 holes on a 100 mm x 60 mm grid.',
  'A NEMA-17 motor mount bracket with two M3 holes and a 22 mm motor boss.',
  'A wheel hub with a 6 mm D-shaft bore and four M3 holes on a 30 mm PCD.',
]

export default function PromptInput({ onGenerate, loading }) {
  const [prompt, setPrompt] = useState('')
  const [maxRetries, setMaxRetries] = useState(2)
  const [model, setModel] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    onGenerate({ prompt: prompt.trim(), max_retries: maxRetries, model: model || null })
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: '1rem' }}>
      <label htmlFor="prompt">Describe the robot part you want:</label>
      <textarea
        id="prompt"
        rows={4}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="e.g. A 120 mm x 80 mm x 3 mm base plate with four M3 mounting holes..."
        style={{ width: '100%', marginTop: '0.25rem', marginBottom: '0.5rem' }}
        disabled={loading}
      />
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="retries">Retries: {maxRetries}</label>
          <input
            id="retries"
            type="range"
            min={0}
            max={5}
            value={maxRetries}
            onChange={(e) => setMaxRetries(Number(e.target.value))}
            disabled={loading}
          />
        </div>
        <div>
          <label htmlFor="model">Model override:</label>
          <input
            id="model"
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="default"
            style={{ width: '180px' }}
            disabled={loading}
          />
        </div>
        <button type="submit" disabled={loading || !prompt.trim()} style={{ marginLeft: 'auto' }}>
          {loading ? 'Generating...' : 'Generate'}
        </button>
      </div>
      <div style={{ marginTop: '0.75rem' }}>
        <small>Try:{' '}</small>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setPrompt(s)}
            disabled={loading}
            style={{ marginRight: '0.5rem', marginBottom: '0.25rem', fontSize: '0.8rem' }}
          >
            {s.length > 50 ? s.slice(0, 50) + '...' : s}
          </button>
        ))}
      </div>
    </form>
  )
}
