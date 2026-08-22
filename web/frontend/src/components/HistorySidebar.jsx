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

  const allTags = Array.from(new Set(designs.flatMap((d) => d.tags || [])))

  return (
    <div className="panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>History</h3>
        <button type="button" onClick={onRefresh} style={{ fontSize: '0.8rem' }}>
          Refresh
        </button>
      </div>
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search prompts or tags"
        style={{ width: '100%', marginBottom: '0.5rem' }}
      />
      {allTags.length > 0 && (
        <select
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
          style={{ width: '100%', marginBottom: '0.5rem' }}
        >
          <option value="">All tags</option>
          {allTags.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      )}
      {filtered.length === 0 ? (
        <p style={{ color: '#666', fontSize: '0.9rem' }}>No designs match.</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {filtered.map((d) => (
            <li
              key={d.id}
              onClick={() => onSelect(d.id)}
              style={{
                cursor: 'pointer',
                padding: '0.5rem',
                marginBottom: '0.25rem',
                borderRadius: '4px',
                background: selectedId === d.id ? '#dbeafe' : '#f8fafc',
                border: '1px solid #e2e8f0',
              }}
            >
              <div style={{ fontWeight: 500 }}>
                {d.success ? '✅' : '❌'} {d.prompt.slice(0, 60)}{d.prompt.length > 60 ? '...' : ''}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                {new Date(d.created_at).toLocaleString()} · {d.latency_seconds?.toFixed(1) || '?'}s
                {d.parent_id ? ` · remix of ${d.parent_id.slice(0, 8)}` : ''}
              </div>
              {(d.tags || []).length > 0 && (
                <div style={{ fontSize: '0.7rem', color: '#0ea5e9', marginTop: '0.2rem' }}>
                  {d.tags.join(', ')}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
