import { useEffect, useState } from 'react'
import { getMorphologySearch, listMorphologyTemplates, runMorphologySearch, simulateMorphologyCandidate } from '../api.js'

const DEFAULT_BOUNDS = {
  humanoid: {
    robot_height: { min: 600, max: 1400, step: 200 },
    thigh_length: { min: 150, max: 300, step: 50 },
    shin_length: { min: 150, max: 300, step: 50 },
    upper_arm_length: { min: 100, max: 250, step: 50 },
    forearm_length: { min: 100, max: 250, step: 50 },
  },
  quadruped: {
    robot_height: { min: 300, max: 800, step: 100 },
    thigh_length: { min: 100, max: 220, step: 40 },
    shin_length: { min: 100, max: 220, step: 40 },
  },
  manipulator_on_base: {
    reach: { min: 400, max: 1200, step: 200 },
    link1_length: { min: 150, max: 400, step: 50 },
    link2_length: { min: 150, max: 400, step: 50 },
    link3_length: { min: 100, max: 300, step: 50 },
  },
}

export default function MorphologyPanel() {
  const [templates, setTemplates] = useState([])
  const [selected, setSelected] = useState('humanoid')
  const [bounds, setBounds] = useState(DEFAULT_BOUNDS.humanoid)
  const [nMax, setNMax] = useState(32)
  const [seed, setSeed] = useState(0)
  const [payloadKg, setPayloadKg] = useState(5)
  const [searching, setSearching] = useState(false)
  const [searchId, setSearchId] = useState(null)
  const [results, setResults] = useState(null)
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [simulating, setSimulating] = useState(false)
  const [simulateReport, setSimulateReport] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listMorphologyTemplates()
      .then((data) => {
        setTemplates(data.templates || [])
      })
      .catch(() => setTemplates([]))
  }, [])

  useEffect(() => {
    setSelected('humanoid')
    setBounds(DEFAULT_BOUNDS.humanoid)
    setResults(null)
    setSelectedCandidate(null)
    setSimulateReport(null)
    setError(null)
  }, [])

  useEffect(() => {
    setBounds(DEFAULT_BOUNDS[selected] || {})
    setResults(null)
    setSelectedCandidate(null)
    setSimulateReport(null)
  }, [selected])

  function updateBound(name, field, value) {
    setBounds((prev) => ({
      ...prev,
      [name]: { ...prev[name], [field]: value },
    }))
  }

  async function handleSearch() {
    setSearching(true)
    setError(null)
    setResults(null)
    setSelectedCandidate(null)
    setSimulateReport(null)
    try {
      const dimensions = Object.entries(bounds).map(([name, b]) => ({
        name,
        min: Number(b.min),
        max: Number(b.max),
        step: Number(b.step),
      }))
      const data = await runMorphologySearch({
        template: selected,
        dimensions,
        nMax: Number(nMax),
        seed: Number(seed),
        payloadKg: Number(payloadKg),
      })
      setSearchId(data.search_id)
      setResults(data.candidates)
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
    }
  }

  async function handleSimulate(candidate) {
    if (!searchId) return
    setSimulating(true)
    setError(null)
    setSimulateReport(null)
    try {
      const data = await simulateMorphologyCandidate(searchId, candidate.candidate_id, {
        worldTemplate: selected === 'manipulator_on_base' ? 'pick_place' : 'walker',
        nIters: 5,
        popSize: 20,
        evalEpisodes: 5,
        seed: Number(seed),
      })
      setSimulateReport(data.brain_smoke_test)
      setSelectedCandidate(candidate)
    } catch (err) {
      setError(err.message)
    } finally {
      setSimulating(false)
    }
  }

  return (
    <section className="kp-panel" aria-labelledby="morphology-heading">
      <div className="kp-panel-header">
        <h3 id="morphology-heading" className="kp-panel-title">Morphology Co-Design Lab</h3>
      </div>

      <div className="kp-flex-col kp-gap-2">
        <label className="kp-label">Robot template</label>
        <select
          className="kp-input"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={searching || simulating}
        >
          {templates.map((t) => (
            <option key={t.name} value={t.name}>{t.name}</option>
          ))}
        </select>

        <div className="kp-flex kp-gap-2">
          <div className="kp-flex-col kp-gap-1" style={{ flex: 1 }}>
            <label className="kp-label">Candidates</label>
            <input
              className="kp-input"
              type="number"
              min={4}
              max={128}
              value={nMax}
              onChange={(e) => setNMax(e.target.value)}
              disabled={searching || simulating}
            />
          </div>
          <div className="kp-flex-col kp-gap-1" style={{ flex: 1 }}>
            <label className="kp-label">Seed</label>
            <input
              className="kp-input"
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              disabled={searching || simulating}
            />
          </div>
          <div className="kp-flex-col kp-gap-1" style={{ flex: 1 }}>
            <label className="kp-label">Payload (kg)</label>
            <input
              className="kp-input"
              type="number"
              min={0.1}
              step={0.5}
              value={payloadKg}
              onChange={(e) => setPayloadKg(e.target.value)}
              disabled={searching || simulating}
            />
          </div>
        </div>

        <div className="kp-flex-col kp-gap-1">
          <span className="kp-label">Search bounds</span>
          <div className="kp-flex-col kp-gap-1" style={{ maxHeight: '160px', overflowY: 'auto' }}>
            {Object.entries(bounds).map(([name, b]) => (
              <div key={name} className="kp-flex kp-gap-2 kp-align-center">
                <span className="kp-small" style={{ width: '140px' }}>{name}</span>
                <input
                  className="kp-input kp-small"
                  type="number"
                  value={b.min}
                  onChange={(e) => updateBound(name, 'min', e.target.value)}
                  disabled={searching || simulating}
                />
                <input
                  className="kp-input kp-small"
                  type="number"
                  value={b.max}
                  onChange={(e) => updateBound(name, 'max', e.target.value)}
                  disabled={searching || simulating}
                />
                <input
                  className="kp-input kp-small"
                  type="number"
                  value={b.step}
                  onChange={(e) => updateBound(name, 'step', e.target.value)}
                  disabled={searching || simulating}
                />
              </div>
            ))}
          </div>
        </div>

        <button
          type="button"
          className="kp-button kp-button-primary"
          onClick={handleSearch}
          disabled={searching || simulating}
        >
          {searching ? 'Searching…' : 'Run morphology search'}
        </button>
      </div>

      {error && <div className="kp-alert kp-alert-error kp-mt-2">{error}</div>}

      {results && (
        <div className="kp-flex-col kp-gap-2 kp-mt-3">
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-label">Ranked candidates</span>
            <span className="kp-small kp-mono">{results.length} found</span>
          </div>
          <div style={{ maxHeight: '280px', overflowY: 'auto', border: '1px solid var(--kp-border)', borderRadius: 'var(--kp-radius-md)' }}>
            <table className="kp-table kp-small">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Score</th>
                  <th>Stability</th>
                  <th>Gait</th>
                  <th>Reach (mm)</th>
                  <th>Actuator</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {results.map((c) => (
                  <tr key={c.candidate_id} className={selectedCandidate?.candidate_id === c.candidate_id ? 'selected' : ''}>
                    <td className="kp-mono">{c.rank}</td>
                    <td className="kp-mono">{c.composite_score.toFixed(3)}</td>
                    <td className="kp-mono">{c.scores.stability.toFixed(2)}</td>
                    <td className="kp-mono">{c.scores.gait.toFixed(2)}</td>
                    <td className="kp-mono">{Math.round(c.scores.workspace_reach_mm)}</td>
                    <td className="kp-mono">{c.scores.actuator.toFixed(2)}</td>
                    <td>
                      <button
                        type="button"
                        className="kp-button kp-button-secondary"
                        onClick={() => handleSimulate(c)}
                        disabled={simulating}
                      >
                        Simulate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {simulateReport && (
        <div className="kp-flex-col kp-gap-2 kp-mt-3" style={{ padding: 'var(--kp-space-2)', background: 'var(--kp-surface-container)', borderRadius: 'var(--kp-radius-md)', border: '1px solid var(--kp-border)' }}>
          <span className="kp-label">Brain smoke test</span>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-small">Success rate</span>
            <span className={`kp-badge ${simulateReport.success ? 'kp-badge-success' : 'kp-badge-error'}`}>
              {(simulateReport.success_rate * 100).toFixed(0)}%
            </span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-small">Mean reward</span>
            <span className="kp-mono kp-small">{simulateReport.mean_reward.toFixed(4)}</span>
          </div>
          <div className="kp-flex kp-justify-between kp-align-center">
            <span className="kp-small">Mean final distance</span>
            <span className="kp-mono kp-small">{simulateReport.mean_final_distance.toFixed(4)}</span>
          </div>
        </div>
      )}
    </section>
  )
}
