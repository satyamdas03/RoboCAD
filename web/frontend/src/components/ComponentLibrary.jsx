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
    <section className="rc-panel" aria-labelledby="library-heading">
      <h3 id="library-heading" className="rc-panel-title">Component Library</h3>
      <p className="rc-panel-subtitle">
        Click a component to load its seed prompt into the generator.
      </p>

      <div className="rc-flex-col rc-gap-2">
        {catalog.categories.map((category) => (
          <div key={category.name} className="rc-accordion">
            <button
              type="button"
              onClick={() => toggleCategory(category.name)}
              className="rc-accordion-header"
              aria-expanded={expanded[category.name]}
            >
              <span>{category.name}</span>
              <span aria-hidden="true">{expanded[category.name] ? '−' : '+'}</span>
            </button>

            {expanded[category.name] && (
              <div className="rc-accordion-body">
                <ul className="rc-list">
                  {category.items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        disabled={loading}
                        onClick={() => onPrompt(item.prompt)}
                        className="rc-button rc-button-ghost"
                        style={{ width: '100%', justifyContent: 'flex-start', textAlign: 'left' }}
                      >
                        <span className="rc-flex-col rc-gap-1">
                          <span style={{ fontWeight: 500 }}>{item.name}</span>
                          <span className="rc-small rc-text-muted">{item.description}</span>
                          <span className="rc-small rc-text-subtle">{item.tags.join(', ')}</span>
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
