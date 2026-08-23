function ValidationGrid({ validation }) {
  if (!validation) return null
  const { manifold, watertight, bounds_mm, volume_mm3, errors, warnings } = validation

  return (
    <div className="rc-strip">
      <span>
        <strong>Manifold:</strong> {manifold ? 'Yes' : 'No'}
      </span>
      <span>
        <strong>Watertight:</strong> {watertight ? 'Yes' : 'No'}
      </span>
      {bounds_mm && (
        <span>
          <strong>Bounds:</strong> {bounds_mm.map((n) => n.toFixed(1)).join(' × ')} mm
        </span>
      )}
      {volume_mm3 && (
        <span>
          <strong>Volume:</strong> {volume_mm3.toFixed(1)} mm³
        </span>
      )}
      {errors?.length > 0 && (
        <span className="rc-badge rc-badge-error">{errors.length} error{errors.length > 1 ? 's' : ''}</span>
      )}
      {warnings?.length > 0 && (
        <span className="rc-badge rc-badge-warning">{warnings.length} warning{warnings.length > 1 ? 's' : ''}</span>
      )}
    </div>
  )
}

export default function StatusPanel({ result, error, loading }) {
  if (loading) {
    return (
      <div className="rc-alert rc-alert-info">
        <strong>Running…</strong> Generating parametric CAD code, executing it, and validating the resulting geometry.
      </div>
    )
  }

  if (error) {
    return (
      <div className="rc-alert rc-alert-error">
        <strong>Error:</strong> {error}
      </div>
    )
  }

  if (!result) {
    return (
      <div className="rc-empty">
        <div className="rc-empty-icon" aria-hidden="true">◈</div>
        <p>Type a prompt and generate a part to see the 3D model, parameters, and manufacturing readouts.</p>
      </div>
    )
  }

  const v = result.validation
  const statusClass = result.success ? 'rc-alert-success' : 'rc-alert-warning'

  return (
    <div className={`rc-alert ${statusClass}`}>
      <div className="rc-strip">
        <span>
          <strong>Status:</strong> {result.success ? 'Success' : 'Failed'}
        </span>
        {result.design_id && (
          <span className="rc-mono">
            <strong>Design:</strong> #{result.design_id.slice(0, 8)}
          </span>
        )}
        {result.model && (
          <span>
            <strong>Model:</strong> {result.model}
          </span>
        )}
        {result.attempts_used != null && (
          <span>
            <strong>Attempts:</strong> {result.attempts_used}/{result.max_retries + 1}
          </span>
        )}
        {result.latency_seconds != null && (
          <span>
            <strong>Latency:</strong> {result.latency_seconds}s
          </span>
        )}
      </div>

      <ValidationGrid validation={v} />

      {result.traceback && (
        <details className="rc-mt-3">
          <summary>Traceback / details</summary>
          <pre className="rc-mono rc-mt-2" style={{ fontSize: '0.75rem', overflow: 'auto', whiteSpace: 'pre-wrap' }}>{result.traceback}</pre>
        </details>
      )}
    </div>
  )
}
