/**
 * The page's section listener, runnable with no browser: `node --test docs/demo/page/`.
 *
 * These load `sections.js` itself into a fake window, so the thing tested is the thing that ships
 * in the zip. What matters here is not that a message scrolls a panel -- it is that only a message
 * from this page's own origin, naming a section this page has, does anything at all.
 */

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const SOURCE = readFileSync(new URL('./sections.js', import.meta.url), 'utf8')

function fakeWindow({ protocol = 'http:', origin = 'http://localhost:8000', panels = {} } = {}) {
  const listeners = new Map()
  const made = new Map()
  const timers = []

  const document = {
    getElementById(id) {
      if (!(id in panels)) return null
      if (!made.has(id)) {
        const spec = panels[id]
        const classes = new Set()
        made.set(id, {
          id,
          style: { display: spec.hidden ? 'none' : '' },
          textContent: spec.text || '',
          scrolled: 0,
          scrollIntoView() { this.scrolled += 1 },
          scrollOptions: null,
          classList: { add: c => classes.add(c), remove: c => classes.delete(c), has: c => classes.has(c) },
          classes,
        })
      }
      return made.get(id)
    },
  }

  const window = {
    document,
    location: { protocol, origin, hash: '' },
    matchMedia: () => ({ matches: false }),
    // captured rather than real, so the 1.5 s flash can be inspected without waiting for it
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, [])
      listeners.get(type).push(fn)
    },
  }
  window.dispatch = (type, event) => (listeners.get(type) || []).forEach(fn => fn(event))
  return { window, made, timers }
}

function load(window) {
  const context = vm.createContext(window)
  vm.runInContext(SOURCE, context)
  return window.ROBOCAD_SECTIONS
}

const PANELS = {
  hud: { text: 'twin preview' },
  'checks-grp': { text: '5 pass 1 fail 1 skipped' },
  'cmp-grp': { text: 'compiled vs official' },
  'torque-grp': { text: '0.7668 vs 0.5377' },
  'rev-grp': { text: '0.2 to 0.3' },
  'twin-grp': { text: 'SYNTHETIC' },
}

test('a section message from the page own origin is accepted', () => {
  const { window } = fakeWindow()
  const sections = load(window)
  assert.equal(sections.accept({ type: 'robocad.section', section: 'torque' },
    'http://localhost:8000', window.location), 'torque')
})

test('a message from any other origin is ignored, whatever it names', () => {
  const { window } = fakeWindow()
  const sections = load(window)
  for (const origin of ['http://evil.example', 'https://localhost:8000', 'null', '', null]) {
    assert.equal(sections.accept({ type: 'robocad.section', section: 'torque' }, origin,
      window.location), null, `origin ${origin} must be refused`)
  }
})

test('an unknown section, another type, or a non-string section is ignored', () => {
  const { window } = fakeWindow()
  const sections = load(window)
  const here = 'http://localhost:8000'
  assert.equal(sections.accept({ type: 'robocad.section', section: 'secrets' }, here,
    window.location), null)
  assert.equal(sections.accept({ type: 'robocad.render', section: 'torque' }, here,
    window.location), null)
  assert.equal(sections.accept({ type: 'robocad.section', section: 7 }, here, window.location), null)
  assert.equal(sections.accept(null, here, window.location), null)
})

test('a page opened from file:// accepts nothing, and still navigates by fragment', () => {
  const { window, made } = fakeWindow({ protocol: 'file:', origin: 'null' })
  const sections = load(window)
  assert.equal(sections.accept({ type: 'robocad.section', section: 'torque' }, 'null',
    window.location), null)
  assert.equal(sections.show(window.document, 'torque'), false, 'no panel exists in this fake')
  window.location.hash = '#checks'
  sections.wire(window.document, window)
  const checks = window.document.getElementById('checks-grp')
  assert.equal(checks, null)
  assert.equal(made.size, 0)
})

test('showing a section scrolls it and flashes it for 1.5 seconds', () => {
  const { window, timers } = fakeWindow({ panels: PANELS })
  const sections = load(window)
  assert.equal(sections.show(window.document, 'torque'), true)
  const panel = window.document.getElementById('torque-grp')
  assert.equal(panel.scrolled, 1)
  assert.equal(panel.classes.has('nav-flash'), true)
  assert.equal(timers.length, 1)
  assert.equal(timers[0].ms, sections.FLASH_MS)
  assert.equal(sections.FLASH_MS, 1500)
  timers[0].fn()
  assert.equal(panel.classes.has('nav-flash'), false)
})

test('a panel the payload did not fill is not revealed by a message', () => {
  const { window } = fakeWindow({ panels: { ...PANELS, 'torque-grp': { hidden: true, text: '' } } })
  const sections = load(window)
  assert.equal(sections.show(window.document, 'torque'), false)
  assert.equal(window.document.getElementById('torque-grp').style.display, 'none')
})

test('wired, a message from the right origin scrolls and one from elsewhere does not', () => {
  const { window } = fakeWindow({ panels: PANELS })
  const sections = load(window)
  sections.wire(window.document, window)

  window.dispatch('message', { origin: 'http://evil.example',
    data: { type: 'robocad.section', section: 'revision' } })
  assert.equal(window.document.getElementById('rev-grp').scrolled, 0)

  window.dispatch('message', { origin: 'http://localhost:8000',
    data: { type: 'robocad.section', section: 'revision' } })
  assert.equal(window.document.getElementById('rev-grp').scrolled, 1)
})

test('a #section in the URL navigates on load and on hashchange', () => {
  const { window } = fakeWindow({ panels: PANELS })
  const sections = load(window)
  window.location.hash = '#comparison'
  sections.wire(window.document, window)
  assert.equal(window.document.getElementById('cmp-grp').scrolled, 1)

  window.location.hash = '#twin'
  window.dispatch('hashchange', {})
  assert.equal(window.document.getElementById('twin-grp').scrolled, 1)
})
