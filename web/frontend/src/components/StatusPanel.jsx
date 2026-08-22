export default function StatusPanel({ result, error, loading }) {
  if (loading) {
    return (
      <div className="panel" style={{ background: '#eef6ff' }}>
        <p>🔄 Generating parametric CAD code and validating geometry...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="panel" style={{ background: '#ffe6e6' }}>
        <p><strong>Error:</strong> {error}</p>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="panel" style={{ background: '#f5f5f5' }}>
        <p>Type a prompt and click Generate to see the result.</p>
      </div>
    )
  }

  const v = result.validation
  return (
    <div className="panel" style={{ background: result.success ? '#e6ffed' : '#fff8e6' }}>
      <p>
        <strong>Status:</strong> {result.success ? '✅ Success' : '⚠️ Failed'}
        {result.design_id ? ` · Design #${result.design_id.slice(0, 8)}` : ''}
      </p>
      <p><strong>Model:</strong> {result.model} · <strong>Attempts:</strong> {result.attempts_used}/{result.max_retries + 1} · <strong>Latency:</strong> {result.latency_seconds}s</p>
      {v && (
        <div>
          <p style={{ margin: 0 }}>
            <strong>Validation:</strong>{' '}
            manifold {v.manifold ? '✅' : '❌'} · watertight {v.watertight ? '✅' : '❌'}
            {v.bounds_mm ? ` · bounds ${v.bounds_mm.map((n) => n.toFixed(1)).join(' × ')} mm` : ''}
            {v.volume_mm3 ? ` · volume ${v.volume_mm3.toFixed(1)} mm³` : ''}
          </p>
          {v.errors?.length > 0 && (
            <ul style={{ color: '#b00000', margin: '0.25rem 0' }}>
              {v.errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}
          {v.warnings?.length > 0 && (
            <ul style={{ color: '#8a6d03', margin: '0.25rem 0' }}>
              {v.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {result.traceback && (
        <details>
          <summary>Traceback / details</summary>
          <pre style={{ fontSize: '0.75rem', overflow: 'auto' }}>{result.traceback}</pre>
        </details>
      )}
    </div>
  )
}
