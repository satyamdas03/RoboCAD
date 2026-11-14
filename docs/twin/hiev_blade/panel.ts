/**
 * The RoboCAD blade: pure state, no React and no DOM.
 *
 * H5 in the v1.1 order. Everything a reviewer would want a test for lives here rather than in the
 * component, because the component cannot be exercised without a browser and this can: which sections
 * exist, which `src` the iframe is allowed to load, what Esc does, what a message from inside the
 * frame may and may not change.
 *
 * The frame is treated as a hostile document. It is a local page served by the RoboCAD daemon, but it
 * is still a separate document that could be swapped for something else on the same port, so its
 * messages are checked against the frame's own window and the expected origin before they are read,
 * and the iframe gets `allow-scripts` without `allow-same-origin`, which is what makes the sandbox
 * worth having at all.
 */

export const PANEL_SECTIONS = [
  'overview',
  'checks',
  'comparison',
  'torque',
  'revision',
  'twin',
] as const

export type PanelSection = (typeof PANEL_SECTIONS)[number]

/** The daemon's read-only mount for the baked page. Absolute, same-origin, no scheme. */
export const PAGE_PREFIX = '/robocad/page/'

/** No `allow-same-origin`: with it, a same-origin frame could reach this document's storage. */
export const IFRAME_SANDBOX = 'allow-scripts'

export type BladeState = {
  open: boolean
  section: PanelSection
  src: string
  presenter: boolean
  /** The last `src` the guard refused, kept so a rejection is visible rather than silent. */
  rejected: string | null
}

export const CLOSED: BladeState = {
  open: false,
  section: 'overview',
  src: `${PAGE_PREFIX}index.html`,
  presenter: false,
  rejected: null,
}

export function isSection(value: unknown): value is PanelSection {
  return typeof value === 'string' && (PANEL_SECTIONS as readonly string[]).includes(value)
}

/**
 * A `src` the iframe may load, or null.
 *
 * The order says the daemon serves the baked page at `/robocad/page/`, so anything else is not the
 * page this blade exists to show: an absolute URL, a scheme, a `..` segment or a backslash is
 * refused. `..` matters because `/robocad/page/../secrets` is a valid relative path that resolves
 * outside the mount, and a backslash matters because Windows clients normalise it to a separator.
 */
export function safeSrc(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0 || value.length > 300) return null
  if (!value.startsWith(PAGE_PREFIX)) return null
  if (value.includes('..') || value.includes('\\')) return null
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) return null
  // Control characters would let a crafted value break out of the attribute it is rendered into.
  if (/[\u0000-\u001f\u007f]/.test(value)) return null
  return value
}

/** A `panel` event from the daemon, applied. An unknown section is not a reason to refuse the panel. */
export function applyPanelEvent(
  state: BladeState,
  event: { kind?: unknown; section?: unknown; src?: unknown },
): BladeState {
  const src = safeSrc(event.src)
  if (src === null) {
    return { ...state, rejected: typeof event.src === 'string' ? event.src.slice(0, 120) : String(event.src) }
  }
  const section = isSection(event.section) ? event.section : 'overview'
  // The presenter flag survives an open: the same presenter opens the same way each time.
  return { ...state, open: true, section, src, rejected: null }
}

export function closeBlade(state: BladeState): BladeState {
  return { ...state, open: false, presenter: state.presenter }
}

export function togglePresenter(state: BladeState): BladeState {
  return { ...state, presenter: !state.presenter }
}

export function selectSection(state: BladeState, section: PanelSection): BladeState {
  return { ...state, section }
}

/** What the host posts into the frame to move it. The page listens for exactly this shape. */
export function sectionMessage(section: PanelSection): { type: 'robocad.section'; section: PanelSection } {
  return { type: 'robocad.section', section }
}

/**
 * Esc: close the blade, and always hush the voice.
 *
 * The order asks for both. They are one action rather than two because a person pressing Esc during
 * a spoken answer means "stop", and a blade that closed while the answer kept playing would be the
 * interface disagreeing with itself.
 */
export function escapeAction(state: BladeState): { close: boolean; hush: true } {
  return { close: state.open, hush: true }
}

export function applyEscape(state: BladeState): { state: BladeState; hush: true } {
  const action = escapeAction(state)
  return { state: action.close ? closeBlade(state) : state, hush: true }
}

/**
 * A message from inside the frame, or null.
 *
 * Three checks, and all three are needed: `source` proves it came from this frame rather than any
 * other window, `origin` proves which document is running in it, and the shape check means a frame
 * that starts emitting something else cannot change the host's section by accident.
 */
export function acceptFrameMessage(
  data: unknown,
  sourceMatches: boolean,
  origin: unknown,
  expectedOrigin: string,
): PanelSection | null {
  if (!sourceMatches) return null
  if (origin !== expectedOrigin) return null
  if (typeof data !== 'object' || data === null) return null
  const message = data as { type?: unknown; section?: unknown }
  if (message.type !== 'robocad.section') return null
  return isSection(message.section) ? message.section : null
}

/** The CSP fragment the desktop shell needs for the frame to load at all. */
export const FRAME_CSP = 'frame-src http://127.0.0.1:7345'
