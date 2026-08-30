import { useEffect, useState } from 'react'
import { createRobotTemplate, listRobotTemplates, runRobotAnalysis } from '../api.js'

const DEFAULT_PARAMS = {
  humanoid: { robot_height: 1000, payload_kg: 5, robot_mass_kg: 20, leg_dof: 6, arm_dof: 4, gait_style: 'biped_walk' },
  quadruped: { robot_height: 600, payload_kg: 10, robot_mass_kg: 25, leg_dof: 3, gait_style: 'trot' },
  manipulator_on_base: { base_size: 300, reach: 800, payload_kg: 2, robot_mass_kg: 15, arm_dof: 6 },
}

export default function HumanoidPanel({ designId, onDesignCreated }) {
  const [templates, setTemplates] = useState([])
  const [selected, setSelected] = useState('humanoid')
  const [params, setParams] = useState(DEFAULT_PARAMS.humanoid)
  const [creating, setCreating] = useState(false)
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [createdId, setCreatedId] = useState(null)

  useEffect(() => {
    listRobotTemplates().then((data) => setTemplates(data.templates || [])).catch(() => setTemplates([]))
  }, [])

  useEffect(() => {
    setSelected('humanoid')
    setParams(DEFAULT_PARAMS.humanoid)
    setReport(null)
    setError(null)
    setCreatedId(null)
  }, [designId])

  useEffect(() => {
    setParams(DEFAULT_PARAMS[selected] || {})
  }, [selected])

  async function handleCreate() {
    setCreating(true)
    setError(null)
    setReport(null)
    try {
      const data = await createRobotTemplate({ template: selected, parameters: params })
      setCreatedId(data.design_id)
      if (onDesignCreated) onDesignCreated(data.design_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  async function handleAnalyze() {
    const id = createdId || designId
    if (!id) return
    setRunning(true)
    setError(null)
    setReport(null)
    try {
      const data = await runRobotAnalysis(id)
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  function updateParam(name, value) {
    setParams((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <section className="kp-panel" aria-labelledby="humanoid-heading">
      <div className="kp-panel-header">
        <h3 id="humanoid-heading" className="kp-panel-title">Humanoid / robot synthesis</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Robot template</label>
        <select
          className="kp-input"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={creating || running}
        >
          {templates.map((t) => (
            <option key={t.name} value={t.name}>{t.name}</option>
          ))}
        </select>

        {Object.entries(params).map(([name, value]) => (
          <div key={name} className="kp-flex-col kp-gap-1">
            <label className="kp-label">{name}</label>
            <input
              className="kp-input"
              type={typeof value === 'number' ? 'number' : 'text'}
              value={value}
              onChange={(e) => updateParam(name, e.target.value)}
              disabled={creating || running}
            />
          </div>
        ))}

        <div className="kp-flex kp-gap-2">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleCreate}
            disabled={creating || running}
          >
            {creating ? 'Creating…' : 'Create robot'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleAnalyze}
            disabled={running || (!createdId && !designId)}
          >
            {running ? 'Analyzing…' : 'Run analysis'}
          </button>
        </div>

        {createdId && (
          <div className="kp-text-muted kp-small">
            Created design <span className="kp-mono">{createdId}</span>
          </div>
        )}
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Actuator count</span>
            <span className="kp-mono">{report.actuator_summary?.joint_count ?? 0}</span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Max torque</span>
            <span className="kp-mono">{(report.actuator_summary?.max_torque_nm ?? 0).toFixed(4)} N·m</span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Total power</span>
            <span className="kp-mono">{(report.actuator_summary?.total_power_w ?? 0).toFixed(4)} W</span>
          </div>

          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Statically stable</span>
            <span className={`kp-badge ${report.stability?.statically_stable ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.stability?.statically_stable ? 'YES' : 'NO'}
            </span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Dynamically stable</span>
            <span className={`kp-badge ${report.stability?.dynamically_stable ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.stability?.dynamically_stable ? 'YES' : 'NO'}
            </span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Gait feasible</span>
            <span className={`kp-badge ${report.gait_feasible ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.gait_feasible ? 'YES' : 'NO'}
            </span>
          </div>

          {report.stability?.warnings?.length > 0 && (
            <div className="kp-flex-col kp-gap-1">
              <span className="kp-label">Warnings</span>
              <ul className="kp-list">
                {report.stability.warnings.map((w, i) => (
                  <li key={i} className="kp-tag kp-badge-warning" style={{ width: 'fit-content' }}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {report.reachable_workspace && (
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Reachable workspace ({report.reachable_workspace.end_effector_id})</span>
              <span className="kp-mono kp-small">
                points: {report.reachable_workspace.point_count} · envelope: [
                {(report.reachable_workspace.envelope_mm || []).map((v) => v.toFixed(1)).join(', ')}] mm
              </span>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
