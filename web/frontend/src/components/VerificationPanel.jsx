import { useEffect, useState } from 'react'
import {
  checkMeshQuality,
  runVerification,
  getSolverAvailability,
  submitDeepVerification,
  getDeepVerificationJob,
  getDeepVerificationField,
  listDeepVerificationJobs,
  cancelDeepVerificationJob,
} from '../api.js'

const LOAD_CASES = [
  { value: 'static_stress', label: 'Static stress' },
  { value: 'drop_test', label: 'Drop test' },
  { value: 'thermal_expansion', label: 'Thermal expansion' },
  { value: 'fatigue_cycles', label: 'Fatigue cycles' },
  { value: 'fastener_pull_out', label: 'Fastener pull-out' },
  { value: 'wind_tunnel_drag', label: 'Wind-tunnel drag' },
  { value: 'heat_sink_thermal_resistance', label: 'Heat-sink thermal resistance' },
  { value: 'joint_torque_check', label: 'Joint torque check' },
  { value: 'mesh_quality', label: 'Mesh quality' },
  { value: 'assembly_clearance', label: 'Assembly clearance' },
]

const MATERIALS = [
  'PLA',
  'PETG',
  'ABS',
  'Nylon 12',
  'Aluminum 6061',
  'Mild Steel',
  'Copper',
  'Brass',
  'Titanium 6Al-4V',
  'FR4',
  'CopperTrace',
]

const DEEP_SOLVERS = [
  { value: 'calculix', label: 'CalculiX' },
  { value: 'elmer', label: 'ElmerFEM' },
  { value: 'openfoam', label: 'OpenFOAM' },
  { value: 'surrogate', label: 'NVIDIA surrogate' },
]

const SOLVER_MODES = [
  { value: 'auto', label: 'Auto (real if installed)' },
  { value: 'real', label: 'Real solver only' },
  { value: 'surrogate', label: 'Surrogate only' },
]

const DEFAULT_BOUNDARY_JSON = JSON.stringify({
  fixed_faces: ['-x'],
  loaded_faces: ['+x'],
  load_magnitude_n: 100,
  ambient_temp_c: 25,
  flow_velocity_ms: 10,
}, null, 2)

