import { useEffect, useState } from 'react'
import { composeScene, getSceneReport, exportUrl } from '../api.js'

const TEMPLATES = [
  { key: 'gripper_cube_grasp', label: 'Gripper → cube grasp' },
  { key: 'bracket_hook_hang', label: 'Bracket → hook hang' },
  { key: 'wedge_push_block', label: 'Wedge → push block' },
  { key: 'peg_insertion', label: 'Peg → hole insertion' },
]

export default function SceneTemplatePanel({ designId }) {
  const [template, setTemplate] = useState('gripper_cube_grasp')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setError(null)
    setLoading(true)
    getSceneReport(designId, template)
      .then((data) => setReport(data))
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }, [designId, template])

  async function handleCompose() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await composeScene(designId, { template })
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const sceneUrl = report?.scene_url ? exportUrl(report.scene_url) : null
  const runtimeOk = report?.runtime_ok ?? report?.scene?.runtime_ok

  if (!designId) return null

  return (
    <section className="kp-panel" aria-labelledby="scene-heading">
      <div className="kp-panel-header">
        <h3 id="scene-heading" className="kp-panel-title">Scene template</h3>
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

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleCompose}
          disabled={loading}
        >
          {loading ? 'Composing scene…' : 'Compose scene'}
        </button>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {report && (
        <div className="kp-flex-col kp-gap-3 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Scene status</span>
            <span className={`kp-badge ${runtimeOk ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {runtimeOk ? 'Loadable' : 'Check failed'}
            </span>
          </div>

          {runtimeOk && (
            <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--kp-space-3)' }}>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Bodies</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.runtime_info?.scene_nbody ?? report.scene?.runtime_info?.scene_nbody ?? '—'}
                </span>
              </div>
              <div className="kp-flex-col kp-gap-1" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
                <span className="kp-label">Template</span>
                <span className="kp-mono" style={{ fontSize: '0.9rem', color: 'var(--kp-on-surface)' }}>
                  {report.template ?? report.scene?.template ?? template}
                </span>
              </div>
            </div>
          )}

          {sceneUrl && (
            <a
              href={sceneUrl}
              download
              className="kp-button kp-button-secondary"
              style={{ width: 'fit-content' }}
            >
              Download scene (.mjcf)
            </a>
          )}
        </div>
      )}
    </section>
  )
}
