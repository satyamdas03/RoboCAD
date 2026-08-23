import { useEffect, useState } from 'react'
import { listOnshapeDocuments, uploadToOnshape } from '../api.js'

export default function OnshapeUpload({ designId, prompt }) {
  const [mode, setMode] = useState('new') // 'new' | 'existing'
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
    <div className="panel">
      <h3>Onshape</h3>
      <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '-0.5rem' }}>
        Upload this design's STEP file to Onshape.
      </p>

      <form onSubmit={handleSubmit} style={{ fontSize: '0.9rem' }}>
        <div style={{ marginBottom: '0.5rem' }}>
          <label style={{ marginRight: '0.5rem' }}>
            <input
              type="radio"
              value="new"
              checked={mode === 'new'}
              onChange={() => setMode('new')}
            />
            New document
          </label>
          <label>
            <input
              type="radio"
              value="existing"
              checked={mode === 'existing'}
              onChange={() => setMode('existing')}
            />
            Existing document
          </label>
        </div>

        {mode === 'new' && (
          <div style={{ marginBottom: '0.5rem' }}>
            <input
              type="text"
              value={documentName}
              onChange={(e) => setDocumentName(e.target.value)}
              placeholder="Onshape document name"
              style={{ width: '100%' }}
              disabled={loading}
            />
            <p style={{ fontSize: '0.75rem', color: '#64748b', margin: '0.2rem 0 0' }}>
              Free Onshape accounts create public documents.
            </p>
          </div>
        )}

        {mode === 'existing' && (
          <div style={{ marginBottom: '0.5rem' }}>
            {documents.length === 0 && loading && <p style={{ color: '#64748b' }}>Loading documents...</p>}
            {documents.length > 0 && (
              <select
                value={selectedDoc}
                onChange={(e) => setSelectedDoc(e.target.value)}
                style={{ width: '100%' }}
                disabled={loading}
              >
                <option value="">Select a document...</option>
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

        <button type="submit" disabled={loading || (mode === 'existing' && !selectedDoc)}>
          {loading ? 'Uploading...' : 'Upload STEP to Onshape'}
        </button>
      </form>

      {error && <p style={{ color: '#b00000', fontSize: '0.9rem', marginTop: '0.5rem' }}>{error}</p>}

      {result && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', background: '#f0fdf4', padding: '0.5rem', borderRadius: '4px' }}>
          <p style={{ margin: 0 }}>✅ Uploaded to Onshape</p>
          <a href={result.document_url} target="_blank" rel="noreferrer" style={{ wordBreak: 'break-all' }}>
            {result.document_url}
          </a>
          {result.element_url && (
            <p style={{ margin: '0.25rem 0 0' }}>
              <a href={result.element_url} target="_blank" rel="noreferrer">Open imported Part Studio {'->'}</a>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
