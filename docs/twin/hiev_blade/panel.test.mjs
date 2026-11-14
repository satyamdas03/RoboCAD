/**
 * The blade's rules, runnable with no browser: `node --test docs/twin/hiev_blade/`.
 *
 * These import `panel.ts` directly (node strips the types), so the thing tested is the thing that
 * ships. There is no JS copy of the logic to drift from it.
 */

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CLOSED,
  FRAME_CSP,
  IFRAME_SANDBOX,
  PANEL_SECTIONS,
  acceptFrameMessage,
  applyEscape,
  applyPanelEvent,
  closeBlade,
  escapeAction,
  safeSrc,
  sectionMessage,
  selectSection,
  togglePresenter,
} from './panel.ts'
import { FIXTURE_EVENTS, drive, driveEscape } from './fixture.mjs'

test('the fixture opens the blade on the section the daemon asked for', () => {
  const state = drive(FIXTURE_EVENTS)
  assert.deepEqual(state.phases, ['tooling:robocad'])
  assert.equal(state.blade.open, true)
  assert.equal(state.blade.section, 'torque')
  assert.equal(state.blade.src, '/robocad/page/index.html')
  assert.deepEqual(state.rejected, [])
  assert.match(state.text, /masses differ/)
})

test('esc closes the blade and hushes the voice, whether or not it was open', () => {
  const opened = drive(FIXTURE_EVENTS)
  const after = driveEscape(opened)
  assert.equal(after.blade.open, false)
  assert.equal(after.hushed, 1)
  assert.deepEqual(escapeAction(CLOSED), { close: false, hush: true })
  assert.deepEqual(escapeAction(opened.blade), { close: true, hush: true })
  assert.equal(applyEscape(CLOSED).hush, true)
})

test('a panel_close event closes without changing the section or presenter flag', () => {
  const opened = togglePresenter(drive(FIXTURE_EVENTS).blade)
  const state = drive([{ type: 'panel_close' }])
  assert.equal(state.blade.open, false)
  const closed = closeBlade(opened)
  assert.equal(closed.presenter, true)
  assert.equal(closed.section, 'torque')
})

test('only the daemon page mount can be loaded in the frame', () => {
  assert.equal(safeSrc('/robocad/page/index.html'), '/robocad/page/index.html')
  for (const bad of [
    'https://evil.example/robocad/page/index.html',
    '//evil.example/robocad/page/index.html',
    '/robocad/page/../secrets',
    '/robocad/page/index.html?x=..',
    '/robocad/page\\index.html',
    'javascript:alert(1)',
    '/etc/passwd',
    '/robocad/pagex/index.html',
    '/robocad/page/index.html\u0000',
    '',
    null,
    undefined,
    42,
    'x'.repeat(301),
  ]) {
    assert.equal(safeSrc(bad), null, `accepted ${String(bad)}`)
  }
})

test('a refused src leaves the blade shut and says what it refused', () => {
  const state = applyPanelEvent(CLOSED, { kind: 'robocad', section: 'torque', src: 'https://evil.example/' })
  assert.equal(state.open, false)
  assert.equal(state.rejected, 'https://evil.example/')
  const recovered = applyPanelEvent(state, { kind: 'robocad', section: 'checks', src: '/robocad/page/index.html' })
  assert.equal(recovered.open, true)
  assert.equal(recovered.section, 'checks')
  assert.equal(recovered.rejected, null)
})

test('an unknown or absent section opens the blade on overview rather than refusing it', () => {
  const unknown = applyPanelEvent(CLOSED, { section: 'secrets', src: '/robocad/page/index.html' })
  assert.equal(unknown.open, true)
  assert.equal(unknown.section, 'overview')
  const absent = applyPanelEvent(CLOSED, { src: '/robocad/page/index.html' })
  assert.equal(absent.section, 'overview')
})

test('every section the order names exists, and nothing else does', () => {
  assert.deepEqual([...PANEL_SECTIONS], [
    'overview',
    'checks',
    'comparison',
    'torque',
    'revision',
    'twin',
  ])
})

test('section navigation posts exactly the message the page is told to listen for', () => {
  const moved = selectSection(CLOSED, 'revision')
  assert.equal(moved.section, 'revision')
  assert.deepEqual(sectionMessage('revision'), { type: 'robocad.section', section: 'revision' })
})

test('a message from the frame is accepted only from that frame, at that origin, in that shape', () => {
  const origin = 'http://127.0.0.1:7345'
  const good = { type: 'robocad.section', section: 'checks' }
  assert.equal(acceptFrameMessage(good, true, origin, origin), 'checks')
  assert.equal(acceptFrameMessage(good, false, origin, origin), null, 'wrong window')
  assert.equal(acceptFrameMessage(good, true, 'http://evil.example', origin), null, 'wrong origin')
  assert.equal(acceptFrameMessage({ type: 'panel', section: 'checks' }, true, origin, origin), null)
  assert.equal(acceptFrameMessage({ type: 'robocad.section', section: 'nope' }, true, origin, origin), null)
  assert.equal(acceptFrameMessage('checks', true, origin, origin), null)
  assert.equal(acceptFrameMessage(null, true, origin, origin), null)
})

test('the frame is sandboxed without same-origin, and the desktop shell is told to allow it', () => {
  assert.equal(IFRAME_SANDBOX, 'allow-scripts')
  assert.ok(!IFRAME_SANDBOX.includes('allow-same-origin'))
  assert.equal(FRAME_CSP, 'frame-src http://127.0.0.1:7345')
})
