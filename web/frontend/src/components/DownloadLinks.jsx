import { exportUrl } from '../api.js'

export default function DownloadLinks({ exportUrls }) {
  if (!exportUrls) return null

  const links = [
    { key: 'stl', label: 'Download STL', ext: 'stl' },
    { key: 'step', label: 'Download STEP', ext: 'step' },
    { key: 'script', label: 'Download Python code', ext: 'py' },
  ]

  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
      {links.map(({ key, label, ext }) => {
        const url = exportUrls[key]
        if (!url) return null
        return (
          <a
            key={key}
            href={exportUrl(url)}
            download={`model.${ext}`}
            className="button"
            style={{ textDecoration: 'none' }}
          >
            {label}
          </a>
        )
      })}
    </div>
  )
}
