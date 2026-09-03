import { useEffect, useState } from 'react'
import { buildWorld, getWorldReport, randomizeWorld, replayWorld, exportUrl } from '../api.js'

const TEMPLATES = [
  { key: 'pick_place', label: 'Pick & place' },
  { key: 'push', label: 'Push block' },
  { key: 'walker', label: 'Walker' },
  { key: 'drone_hover', label: 'Drone hover' },
  { key: 'humanoid_stand', label: 'Humanoid stand' },
]

const MATERIALS = ['PLA', 'PETG', 'ABS', 'aluminum', 'steel']

export default function WorldBuilderPanel({ designId }) {
  const [template, setTemplate] = useState('pick_place')
  const [material, setMaterial] = useState('PLA')
  const [tolerance, setTolerance] = useState(0.1)
  const [randomize, setRandomize] = useState(false)
  const [seed, setSeed] = useState('')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setError(null)
    setLoading(true)
    getWorldReport(designId, template)
      .then((data) => setReport(data))
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }, [designId, template])

  async function handleBuild() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await buildWorld(designId, {
        template,
        material,
        tolerance,
        randomize,
        seed: seed ? Number(seed) : null,
      })
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleRandomize() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await randomizeWorld(designId, { seed: seed ? Number(seed) : null })
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleReplay() {
    if (!designId) return
    setLoading(true)
    setError(null)
    try {
      const data = await replayWorld(designId, { durationSeconds: 3.0, fps: 10.0 })
      setReport((prev) => (prev ? { ...prev, replay: data.replay } : { replay: data.replay }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const runtimeOk = report?.runtime_ok ?? report?.world?.runtime_ok
  const worldUrl = report?.world_url ? exportUrl(report.world_url) : null
  const isaacUrl = report?.isaac_json_url ? exportUrl(report.isaac_json_url) : null
  const replay = report?.replay

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="world-heading">
      <div className="kp-panel-header">
        <h3 id="world-heading" className="kp-panel-title">World builder</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Template</label>
        <select
          className="kp-input"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          disabled={loading}
        >
          {TEMPLATES.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>

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

        <label className="kp-flex kp-align-center kp-gap-1 kp-label">
          <input
            type="checkbox"
            checked={randomize}
            onChange={(e) => setRandomize(e.target.checked)}
            disabled={loading}
          />
          Domain randomization
        </label>

        <label className="kp-label">Seed (optional)</label>
        <input
          className="kp-input"
          type="number"
          value={seed}
          onChange={(e) => setSeed(e.target.value)}
          disabled={loading}
          placeholder="random"
        />

        <div className="kp-flex kp-gap-2 kp-flex-wrap">
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleBuild}
            disabled={loading}
          >
            {loading ? 'Building…' : 'Build world'}
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleRandomize}
            disabled={loading}
          >
            Randomize
          </button>
          <button
            type="button"
            className="kp-button kp-button-secondary"
            onClick={handleReplay}
            disabled={loading || !runtimeOk}
          >
            Replay
          </button>
        </div>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">World status</span>
            <span className={`kp-badge ${runtimeOk ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {runtimeOk ? 'Loadable' : 'Check failed'}
            </span>
          </div>

          {runtimeOk && (
            <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Bodies</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.runtime_info?.nbody ?? report.world?.runtime_info?.nbody ?? '—'}
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Randomized</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.randomized ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          )}

          {replay && (
            <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
              <span className="kp-label">Replay</span>
              <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                {replay.success ? `OK (${replay.times?.length ?? 0} samples)` : 'Failed'}
              </span>
            </div>
          )}

          <div className="kp-flex kp-gap-2 kp-flex-wrap">
            {worldUrl && (
              <a href={worldUrl} download className="kp-button kp-button-secondary" style={{ width: 'fit-content' }}>
                Download world (.mjcf)
              </a>
            )}
            {isaacUrl && (
              <a href={isaacUrl} download className="kp-button kp-button-secondary" style={{ width: 'fit-content' }}>
                Isaac JSON
              </a>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