export default function VerificationPanel({ designId, onFieldLoaded }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [loadCase, setLoadCase] = useState('static_stress')
  const [material, setMaterial] = useState('PLA')
  const [paramJson, setParamJson] = useState('{}')

  const [mode, setMode] = useState('quick')
  const [solver, setSolver] = useState('calculix')
  const [solverMode, setSolverMode] = useState('auto')
  const [boundaryJson, setBoundaryJson] = useState(DEFAULT_BOUNDARY_JSON)
  const [solverAvailability, setSolverAvailability] = useState({})
  const [deepJobId, setDeepJobId] = useState(null)
  const [deepJob, setDeepJob] = useState(null)
  const [deepJobs, setDeepJobs] = useState([])
  const [fieldData, setFieldData] = useState(null)
  const [fieldLoading, setFieldLoading] = useState(false)

  useEffect(() => {
    setReport(null)
    setError(null)
    setDeepJobId(null)
    setDeepJob(null)
    setDeepJobs([])
    setFieldData(null)
  }, [designId, loadCase])

  useEffect(() => {
    if (!designId || mode !== 'deep') return
    let cancelled = false
    async function loadDeepContext() {
      try {
        const [availability, jobs] = await Promise.all([
          getSolverAvailability(designId),
          listDeepVerificationJobs(designId),
        ])
        if (cancelled) return
        setSolverAvailability(availability?.solvers || availability || {})
        setDeepJobs(jobs?.jobs || jobs || [])
      } catch (err) {
        if (!cancelled) setError((prev) => prev || err.message)
      }
    }
    loadDeepContext()
    return () => { cancelled = true }
  }, [designId, mode])

  useEffect(() => {
    if (!deepJobId) return
    let cancelled = false
    const interval = setInterval(async () => {
      if (cancelled) return
      try {
        const data = await getDeepVerificationJob(designId, deepJobId)
        const job = data?.job || data
        setDeepJob(job)
        if (job?.status === 'completed' || job?.status === 'failed' || job?.status === 'cancelled') {
          clearInterval(interval)
          refreshJobs()
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }, 2000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [designId, deepJobId])

  async function handleRun() {
    if (!designId) return
    let parameters = {}
    try {
      parameters = JSON.parse(paramJson || '{}')
    } catch (err) {
      setError('Parameters JSON is invalid: ' + err.message)
      return
    }
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await runVerification(designId, {
        loadCase,
        materials: { default: material },
        parameters: { ...parameters, material },
      })
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleMeshCheck() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await checkMeshQuality(designId)
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function refreshJobs() {
    if (!designId) return
    try {
      const data = await listDeepVerificationJobs(designId)
      setDeepJobs(data?.jobs || data || [])
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSubmitDeep() {
    if (!designId) return
    let boundaryConditions = {}
    let parameters = {}
    try {
      boundaryConditions = JSON.parse(boundaryJson || '{}')
    } catch (err) {
      setError('Boundary conditions JSON is invalid: ' + err.message)
      return
    }
    try {
      parameters = JSON.parse(paramJson || '{}')
    } catch (err) {
      setError('Parameters JSON is invalid: ' + err.message)
      return
    }
    setLoading(true)
    setError(null)
    setDeepJob(null)
    try {
      const data = await submitDeepVerification(designId, {
        solver,
        solverMode,
        loadCase,
        materials: { default: material },
        parameters: { ...parameters, material },
        boundaryConditions,
      })
      const job = data?.job || data
      setDeepJobId(job?.job_id || job?.id)
      setDeepJob(job)
      await refreshJobs()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleCancelDeep() {
    if (!designId || !deepJobId) return
    setLoading(true)
    try {
      await cancelDeepVerificationJob(designId, deepJobId)
      const data = await getDeepVerificationJob(designId, deepJobId)
      setDeepJob(data?.job || data)
      await refreshJobs()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleLoadField() {
    if (!designId || !deepJobId) return
    setFieldLoading(true)
    setError(null)
    try {
      const fieldName = loadCase === 'heat_sink_thermal_resistance' || loadCase === 'thermal_expansion'
        ? 'temperature_c'
        : 'von_mises_stress_mpa'
      const data = await getDeepVerificationField(designId, deepJobId, fieldName)
      const field = data?.field || data
      setFieldData(field)
      if (onFieldLoaded) {
        onFieldLoaded(field)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setFieldLoading(false)
    }
  }

  function handleClearField() {
    setFieldData(null)
    if (onFieldLoaded) {
      onFieldLoaded(null)
    }
  }

  if (!designId) return null

  const isMeshCase = loadCase === 'mesh_quality'
  const deepStatus = deepJob?.status || 'idle'
  const deepResult = deepJob?.result

  function renderQuickForm() {
    return (
      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Load case</label>
        <select
          className="kp-input"
          value={loadCase}
          onChange={(e) => setLoadCase(e.target.value)}
          disabled={loading}
        >
          {LOAD_CASES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>

        {!isMeshCase && (
          <>
            <label className="kp-label">Material</label>
            <select
              className="kp-input"
              value={material}
              onChange={(e) => setMaterial(e.target.value)}
              disabled={loading}
            >
              {MATERIALS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </>
        )}

        <label className="kp-label">Parameters (JSON)</label>
        <textarea
          className="kp-input"
          rows={3}
          value={paramJson}
          onChange={(e) => setParamJson(e.target.value)}
          disabled={loading}
          placeholder='{"load_magnitude_n": 100}'
        />

        <div className="kp-flex kp-gap-2">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleRun}
            disabled={loading}
          >
            {loading && mode === 'quick' ? 'Running…' : 'Run verification'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleMeshCheck}
            disabled={loading}
          >
            Mesh quality
          </button>
        </div>
      </div>
    )
  }

  function renderDeepForm() {
    return (
      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Solver</label>
        <select
          className="kp-input"
          value={solver}
          onChange={(e) => setSolver(e.target.value)}
          disabled={loading}
        >
          {DEEP_SOLVERS.map((s) => {
            const available = solverAvailability[s.value]?.available !== false
            return (
              <option key={s.value} value={s.value}>
                {s.label} {!available ? '(unavailable)' : ''}
              </option>
            )
          })}
        </select>

        {solverAvailability[solver]?.description && (
          <div className="kp-small kp-text-muted">
            {solverAvailability[solver].description}
          </div>
        )}

        <label className="kp-label">Solver mode</label>
        <select
          className="kp-input"
          value={solverMode}
          onChange={(e) => setSolverMode(e.target.value)}
          disabled={loading}
        >
          {SOLVER_MODES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>

        <label className="kp-label">Boundary conditions (JSON)</label>
        <textarea
          className="kp-input"
          rows={5}
          value={boundaryJson}
          onChange={(e) => setBoundaryJson(e.target.value)}
          disabled={loading}
          placeholder='{"fixed_faces": ["-x"], "loaded_faces": ["+x"], "load_magnitude_n": 100}'
        />

        <label className="kp-label">Parameters (JSON)</label>
        <textarea
          className="kp-input"
          rows={3}
          value={paramJson}
          onChange={(e) => setParamJson(e.target.value)}
          disabled={loading}
          placeholder='{"load_magnitude_n": 100}'
        />

        <div className="kp-flex kp-gap-2 kp-flex-wrap">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleSubmitDeep}
            disabled={loading || solverAvailability[solver]?.available === false}
          >
            {loading && mode === 'deep' ? 'Submitting…' : 'Submit deep analysis'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleCancelDeep}
            disabled={!deepJobId || deepStatus === 'completed' || deepStatus === 'failed' || deepStatus === 'cancelled'}
          >
            Cancel job
          </button>
          <button
            type="button"
            className="kp-button kp-button-ghost"
            onClick={refreshJobs}
            disabled={loading}
          >
            Refresh jobs
          </button>
        </div>
      </div>
    )
  }

  function statusBadgeClass(status) {
    if (status === 'completed' || status === 'passed' || status === 'success') return 'kp-badge-success'
    if (status === 'failed' || status === 'error' || status === 'cancelled') return 'kp-badge-error'
    if (status === 'running' || status === 'pending') return 'kp-badge-warning'
    return 'kp-badge-secondary'
  }

  return (
    <section className="kp-panel" aria-labelledby="verify-heading">
      <div className="kp-panel-header">
        <h3 id="verify-heading" className="kp-panel-title">Multi-physics verification</h3>
      </div>

      <div className="kp-flex kp-gap-2 kp-mb-2">
        <button
          type="button"
          className={`kp-button ${mode === 'quick' ? 'kp-button-primary' : 'kp-button-ghost'}`}
          onClick={() => setMode('quick')}
        >
          Quick verify
        </button>
        <button
          type="button"
          className={`kp-button ${mode === 'deep' ? 'kp-button-primary' : 'kp-button-ghost'}`}
          onClick={() => setMode('deep')}
        >
          Deep analysis
        </button>
      </div>

      {mode === 'quick' ? renderQuickForm() : renderDeepForm()}

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {mode === 'quick' && report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Status</span>
            <span className={`kp-badge ${report.passed ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.passed ? 'PASS' : 'FAIL'}
            </span>
          </div>

          {report.load_case && (
            <div className="kp-flex kp-justify-between kp-align-center">
              <span className="kp-label">Load case</span>
              <span className="kp-mono" style={{ fontSize: '0.85rem' }}>{report.load_case}</span>
            </div>
          )}

          {report.metrics && Object.keys(report.metrics).length > 0 && (
            <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
              {Object.entries(report.metrics).map(([key, value]) => (
                <div key={key} className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                  <span className="kp-label">{key}</span>
                  <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                    {typeof value === 'number' ? value.toFixed(4) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {report.mesh_report && (
            <div className="kp-flex-col kp-gap-2" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <div className="kp-flex kp-justify-between kp-align-center">
                <span className="kp-label">Mesh suitable for solver</span>
                <span className={`kp-badge ${report.mesh_report.is_suitable_for_solver ? 'kp-badge-success' : 'kp-badge-error'}`}>
                  {report.mesh_report.is_suitable_for_solver ? 'YES' : 'NO'}
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1">
                <span className="kp-label">Issues</span>
                {report.mesh_report.issues?.length > 0 ? (
                  <ul className="kp-list">
                    {report.mesh_report.issues.map((issue, i) => (
                      <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{issue}</li>
                    ))}
                  </ul>
                ) : (
                  <span className="kp-text-muted kp-small">No issues detected.</span>
                )}
              </div>
            </div>
          )}

          {report.failure_modes?.length > 0 && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Failure modes</span>
              <ul className="kp-list">
                {report.failure_modes.map((mode, i) => (
                  <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{mode}</li>
                ))}
              </ul>
            </div>
          )}

          {report.redesign_suggestions?.length > 0 && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Redesign suggestions</span>
              <ul className="kp-list">
                {report.redesign_suggestions.map((s, i) => (
                  <li key={i} className="kp-tag" style={{ width: 'fit-content' }}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {report.errors?.length > 0 && (
            <ul className="kp-list">
              {report.errors.map((err, i) => (
                <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{err}</li>
              ))}
            </ul>
          )}

          {report.warnings?.length > 0 && (
            <ul className="kp-list">
              {report.warnings.map((warn, i) => (
                <li key={i} className="kp-tag kp-badge-warning" style={{ width: 'fit-content' }}>{warn}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {mode === 'deep' && deepJob && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Deep job</span>
            <span className="kp-mono" style={{ fontSize: '0.8rem' }}>{deepJob.job_id || deepJob.id}</span>
          </div>

          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Status</span>
            <span className={`kp-badge ${statusBadgeClass(deepStatus)}`}>
              {deepStatus}
            </span>
          </div>

          {typeof deepJob.progress === 'number' && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Progress</span>
              <div
                style={{
                  width: '100%',
                  height: '6px',
                  background: 'var(--kp-surface-container-high)',
                  borderRadius: 'var(--kp-radius-sm)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${Math.max(0, Math.min(100, deepJob.progress * 100))}%`,
                    height: '100%',
                    background: 'var(--kp-primary-container)',
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
              <span className="kp-small kp-text-muted">{(deepJob.progress * 100).toFixed(0)}%</span>
            </div>
          )}

          {deepJob.solver && (
            <div className="kp-flex kp-justify-between kp-align-center">
              <span className="kp-label">Solver</span>
              <span className="kp-mono" style={{ fontSize: '0.85rem' }}>{deepJob.solver}</span>
            </div>
          )}

          {deepJob.load_case && (
            <div className="kp-flex kp-justify-between kp-align-center">
              <span className="kp-label">Load case</span>
              <span className="kp-mono" style={{ fontSize: '0.85rem' }}>{deepJob.load_case}</span>
            </div>
          )}

          {deepResult && (
            <>
              {deepResult.passed !== undefined && (
                <div className="kp-flex kp-justify-between kp-align-center">
                  <span className="kp-label">Result</span>
                  <span className={`kp-badge ${deepResult.passed ? 'kp-badge-success' : 'kp-badge-error'}`}>
                    {deepResult.passed ? 'PASS' : 'FAIL'}
                  </span>
                </div>
              )}

              {deepResult.metrics && Object.keys(deepResult.metrics).length > 0 && (
                <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
                  {Object.entries(deepResult.metrics).map(([key, value]) => (
                    <div key={key} className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                      <span className="kp-label">{key}</span>
                      <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                        {typeof value === 'number' ? value.toFixed(4) : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {deepResult.failure_modes?.length > 0 && (
                <div className="kp-flex-col kp-gap-1">
                  <span className="kp-label">Failure modes</span>
                  <ul className="kp-list">
                    {deepResult.failure_modes.map((mode, i) => (
                      <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{mode}</li>
                    ))}
                  </ul>
                </div>
              )}

              {deepResult.redesign_suggestions?.length > 0 && (
                <div className="kp-flex-col kp-gap-1">
                  <span className="kp-label">Redesign suggestions</span>
                  <ul className="kp-list">
                    {deepResult.redesign_suggestions.map((s, i) => (
                      <li key={i} className="kp-tag" style={{ width: 'fit-content' }}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {deepResult.errors?.length > 0 && (
                <ul className="kp-list">
                  {deepResult.errors.map((err, i) => (
                    <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>{err}</li>
                  ))}
                </ul>
              )}

              {deepResult.warnings?.length > 0 && (
                <ul className="kp-list">
                  {deepResult.warnings.map((warn, i) => (
                    <li key={i} className="kp-tag kp-badge-warning" style={{ width: 'fit-content' }}>{warn}</li>
                  ))}
                </ul>
              )}

              <div className="kp-flex kp-gap-2 kp-flex-wrap">
                <button
                  type="button"
                  className="kp-button kp-button-secondary"
                  onClick={handleLoadField}
                  disabled={fieldLoading || deepStatus !== 'completed'}
                >
                  {fieldLoading ? 'Loading field…' : 'Show heatmap'}
                </button>
                {fieldData && (
                  <button
                    type="button"
                    className="kp-button kp-button-ghost"
                    onClick={handleClearField}
                  >
                    Clear heatmap
                  </button>
                )}
              </div>

              {fieldData?.message === 'ok' && fieldData.scalars?.length > 0 && (
                <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                  <span className="kp-label">Field: {fieldData.field_name} ({fieldData.unit || 'n/a'})</span>
                  <div className="kp-flex kp-justify-between kp-align-center">
                    <span className="kp-small kp-text-muted">min: {fieldData.min?.toFixed?.(4) ?? fieldData.min}</span>
                    <span className="kp-small kp-text-muted">max: {fieldData.max?.toFixed?.(4) ?? fieldData.max}</span>
                  </div>
                </div>
              )}

              {deepResult.output_url && (
                <a
                  href={deepResult.output_url}
                  download
                  className="kp-button kp-button-secondary"
                  style={{ width: 'fit-content' }}
                >
                  Download solver output
                </a>
              )}
            </>
          )}

          {deepJob.log && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Solver log</span>
              <pre className="kp-code">{deepJob.log}</pre>
            </div>
          )}
        </div>
      )}

      {mode === 'deep' && deepJobs.length > 0 && (
        <div className="kp-flex-col kp-gap-2 kp-mt-3">
          <span className="kp-label">Recent deep jobs</span>
          <div className="kp-flex-col kp-gap-2">
            {deepJobs.slice(0, 6).map((job) => (
              <div
                key={job.job_id || job.id}
                className="kp-flex kp-justify-between kp-align-center"
                style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}
              >
                <div className="kp-flex-col kp-gap-1">
                  <span className="kp-mono" style={{ fontSize: '0.8rem' }}>{job.job_id || job.id}</span>
                  <span className="kp-small kp-text-muted">{job.solver} · {job.load_case}</span>
                </div>
                <div className="kp-flex kp-gap-2 kp-align-center">
                  <span className={`kp-badge ${statusBadgeClass(job.status)}`}>{job.status}</span>
                  <button
                    type="button"
                    className="kp-button kp-button-small kp-button-ghost"
                    onClick={() => setDeepJobId(job.job_id || job.id)}
                  >
                    View
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
