/**
 * A fixture event stream for the RoboCAD blade, in the exact envelope the daemon emits.
 *
 * The order asks for the blade to be written against a fixture rather than discovered against the
 * live daemon: a UI that is only ever tried on real events cannot tell "the event never arrived" from
 * "the event arrived and nothing happened". These are hand-written, in the union `bridge.ts` defines,
 * and they are what the tests and the handoff run on.
 *
 * Sequence: phase -> panel -> delta -> done, then a panel_close when Esc is pressed.
 */

import {
  CLOSED,
  applyEscape,
  applyPanelEvent,
} from './panel.ts'

export const FIXTURE_EVENTS = [
  { type: 'phase', phase: 'tooling:robocad' },
  {
    type: 'panel',
    kind: 'robocad',
    section: 'torque',
    src: '/robocad/page/index.html',
  },
  { type: 'delta', text: 'The compiled model carries less torque than the published one at ' },
  { type: 'delta', text: 'the same motion, because the masses differ.' },
  { type: 'done' },
]

export const FIXTURE_ESC = { type: 'panel_close' }

/**
 * Fold the fixture through the same state the store holds.
 *
 * This is deliberately not the store: it is the reducer the store's `panel` branch calls, so a test
 * that passes here is a test about the blade's rules and not about zustand.
 */
export function drive(events) {
  const state = { blade: CLOSED, phases: [], text: '', closed: 0, hushed: 0, rejected: [] }
  for (const event of events) {
    switch (event.type) {
      case 'phase':
        state.phases.push(event.phase)
        break
      case 'panel':
        state.blade = applyPanelEvent(state.blade, event)
        if (state.blade.rejected !== null) state.rejected.push(state.blade.rejected)
        break
      case 'delta':
        state.text += event.text
        break
      case 'panel_close':
        state.blade = { ...state.blade, open: false }
        state.closed += 1
        break
      case 'done':
        break
      default:
        throw new Error(`the fixture carried an event the blade does not handle: ${event.type}`)
    }
  }
  return state
}

/** Esc, as the host handles it: close whatever is open and stop the voice either way. */
export function driveEscape(state) {
  const result = applyEscape(state.blade)
  return { ...state, blade: result.state, hushed: state.hushed + 1 }
}

if (import.meta.url === `file://${process.argv[1]?.replace(/\\/g, '/')}`) {
  const opened = drive(FIXTURE_EVENTS)
  console.log(JSON.stringify({
    opened: opened.blade,
    phases: opened.phases,
    text: opened.text,
    rejected: opened.rejected,
  }, null, 2))
  const escaped = driveEscape(opened)
  console.log(JSON.stringify({
    after_escape: escaped.blade,
    hushed: escaped.hushed,
  }, null, 2))
}
