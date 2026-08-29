import { useEffect, useState } from 'react'
import { decomposePrompt } from '../api.js'
import DomainBadge from './DomainBadge.jsx'

export default function DecomposePanel({ prompt, decomposition }) {
  const [plan, setPlan] = useState(decomposition || null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (decomposition) {
      setPlan(decomposition)
      setError(null)
      return
    }
    if (!prompt) {
      setPlan(null)
      return
    }
    let cancelled = false
    decomposePrompt(prompt)
      .then((data) => {
        if (!cancelled) setPlan(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [prompt, decomposition])

  if (error) {
    return (
      <section className="kp-panel" aria-labelledby="decompose-heading">
        <div className="kp-panel-header">
          <h3 id="decompose-heading" className="kp-panel-title">Decomposition</h3>
        </div>
        <p className="kp-text-muted kp-small">Could not preview decomposition: {error}</p>
      </section>
    )
  }

  if (!plan || !plan.parts?.length) {
    return null
  }

  return (
    <section className="kp-panel" aria-labelledby="decompose-heading">
      <div className="kp-panel-header">
        <h3 id="decompose-heading" className="kp-panel-title">System decomposition</h3>
        <DomainBadge domain={plan.primary_domain} multiDomain={plan.multi_domain} />
      </div>
      <p className="kp-panel-subtitle">
        {plan.parts.length} part family{plan.parts.length === 1 ? '' : 'ies'} detected.
      </p>

      <div style={{ overflowX: 'auto' }}>
        <table className="kp-table">
          <thead>
            <tr>
              <th>Part</th>
              <th>Domain</th>
              <th>Family</th>
              <th>Qty</th>
            </tr>
          </thead>
          <tbody>
            {plan.parts.map((part) => (
              <tr key={part.id}>
                <td>{part.name}</td>
                <td>
                  <DomainBadge domain={part.domain} />
                </td>
                <td>
                  <code>{part.family}</code>
                </td>
                <td>{part.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {plan.notes?.length > 0 && (
        <ul className="kp-list kp-small kp-text-muted" style={{ marginTop: '0.75rem' }}>
          {plan.notes.map((note, idx) => (
            <li key={idx}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
