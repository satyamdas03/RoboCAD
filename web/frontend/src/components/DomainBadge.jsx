const DOMAIN_COLORS = {
  mechanical: '#00e5ff',
  aero: '#76ff03',
  thermal: '#ff9100',
  electronics: '#d500f9',
  humanoid: '#ff4081',
  multi: '#ffd600',
}

export default function DomainBadge({ domain, multi }) {
  const color = DOMAIN_COLORS[multi ? 'multi' : domain] || '#ffffff'
  const label = multi ? 'multi-domain' : domain
  return (
    <span
      style={{
        color,
        border: `1px solid ${color}`,
        borderRadius: 4,
        padding: '2px 6px',
        fontSize: 11,
        textTransform: 'uppercase',
        fontWeight: 600,
        letterSpacing: '0.05em',
      }}
    >
      {label}
    </span>
  )
}
