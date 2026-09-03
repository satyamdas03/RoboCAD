import { useEffect, useState } from 'react'
import { getBrainReport, replayBrainAttention, trainBrain } from '../api.js'

export default function BrainTrainingPanel({ designId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [nIters, setNIters] = useState(15)
  const [popSize, setPopSize] = useState(40)
  const [evalEpisodes, setEvalEpisodes] = useState(10)
  const [successRateThreshold, setSuccessRateThreshold] = useState(0.7)
  const [seed, setSeed] = useState(42)
  const [smoke, setSmoke] = useState(null)

  useEffect(() => {
    if (!designId) return
    setReport(null)
    setError(null)
    setLoading(true)
    getBrainReport(designId)
      .then((data) => setReport(data.brain))
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }, [designId])

  async function handleTrain() {
    if (!designId) return
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const data = await trainBrain(designId, {
        nIters,
        popSize,
        evalEpisodes,
        successRateThreshold,
        seed,
      })
      setReport({
        success: data.success,
        success_rate: data.success_rate,
        mean_reward: data.mean_reward,
        mean_final_distance: data.mean_final_distance,
        best_training_reward: data.best_training_reward,
        policy_architecture: data.policy_architecture,
        created_at: new Date().toISOString(),
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSmoke() {
    if (!designId) return
    setLoading(true)
    setError(null)
    try {
      const data = await replayBrainAttention(designId)
      setSmoke(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="kp-panel">
      <div className="kp-panel-header">
        <h3 className="kp-panel-title">🧠 Brain training</h3>
        <span className="kp-badge kp-badge-secondary">Phase 25</span>
      </div>

      <div className="kp-flex-col kp-gap-2 kp-mt-2">
        <p className="kp-help-text">
          Train an attention-aware policy using the world-model and compute-budget
          ideas from high-performance AI chip co-design. The trainer runs entirely in
          the browser-facing backend with NumPy, no PyTorch/JAX required.
        </p>

        <div className="kp-grid-2">
          <div className="kp-flex-col kp-gap-1">
            <label className="kp-label">CEM iterations</label>
            <input
              type="number"
              className="kp-input"
              min={1}
              max={100}
              value={nIters}
              onChange={(e) => setNIters(Number(e.target.value))}
            />
          </div>
          <div className="kp-flex-col kp-gap-1">
            <label className="kp-label">Population size</label>
            <input
              type="number"
              className="kp-input"
              min={4}
              max={200}
              value={popSize}
              onChange={(e) => setPopSize(Number(e.target.value))}
            />
          </div>
          <div className="kp-flex-col kp-gap-1">
            <label className="kp-label">Eval episodes</label>
            <input
              type="number"
              className="kp-input"
              min={1}
              max={50}
              value={evalEpisodes}
              onChange={(e) => setEvalEpisodes(Number(e.target.value))}
            />
          </div>
          <div className="kp-flex-col kp-gap-1">
            <label className="kp-label">Success threshold</label>
            <input
              type="number"
              className="kp-input"
              min={0}
              max={1}
              step={0.05}
              value={successRateThreshold}
              onChange={(e) => setSuccessRateThreshold(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="kp-flex kp-gap-2 kp-mt-1">
          <button
            className="kp-button kp-button-primary"
            onClick={handleTrain}
            disabled={loading || !designId}
          >
            {loading ? 'Training…' : 'Train attention brain'}
          </button>
          <button
            className="kp-button kp-button-secondary"
            onClick={handleSmoke}
            disabled={loading || !designId}
          >
            Attention smoke test
          </button>
        </div>

        {error && <div className="kp-error">{error}</div>}

        {report && (
          <div className="kp-result-card kp-mt-2">
            <div className="kp-flex kp-justify-between kp-align-center">
              <strong>Training complete</strong>
              <span
                className={`kp-badge ${
                  report.success ? 'kp-badge-success' : 'kp-badge-warning'
                }`}
              >
                {report.success ? 'Success' : 'Below threshold'}
              </span>
            </div>
            <div className="kp-mono kp-flex-col kp-gap-1 kp-mt-2" style={{ fontSize: '0.8rem' }}>
              <div className="kp-flex kp-justify-between">
                <span>Success rate</span>
                <span>{(report.success_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Mean reward</span>
                <span>{report.mean_reward?.toFixed(3)}</span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Mean final distance</span>
                <span>{report.mean_final_distance?.toFixed(3)}</span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Best training reward</span>
                <span>{report.best_training_reward?.toFixed(3)}</span>
              </div>
              {report.policy_architecture && (
                <div className="kp-flex kp-justify-between">
                  <span>Policy</span>
                  <span>
                    {report.policy_architecture.input_dim}→
                    {report.policy_architecture.hidden_dim}→
                    {report.policy_architecture.output_dim}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {smoke && (
          <div className="kp-result-card kp-mt-2">
            <strong>Attention smoke test</strong>
            <div className="kp-mono kp-flex-col kp-gap-1 kp-mt-1" style={{ fontSize: '0.8rem' }}>
              <div className="kp-flex kp-justify-between">
                <span>TOPS</span>
                <span>{smoke.budget?.tops}</span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Power</span>
                <span>{smoke.budget?.power_w} W</span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Latency</span>
                <span>{smoke.budget?.latency_ms} ms</span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Active dims</span>
                <span>
                  {smoke.budget?.active_dimensions} / 6
                </span>
              </div>
              <div className="kp-flex kp-justify-between">
                <span>Zero-policy reward</span>
                <span>{smoke.zero_policy_rollout?.reward?.toFixed(3)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
