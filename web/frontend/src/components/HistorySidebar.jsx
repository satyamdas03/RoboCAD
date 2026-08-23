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
    <section className="rc-panel" aria-labelledby="history-heading">
      <div className="rc-panel-header">
        <h3 id="history-heading" className="rc-panel-title">History</h3>
        <button type="button" onClick={onRefresh} className="rc-button rc-button-small rc-button-ghost">
          Refresh
        </button>
      </div>

      <div className="rc-flex-col rc-gap-2">
        <div className="rc-field">
          <label htmlFor="history-search" className="rc-label">Search</label>
          <input
            id="history-search"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search prompts or tags"
            className="rc-input"
          />
        </div>

        {allTags.length > 0 && (
          <div className="rc-field">
            <label htmlFor="history-tag" className="rc-label">Filter by tag</label>
            <select
              id="history-tag"
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              className="rc-select"
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
        <div className="rc-empty">
          <p>No designs match.</p>
        </div>
      ) : (
        <ul className="rc-list rc-mt-3" style={{ maxHeight: '420px', overflowY: 'auto' }}>
          {filtered.map((d) => (
            <li
              key={d.id}
              onClick={() => onSelect(d.id)}
              className={`rc-list-item ${selectedId === d.id ? 'rc-list-item-active' : ''}`}
              aria-current={selectedId === d.id ? 'true' : undefined}
            >
              <div className="rc-flex rc-justify-between rc-align-center rc-gap-2">
                <span style={{ fontWeight: 500, lineHeight: 1.35 }}>
                  {d.success ? <span className="rc-text-muted" aria-hidden="true">✓ </span> : <span aria-hidden="true">✗ </span>}
                  {d.prompt.slice(0, 60)}{d.prompt.length > 60 ? '…' : ''}
                </span>
                <span className="rc-small rc-text-subtle rc-mono">{d.latency_seconds?.toFixed(1) || '?'}s</span>
              </div>
              <div className="rc-small rc-text-subtle rc-mt-2 rc-flex rc-align-center rc-gap-2 rc-flex-wrap">
                <span>{new Date(d.created_at).toLocaleString()}</span>
                {d.parent_id && <span>remix of #{d.parent_id.slice(0, 8)}</span>}
              </div>
              {(d.tags || []).length > 0 && (
                <div className="rc-flex rc-gap-1 rc-mt-2 rc-flex-wrap">
                  {d.tags.map((t) => (
                    <span key={t} className="rc-tag">{t}</span>
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
