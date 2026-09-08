import { useEffect, useState } from 'react'
import DomainBadge from './DomainBadge.jsx'
import {
  listMarketplaceItems,
  uploadMarketplaceItem,
  uploadMarketplaceArchive,
  downloadMarketplaceItem,
  importMarketplaceItem,
} from '../api.js'

const DOMAINS = ['mechanical', 'aero', 'thermal', 'electronics', 'humanoid', 'multi']
const ASSET_TYPES = ['part', 'scene_template', 'robot_template', 'world_template', 'electronics_template', 'aero_template']

export default function MarketplacePanel({ designId, onDesignCreated }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [importingId, setImportingId] = useState(null)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [filter, setFilter] = useState('')

  const [form, setForm] = useState({
    name: '',
    description: '',
    domain: 'mechanical',
    assetType: 'part',
    sourcePath: '',
  })
  const [archiveFile, setArchiveFile] = useState(null)

  useEffect(() => {
    refreshItems()
  }, [])

  useEffect(() => {
    setForm((prev) => ({ ...prev, sourcePath: designId ? `designs/${designId}` : '' }))
  }, [designId])

  async function refreshItems() {
    setLoading(true)
    setError(null)
    try {
      const data = await listMarketplaceItems()
      setItems(data.items || data || [])
    } catch (err) {
      setError(err.message)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  function updateForm(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!form.name.trim()) {
      setError('Name is required.')
      return
    }
    if (!archiveFile && !form.sourcePath.trim()) {
      setError('Provide either an archive file or a source path.')
      return
    }
    setUploading(true)
    setError(null)
    setSuccess(null)
    try {
      if (archiveFile) {
        await uploadMarketplaceArchive({
          file: archiveFile,
          name: form.name.trim(),
          description: form.description.trim(),
          assetType: form.assetType,
          tags: [form.domain],
        })
      } else {
        await uploadMarketplaceItem({
          name: form.name.trim(),
          description: form.description.trim(),
          assetType: form.assetType,
          sourcePath: form.sourcePath.trim(),
          tags: [form.domain],
          metadata: { domain: form.domain },
        })
      }
      setSuccess(`Uploaded ${form.name.trim()} to marketplace.`)
      setForm({
        name: '',
        description: '',
        domain: 'mechanical',
        assetType: 'part',
        sourcePath: designId ? `designs/${designId}` : '',
      })
      setArchiveFile(null)
      await refreshItems()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleDownload(item) {
    try {
      const blob = await downloadMarketplaceItem(item.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = item.filename || `${item.id}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(`Download failed: ${err.message}`)
    }
  }

  async function handleImport(item) {
    if (!designId) {
      setError('Select or create a design before importing.')
      return
    }
    setImportingId(item.id)
    setError(null)
    setSuccess(null)
    try {
      const data = await importMarketplaceItem(item.id, designId)
      if (data.design_id && onDesignCreated) {
        onDesignCreated(data.design_id)
      }
      setSuccess(`Imported ${item.name} into design ${data.design_id || 'local'}.`)
    } catch (err) {
      setError(`Import failed: ${err.message}`)
    } finally {
      setImportingId(null)
    }
  }

  const filteredItems = (items || []).filter((item) => {
    const query = filter.toLowerCase()
    return (
      (item.name || '').toLowerCase().includes(query) ||
      (item.description || '').toLowerCase().includes(query) ||
      (item.domain || '').toLowerCase().includes(query) ||
      (item.tags || []).some((t) => t.toLowerCase().includes(query))
    )
  })

  return (
    <section className="kp-panel" aria-labelledby="marketplace-heading">
      <div className="kp-panel-header">
        <h3 id="marketplace-heading" className="kp-panel-title">Marketplace</h3>
      </div>

      <div className="kp-flex-col kp-gap-4">
        <form onSubmit={handleUpload}>
          <div className="kp-flex-col kp-gap-2">
            <div className="kp-field">
              <label htmlFor="mp-name" className="kp-label">Asset name</label>
              <input
                id="mp-name"
                type="text"
                className="kp-input"
                value={form.name}
                onChange={(e) => updateForm('name', e.target.value)}
                placeholder="e.g. 6-DOF robot arm bracket"
                disabled={uploading}
                required
              />
            </div>

            <div className="kp-field">
              <label htmlFor="mp-desc" className="kp-label">Description</label>
              <textarea
                id="mp-desc"
                className="kp-textarea"
                value={form.description}
                onChange={(e) => updateForm('description', e.target.value)}
                placeholder="Brief description, use cases, and constraints"
                disabled={uploading}
              />
            </div>

            <div className="kp-flex kp-gap-2">
              <div className="kp-field" style={{ flex: 1 }}>
                <label htmlFor="mp-domain" className="kp-label">Domain</label>
                <select
                  id="mp-domain"
                  className="kp-input"
                  value={form.domain}
                  onChange={(e) => updateForm('domain', e.target.value)}
                  disabled={uploading}
                >
                  {DOMAINS.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>

              <div className="kp-field" style={{ flex: 1 }}>
                <label htmlFor="mp-asset-type" className="kp-label">Asset type</label>
                <select
                  id="mp-asset-type"
                  className="kp-input"
                  value={form.assetType}
                  onChange={(e) => updateForm('assetType', e.target.value)}
                  disabled={uploading}
                >
                  {ASSET_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="kp-field">
              <label htmlFor="mp-source-path" className="kp-label">Source path (repo-relative asset directory)</label>
              <input
                id="mp-source-path"
                type="text"
                className="kp-input"
                value={form.sourcePath}
                onChange={(e) => updateForm('sourcePath', e.target.value)}
                placeholder="marketplace/starter_packs/parts/bracket"
                disabled={uploading}
              />
            </div>

            <div className="kp-field">
              <label htmlFor="mp-archive-file" className="kp-label">Or upload archive (.zip, .tar.gz, .tgz)</label>
              <input
                id="mp-archive-file"
                type="file"
                accept=".zip,.tar.gz,.tgz"
                className="kp-input"
                onChange={(e) => setArchiveFile(e.target.files?.[0] || null)}
                disabled={uploading}
              />
            </div>

            <div className="kp-flex kp-justify-end">
              <button
                type="submit"
                className="kp-button kp-button-primary"
                disabled={uploading || !form.name.trim() || (!archiveFile && !form.sourcePath.trim())}
              >
                {uploading ? 'Uploading…' : 'Contribute asset'}
              </button>
            </div>
          </div>
        </form>

        <div className="kp-section-divider"></div>

        <div className="kp-flex kp-justify-between kp-align-center">
          <span className="kp-label">Browse assets</span>
          <div className="kp-flex kp-gap-2 kp-align-center" style={{ flex: 1, justifyContent: 'flex-end' }}>
            <input
              type="text"
              className="kp-input"
              style={{ maxWidth: 220 }}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search marketplace…"
            />
            <button
              type="button"
              className="kp-button kp-button-secondary kp-button-small"
              onClick={refreshItems}
              disabled={loading}
            >
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </div>

        {error && <div className="kp-alert kp-alert-error">{error}</div>}
        {success && <div className="kp-alert kp-alert-success">{success}</div>}

        <div className="kp-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 'var(--kp-space-3)' }}>
          {filteredItems.length === 0 && !loading && (
            <div className="kp-empty" style={{ gridColumn: '1 / -1' }}>
              <div className="kp-empty-icon">◈</div>
              <p className="kp-small">No marketplace assets found.</p>
              <p className="kp-text-muted kp-small">Upload a design bundle or check the backend marketplace endpoint.</p>
            </div>
          )}

          {filteredItems.map((item) => (
            <article
              key={item.id}
              className="kp-panel"
              style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kp-space-2)', padding: 'var(--kp-space-3)' }}
            >
              <div
                className="kp-flex kp-justify-center kp-align-center"
                style={{
                  aspectRatio: '16/10',
                  background: 'var(--kp-surface-container)',
                  borderRadius: 'var(--kp-radius-md)',
                  border: '1px solid var(--kp-border)',
                  color: 'var(--kp-outline)',
                  fontSize: '1.5rem',
                }}
                aria-label="Preview placeholder"
              >
                ◈
              </div>

              <div className="kp-flex-col kp-gap-1">
                <div className="kp-flex kp-justify-between kp-align-center">
                  <span className="kp-text-primary" style={{ fontWeight: 600, fontSize: '0.9rem' }}>{item.name}</span>
                  {item.verified && <span className="kp-badge kp-badge-success">Verified</span>}
                </div>
                <p className="kp-small kp-text-muted" style={{ lineClamp: 2, WebkitLineClamp: 2, display: '-webkit-box', WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {item.description || 'No description.'}
                </p>
              </div>

              <div className="kp-flex kp-gap-1 kp-flex-wrap">
                <DomainBadge domain={item.domain} multi={item.domain === 'multi' || (item.domains || []).length > 1} />
                {(item.domains || []).filter((d) => d !== item.domain).map((d) => (
                  <DomainBadge key={d} domain={d} />
                ))}
                {(item.tags || []).map((tag) => (
                  <span key={tag} className="kp-tag">{tag}</span>
                ))}
              </div>

              <div className="kp-flex kp-gap-2 kp-justify-end" style={{ marginTop: 'auto', paddingTop: 'var(--kp-space-2)' }}>
                <button
                  type="button"
                  className="kp-button kp-button-small"
                  onClick={() => handleDownload(item)}
                  disabled={uploading || importingId === item.id}
                >
                  Download
                </button>
                <button
                  type="button"
                  className="kp-button kp-button-primary kp-button-small"
                  onClick={() => handleImport(item)}
                  disabled={importingId === item.id}
                >
                  {importingId === item.id ? 'Importing…' : 'Import'}
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
