# H5 handoff: the RoboCAD blade for the Hi-EV HUD

Lane A wrote this against the envelope and route prefix Lane B sent (`BridgeEvent` union in
`web/src/lib/bridge.ts`, page served at `/robocad/page/`, `robocad_show` already returning
`{"type":"panel","kind":"robocad","section":"torque","src":"/robocad/page/"}`). It lives in RoboCAD so
the repos stay separate: copy the files in, apply the hunks, and the tests come with it.

    docs/twin/hiev_blade/
      panel.ts          the rules: sections, src guard, Esc, frame messages, sandbox, CSP
      Blade.tsx         the component: iframe + postMessage plumbing + presenter mode
      fixture.mjs       the fixture event stream (phase -> panel -> delta -> done, then panel_close)
      panel.test.mjs    10 tests, run with `node --test` and no browser
      INTEGRATION.md    this file

[verified: ran] `node --test` in that directory: 10 tests, 10 pass. `node panel.ts` imports cleanly
under node 25's type stripping, so the tests exercise the file that ships rather than a JS copy.

## Files to place

| from | to (Hi-EV) |
|---|---|
| `panel.ts` | `web/src/robocad/panel.ts` |
| `Blade.tsx` | `web/src/ui/Blade.tsx` |
| `fixture.mjs`, `panel.test.mjs` | `web/src/robocad/` (or keep outside `src/`; they are node tests) |

`Blade.tsx` imports `'../robocad/panel'`, which is correct once `panel.ts` sits at
`web/src/robocad/panel.ts` and `Blade.tsx` at `web/src/ui/Blade.tsx`: from `ui/`, `../` is `src/`, so
`../robocad/panel` is `src/robocad/panel`. An earlier version of the file said `'../../robocad/panel'`,
one level too high, which resolves to `web/robocad/panel` and fails the build; Lane B hit it on
integration and corrected it, and the file and this table now agree.

## Hunk 1: `web/src/lib/bridge.ts`, extend the union

```ts
export type BridgeEvent =
  | { type: 'pong' }
  | { type: 'phase'; phase: string }
  | { type: 'delta'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string }
  | { type: 'alert'; category: string; title: string; body: string; items?: unknown[] }
  | { type: 'confirm'; tool: string; tier: number; risk: string; prompt: string; args: Record<string, unknown> }
  | { type: 'focus' }
  | { type: 'panel'; kind: 'robocad'; section: string; src: string }
  | { type: 'panel_close' }
```

## Hunk 2: `web/src/store.ts`, the phase union and the panel slice

`phase` arrives as a bare string in the envelope while `Phase` is a closed union, so a namespaced
phase like `tooling:robocad` is dropped by the store today. Widen it rather than mapping it, so the
namespace survives to the status line:

```ts
export type Phase =
  | 'offline' | 'boot' | 'dormant' | 'listening' | 'thinking'
  | 'speaking' | 'streaming' | 'tooling' | 'error'
  | `tooling:${string}`
```

Add the slice:

```ts
import type { BladeState } from './robocad/panel'
import { CLOSED, closeBlade } from './robocad/panel'

// in EvState
panel: BladeState
setPanel: (panel: BladeState) => void
closePanel: () => void

// in the store body
panel: CLOSED,
setPanel: (panel) => set({ panel }),
closePanel: () => set((s) => ({ panel: closeBlade(s.panel) })),
```

## Hunk 3: `web/src/lib/voice.ts` (or wherever `handleBridgeEvent` lives), two cases

```ts
case 'panel': {
  const next = applyPanelEvent(useStore.getState().panel, event)
  useStore.getState().setPanel(next)
  // The reactor shrink is driven from here, not from the iframe's load event: the frame can be slow
  // or refused, and a scene that waits for it sits still while the answer is already being spoken.
  useStore.getState().setActiveTool('robocad')
  break
}
case 'panel_close':
  useStore.getState().closePanel()
  break
```

## Hunk 4: `web/src/ui/Hud.tsx`, mount it once

```tsx
import { Blade } from './Blade'

// inside the HUD root, beside the other rails
<Blade />
```

## Hunk 5: keyboard

Nothing to add. `Blade.tsx` registers Esc and P itself: Esc closes the blade and calls
`stopSpeaking()` in the same handler, and P toggles presenter mode only while the blade is open and
the event did not come from a text field. Registering Esc in `App.tsx`'s shortcut handler instead
would fire while someone is typing mid-sentence.

## Hunk 6: the desktop shell's CSP

The frame does not load under a strict CSP without this, and the failure looks like a blank panel:

```
frame-src http://127.0.0.1:7345
```

Only that origin, no wildcard, and no `child-src`.

## The origin is a setting, not a constant

`Blade.tsx` carries `PAGE_ORIGIN = 'http://127.0.0.1:7345'`, matching `ev/config.py`'s `base_url`.
Lane B confirmed that default. If anyone overrides `EV_BASE_URL` to another port, or to `localhost`,
three things move together: the CSP `frame-src`, the `src` the frame loads, and the `origin` check on
messages coming back. The blade then refuses every message in silence and looks like a dead page.

Two ways out, and the handoff does the cheap one: `Blade.tsx` logs `refused a frame message from
<origin>; expected <origin>` on any origin mismatch, so the cause is one console line away. The
thorough one is to read `base_url` at build time instead of hardcoding it, which is worth doing if the
desktop shell ever ships with more than one port configuration.

## The daemon side, which is Lane B's

`/robocad/page/` must be a read-only `StaticFiles` mount with no directory listing, resolved inside
`ROBOCAD_ROOT`, serving exactly what `python -m robocad twin page --bundle <dir> --out <dir>` wrote.
`twin page` refuses to build a page whose local links do not resolve, so a 404 for a script in that
mount is a packaging bug, not a rendering one.

## What the page sends back

The page may post `{"type":"robocad.section","section":"checks"}` to the host when someone clicks
inside it. The host accepts it only from that frame's own window, at that origin, with that shape;
anything else is ignored (three checks, tested). The host posts the same shape into the frame to move
it. If the page never implements the listener, nothing breaks: the tabs in the blade header still
work, and they change the section through the store.

## Fixture

`fixture.mjs` exports `FIXTURE_EVENTS` and `drive()`, which folds the stream through the same reducer
the store branch calls:

    node docs/twin/hiev_blade/fixture.mjs

prints the blade state after `phase -> panel -> delta -> done`, then the state after Esc
(`open: false`, one hush). Replaying it against the real `EvBridge` is the first thing to try once
the hunks are in, before the daemon is wired: if the fixture opens the blade and the live event does
not, the difference is on the daemon side.
