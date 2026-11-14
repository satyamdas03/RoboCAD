/**
 * The RoboCAD blade, as a drop-in component for the Hi-EV HUD.
 *
 * Nothing in here decides anything: which section, which src, what Esc does and which frame messages
 * are trusted all live in `panel.ts`, where they are tested without a browser. This file is the part
 * that has to exist as DOM — the iframe, its sandbox attributes, the postMessage plumbing and the
 * presenter-mode class.
 *
 * Wire-up notes for the host (also in INTEGRATION.md):
 * - Mount it once, in `Hud`, beside the other rails. It renders nothing while closed.
 * - The reactor shrink is driven by the `panel` event changing store state, not by the iframe firing
 *   `load`: the frame can be slow or blocked, and a scene that waits for it sits still while the
 *   answer is already being spoken.
 */

import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { stopSpeaking } from '../lib/tts'
import {
  IFRAME_SANDBOX,
  type PanelSection,
  acceptFrameMessage,
  applyPanelEvent,
  applyEscape,
  sectionMessage,
  selectSection,
} from '../../robocad/panel'

/** The daemon's page origin, as the desktop shell loads it. */
const PAGE_ORIGIN = 'http://127.0.0.1:7345'

export function Blade() {
  const blade = useStore((s) => s.panel)
  const setPanel = useStore((s) => s.setPanel)
  const closePanel = useStore((s) => s.closePanel)
  const frame = useRef<HTMLIFrameElement | null>(null)

  // Esc closes the blade and always hushes the voice. Registered here rather than in the global
  // shortcut handler so it cannot misfire while the textarea has focus mid-sentence.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        const result = applyEscape(useStore.getState().panel)
        setPanel(result.state)
        stopSpeaking()
        return
      }
      if (e.key === 'p' || e.key === 'P') {
        const tag = (e.target as HTMLElement)?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA') return
        const current = useStore.getState().panel
        if (!current.open) return
        setPanel({ ...current, presenter: !current.presenter })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [setPanel])

  // Host -> frame: the section can change without reloading the page, and without the host touching
  // the frame's internals. The page listens for exactly this shape.
  useEffect(() => {
    const target = frame.current?.contentWindow
    if (!blade.open || !target) return
    target.postMessage(sectionMessage(blade.section), PAGE_ORIGIN)
  }, [blade.open, blade.section])

  // Frame -> host: only this frame, only that origin, only that shape.
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const section: PanelSection | null = acceptFrameMessage(
        event.data,
        event.source === frame.current?.contentWindow,
        event.origin,
        PAGE_ORIGIN,
      )
      if (section === null) {
        // A refused message is silent by design, but silence that cannot be told from "the page
        // never spoke" costs an hour. The common cause is a daemon on a different origin than the
        // one configured here (an EV_BASE_URL override onto another port or `localhost`), which
        // changes the origin check and the CSP together and looks exactly like a dead page.
        if (event.origin !== PAGE_ORIGIN) {
          console.warn(`[robocad blade] refused a frame message from ${event.origin}; expected ${PAGE_ORIGIN}`)
        }
        return
      }
      const current = useStore.getState().panel
      if (!current.open) return
      setPanel(selectSection(current, section))
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [setPanel])

  if (!blade.open) return null

  return (
    <aside
      className={`blade${blade.presenter ? ' blade-presenter' : ''}`}
      aria-label="RoboCAD twin"
    >
      <header className="blade-top">
        <span className="blade-title">ROBOCAD TWIN</span>
        <nav className="blade-tabs">
          {(['overview', 'checks', 'comparison', 'torque', 'revision', 'twin'] as PanelSection[]).map(
            (section) => (
              <button
                key={section}
                type="button"
                className={section === blade.section ? 'blade-tab blade-tab-on' : 'blade-tab'}
                onClick={() => setPanel(selectSection(useStore.getState().panel, section))}
              >
                {section}
              </button>
            ),
          )}
        </nav>
        <button type="button" className="blade-close" onClick={closePanel} aria-label="Close">
          ✕
        </button>
      </header>

      <iframe
        ref={frame}
        key={blade.src}
        src={blade.src}
        title="RoboCAD twin"
        className="blade-frame"
        sandbox={IFRAME_SANDBOX}
        referrerPolicy="no-referrer"
      />

      <footer className="blade-foot">
        <span>esc closes · p presenter</span>
        <span className="blade-src">{blade.src}</span>
      </footer>
    </aside>
  )
}

/** The store branch the `panel` and `panel_close` events call. Kept here so the wiring is one file. */
export function panelEventToPatch(event: {
  type: 'panel'
  kind?: unknown
  section?: unknown
  src?: unknown
}): ReturnType<typeof applyPanelEvent> {
  return applyPanelEvent(useStore.getState().panel, event)
}
