import { useState } from 'react'

export default function HistorySidebar({ designs, selectedId, onSelect, onRefresh }) {
  const [search, setSearch] = useState('')
  const [tagFilter, setTagFilter] = useState('')

  const filtered = designs.filter((d) => {
    const matchesSearch =
      search === '' ||
      d.prompt.toLowerCase().includes(search.toLowerCase()) ||
      (d.tags || []).some((t) => t.toLowerCase().includes(search.toLowerCase()))
    const matchesTag = tagFilter === '' || (d.tags || []).some((t) => t.toLowerCase() === tagFilter.toLowerCase())
    return matchesSearch && matchesTag
  })

  const allTags = Array.from(new Set(designs.flatMap((d) => d.tags || []))).sort()

  return (
    <section className="kp-flex-col" aria-labelledby="history-heading" style={{ flex: 1, minHeight: 0 }}>
      <div className="kp-panel-header" style={{ padding: 'var(--kp-space-2) var(--kp-space-3)', borderBottom: '1px solid var(--kp-border)' }}>
        <h3 id="history-heading" className="kp-panel-title">History</h3>
        <button type="button" onClick={onRefresh} className="kp-button kp-button-small kp-button-ghost">
          ↻ Refresh
        </button>
      </div>

      <div className="kp-flex-col kp-gap-2" style={{ padding: 'var(--kp-space-3)' }}>
        <div className="kp-field">
          <input
            id="history-search"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search prompts or tags"
            className="kp-input kp-mono"
          />
        </div>

        {allTags.length > 0 && (
          <div className="kp-field">
            <select
              id="history-tag"
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              className="kp-select kp-mono"
            >
              <option value="">All tags</option>
              {allTags.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="kp-empty" style={{ padding: 'var(--kp-space-4)' }}>
          <p className="kp-text-muted">No designs match.</p>
        </div>
      ) : (
        <ul className="kp-list" style={{ overflowY: 'auto', flex: 1, padding: '0 var(--kp-space-3) var(--kp-space-3)' }}>
          {filtered.map((d) => (
            <li
              key={d.id}
              onClick={() => onSelect(d.id)}
              className={`kp-list-item ${selectedId === d.id ? 'kp-list-item-active' : ''} ${!d.success ? 'kp-list-item-error' : ''}`}
              aria-current={selectedId === d.id ? 'true' : undefined}
            >
              <div className="kp-flex kp-justify-between kp-align-center kp-gap-2">
                <span style={{ fontWeight: 500, lineHeight: 1.35, fontSize: '0.85rem' }}>
                  <span className={d.success ? 'kp-text-primary' : 'kp-text-muted'} aria-hidden="true">
                    {d.success ? '● ' : '● '}
                  </span>
                  {d.prompt.slice(0, 60)}{d.prompt.length > 60 ? '…' : ''}
                </span>
                <span className="kp-small kp-text-subtle kp-mono">{d.latency_seconds?.toFixed(1) || '?'}s</span>
              </div>
              <div className="kp-small kp-text-subtle kp-mt-2 kp-flex kp-align-center kp-gap-2 kp-flex-wrap">
                <span>{new Date(d.created_at).toLocaleString()}</span>
                {d.parent_id && <span>remix of #{d.parent_id.slice(0, 8)}</span>}
              </div>
              {(d.tags || []).length > 0 && (
                <div className="kp-flex kp-gap-1 kp-mt-2 kp-flex-wrap">
                  {d.tags.map((t) => (
                    <span key={t} className="kp-tag">{t}</span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
