import { exportUrl } from '../api.js'

export default function DownloadLinks({ exportUrls }) {
  if (!exportUrls) return null

  const links = [
    { key: 'stl', label: 'STL', ext: 'stl', desc: '3D print' },
    { key: 'step', label: 'STEP', ext: 'step', desc: 'machining / Onshape' },
    { key: 'script', label: 'Code', ext: 'py', desc: 'build123d script' },
  ]

  const visible = links.filter(({ key }) => exportUrls[key])
  if (visible.length === 0) return null

  return (
    <section className="rc-flex rc-align-center rc-gap-2 rc-flex-wrap" aria-label="Downloads">
      <span className="rc-small rc-text-muted">Export:</span>
      {visible.map(({ key, label, ext, desc }) => (
        <a
          key={key}
          href={exportUrl(exportUrls[key])}
          download={`model.${ext}`}
          className="rc-button rc-button-small"
          title={desc}
        >
          {label}
        </a>
      ))}
    </section>
  )
}
