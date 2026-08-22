export default function ParameterList({ parameters }) {
  if (!parameters || parameters.length === 0) return null

  return (
    <div className="panel">
      <h3>Parameters</h3>
      <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '-0.5rem' }}>
        Read-only in Phase 2. Editing coming in Phase 3.
      </p>
      <table style={{ width: '100%', fontSize: '0.9rem' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>Name</th>
            <th style={{ textAlign: 'left' }}>Value</th>
            <th style={{ textAlign: 'left' }}>Unit</th>
            <th style={{ textAlign: 'left' }}>Description</th>
          </tr>
        </thead>
        <tbody>
          {parameters.map((p) => (
            <tr key={p.name}>
              <td><code>{p.name}</code></td>
              <td>{p.value}</td>
              <td>{p.unit || 'mm'}</td>
              <td>{p.description || '—'}</td>
            </tr>
          ))}
        </tbody>
      <table>
    </div>
  )
}
