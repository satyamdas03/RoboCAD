import { useEffect, useState } from 'react'
import PromptInput from './components/PromptInput.jsx'
import StatusPanel from './components/StatusPanel.jsx'
import STLViewer from './components/STLViewer.jsx'
import ParameterList from './components/ParameterList.jsx'
import DownloadLinks from './components/DownloadLinks.jsx'
import HistorySidebar from './components/HistorySidebar.jsx'
import TagEditor from './components/TagEditor.jsx'
import RemixPanel from './components/RemixPanel.jsx'
import ComponentLibrary from './components/ComponentLibrary.jsx'
import ManufacturingReport from './components/ManufacturingReport.jsx'
import DFMReport from './components/DFMReport.jsx'
import ToleranceReport from './components/ToleranceReport.jsx'
import FEAPanel from './components/FEAPanel.jsx'
import OnshapeUpload from './components/OnshapeUpload.jsx'
import FeatureTreePanel from './components/FeatureTreePanel.jsx'
import AssemblyPanel from './components/AssemblyPanel.jsx'
import SimulatePanel from './components/SimulatePanel.jsx'
import SceneTemplatePanel from './components/SceneTemplatePanel.jsx'
import {
  checkHealth,
  generateDesign,
  listDesigns,
  loadDesign,
  regenerateDesign,
  regenerateFromFeatureTree,
  remixDesign,
  updateDesignTags,
  guessParameter,
} from './api.js'

