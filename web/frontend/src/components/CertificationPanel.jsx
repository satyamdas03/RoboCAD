import { useEffect, useState } from 'react'
import {
  runSimulationCertification,
  listSimulationCertificates,
} from '../api.js'

export default function CertificationPanel({ designId }) {
  const [cert, setCert] = useState(null)
  const [certs, setCerts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setCert(null)
    setCerts([])
    setError(null)
    if (!designId) return
    let cancelled = false
    async function loadCerts() {
      try {
        const data = await listSimulationCertificates(designId)
        if (cancelled) return
        setCerts(data?.certificates || [])
        if (data?.certificates?.length) {
          setCert(data.certificates[0])
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    loadCerts()
    return () => { cancelled = true }
  }, [designId])

  async function handleRun() {
    if (!designId) return
    setLoading(true)
    setError(null)
    try {
      const data = await runSimulationCertification(designId)
      const certificate = data?.certificate
      setCert(certificate)
      setCerts((prev) => [certificate, ...prev])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const score = cert?.score ?? null
  const passed = cert?.passed ?? false
  const checks = cert?.checks || []

  return (
    <div className="kp-panel">
      <div className="kp-panel-header">
        <span className="kp-panel-title">Simulation Certification</span>
        <span className={`kp-badge ${passed ? 'kp-badge-success' : score !== null ? 'kp-badge-warning' : 'kp-badge-neutral'}`}>
          {passed ? 'CERTIFIED' : score !== null ? 'NOT CERTIFIED' : 'NO CERT'}
        </span>
      </div>

      <div className="kp-panel-body">
        {score !== null && (
          <div className="kp-metric-row">
            <div className="kp-metric">
              <span className="kp-metric-value">{score.toFixed(1)}</span>
              <span className="kp-metric-label">score / 100</span>
            </div>
            <div className="kp-metric">
              <span className="kp-metric-value">{checks.length}</span>
              <span className="kp-metric-label">checks</span>
            </div>
            <div className="kp-metric">
              <span className="kp-metric-value">{checks.filter(c => c.passed).length}</span>
              <span className="kp-metric-label">passed</span>
            </div>
          </div>
        )}

        <button
          className="kp-button kp-button-primary"
          onClick={handleRun}
          disabled={loading || !designId}
        >
          {loading ? 'Running…' : cert ? 'Re-run Certification' : 'Run Certification'}
        </button>

        {error && <div className="kp-alert kp-alert-error">{error}</div>}

        {checks.length > 0 && (
          <div className="kp-section">
            <h4 className="kp-section-title">Checks</h4>
            <div className="kp-check-list">
              {checks.map((check) => (
                <div key={check.name} className={`kp-check-item ${check.passed ? 'kp-check-pass' : 'kp-check-fail'}`}>
                  <div className="kp-check-header">
                    <span className="kp-check-name">{check.name.replace(/_/g, ' ')}</span>
                    <span className="kp-check-score">{(check.score * 100).toFixed(0)}%</span>
                  </div>
                  <div className="kp-check-meta">
                    weight {(check.weight * 100).toFixed(0)}% · {check.passed ? 'PASS' : 'FAIL'}
                  </div>
                  {check.name === 'robot_randomized_world_certification' && check.details?.cases && (
                    <div className="kp-sub-check-list">
                      {check.details.cases.map((c) => (
                        <div key={c.case} className={`kp-sub-check ${c.passed ? 'kp-sub-check-pass' : c.skipped ? 'kp-sub-check-skip' : 'kp-sub-check-fail'}`}>
                          <span className="kp-sub-check-name">{c.case.replace(/_/g, ' ')}</span>
                          <span className="kp-sub-check-status">{c.skipped ? 'skipped' : c.passed ? 'pass' : 'fail'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {certs.length > 1 && (
          <div className="kp-section">
            <h4 className="kp-section-title">History ({certs.length})</h4>
            <ul className="kp-list">
              {certs.slice(1).map((c, idx) => (
                <li key={c.cert_id || idx} className="kp-list-item">
                  <span>{new Date(c.created_at * 1000).toLocaleString()}</span>
                  <span className={`kp-badge ${c.passed ? 'kp-badge-success' : 'kp-badge-warning'}`}>
                    {c.score?.toFixed(1) ?? '-'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
