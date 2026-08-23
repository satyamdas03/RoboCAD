import { useEffect, useState } from 'react'
import { listOnshapeDocuments, uploadToOnshape } from '../api.js'

export default function OnshapeUpload({ designId, prompt }) {
  const [mode, setMode] = useState('new')
  const [documentName, setDocumentName] = useState('')
  const [documents, setDocuments] = useState([])
  const [selectedDoc, setSelectedDoc] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (mode !== 'existing') return
    setLoading(true)
    listOnshapeDocuments()
      .then((data) => setDocuments(data.documents || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [mode])

  useEffect(() => {
    if (prompt) {
      setDocumentName(`RoboCAD ${prompt.slice(0, 40)}`)
    }
  }, [prompt])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!designId) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      let payload = {}
      if (mode === 'existing') {
        const [docId, wsId] = selectedDoc.split('|')
        payload = { documentId: docId, workspaceId: wsId }
      } else {
        payload = { documentName: documentName || `RoboCAD ${designId.slice(0, 8)}` }
      }
      const data = await uploadToOnshape(designId, payload)
      setResult(data.onshape)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!designId) return null

  return (
    <section className="rc-panel" aria-labelledby="onshape-heading">
      <h3 id="onshape-heading" className="rc-panel-title">Onshape</h3>
      <p className="rc-panel-subtitle">Upload this design's STEP file to Onshape.</p>

      <form onSubmit={handleSubmit}>
        <div className="rc-flex rc-gap-4 rc-flex-wrap rc-mt-2">
          <label className="rc-flex rc-align-center rc-gap-2">
            <input
              type="radio"
              value="new"
              checked={mode === 'new'}
              onChange={() => setMode('new')}
            />
            <span className="rc-text-muted">New document</span>
          </label>
          <label className="rc-flex rc-align-center rc-gap-2">
            <input
              type="radio"
              value="existing"
              checked={mode === 'existing'}
              onChange={() => setMode('existing')}
            />
            <span className="rc-text-muted">Existing document</span>
          </label>
        </div>

        {mode === 'new' && (
          <div className="rc-field rc-mt-3">
            <label htmlFor="doc-name" className="rc-label">Document name</label>
            <input
              id="doc-name"
              type="text"
              value={documentName}
              onChange={(e) => setDocumentName(e.target.value)}
              placeholder="Onshape document name"
              className="rc-input"
              disabled={loading}
            />
            <p className="rc-small rc-text-subtle rc-mt-2">Free Onshape accounts create public documents.</p>
          </div>
        )}

        {mode === 'existing' && (
          <div className="rc-field rc-mt-3">
            <label htmlFor="existing-doc" className="rc-label">Select document</label>
            {documents.length === 0 && loading && <p className="rc-text-muted">Loading documents…</p>}
            {documents.length > 0 && (
              <select
                id="existing-doc"
                value={selectedDoc}
                onChange={(e) => setSelectedDoc(e.target.value)}
                className="rc-select"
                disabled={loading}
              >
                <option value="">Select a document…</option>
                {documents.map((doc) => {
                  const wsId = doc.defaultWorkspace?.id || ''
                  return (
                    <option key={doc.id} value={`${doc.id}|${wsId}`}>
                      {doc.name}
                    </option>
                  )
                })}
              </select>
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || (mode === 'existing' && !selectedDoc)}
          className="rc-button rc-button-primary rc-mt-3"
        >
          {loading ? 'Uploading…' : 'Upload STEP to Onshape'}
        </button>
      </form>

      {error && <div className="rc-alert rc-alert-error rc-mt-3">{error}</div>}

      {result && (
        <div className="rc-alert rc-alert-success rc-mt-3">
          <p><strong>Uploaded to Onshape</strong></p>
          <p className="rc-mt-2">
            <a href={result.document_url} target="_blank" rel="noreferrer" className="rc-text-muted" style={{ wordBreak: 'break-all' }}>
              {result.document_url}
            </a>
          </p>
          {result.element_url && (
            <p className="rc-mt-2">
              <a href={result.element_url} target="_blank" rel="noreferrer" className="rc-button rc-button-small">
                Open Part Studio →
              </a>
            </p>
          )}
        </div>
      )}
    </section>
  )
}
