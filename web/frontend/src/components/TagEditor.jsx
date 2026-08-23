import { useState } from 'react'

export default function TagEditor({ tags, onUpdate }) {
  const [input, setInput] = useState(tags.join(', '))

  const handleSubmit = (e) => {
    e.preventDefault()
    const newTags = input
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t.length > 0)
    onUpdate(newTags)
  }

  return (
    <section className="kp-panel" aria-labelledby="tags-heading">
      <div className="kp-panel-header">
        <h3 id="tags-heading" className="kp-panel-title">Tags</h3>
      </div>
      <p className="kp-panel-subtitle">Organize this design for search and remix.</p>

      <form onSubmit={handleSubmit}>
        <div className="kp-field">
          <label htmlFor="tags" className="kp-label">Tags (comma separated)</label>
          <input
            id="tags"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="chassis, base-plate, nema17"
            className="kp-input"
          />
        </div>
        <button type="submit" className="kp-button kp-button-primary kp-mt-3">Save tags</button>
      </form>

      {tags.length > 0 && (
        <div className="kp-flex kp-gap-1 kp-mt-3 kp-flex-wrap">
          {tags.map((t) => (
            <span key={t} className="kp-tag">{t}</span>
          ))}
        </div>
      )}
    </section>
  )
}
