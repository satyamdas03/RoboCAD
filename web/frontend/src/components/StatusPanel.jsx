function ValidationGrid({ validation }) {
  if (!validation) return null
  const { manifold, watertight, bounds_mm, volume_mm3, errors, warnings } = validation

  return (
    <div className="kp-strip">
      <span className="kp-flex kp-align-center kp-gap-1">
        <strong>Manifold:</strong>
        <span className={`kp-badge ${manifold ? 'kp-badge-success' : 'kp-badge-error'}`}>
          {manifold ? 'OK' : 'FAIL'}
        </span>
      </span>
      <span className="kp-flex kp-align-center kp-gap-1">
        <strong>Watertight:</strong>
        <span className={`kp-badge ${watertight ? 'kp-badge-success' : 'kp-badge-error'}`}>
          {watertight ? 'OK' : 'FAIL'}
        </span>
      </span>
      {bounds_mm && (
        <span className="kp-mono">
          <strong>Bounds:</strong> {bounds_mm.map((n) => n.toFixed(1)).join(' × ')} mm
        </span>
      )}
      {volume_mm3 && (
        <span className="kp-mono">
          <strong>Volume:</strong> {volume_mm3.toFixed(1)} mm³
        </span>
      )}
      {errors?.length > 0 && (
        <span className="kp-badge kp-badge-error">{errors.length} error{errors.length > 1 ? 's' : ''}</span>
      )}
      {warnings?.length > 0 && (
        <span className="kp-badge kp-badge-warning">{warnings.length} warning{warnings.length > 1 ? 's' : ''}</span>
      )}
    </div>
  )
}

export default function StatusPanel({ result, error, loading }) {
  if (loading) {
    return (
      <div className="kp-alert kp-alert-info">
        <div className="kp-flex kp-align-center kp-gap-2">
          <span className="kp-glow-dot"></span>
          <strong>Running…</strong>
          <span className="kp-text-muted">Generating parametric CAD code, executing it, and validating the resulting geometry.</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="kp-alert kp-alert-error">
        <strong>Error:</strong> {error}
      </div>
    )
  }

  if (!result) {
    return (
      <div className="kp-panel" style={{ borderStyle: 'dashed' }}>
        <div className="kp-empty" style={{ padding: 'var(--kp-space-6)' }}>
          <div className="kp-empty-icon" aria-hidden="true">◈</div>
          <p>Type a prompt and generate a part to see the 3D model, parameters, and manufacturing readouts.</p>
        </div>
      </div>
    )
  }

  const v = result.validation
  const statusClass = result.success ? 'kp-alert-success' : 'kp-alert-warning'

  return (
    <div className={`kp-alert ${statusClass}`}>
      <div className="kp-strip">
        <span className="kp-flex kp-align-center kp-gap-1">
          <strong>Status:</strong>
          <span className={`kp-badge ${result.success ? 'kp-badge-success' : 'kp-badge-error'}`}>
            {result.success ? 'Success' : 'Failed'}
          </span>
        </span>
        {result.design_id && (
          <span className="kp-mono">
            <strong>Design:</strong> #{result.design_id.slice(0, 8)}
          </span>
        )}
        {result.model && (
          <span className="kp-mono">
            <strong>Model:</strong> {result.model}
          </span>
        )}
        {result.attempts_used != null && (
          <span>
            <strong>Attempts:</strong> {result.attempts_used}/{result.max_retries + 1}
          </span>
        )}
        {result.latency_seconds != null && (
          <span className="kp-mono">
            <strong>Latency:</strong> {result.latency_seconds}s
          </span>
        )}
      </div>

      <ValidationGrid validation={v} />

      {result.traceback && (
        <details className="kp-mt-3">
          <summary className="kp-text-muted" style={{ cursor: 'pointer', fontSize: '0.8rem' }}>Show traceback</summary>
          <pre className="kp-code kp-mt-2">{result.traceback}</pre>
        </details>
      )}
    </div>
  )
}
