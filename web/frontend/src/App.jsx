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
import { checkHealth, generateDesign, listDesigns, loadDesign, regenerateDesign, remixDesign, updateDesignTags, guessParameter } from './api.js'

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
      const data = await regenerateDesign(selectedId, updates)
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
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '1rem', fontFamily: 'system-ui, sans-serif' }}>
      <header style={{ marginBottom: '1rem' }}>
        <h1>🤖 RoboCAD</h1>
        <p>AI-powered parametric CAD for robotics. Type a part, get a build123d model + STL viewer.</p>
        {!apiReady && (
          <p style={{ color: '#b00000' }}>
            ⚠️ Backend not reachable. Make sure uvicorn is running on port 8000.
          </p>
        )}
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1rem' }}>
        <div>
          <PromptInput onGenerate={handleGenerate} loading={loading} seedPrompt={seedPrompt} />
          <StatusPanel result={result} error={error} loading={loading} />
          <STLViewer
            url={result?.export_urls?.stl}
            onFaceClick={handleFaceClick}
            selectedFace={selectedFace}
            guessResult={guessResult}
          />
          <DownloadLinks exportUrls={result?.export_urls} />
          <ParameterList
            parameters={result?.parameters}
            selectedParameter={selectedParameter}
            onRegenerate={handleRegenerate}
            loading={loading}
            nudge={nudge}
          />
          {selectedId && (
            <>
              <TagEditor tags={result?.tags || []} onUpdate={handleUpdateTags} />
              <RemixPanel designId={selectedId} onRemix={handleRemix} loading={loading} />
            </>
          )}
        </div>

        <div>
          <ComponentLibrary onPrompt={handleLoadComponentPrompt} loading={loading} />
          <HistorySidebar
            designs={designs}
            selectedId={selectedId}
            onSelect={handleSelect}
            onRefresh={refreshHistory}
          />
        </div>
      </div>
    </div>
  )
}
