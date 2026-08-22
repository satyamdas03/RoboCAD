import { useEffect, useState } from 'react'
import PromptInput from './components/PromptInput.jsx'
import StatusPanel from './components/StatusPanel.jsx'
import STLViewer from './components/STLViewer.jsx'
import ParameterList from './components/ParameterList.jsx'
import DownloadLinks from './components/DownloadLinks.jsx'
import HistorySidebar from './components/HistorySidebar.jsx'
import { checkHealth, generateDesign, listDesigns, loadDesign } from './api.js'

export default function App() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [designs, setDesigns] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [apiReady, setApiReady] = useState(false)

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
          <PromptInput onGenerate={handleGenerate} loading={loading} />
          <StatusPanel result={result} error={error} loading={loading} />
          <STLViewer url={result?.export_urls?.stl} />
          <DownloadLinks exportUrls={result?.export_urls} />
          <ParameterList parameters={result?.parameters} />
        </div>

        <div>
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
