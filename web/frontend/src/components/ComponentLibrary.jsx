import { useState } from 'react'
import catalog from './standard_components.json'

export default function ComponentLibrary({ onPrompt, loading }) {
  const [expanded, setExpanded] = useState({})

  const toggleCategory = (name) => {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }))
  }

  return (
    <div className="panel">
      <h3>Component Library</h3>
      <p style={{ fontSize: '0.85rem', color: '#666' }}>
        Click a component to load its seed prompt into the generator.
      </p>
      {catalog.categories.map((category) => (
        <div key={category.name} style={{ marginBottom: '0.5rem' }}>
          <button
            type="button"
            onClick={() => toggleCategory(category.name)}
            style={{
              width: '100%',
              textAlign: 'left',
              background: '#f1f5f9',
              border: '1px solid #cbd5e1',
              borderRadius: '4px',
              padding: '0.4rem 0.6rem',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {expanded[category.name] ? '▼' : '▶'} {category.name}
          </button>
          {expanded[category.name] && (
            <ul style={{ listStyle: 'none', padding: 0, margin: '0.25rem 0 0' }}>
              {category.items.map((item) => (
                <li key={item.id} style={{ marginBottom: '0.25rem' }}>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => onPrompt(item.prompt)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background: '#fff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '4px',
                      padding: '0.4rem 0.6rem',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 500, fontSize: '0.9rem' }}>{item.name}</div>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.15rem' }}>
                      {item.description}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#0ea5e9', marginTop: '0.15rem' }}>
                      {item.tags.join(', ')}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  )
}
