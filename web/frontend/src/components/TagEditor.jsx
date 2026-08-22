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
    <div className="panel">
      <h3>Tags</h3>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="chassis, base-plate, nema17"
          style={{ width: '100%' }}
        />
        <button type="submit" style={{ marginTop: '0.5rem' }}>Save tags</button>
      </form>
    </div>
  )
}