export default function App() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [designs, setDesigns] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [apiReady, setApiReady] = useState(false)
  const [seedPrompt, setSeedPrompt] = useState('')
  const [selectedFace, setSelectedFace] = useState(null)
  const [selectedParameter, setSelectedParameter] = useState(null)
  const [guessResult, setGuessResult] = useState(null)
  const [nudge, setNudge] = useState(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    checkHealth()
      .then(() => setApiReady(true))
      .catch(() => setApiReady(false))
    refreshHistory()
  }, [])

  async function refreshHistory() {
    try {
      const data = await listDesigns()
      setDesigns(data)
    } catch (err) {
      console.error('Failed to load history', err)
    }
  }

  async function handleGenerate({ prompt, max_retries, model }) {
    setLoading(true)
    setError(null)
    setResult(null)
    clearFaceSelection()
    try {
      const data = await generateDesign({ prompt, max_retries, model })
      setResult(data)
      setSelectedId(data.design_id)
      await refreshHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSelect(id) {
    setLoading(true)
    setError(null)
    clearFaceSelection()
    try {
      const data = await loadDesign(id)
      setResult({
        ...data,
        design_id: data.id,
        export_urls: data.export_urls,
      })
      setSelectedId(id)
      setSidebarOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleRegenerate(updates) {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    clearFaceSelection()
    try {
      const hasFeatureTree = result?.feature_tree != null
      const data = hasFeatureTree
        ? await regenerateFromFeatureTree(selectedId, updates)
        : await regenerateDesign(selectedId, updates)
      setResult({
        ...data,
        design_id: data.design_id,
        export_urls: data.export_urls,
      })
      await refreshHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpdateTags(tags) {
    if (!selectedId) return
    try {
      await updateDesignTags(selectedId, tags)
      await refreshHistory()
    } catch (err) {
      setError(err.message)
    }
  }

  function handleLoadComponentPrompt(prompt) {
    setSeedPrompt(prompt)
  }

  async function handleRemix({ prompt, max_retries, model }) {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    setResult(null)
    clearFaceSelection()
    try {
      const data = await remixDesign(selectedId, { prompt, max_retries, model })
      setResult(data)
      setSelectedId(data.design_id)
      await refreshHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function clearFaceSelection() {
    setSelectedFace(null)
    setSelectedParameter(null)
    setGuessResult(null)
    setNudge(null)
  }

  async function handleFaceClick({ faceIndex, faceNormal, centroid }) {
    if (!selectedId) return
    setSelectedFace(faceIndex)
    try {
      const guess = await guessParameter(selectedId, { faceNormal, faceCentroid: centroid })
      setGuessResult(guess)
      if (guess.guessed_parameter) {
        setSelectedParameter(guess.guessed_parameter)
      }
    } catch (err) {
      console.error('Failed to guess parameter from face', err)
      setError('Could not guess parameter for that face.')
    }
  }

  return (
    <div className="kp-app">
      <header className="kp-header">
        <div className="kp-header-left">
          <div className="kp-logo" aria-label="RoboCAD">
            <span className="kp-logo-mark" aria-hidden="true">◈</span>
            <span>RoboCAD</span>
          </div>
          <span className="kp-tagline">AI parametric CAD for robotics</span>
        </div>

        <div className="kp-search" role="search">
          <span aria-hidden="true" className="kp-text-subtle">⌕</span>
          <input
            type="text"
            placeholder="Search history and components"
            aria-label="Search history and components"
          />
          <span className="kp-mono kp-text-subtle" style={{ fontSize: '0.65rem', border: '1px solid var(--kp-outline-variant)', padding: '0 0.25rem', borderRadius: '2px' }}>Ctrl K</span>
        </div>

        <div className="kp-header-right">
          <div className="kp-flex kp-align-center kp-gap-2" style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid var(--kp-outline-variant)', background: 'var(--kp-surface-container)' }}>
            <span className={`kp-glow-dot ${apiReady ? '' : 'kp-badge-error'}`} style={{ background: apiReady ? 'var(--kp-primary-container)' : 'var(--kp-error)' }}></span>
            <span className="kp-mono" style={{ fontSize: '0.75rem', color: 'var(--kp-on-surface)' }}>
              {apiReady ? 'Backend online' : 'Backend offline'}
            </span>
          </div>
          <button
            type="button"
            className="kp-button kp-button-icon kp-button-ghost"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle sidebar"
            title="Toggle sidebar"
          >
            ☰
          </button>
          <button
            type="button"
            className="kp-button kp-button-icon kp-button-ghost"
            onClick={() => setInspectorOpen(!inspectorOpen)}
            aria-label="Toggle inspector"
            title="Toggle inspector"
          >
            ℹ
          </button>
          <button
            type="button"
            className="kp-button kp-button-icon kp-button-ghost"
            onClick={() => {
              clearFaceSelection()
              setResult(null)
              setSelectedId(null)
              setError(null)
              setSeedPrompt('')
            }}
            aria-label="New design"
            title="New design"
          >
            +
          </button>
        </div>
      </header>

      <div className="kp-workspace">
        <aside className={`kp-sidebar ${sidebarOpen ? 'open' : ''}`}>
          <ComponentLibrary onPrompt={handleLoadComponentPrompt} loading={loading} />
          <div className="kp-section-divider"></div>
          <HistorySidebar
            designs={designs}
            selectedId={selectedId}
            onSelect={handleSelect}
            onRefresh={refreshHistory}
          />
        </aside>

        <main className="kp-main">
          <PromptInput onGenerate={handleGenerate} loading={loading} seedPrompt={seedPrompt} />

          <StatusPanel result={result} error={error} loading={loading} />

          <STLViewer
            url={result?.export_urls?.stl}
            onFaceClick={handleFaceClick}
            selectedFace={selectedFace}
            guessResult={guessResult}
            designId={result?.design_id}
          />

          <div className="kp-flex kp-justify-between kp-align-center">
            <DownloadLinks exportUrls={result?.export_urls} />
          </div>

          <ParameterList
            parameters={result?.parameters}
            selectedParameter={selectedParameter}
            onRegenerate={handleRegenerate}
            loading={loading}
            nudge={nudge}
          />

          {selectedId && (
            <div className="kp-panels-grid">
              <AssemblyPanel designId={selectedId} />
              <SimulatePanel designId={selectedId} />
              <SceneTemplatePanel designId={selectedId} />
              <FeatureTreePanel
                designId={selectedId}
                parameters={result?.parameters}
                onRegenerate={handleRegenerate}
                loading={loading}
              />
              <ManufacturingReport designId={selectedId} />
              <DFMReport designId={selectedId} />
              <ToleranceReport designId={selectedId} designs={designs} />
              <FEAPanel designId={selectedId} />
              <OnshapeUpload designId={selectedId} prompt={result?.prompt} />
              <TagEditor tags={result?.tags || []} onUpdate={handleUpdateTags} />
              <RemixPanel designId={selectedId} onRemix={handleRemix} loading={loading} />
            </div>
          )}
        </main>

        <aside className={`kp-inspector ${inspectorOpen ? 'open' : ''}`}>
          <div className="kp-panel" style={{ borderRadius: 0, border: 'none', borderBottom: '1px solid var(--kp-outline-variant)', boxShadow: 'none' }}>
            <div className="kp-panel-header">
              <h3 className="kp-panel-title">Design metadata</h3>
            </div>
            <div className="kp-flex-col kp-gap-2 kp-mono" style={{ fontSize: '0.75rem', color: 'var(--kp-on-surface-variant)' }}>
              {result?.design_id && (
                <div className="kp-flex kp-justify-between">
                  <span>ID</span>
                  <span className="kp-text-primary">#{result.design_id.slice(0, 8)}</span>
                </div>
              )}
              {result?.model && (
                <div className="kp-flex kp-justify-between">
                  <span>Model</span>
                  <span>{result.model}</span>
                </div>
              )}
              {result?.attempts_used != null && (
                <div className="kp-flex kp-justify-between">
                  <span>Attempts</span>
                  <span>{result.attempts_used}/{result.max_retries + 1}</span>
                </div>
              )}
              {result?.latency_seconds != null && (
                <div className="kp-flex kp-justify-between">
                  <span>Latency</span>
                  <span>{result.latency_seconds}s</span>
                </div>
              )}
              <div className="kp-flex kp-justify-between">
                <span>Status</span>
                <span className={result?.success ? 'kp-text-primary' : 'kp-text-muted'}>
                  {result?.success ? 'Success' : result ? 'Failed' : 'Idle'}
                </span>
              </div>
            </div>
          </div>

          <div className="kp-panel" style={{ borderRadius: 0, border: 'none', borderBottom: '1px solid var(--kp-outline-variant)', boxShadow: 'none' }}>
            <div className="kp-panel-header">
              <h3 className="kp-panel-title">Validation</h3>
            </div>
            {result?.validation ? (
              <div className="kp-flex-col kp-gap-2" style={{ fontSize: '0.8rem' }}>
                <div className="kp-flex kp-justify-between kp-align-center">
                  <span className="kp-text-muted">Manifold</span>
                  <span className={`kp-badge ${result.validation.manifold ? 'kp-badge-success' : 'kp-badge-error'}`}>
                    {result.validation.manifold ? 'OK' : 'FAIL'}
                  </span>
                </div>
                <div className="kp-flex kp-justify-between kp-align-center">
                  <span className="kp-text-muted">Watertight</span>
                  <span className={`kp-badge ${result.validation.watertight ? 'kp-badge-success' : 'kp-badge-error'}`}>
                    {result.validation.watertight ? 'OK' : 'FAIL'}
                  </span>
                </div>
                {result.validation.volume_mm3 != null && (
                  <div className="kp-flex kp-justify-between">
                    <span className="kp-text-muted">Volume</span>
                    <span className="kp-mono">{result.validation.volume_mm3.toFixed(1)} mm³</span>
                  </div>
                )}
                {result.validation.bounds_mm && (
                  <div className="kp-flex kp-justify-between">
                    <span className="kp-text-muted">Bounds</span>
                    <span className="kp-mono">{result.validation.bounds_mm.map((n) => n.toFixed(1)).join('×')} mm</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="kp-text-muted kp-small">No validation data yet.</p>
            )}
          </div>

          <div className="kp-panel" style={{ borderRadius: 0, border: 'none', borderBottom: '1px solid var(--kp-outline-variant)', boxShadow: 'none' }}>
            <div className="kp-panel-header">
              <h3 className="kp-panel-title">Selected face</h3>
            </div>
            {guessResult ? (
              <div className="kp-flex-col kp-gap-2" style={{ fontSize: '0.8rem' }}>
                <div className="kp-flex kp-justify-between">
                  <span className="kp-text-muted">Parameter</span>
                  <span className="kp-mono kp-text-primary">{guessResult.guessed_parameter}</span>
                </div>
                <div className="kp-flex kp-justify-between">
                  <span className="kp-text-muted">Suggested</span>
                  <span className="kp-mono">{guessResult.suggested_value}{guessResult.unit || 'mm'}</span>
                </div>
                <div className="kp-flex kp-justify-between">
                  <span className="kp-text-muted">Axis</span>
                  <span className="kp-mono">{guessResult.axis}</span>
                </div>
                <div className="kp-flex kp-justify-between">
                  <span className="kp-text-muted">Confidence</span>
                  <span className="kp-mono">{(guessResult.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ) : (
              <p className="kp-text-muted kp-small">Click a face in the viewer to guess its controlling parameter.</p>
            )}
          </div>

          <div className="kp-panel" style={{ borderRadius: 0, border: 'none', boxShadow: 'none' }}>
            <div className="kp-panel-header">
              <h3 className="kp-panel-title">Quick export</h3>
            </div>
            <DownloadLinks exportUrls={result?.export_urls} />
          </div>
        </aside>
      </div>
    </div>
  )
}
