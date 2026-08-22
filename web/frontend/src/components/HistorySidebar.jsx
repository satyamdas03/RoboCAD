export default function HistorySidebar({ designs, selectedId, onSelect, onRefresh }) {
  return (
    <div className="panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>History</h3>
        <button type="button" onClick={onRefresh} style={{ fontSize: '0.8rem' }}>
          Refresh
        </button>
      </div>
      {designs.length === 0 ? (
        <p style={{ color: '#666', fontSize: '0.9rem' }}>No designs yet.</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {designs.map((d) => (
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
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
