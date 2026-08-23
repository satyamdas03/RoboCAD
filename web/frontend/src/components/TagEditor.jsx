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
    <section className="rc-panel" aria-labelledby="tags-heading">
      <h3 id="tags-heading" className="rc-panel-title">Tags</h3>
      <p className="rc-panel-subtitle">Organize this design for search and remix.</p>

      <form onSubmit={handleSubmit}>
        <div className="rc-field">
          <label htmlFor="tags" className="rc-label">Tags (comma separated)</label>
          <input
            id="tags"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="chassis, base-plate, nema17"
            className="rc-input"
          />
        </div>
        <button type="submit" className="rc-button rc-mt-3">Save tags</button>
      </form>

      {tags.length > 0 && (
        <div className="rc-flex rc-gap-1 rc-mt-3 rc-flex-wrap">
          {tags.map((t) => (
            <span key={t} className="rc-tag">{t}</span>
          ))}
        </div>
      )}
    </section>
  )
}
