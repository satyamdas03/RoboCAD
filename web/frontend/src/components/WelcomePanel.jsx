const EXAMPLE_PROMPTS = [
  'robot arm with gripper',
  'biped humanoid robot',
  'quadruped walker',
  'drone propeller',
  'heat sink for motor',
]

const STEPS = [
  { number: 1, title: 'Prompt', description: 'Voice, text, or sketch' },
  { number: 2, title: 'Parametric design', description: 'build123d code + validation' },
  { number: 3, title: 'Simulate & certify', description: 'Physics, brain, export' },
]

export default function WelcomePanel({ onGenerate, onOpenHermes, loading }) {
  async function handleChipClick(prompt) {
    if (loading) return
    await onGenerate({ prompt, max_retries: 2, model: null, detectDomain: true, decompose: true })
  }

  function handleTalkToHermes() {
    if (onOpenHermes) {
      onOpenHermes()
    }
  }

  return (
    <section className="kp-panel" aria-labelledby="welcome-heading">
      <div className="kp-panel-header">
        <h2 id="welcome-heading" className="kp-panel-title">Welcome</h2>
        <span className={`kp-badge ${loading ? 'kp-badge-warning' : 'kp-badge-accent'}`}>
          {loading ? 'Running…' : 'Ready'}
        </span>
      </div>

      <div className="kp-flex-col kp-gap-4" style={{ textAlign: 'center', padding: '2rem 1rem' }}>
        <div className="kp-flex-col kp-gap-2">
          <h1 style={{ fontSize: '2.5rem', fontWeight: 700, letterSpacing: '-0.03em', margin: 0, color: 'var(--kp-on-surface)' }}>
            RoboCAD
          </h1>
          <p style={{ fontSize: '1rem', color: 'var(--kp-on-surface-variant)', maxWidth: '560px', margin: '0 auto' }}>
            Turn voice, text, or sketches into parametric robots — verified, simulated, and ready to build.
          </p>
        </div>

        <div className="kp-flex kp-gap-2 kp-flex-wrap" style={{ justifyContent: 'center' }}>
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="kp-button kp-button-small kp-welcome-chip"
              onClick={() => handleChipClick(prompt)}
              disabled={loading}
            >
              {prompt}
            </button>
          ))}
        </div>

        <div className="kp-flex kp-gap-4 kp-align-center" style={{ justifyContent: 'center', flexWrap: 'wrap', marginTop: '1rem' }}>
          {STEPS.map((step, idx) => (
            <div key={step.number} className="kp-flex kp-gap-2 kp-align-center">
              <div
                className="kp-flex kp-align-center kp-justify-center"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  background: 'var(--kp-primary-container)',
                  color: 'var(--kp-on-primary)',
                  fontWeight: 700,
                  fontSize: '1rem',
                  flexShrink: 0,
                }}
              >
                {step.number}
              </div>
              <div className="kp-flex-col" style={{ textAlign: 'left' }}>
                <span style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--kp-on-surface)' }}>{step.title}</span>
                <span className="kp-small" style={{ color: 'var(--kp-on-surface-variant)' }}>{step.description}</span>
              </div>
              {idx < STEPS.length - 1 && (
                <span
                  aria-hidden="true"
                  style={{
                    color: 'var(--kp-outline)',
                    fontSize: '1.2rem',
                    marginLeft: '0.5rem',
                    marginRight: '0.5rem',
                  }}
                >
                  →
                </span>
              )}
            </div>
          ))}
        </div>

        <div style={{ marginTop: '1rem' }}>
          <button
            type="button"
            className="kp-button kp-button-primary"
            onClick={handleTalkToHermes}
            disabled={loading}
          >
            Talk to HERMES
          </button>
          <p className="kp-help-text" style={{ marginTop: '0.5rem' }}>
            Or pick an example above to generate your first design.
          </p>
        </div>
      </div>
    </section>
  )
}
