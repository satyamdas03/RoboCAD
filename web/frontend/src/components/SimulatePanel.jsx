import { useEffect, useState } from 'react'
import {
  simulateDesign,
  getSimulationReport,
  getBundleUrl,
  exportUrl,
  recommendSkill,
  trainSkill,
  getSkills,
  runVariantSweep,
} from '../api.js'

const MATERIALS = ['PLA', 'PETG', 'ABS', 'aluminum', 'steel']

export default function SimulatePanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [material, setMaterial] = useState('PLA')
  const [tolerance, setTolerance] = useState(0.1)

  const [activeTab, setActiveTab] = useState('bundle')
  const [skillDesc, setSkillDesc] = useState('push the block to the goal')
  const [skillLoading, setSkillLoading] = useState(false)
  const [skillResult, setSkillResult] = useState(null)
  const [recommended, setRecommended] = useState(null)

  const [sweepRanges, setSweepRanges] = useState('')
  const [sweepLoading, setSweepLoading] = useState(false)
  const [sweepResult, setSweepResult] = useState(null)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setError(null)
    setLoading(true)
    setSkillResult(null)
    setSweepResult(null)
    setRecommended(null)
    getSimulationReport(designId)
      .then((data) => setReport(data))
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }, [designId])

  async function handleSimulate() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await simulateDesign(designId, { material, tolerance })
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleRecommendSkill() {
    if (!designId) return
    setSkillLoading(true)
    setError(null)
    try {
      const data = await recommendSkill(designId, skillDesc)
      setRecommended(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setSkillLoading(false)
    }
  }

  async function handleTrainSkill() {
    if (!designId) return
    setSkillLoading(true)
    setError(null)
    try {
      const data = await trainSkill(designId, { skillDescription: skillDesc, nIters: 15, popSize: 40 })
      setSkillResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setSkillLoading(false)
    }
  }

  async function handleVariantSweep() {
    if (!designId) return
    setSweepLoading(true)
    setError(null)
    let ranges
    try {
      ranges = sweepRanges.trim() ? JSON.parse(sweepRanges) : {}
    } catch (err) {
      setError('Invalid JSON for parameter ranges: ' + err.message)
      setSweepLoading(false)
      return
    }
    try {
      const data = await runVariantSweep(designId, { parameterRanges: ranges, nVariants: 3, runStability: true })
      setSweepResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setSweepLoading(false)
    }
  }

  const totalMass = report?.manifest?.parts?.reduce((sum, p) => sum + (p.inertial?.mass_kg || 0), 0)
  const bundleUrl = report?.bundle_url ? exportUrl(report.bundle_url) : null

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="sim-heading">
      <div className="kp-panel-header">
        <h3 id="sim-heading" className="kp-panel-title">Simulation / GEDA Bridge</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
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

        <label className="kp-label">Mesh tolerance (mm)</label>
        <input
          className="kp-input"
          type="number"
          min={0.01}
          max={1.0}
          step={0.01}
          value={tolerance}
          onChange={(e) => setTolerance(Number(e.target.value))}
          disabled={loading}
        />

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleSimulate}
          disabled={loading}
        >
          {loading ? 'Building bundle…' : 'Generate simulation bundle'}
        </button>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Bundle status</span>
            <span className={`kp-badge ${report.valid ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {report.valid ? 'Verified' : 'Failed'}
            </span>
          </div>

          <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Bodies</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.manifest?.parts?.length ?? '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Total mass</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {totalMass != null ? totalMass.toFixed(4) + ' kg' : '—'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Watertight</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.verification?.all_watertight ? 'Yes' : 'No'}
              </span>
            </div>
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Inertia valid</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {report.verification?.all_inertia_positive_definite ? 'Yes' : 'No'}
              </span>
            </div>
          </div>

          {report.verification?.errors?.length > 0 && (
            <ul className="kp-list">
              {report.verification.errors.map((err, i) => (
                <li key={i} className="kp-tag kp-badge-error" style={{ width: 'fit-content' }}>
                  {err}
                </li>
              ))}
            </ul>
          )}

          {bundleUrl && (
            <a
              href={bundleUrl}
              download
              className="kp-button kp-button-secondary"
              style={{ width: 'fit-content' }}
            >
              Download bundle (.zip)
            </a>
          )}

          <div className="kp-flex kp-gap-2" style={{ marginTop: 'var(--kp-space-3)' }}>
            {['bundle', 'train skill', 'variant sweep'].map((tab) => (
              <button
                key={tab}
                type="button"
                className={`kp-button ${activeTab === tab ? 'kp-button-primary' : 'kp-button-secondary'}`}
                onClick={() => setActiveTab(tab)}
                disabled={skillLoading || sweepLoading}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {activeTab === 'train skill' && (
            <div className="kp-flex-col kp-gap-2 kp-mt-3">
              <label className="kp-label">Skill description</label>
              <input
                className="kp-input"
                value={skillDesc}
                onChange={(e) => setSkillDesc(e.target.value)}
                disabled={skillLoading}
              />
              <div className="kp-flex kp-gap-2">
                <button
                  type="button"
                  className="kp-button kp-button-secondary"
                  onClick={handleRecommendSkill}
                  disabled={skillLoading}
                >
                  Recommend scene
                </button>
                <button
                  type="button"
                  className="kp-button kp-button-primary"
                  onClick={handleTrainSkill}
                  disabled={skillLoading || !report?.valid}
                >
                  {skillLoading ? 'Training…' : 'Train skill'}
                </button>
              </div>
              {recommended && (
                <div className="kp-tag" style={{ width: 'fit-content' }}>
                  Recommended: {recommended.template} ({(recommended.confidence * 100).toFixed(0)}%)
                </div>
              )}
              {skillResult && (
                <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
                  <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                    <span className="kp-label">Success rate</span>
                    <span className="kp-mono">{(skillResult.success_rate * 100).toFixed(1)}%</span>
                  </div>
                  <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                    <span className="kp-label">Mean final distance</span>
                    <span className="kp-mono">{skillResult.mean_final_distance_m?.toFixed(4)} m</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'variant sweep' && (
            <div className="kp-flex-col kp-gap-2 kp-mt-3">
              <label className="kp-label">Parameter ranges (JSON)</label>
              <textarea
                className="kp-input"
                rows={4}
                placeholder='{"length": {"relative_min": -0.1, "relative_max": 0.1}}'
                value={sweepRanges}
                onChange={(e) => setSweepRanges(e.target.value)}
                disabled={sweepLoading}
              />
              <button
                type="button"
                className="kp-button kp-button-primary"
                onClick={handleVariantSweep}
                disabled={sweepLoading || !report?.valid}
              >
                {sweepLoading ? 'Sweeping…' : 'Run variant sweep'}
              </button>
              {sweepResult && (
                <div className="kp-flex-col kp-gap-1">
                  <span className="kp-label">
                    Valid variants: {sweepResult.aggregate?.valid_count} / {sweepResult.aggregate?.n_variants}
                  </span>
                  <span className="kp-label">
                    Stability pass: {sweepResult.aggregate?.stability_success_count}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
