import { useState } from 'react'
import catalog from './standard_components.json'

export default function ComponentLibrary({ onPrompt, loading }) {
  const [expanded, setExpanded] = useState(() => {
    const initial = {}
    if (catalog.categories?.[0]) initial[catalog.categories[0].name] = true
    return initial
  })

  const toggleCategory = (name) => {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }))
  }

  return (
    <section className="kp-flex-col" aria-labelledby="library-heading">
      <div className="kp-panel-header" style={{ padding: 'var(--kp-space-2) var(--kp-space-3)', borderBottom: '1px solid var(--kp-border)' }}>
        <h3 id="library-heading" className="kp-panel-title">Component Library</h3>
      </div>
      <p className="kp-panel-subtitle" style={{ padding: '0 var(--kp-space-3)', marginTop: 'var(--kp-space-2)' }}>
        Click a component to load its seed prompt into the generator.
      </p>

      <div className="kp-flex-col kp-gap-2" style={{ padding: 'var(--kp-space-3)' }}>
        {catalog.categories.map((category) => (
          <div key={category.name} className="kp-accordion">
            <button
              type="button"
              onClick={() => toggleCategory(category.name)}
              className="kp-accordion-header"
              aria-expanded={expanded[category.name]}
            >
              <span className="kp-flex kp-align-center kp-gap-2">
                <span>{category.name}</span>
              </span>
              <span aria-hidden="true" className="kp-mono">{expanded[category.name] ? '−' : '+'}</span>
            </button>

            {expanded[category.name] && (
              <div className="kp-accordion-body">
                <ul className="kp-list">
                  {category.items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        disabled={loading}
                        onClick={() => onPrompt(item.prompt)}
                        className="kp-button kp-button-ghost kp-textured"
                        style={{ width: '100%', justifyContent: 'flex-start', textAlign: 'left', padding: 'var(--kp-space-3)' }}
                      >
                        <span className="kp-flex-col kp-gap-1">
                          <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{item.name}</span>
                          <span className="kp-small kp-text-muted">{item.description}</span>
                          <span className="kp-small kp-text-subtle">{item.tags.join(', ')}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
