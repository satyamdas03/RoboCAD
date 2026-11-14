# Final status, demo sprint

Owner of this file: build session (Lane A, `robocad-61`), with the show-path rows contributed by the
monitor session (Lane B) and every one of them re-derived before it was written here. Updated
2026-11-14 for **v1.7** (see the section immediately below); the v1.3 sections further down are kept
as history. Every claim carries a tag: `verified-ran`, `verified-read`, `claimed`. Deadline: hard
freeze Sat 14 Nov 2026, 13:15 Sydney.

## Final visual stretch: v1.7 is the package to hand anyone

`demo-bundle-v1.7`, commit `656d244`, zip sha256
`f14291bf796f01c6fd17687ad56d7d4d32426111d1b79232494ebea7f69fa052`. Two earlier tags from the same
sprint (`v1.5`, `v1.6`) are superseded and left in place; `DECISIONS.md` explains why they were not
moved.

| Gate | Evidence | Tag |
|---|---|---|
| Package baked once, after the page gates were green | `python teardown_export/package_demo.py --tag demo-bundle-v1.7 --tag-pending` → `PACKAGE OK` | verified-ran |
| Tag proves its own bytes | `python scripts/verify_demo_zip.py docs/demo/so101_demo.zip --tag demo-bundle-v1.7 --built-from 656d2444… --out docs/demo/verify.json` → 5/5 PASS, `VERIFIED`; tag → `656d2444`, zip in tag matches, `manifest.js` records `demo-bundle-v1.7`, page reads `demo-bundle-v1.7` | verified-ran |
| Package opens from `file://`, offline | same run, check 4: 7 check rows, 7 link rows, revision panel 284 chars over 7 rows, 0 page errors, 0 non-file requests, 0 missing links | verified-ran |
| Fresh clone → `start_demo` → HUD | clone of `83ecc0f`; `start_demo.ps1 -RoboCadRoot <clone> -Fresh`: package digest `f14291bf796f01c6` matches `verify.json`, `EV_DEMO_BUNDLE_TAG=v1.7`, `setup hidden  needs_setup false, demo true`, daemon up, page served | verified-ran |
| The release journey, typed into that HUD | `python scripts/release_journey.py --base http://127.0.0.1:7345`: 7 phrases, 0 unanswered, 0 over the 1500 ms budget, 0 console errors; first phrase 1337 ms cold, the rest 44–59 ms; Escape closes the input and `/` reopens it | verified-ran |
| Every frame of that journey | `docs/demo/screens/release/01-…09-….png`, plus `package-tile.png` and `infill-30-page.png` | verified-ran |
| PACKAGE tile names the tag, unclipped | `pytest tests/test_page_package_tile.py -m ""` → 1 passed (asserts no doubled prefix, tag once, pill `tagged`/`ok`, pill box inside the tile, no clipped span) | verified-ran |
| Cockpit at the blade's 870 px | `pytest tests/test_page_blade_width.py -m ""` → 1 passed; pre-fix reproduction at a 198 px stage in `screens/v1.4/defect-blade-870x680.png` | verified-ran |
| Infill moves every dependent number | `pytest tests/test_page_infill_bridge.py -m ""` → 1 passed; `node --test docs/demo/page/sections.test.mjs` → 15 passed (origin rule, range rule, both message types) | verified-ran |
| Printed mass for any infill, no STEP | `tests/test_print_from_bundle.py`, `test_print_model.py`, `test_revise_from_bundle.py` → 40 passed; bundle arithmetic 0.9554530302470396 vs an independent compile 0.9554530302470398 kg | verified-ran |
| Hostile bundle input refused, not crashed | `pytest tests/test_bundle_untrusted_input.py` → 27 passed (terminal, markdown, arithmetic sinks; backslash-neutralised pipes; `float(10**400)`; two bodies sanitising to one id) | verified-ran |
| Hi-EV reads the same summary | fixture re-exported from `f14291bf…` into both repos; `pytest tests/test_robocad_tool.py` → 11 passed | verified-ran |

**What is still not done, plainly.**

* The HUD does not yet send `robocad.infill`. The page accepts the message and moves every number
  (`infill-30-page.png` shows the card at 0.955 kg), but in the live HUD frame `07-infill-30.png` the
  chat answer says 0.955 kg while the card still shows 0.902 kg. The sender is the Hi-EV HUD, which is
  the peer lane's V7. Until it posts the message, that one frame is the honest picture of the gap.
* `verify.json` lands one commit after the tag, because a tag cannot contain a record of its own
  commit. It is committed at `83ecc0f`.
* Heavy, slow, mujoco and benchmark tiers were run for the page tests only (`-m ""`); the rest of the
  default selection is reported in the release message, not here.
* Nothing has been measured on hardware.


## Everything that is not done, in one place

No "should work": each line is either something nobody ran or something the artifact does not contain.

| Not done | What that means for a reader |
|---|---|
| `film.mp4` is v1.2's | no frame was re-rendered for v1.3; the film shows v1.2's page |
| `docs/twin/so101/comparison.md` in the working tree is the pre-S3 render | it still repeats the hull sentence; it is **not** in the package, and regenerating it needs a bundle re-render this sprint did not spend |
| The live hold fails | `robocad.demo --mode hold` does not hold: 573 mrad steady-state error with every joint pinned at 2.942 N·m. Replay works. This is contact geometry, not a parameter to tune |
| `twin revise` reports mass and the link diff only | no effort check and no torque comparison on the new masses; the frozen 0.652 → 0.687 N·m pair came from the scripted path, not the CLI |
| `revise` cannot run from a clean clone | the SO-101 STEP is third-party and deliberately not in the repo; the command needs that file, `--joints`, `--servo-mass-kg` and `--servo-source` |
| The bundle records no `actuator_mass_kg` | so `revise` cannot read the assumption back from `--before`; it asks instead. A next-bundle change, not one to make under a frozen tag |
| The test suite does not run on `.[dev]` | needs `pip install -e ".[dev,web,sim,ai,voice]"`; the CLI itself needs none of `ai`, `voice`, `web` |
| Heavy, slow, mujoco and benchmark tiers were deselected | 309 tests by configuration; this file does not claim they ran |
| The Hi-EV half of E2 was not re-run here | `[claimed: peer report, a6d2e18]`; the RoboCAD half is re-run below |
| `demo-v1.0` exists, but this file inside it was written before the tag | the tagged blob carries the earlier row saying the tag did not exist; the E5 section below is the later, true statement, and it is not inside `demo-v1.0` |
| Nothing has been measured on hardware | no robot was commanded, no printed part was weighed; mic, speakers and the stopwatch are Satyam's |
| The packaged page is v1.3's, the cockpit exists in the tree only | anything shipped — the zip, the film, a recipient's extract — shows the older scrolling layout; the single-screen cockpit below is `docs/demo/page/index.html` on `master`, not in any bundle |

## v1.3: the artifact of record

Updated 2026-11-14, 15:40 Sydney, for **v1.3**. `demo-bundle-v1.3` replaces v1.2 as the package to
hand anyone. Nothing about the robot changed: the masses, the seven check rows, the failing live hold
and the revision are v1.2's numbers. What changed is what the page says about them, and that every
one of those statements now comes from the summary the voice also speaks from.

| What | v1.3 state | Evidence |
|---|---|---|
| Tag | `demo-bundle-v1.3`, at the commit holding this exact zip | `verified-ran`, `git show demo-bundle-v1.3:docs/demo/so101_demo.zip \| sha256sum` equals the sha in `docs/demo/verify.json` |
| Package | `docs/demo/so101_demo.zip`, 8,135,673 bytes, sha256 `f86c28f703f84ccfcb3269233ad7a0ef88e2843172387728f5af7c01b6b569f3`, 32 files recorded in `FILES.sha256` | `verified-ran`, `scripts/verify_demo_zip.py --built-from demo-bundle-v1.3 --out docs/demo/verify.json`: four PASS rows, `VERIFIED` |
| The tag names itself | the page header reads `packaged demo-bundle-v1.3` from `manifest.js`, which `package_demo.py --tag` writes after checking `refs/tags/demo-bundle-v1.3` exists; no tag in the HTML | `verified-ran`, packaged `manifest.js` `package.tag = "demo-bundle-v1.3"`; a `--tag` that does not exist exits rather than printing a claim |
| One generator for page and voice | the page's torque, comparison, checks, twin and link numbers all come from `summary.js`; `scripts/check_page_numbers.py` renders the page and requires every numeric token in those panels to trace to the summary JSON | `verified-ran`, `80 numeric tokens across torque-grp, cmp, checks, twin-grp all trace to the summary`; `tests/test_page_text_matches_summary.py` 2 passed in the `heavy` tier |
| The pose gate is quoted, not hedged | torque note: "jaw frame differs by **70.69 mm** at the worst sampled pose"; the panel had printed "tens of mm" from a `torque.js` baked against an older `torque.json` than the summary read | `verified-ran`, packaged page text; `test_the_torque_reason_names_the_pose_gate_in_millimetres_not_tens_of_mm` and `test_torque_note_quotes_the_pose_gate` |
| Two datasheet figures, named | `stall (servo) 2.94 N·m` and `rated (servo) 0.98 N·m` as separate rows; the single row that said "rated (servo) 2.94 N·m" was the stall figure | `verified-ran`, `docs/demo/screens/torque.png` |
| Both panels explain 0.652 vs 0.767 | one line each: 0.652 N·m is the effort check's demand at its sampled poses, 0.767 N·m the static load at rest, "the same joint, not the same thing" | `verified-ran`, `screens/torque.png`, `screens/comparison.png` |
| Rungs, no duplicates | rungs 0, 1, 2, 3, 4, 5 once each, rung 5 naming both joints; the blocked rung carries its full reason and the preview count (`0 of 19 parameters identified from 3 synthetic runs at 62 Hz, position logs only`) directly under it; one summary line | `verified-ran`, `screens/twin.png` |
| The friction sentences have figures | the scenario table reaches the panel: `signal to noise is 0.10 … 4.48 … 25.1 … 0.39`; a `$` anchor in the pattern matched nothing and had been sending the panel to its no-table fallback | `verified-ran`, packaged page text |
| Page payload | 533,262 triangles of the bundle's 620,093, **86.0%**, at a 3,000-triangle budget (largest mesh 3,370); raised from 2,500, where the reducer overshot and left ~500 per mesh | `verified-ran`, packaged README "Mesh resolution", `trajectory.js` `triangle_budget` |
| The synthetic preview ships | `synthetic_preview.json` is in the package, so a summary built from the archive carries the preview block the page prints; without it the page showed 270 → 224 mrad while `twin summary` on the same archive had no preview at all | `verified-ran`, fixture `calibration.twin_preview`, `synthetic figures … calibration 40` |
| Both repos read one summary | `docs/demo/robocad_summary.v1.json` (57,755 bytes, zip sha256 `f86c28f703f8` in its sidecar) and `Hi-EV/tests/fixtures/robocad_summary.v1.json` are the same bytes | `verified-ran`, `python -m pytest tests/test_robocad_tool.py -q` in Hi-EV: **8 passed** |
| Screenshots | every panel captured from the packaged page: `docs/demo/screens/{hero,checks,comparison,torque,twin,links}.png` | `verified-ran`, header in each capture reads `packaged demo-bundle-v1.3`, 0 page errors |

### Corrections made while cutting v1.3

- The tag was first created on the code commit, before the zip it names existed in the tree, so
  `git show demo-bundle-v1.3:docs/demo/so101_demo.zip` would have failed. It was deleted and recreated
  at the final commit **before anything was pushed or handed out**; no published tag was moved.
- Three packaging runs were spent on panel defects the screenshots caught, not on content: a
  right-aligned value column overflowing the 320 px side panel, and the value and status columns
  touching the panel edge so the last glyph read as clipped. Each fix is `padding` in `index.html`,
  not a change to a number.

### Not done, stated plainly

- No frame of `film.mp4` was re-rendered for v1.3; the film is v1.2's.
- `docs/twin/so101/comparison.md` in the working tree is still the pre-S3 render (it repeats the hull
  sentence). It is **not in the package**; the packaged copy is `so101_vs_official.md`. Regenerating
  it needs a bundle re-render, which this sprint did not spend.
- The live hold still fails for contact geometry. Nothing in v1.3 changes that, and no panel claims
  otherwise.

### E4 — the revision a voice can call [verified: ran]

Added after v1.3 was cut. This is CLI source, not page content: the package holds no `.py` files
(33 entries, the only twin artefact is `twin.js`), and `docs/demo/so101_demo.zip` still hashes to
`f86c28f703f84ccfcb3269233ad7a0ef88e2843172387728f5af7c01b6b569f3`. **v1.3 remains the artifact of
record and is unchanged by this work.**

| What | State | Evidence |
|---|---|---|
| `twin revise` exists and is discoverable | `usage: robocad twin [-h] {summary,page,compile,revise,unpack} ...`; tested, because a verb only in a changelog is one a subprocess caller cannot find | `verified-ran`, `python -m robocad twin --help`; `test_the_help_names_revise_because_a_caller_scripts_against_the_help` |
| "change the infill to 30 percent" produces a spoken mass | real run on the SO-101 STEP, 25m58s, exit 0: `printed mass 0.9017 kg -> 0.9555 kg (+6.0%)`, `solid bound 1.3320 kg -> 1.3320 kg` | `verified-ran`, `twin revise --infill 0.30 …`; equals the frozen `docs/twin/so101/revision_f030/diff.json` |
| Bounds, and refusal before compiling | infill 0.1–1.0, wall 0.8–3.0 mm; `--infill 0.05` and `--wall-mm 0.4` each exit **2** with the reason, nothing compiled | `verified-ran`, both stderr lines quoted in SPRINT_LOG E4; 4 parametrised cases + exit-2 case in `tests/test_twin_print_model.py` |
| The assumption is announced first | `tooling:print_model` at pct 0, ahead of the compiler's `import` at pct 10; `KNOWN_STAGES` admits it without widening `STAGES` | `verified-ran`, progress stream, first line; 2 tests |
| A diff that is not the revision is refused | the first real run moved the solid bound (1.3320 → 1.0413 kg) because it named no actuators; `revise` now refuses that diff, exit 3, reason written into `diff.md` | `verified-ran`, guard output; `test_revise_refuses_a_diff_where_the_solid_bound_moved` |
| Refused before the compile, not after it | the frozen bundle records 6 bought-in parts, so a revise with no `--servo-mass-kg` exits **2** in 1.08 s naming both flags; a mass with a blank `--servo-source` is refused the same way. The guard downstream caught this only after 25m58s | `verified-ran`, `twin revise … --infill 0.30` on the real bundle; 3 tests |
| A mass-only change is not called unchanged | the real run first printed `0 changed` beside a 6% mass rise, and `diff.md` said `unchanged` next to `+11.35 g`; `diff_links` now counts mass, re-rendered to `7 changed` from the same two bundles without recompiling | `verified-ran`, regenerated `diff.md`; `test_a_mass_only_change_is_not_reported_as_unchanged`, `tests/test_revision.py` 23 passed |
| Tests | `tests/test_twin_print_model.py` **16 passed**; twin/CLI/bundle/demo suites **80 passed, 11 deselected**; full default tier **852 passed, 309 deselected**, exit 0, 11m03s | `verified-ran`, pytest output in SPRINT_LOG E4 |
| Documented under "Try it yourself" | `docs/demo/TRY_IT_YOURSELF.md`, placed outside the packaged README so editing it cannot break re-derivation of the tagged package | `verified-read`, file; `docs/DECISIONS.md` carries the reason |

**Not done, stated plainly:** `revise` reports printed mass and the link diff, not the effort check or
the torque comparison on the new masses — the frozen 0.652 → 0.687 N·m pair came from the scripted
path. Re-deriving a revision through the CLI also requires the caller to pass `--servo-mass-kg` and
`--servo-source` and the frozen `--joints`, because a compile without them counts servo envelopes as
printed plastic; the guard refuses the result rather than reporting it. No default is baked for the
servo mass: 55 g is a datasheet figure for one actuator, and a default would stamp it on every bundle
the tool is run against. The fix is to record `actuator_mass_kg` and its source in `bundle.json` so
`revise` reads them from `--before` — a next-bundle change, not one to make under a frozen tag. The
SO-101 STEP is still not in the repo, so `revise` cannot run from a clean clone without fetching the
third-party file.

### E2 — a clean machine, from the pushed branch [verified: ran]

Fresh directory, fresh clone of `feat/v1.1` at `9f15a15`, fresh `python -m venv`, no repository
history, no cached wheels beyond pip's own. Nothing here was run in the working checkout.

| Install | `twin summary` | `twin page` | `twin unpack --verify-sha` | `twin compile` / `revise` | `python -m pytest` |
|---|---|---|---|---|---|
| `.[dev]` | yes | refuses and names `[sim]` | yes | refuses out-of-range in ~1 s | 30 collection errors |
| `.[dev,web,sim]` | yes | yes, 5.27 s | yes | — | 27 collection errors |
| `.[dev,web,sim,ai,voice]` | yes | yes | yes | — | **853 passed, 309 deselected**, 4m37s, exit 0 |

Proof the CLI does not need the LLM path: in the `.[dev]` venv, `anthropic`, `mujoco`, `fastapi` and
`openai` are all `ABSENT`, and `twin summary --json` still prints `robocad.twin.summary/1` with every
section. `twin unpack --zip docs/demo/so101_demo.zip --verify-sha f86c28f7…` prints
`sha256 … (verified)` and `32 files match the FILES.sha256 the package ships`.

**Three dependencies were undeclared, and a clean machine is the only thing that finds that.**

| Defect | What a clean install did | Fix |
|---|---|---|
| `mujoco` absent, `twin page` | died inside `teardown_export/bake.py` with a bare `ModuleNotFoundError` from a helper module the caller has never heard of | `build_page` checks and refuses with one sentence naming `pip install -e ".[sim]"`, exit 2; `test_a_clean_machine_without_mujoco_is_told_what_to_install` | `0b63ab0` |
| `pyyaml` undeclared | `ai_cad/compiler/revision.py` imports it at module scope and `revise` imported that module **after** compiling, so a clean install would spend 26 minutes then crash on the import | `pyyaml>=6.0` in dependencies; the diff module is imported before the compiler runs | `043b06f` |
| `defusedxml` undeclared | `ai_cad/compiler/compare.py` imports it at module scope; any path reaching the comparison failed on import | `defusedxml>=0.7.1` in dependencies | `9f15a15` |

The full default tier in that fresh venv, at `4f56da0`:

```
$ python -m pytest -q
853 passed, 309 deselected, 3 warnings in 277.56s (0:04:37)
```

The 309 are `heavy`, `slow`, `mujoco` and `benchmark`, deselected by `pytest.ini`'s own `addopts`;
this file does not claim they ran.

**Not done, stated plainly:** the test suite does not run on `.[dev]`. With `[dev,web,sim]` it still
reports 27 collection errors, because 22 test modules import `anthropic` and 4 import `livekit` at
module scope. Making them import lazily or `importorskip` would mean editing 26 test files to get
green, which this sprint's own rules forbid, so the requirement is stated instead: running the suite
needs `pip install -e ".[dev,web,sim,ai,voice]"`, and the CLI does not. The Hi-EV half of E2 was run
by the monitor lane on the same day (`[claimed: peer report, a6d2e18]`, not re-run here).

### E3 — the whole script, keys removed, with the clock running [verified: ran]

`tests/test_journey.py` drives the real daemon WebSocket through all eleven utterances. Run on the
**merged** Hi-EV head (`c76fd47`) in the fresh clone, with `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`
removed from the environment, so an unmatched phrase has no provider to fall through to:

```
walk me through it            25.7 ms      next (x6)  9.0 / 7.8 / 7.6 / 7.1 / 7.8 / 7.6 ms
back                           7.3 ms      show me the torque  7.8 ms
what failed                   10.4 ms      how heavy is it     8.9 ms
open the live simulation      14.6 ms      1 passed in 1.27s
```

Worst case 25.7 ms against the 1.5 s budget. This measures the shell's own path, not a microphone: the
audio device and the speaker are Satyam's to test. The earlier pre-merge run by the monitor lane
(`[claimed: peer report, Hi-EV docs/SPRINT_LOG.md]`) logged 89.3 ms for "walk me through it"; the
merged-head run is faster, and both are far inside budget.

**What "offline" means in that run, exactly.** The network interface was up; `start_demo.ps1 -Offline`
was not used, because that flag fails the launch when the internet is reachable and this machine was
online. What was removed is every API key, so no utterance can reach a provider, and the phrase table
resolves all eleven. A true network-off rehearsal is the mic rehearsal and is Satyam's.

### The page text equals the summary, inside the package [verified: ran]

The packaged page is not the working-tree page. Measured on the merged tree:

| File | Bytes | sha256 (first 16) |
|---|---|---|
| `docs/demo/page/index.html` (working tree) | 49,222 | `b6d301fdbe54628c` |
| `so101_demo/index.html` (inside `so101_demo.zip`) | 49,764 | `6380af6904913a0d` |

So the equality check was run against the **extracted package** (`docs/demo/so101_demo.zip`, digest
`f86c28f7…`, 33 entries, 32 matching `FILES.sha256`), not the tree: `render_texts` on the extracted
`index.html`, every numeric token matched against the extracted `summary.js`.

```
torque-grp  figures=15     cmp  figures=17     checks  figures=16     twin-grp  figures=41
pose gate: 70.69 mm on page: True | 'tens of mm' present: False
OK packaged page matches packaged summary
```

89 figures across four panels, none without a source in the summary. The in-repo test
`tests/test_page_text_matches_summary.py` also passes on the tree (2 passed in 11.06 s, run with
`-m ""` to defeat the heavy deselect), but that is the tree page, which is why the package was checked
separately.

### E5 — both PRs merged, both heads tagged, the merged head starts [verified: ran]

| Step | Result |
|---|---|
| RoboCAD PR | https://github.com/satyamdas03/RoboCAD/pull/1, `feat/v1.1` → `master`, **MERGED** |
| RoboCAD merge commit | `1ac923c`, two parents `df95d33` (master) + `dca41f4` (feat/v1.1) — a merge commit, not a squash |
| Hi-EV PR | https://github.com/satyamdas03/Hi-EV/pull/1, `feat/robocad-shell` → `main`, **MERGED** |
| Hi-EV merge commit | `c76fd47`, merge commit, not a squash |
| Tag `demo-v1.0`, RoboCAD | annotated, object `2b51da8`, peels to `1ac923c` |
| Tag `demo-v1.0`, Hi-EV | annotated, object `c90cc71`, peels to `c76fd47` |
| `demo-bundle-v1.3` | untouched: object `dfcb119`, peels to `7b37d90`, blob still `f86c28f7…` |

Post-merge head proven to start, in a fresh clone of **`origin/master` at `1ac923c`** and
**`origin/main` at `c76fd47`**, fresh `python -m venv`, `pip install -e "./RoboCAD[dev,web,sim]"`
and `pip install -e "./Hi-EV[dev]"`, both exit 0, then:

```
pwsh -File scripts/start_demo.ps1 -RoboCadRoot .\RoboCAD -Port 7361 -Fresh
  1/6 environment   PASS python 3.14, PASS both repos import
  2/6 package       PASS digest f86c28f703f84ccf matches verify.json, 33 files, 32 match FILES.sha256
  3/6 demo profile  PASS EV_PROFILE=demo
  4/6 pre-flight    PASS digest, PASS summary 6 sections, PASS demo profile, PASS tool allowlist,
                    PASS fast path offline 'show me the torque' -> robocad_show/torque
  5/6 daemon        PASS pid 33984 health ok, PASS page served http://127.0.0.1:7361/robocad/page/
  6/6 open the page
```

Daemon stopped afterwards (`Stop-Process -Id 33984`). The HUD itself (`cd web && npm run dev`) was
not started in that clone; the six-phrase table is exercised by the pre-flight fast-path check, and
the mic, speakers and stopwatch are Satyam's.

**Not done:** the `demo-v1.0` tag points at the merge commits, so the FINAL_STATUS blob inside the
tag is the pre-tag one. Re-tagging is forbidden this sprint, so the correction lives in this commit
instead of under the tag.

## v1.2: superseded, kept for the record

Read this paragraph before handing anyone a zip. **The tag `demo-bundle-v1.1` points at a defective
package.** Its zip (sha256 `46b848e9…`, 25 files) carries a page that disagrees with the tree it was
built from, a summary the voice cannot speak from, and no way for the voice to point the page at a
panel. The tag is left where it is on purpose: moving or re-tagging a published artifact rewrites
what somebody may already have downloaded, so v1.1 stays as evidence of the defect and v1.2 is the
package to use.

| What | v1.2 state | Evidence |
|---|---|---|
| Tag | `demo-bundle-v1.2`, at the commit holding this exact zip | `verified-ran`, `git show demo-bundle-v1.2:docs/demo/so101_demo.zip \| sha256sum` equals `docs/demo/verify.json` |
| Package | `docs/demo/so101_demo.zip`, 3,943,593 bytes, **30 files** (29 payloads plus `FILES.sha256`), sha256 `b2f835c019fc114d0753f6e8dda33e3118c2b90eab122ffbeb339174d0744774` | `verified-ran`, `scripts/verify_demo_zip.py` four PASS rows, `VERIFIED` |
| One source of truth | `python -m robocad twin unpack --zip … --out <new dir> --verify-sha …` extracts and refuses on a digest mismatch; consumers point `ROBOCAD_BUNDLE_DIR` at its `bundle` field | `verified-ran`, `tests/test_twin_cli.py` (unpack tests) |
| The summary carries the demo's numbers | `check_counts`, `masses`, `residuals`, `torque`, `revision`, `calibration`, every value copied from the bundle's own files and labelled `{value, kind}` | `verified-ran`, on a fresh unpack of this zip: `checks 5 pass 1 fail 1 skipped`, `masses: solid 1.332 [modelled], print 0.9017 [modelled], published 0.632 [stated]`, `torque at rest: 0.7668 compiled vs 0.5377 published N m`, `revision … 0.9017 -> 0.9555 kg, 7 links changed`, `synthetic figures: 0 of 31 provenance entries, 18 in the calibration block` |
| One report for both repos | the zip's `report.json` is sha256 `34caf7e8…`, the same file the tree's bundle holds; `docs/demo/robocad_summary.v1.json` is that summary exported by `scripts/export_summary_fixture.py` with a sha256 sidecar | `verified-ran` |
| The packaged copy is the fixed copy | the zip carries `FILES.sha256`, one digest per file, written by the packager after its last write; `twin unpack` recomputes all 29 and refuses on a mismatch or an unrecorded file. The first rebuild of v1.2 shipped a stale `sections.js` and only a person diffing two files caught it | `verified-ran`, on this zip: `29 files match the FILES.sha256 the package ships`; three tests in `tests/test_twin_cli.py` cover match, mismatch and an unrecorded file |
| Section navigation | the packaged page ships `sections.js`: `{type:"robocad.section", section}` from the page's own origin scrolls the panel and flashes it 1.5 s; `#section` works from `file://` | `verified-ran`, `node --test docs/demo/page/sections.test.mjs` 10 pass; real browser over http: scroll 0 → 2699, wrong origin refused, no page errors |

Nothing about the robot changed in v1.2. The masses, the checks, the revision and the **failing live
hold** are exactly v1.1's numbers, and the hold still fails for contact geometry, not gain.

### Fixed in source, ships in the next bundle

The `self_collision` check explanation in `report.json` (and the `comparison.md` rendered from it)
stated the hull fact twice: once as "The status stays fail either way: MuJoCo collides the hulls…" and
again as "MuJoCo collides the convex hulls, and this overlap is an overlap of those hulls…". Read
aloud, that is the same sentence twice in 131 words. The generator in
`ai_cad/compiler/compile.py` (`_brep_note`) now states it once, folding the status sentence into the
single hull sentence. `TestExplanationReadsAloud` in `tests/test_twin_bundle.py` fails any check
explanation that repeats a sentence, or a ten-word run, whatever the case or punctuation.

**v1.2 is unchanged: no rebake, no re-tag.** The fix is in the source that builds the next package and
reaches a recipient only when v1.3 is packaged. A v1.2 recipient still hears the repetition.

### What Satyam still has to do, on hardware

These cannot be done from this machine and are not claimed as done anywhere:

1. Run the live viewer and confirm the page and the model agree on the zero pose. Correcting an
   earlier line in this file: the viewer is the MuJoCo window that `robocad demo so101` opens on this
   laptop. `robocad/demo.py` states that nothing in it talks to hardware, so **no SO-101 is needed for
   the rehearsal** — only the microphone, the speakers and the stopwatch.
2. Rehearse the microphone in the room and confirm the voice's section requests land on the intended
   panel while someone is speaking over it.
3. Time the 1.5 s section-navigation latency by ear and by stopwatch; the code flashes for 1.5 s, the
   perceived delay to first scroll has not been measured outside this machine.
4. Record `voice_walkthrough.mp4` against the v1.2 package, and only then describe it as a recording
   of the demo.
5. The bench protocol still needs a human supervisor, joint and torque limits and a stop condition
   at the bench; the licence review of the derived `robot.joints.yaml` is still Satyam's call.

## v1.1: what changed, and what it costs

Superseded by v1.2 above; kept because the defect history is the reason for the unpack rule.

v1.1 is not a new demo. It is the same robot and the same page, with four defects fixed and two
handover artifacts added. The rows below are the delta; the sections after them are still true.

| # | Change | State | Evidence |
|---|---|---|---|
| R1 | Torque contradiction, official vs compiled | **resolved as a definition, not a number**: static load is `qfrc_bias` at rest, and the earlier 2.942 N·m readings were `mj_inverse` reporting the servo's own force limit | `verified-ran`, `tests/test_demo_static_load.py` 6 pass |
| R1.4 | Retest the live hold with the corrected pose mapping | **Still fails, and now says why**: 573.23 mrad steady error, 64 contacts active, `qfrc_constraint` up to 3.29 N·m against a 2.942 N·m limit and 0.254 N·m of gravity. Contact geometry, not gain and not torque | `verified-ran`, `robocad demo so101 --mode hold` |
| R2 | Zero-pose conventions inside the bundle | done: `manifest.json` plus an MJCF comment, both rendered from one `Conventions` object, pinned by a mutation test that breaks the reader | `verified-ran`, `tests/test_conventions.py` 8 pass |
| R3 | Mesh resolution stated | done: the page payload carries `triangle_budget`, so the 500-triangle decimation is disclosed rather than silent | `verified-ran`, `tests/test_mesh_resolution.py` |
| R4 | Calibration against the current channel | **SYNTHETIC**, Lane B, `e1312b1`; the bench protocol carries joint and torque limits, a stop condition and the supervision note | `claimed` by Lane B, protocol read here |
| R5 | Tag, zip, fresh-folder verification | `demo-bundle-v1.1` at `cb33678`; zip rebuilt and verified at sha256 `46b848e9…`, 25 files. **Superseded: that package is defective, see the v1.2 block; the tag stays** | `verified-ran`, see "Freeze state" |
| H0 | JSON CLI for Hi-EV | done: `python -m robocad twin summary|page|compile`, fixed stage set, JSON progress lines, exit codes 0/2/3, every figure labelled | `verified-ran`, `tests/test_twin_cli.py` 15 pass (+2 MuJoCo) |
| H5 | RoboCAD blade for the Hi-EV HUD | done as a drop-in in `docs/twin/hiev_blade/` with its own tests; Hi-EV copies it, the repos stay separate | `verified-ran`, `node --test panel.test.mjs` 10 pass |
| H7 | Cross-verification | Lane A checked eleven of Lane B's spoken figures against the artifacts: ten matched, two were rewritten, and the packaged zip was checked separately | `verified-ran`, `docs/demo/H7_cross_check.md` |

Cost of v1.1, stated plainly: the hold still fails, and it fails for a reason no gain change fixes.
Collision geometry has to be fixed before this robot can be driven, and that is post-demo work.

## Open this first, in this order

1. `docs/demo/page/index.html` — open it directly from disk. No server, no network. Living page.
2. `docs/demo/film/so101_demo.mp4` — 24 s, recorded from that same page.
3. `docs/demo/twin/identification.json` then the page's "Twin method" panel — the identification
   rungs and exactly which one is blocked.
4. `docs/demo/README.md` — the 3 minute walkthrough and the real-versus-synthetic table.
5. `docs/twin/so101/bundle/report.json` and `docs/twin/so101/revision_f030/diff.md`, then
   `docs/twin/so101/CONVENTIONS.md` — the checks, the revision's before/after, and the five zero-pose
   offsets without which the joint origins appear to disagree by centimetres.

## What the page shows today

| Element | Source | State |
|---|---|---|
| 3D view | **the compiled bundle's own 259 visual meshes** | `verified-ran`, offline, 56 fps, 128k triangles |
| Masses: solid 1.332 kg, print model 0.902 kg, published 0.632 kg | compiled bundle `comparison.json` | `verified-ran`, tagged `demo-bundle-v1` |
| Seven checks: 5 pass, `self_collision` fail, 1 skipped | compiled bundle `report.json` | `verified-ran` |
| Required torque per joint | inverse dynamics, both models | `verified-ran` |
| Kinematics vs official | sense-searched datum fit | `verified-ran` |
| Twin method rungs | `identification.json` | `verified-ran` |
| Provenance line | states every split above on screen | `verified-ran` |

## Verified numbers

- Page loads from `file://` with the browser context offline: **zero non-file requests**. `verified-ran`
- Page geometry matches MuJoCo to **0.000 to 0.001 mm** on three mesh geoms. `verified-ran`
- Render 54 to 56 fps headless at the shipped page's 128,073 triangles over 600 frames, zero network
  requests, zero console errors. `verified-ran`
- Compiled bundle, frozen tag `demo-bundle-v1` at `f202c12`: 7 bodies, 6 hinge joints, 692 mesh files
  (433 collision hulls + 259 visual meshes), **0.9017 kg** printed / **1.3320 kg** solid bound. Checks:
  `meshes_load` pass,
  `inertia_valid` pass, `pose_equivalence` pass at 0.000 m over 100 configurations, `mujoco_load`
  pass, `self_collision` **fail**, `limits_and_effort` **pass** (0.652 N·m on `joint_2`, 22% of the
  servo's 2.942 N·m stall, contacts disabled), `free_base_stand` skipped. `verified-read` from
  `report.json` at the tag, and re-derived from the packaged zip's own `report.js` by
  `scripts/verify_demo_zip.py` `verified-ran`
- Default test tier at the tag, measured in a worktree checked out at `demo-bundle-v1`:
  **745 passed, 300 deselected, 3 warnings, 391.13 s, exit 0**, collected 1045. `verified-ran`. The
  three warnings are pre-existing `InsecureKeyLengthWarning`s. Recorded in `docs/BASELINE.md` with no
  caveat, because the tree was the tag and not the tag plus edits.
- Joint axes agree with the published model within **2.14 degrees** (rms 1.05) after a
  sense-searched datum fit over all 64 sense combinations. `verified-ran`
- Joint **origins** do not agree. Bounded metric, anchor to the other joint's axis: **94.2, 110.3,
  54.0, 54.7, 27.7, 54.5 mm**. `verified-ran`. The infinite-line minimum is NOT used: five of six
  joints attain it more than 250 mm along the axis and one at 9.64 m, which is meaningless for a
  robot. No clustering claim is made; the offsets sit between 28 and 110 mm.
- **P0-a verdict, reproduced independently: same robot, missing conventions.** With five constant
  zero-pose offsets applied to the compiled model by joint name, a base translation of (38.74, 6.64,
  -2.86) mm and no rotation, the residual at the five joint origins over 100 poses is **median 2.50
  mm, p90 5.95, max 11.25**, and the fitted offsets are -88.17, +90.29, -90.31, -0.15, 0.00 degrees.
  Both a seeded and a zero start converge to the same vector, so it is not a local basin. `verified-ran`
  Data: `docs/demo/twin/p0a_confirmation.json`.
- Superseded by that verdict, and kept here so the record is honest: the earlier median 168 mm at the
  same joint vector compared two models whose zero poses and base frames differ; the 38 mm after a
  tip-centroid fit was dominated by the jaw frame, which disagrees by 5.74 mm at rest, so five-anchor
  fitting is the correct residual; and the 27.6 to 94.5 mm line-distance family was partly a
  degenerate metric, five of six minima being attained more than 250 mm along the axis.
- What P0-a does **not** clear: collision geometry, mass, inertia, contact behaviour. The
  `self_collision` fail and the 13 oversized hulls live in P0-b and are untouched by this verdict.
- Self-collision: hulls overlap **7.9 mm** at rest. The B-rep solids touch and share **0.52 mm³**
  across 47 of 47 shape pairs, which is contact-scale, not a statement that the parts fit together,
  against a 32.27 cm³ wrist and 20.69 cm³ jaw. Hull overlap is real for the simulator; the solids
  do not interfere. `verified-read` from Lane A, corrected after their unit bug
- Identification rungs 0, 1, 2 and 4 recover (0.57, 1.6/0.86, latency exact, 0.12/0.56 percent).
  Rung 3 is blocked. `verified-ran`
- The freeze run, over every test the default selection collects: **752 passed, 300 deselected, 3
  warnings, 367.27 s, exit 0**, collected 752 of 1052, on the tree at `4af81f5`. This is the row that
  covers the seven artifact tests the earlier post-tag run missed. `verified-ran`, in
  `docs/BASELINE.md` under "The freeze commit".
- **v1.1 default tier: 798 passed, 308 deselected, 3 warnings, 957.27 s, exit 0.** That is 46 more
  tests than the freeze run, which is the four v1.1 test files (`tests/test_twin_cli.py` 15,
  `tests/test_conventions.py`, `tests/test_mesh_resolution.py`, `tests/test_demo_static_load.py` 6 of
  which are MuJoCo-marked). The three warnings are the same pre-existing `InsecureKeyLengthWarning`s.
  `verified-ran`, command `python -m pytest -q -p no:cacheprovider`.
- **The tree moved under that run, and the moved parts were re-run.** Lane B landed
  `teardown_export/bake_torque.py`, `package_demo.py` and `torque_matched.py` changes after the run
  started, so the python that ran is not the python at `HEAD`. Rather than re-run sixteen minutes of
  suite, the tests that cover the moved files were run on the moved tree:
  `python -m pytest tests -k "package or bake or mesh_resolution or torque"` → **17 passed**, and the
  MuJoCo-marked tests in the two files v1.1 changed → `tests/test_demo_static_load.py`,
  `tests/test_twin_cli.py` with `-m mujoco` → **8 passed**. Everything else in the suite is untouched
  by those three files. `verified-ran`

## Cross-verification of Lane A's published bundle

Three targets were named before computing them, so the choice could not flatter the result.

1. **Hashes, quoted so that they mean the same thing on any machine.** Git blob ids at the tag:
   `model.mjcf` `1f18f38adf3e...`, `model.urdf` `760c668dff45...`; sha256 of the repository blobs
   (LF line endings, as `git show` emits them): `model.mjcf`
   `5aa5912b34f79cdfda2fb4d358716c0bf6cfc0e393d2b6b7ffa8c8de7810c2d7`, `model.urdf`
   `50c8cbc66e06961f8bf41df31e3d942d2156262594f2dcb20fb6b39b702030fd`. `verified-ran`. The earlier
   values here (`c427c3e1...`, `86ce5502...`) are withdrawn: they were sha256 of a working-tree copy
   of an earlier bundle, and a working-tree hash depends on `core.autocrlf` — this machine checks
   those files out with CRLF, the repository stores LF, so the same commit produces different bytes
   in different checkouts. That is the same defect as a path printing its producer's separator, and
   it is why the byte-identity argument the earlier text rested on no longer holds: the bundle was
   deliberately regenerated at `f202c12` to add actuators and visual meshes, so its digest moved for
   a stated reason, not an unexplained one.
2. **Pose equivalence**, re-derived on the frozen bundle rather than read: both models loaded in
   MuJoCo, bodies keyed by name, world position and rotation compared at the zero pose and at 20
   random configurations inside the joint limits. 147 body comparisons, worst error
   **0.000e+00** everywhere on both position and rotation. `verified-ran`
3. **Mass consistency**, re-derived from `bundle.json` rather than read: the seven `solid_mass_kg`
   values sum to 1.3320123928506593 kg, equal to `total_solid_mass_kg` to the last bit, and the seven
   `mass_kg` values sum to 0.9016588355893798 kg, equal to `total_mass_kg`. Implied density is
   **1240.0 kg/m³ exactly** on the two all-printed bodies (`upper_arm_so101`, `moving_jaw_so101`) and
   **1476.6 to 2048.9** on the others, which is the datasheet-density path doing its job: a body that
   carries bought-in servos is heavier than PLA alone would explain. The earlier version of this line
   claimed "exactly 1240.0" and a 1.04134 kg total for every body; both were true of the bundle before
   the print model existed and neither is true of the frozen one. `verified-ran`

**The revision diff that shipped.** The `revision.json` published earlier
with the bundle compared `robot.joints.proposed.yaml` against `so101_demo` and reported **19 links
removed, 7 changed, 0 added**, an artefact of two different link identity schemes rather than a
revision. It was excluded from the page and flagged. `ai_cad/compiler/revision.py` now records each
document's link scheme and returns `comparable=False` with a reason instead of a table, and the two
files were removed from the published bundle. A diff that reports deletions that never happened is
worse than a missing panel.

That gap is closed by a real one. Same pipeline, same STEP file, one input changed: the print model's
infill fraction, 0.20 to 0.30, keyed only on the link names `robot.joints.yaml` declares.

| | before (f = 0.20) | after (f = 0.30) | change |
|---|---|---|---|
| printed mass | 0.9017 kg | 0.9555 kg | +0.0538 kg, **+6.0%** |
| solid bound | 1.3320 kg | 1.3320 kg | unchanged, the solid is not a print assumption |
| effort demand | 0.652 N·m on `joint_2` | 0.687 N·m on `joint_2` | 22% to 23% of the 2.942 N·m stall |

Sanity, all re-derived by `python scripts/diff_revision_f030.py` rather than asserted: **0 links
added, 0 links removed**, all **7** printed links heavier (biggest relative movers `upper_arm_so101`
+16.2% and `moving_jaw_so101` +8.3%), and the actuator and joint blocks **byte-identical** between
the two bundles, which is what "servos unchanged" means when a bundle states its hardware in those
blocks. `verified-ran`. Artifacts: `docs/twin/so101/revision_f030/diff.json` and `diff.md`, with the
`f = 0.30` bundle committed beside them (2.5 MB, hulls only) so the diff can be re-derived by someone
who does not trust this machine.

## Identification: the rung reached and why it stopped

Rung 3, 62 Hz with sensor noise and 4096 count quantisation, does not recover. The reason is
arithmetic, not tuning: one count of position error is 1.53 mrad, the published servo is about
998 N m per rad, so a single count is roughly **1.53 N m of actuator torque noise** against a
friction signal of about **0.15 N m**. A signal to noise ratio of 0.1 is not a fitting problem. A
partner's bench log with a real torque or current channel escapes this; a 62 Hz position log does not.

Rung 0 failed at first and the cause was mine: zeroing the other joints' damping removed what keeps
a very stiff position servo stable, the simulation diverged, and the divergence was being fitted as
friction. That is the kind of bug this harness exists to expose, and it is written down because the
same mistake will be made again.

## Assumptions Satyam must confirm

1. **The print model's two inputs: wall 1.2 mm, infill 0.20.** Printed mass is `0.9017 kg` at those
   settings, against a `1.3320 kg` solid bound on the same geometry with no print model at all. Both
   are the model's stated
   assumptions, not measurements, and the bundle prints both figures side by side so the range is
   visible: `print_model` reads `"1.20 mm wall over 20% infill"` in `bundle.json`. The infill value
   is live code, not prose — the `f = 0.30` revision in this report was produced by passing it to the
   compiler. `verified-read` and `verified-ran`. **What Satyam must confirm:** that 1.2 mm and 0.20
   describe how the partner would print this, because every mass here moves with them.
2. **Servo mass, 55 g plus or minus 1 g**, sourced to the Feetech STS3215 product specification
   document (feetech.cn); the code carries the document name, not a URL. It enters the
   comparison only, as the figure that reconciles our mass against the published mass. It does **not**
   enter the bundle's mass properties, which is why `actuator_mass_kg` is null; a reader who assumes
   55 g is already inside our body masses would overstate every body. `verified-read` from Lane A.
   **What Satyam must confirm:** that the STS3215 variant cited is the one the partner ships, because
   a different servo changes the comparison against the published model and not the compiled masses.
3. **Publishing `docs/twin/so101/`.** Satyam authorised this in the sprint directive, verbatim:
   "Publish docs/twin/so101/: YES. Add docs/twin/so101/NOTICE.md crediting the SO-101 project, its
   Apache-2.0 licence, the pinned commit, and a list of what we changed." **Done:** the directory is
   committed, `NOTICE.md` is written, and the tag `demo-bundle-v1` exists at `f202c12`. The earlier
   licence caution on derived CAD is resolved for this directory by that instruction. `verified-ran`
   (`git tag --list`, `git ls-files docs/twin/so101 | wc -l`).
4. **M2 joint skeleton review:** reviewed by the session that did not write it, against four written
   criteria, **PASS 4/4**, with the official URDF's sha256 re-checked against the digest the checker
   pins before the check ran. The skeleton and the review record are committed
   (`docs/twin/so101/robot.joints.yaml`, `docs/twin/so101/JOINT_REVIEW.md`), and the tracker row is
   `[x]`. `verified-ran`.
5. **Actuator gains are assumptions.** `kp` = 20 and `kv` = 1 are labelled as assumptions in the
   bundle; the real servo closes its own loop and publishes no stiffness. The live hold in
   `docs/twin/so101/live_hold.md` fails at those gains and the failure is kept. **What Satyam must
   confirm:** whether the partner can supply measured gains, which is Phase 2 calibration.

## What is deliberately not shipped

- **Collision-hull rendering on the page.** The bundle carries 692 mesh files: 433 collision hulls
  and 259 visual meshes. The shipped page renders the visual meshes, decimated to a 500-triangle
  budget by `teardown_export/bake.py`, which prints `unique meshes 259 triangles 128073 across 259
  mesh geoms`; the bundle's source geometry is 620,093 triangles from `report.json`. The hull bake
  exists at `docs/demo/page_compiled/` (433 hulls, 0.8 MB) and is not shipped, because a printed
  part's hulls render as a block. `verified-read` for the file inventory, `verified-ran` for the
  triangle sum.
- **Official-model toggle**, cut by the sprint's own cut order.
- **Heavy test tier**, stopped by instruction; one frozen Labs test exceeds 900 s.

## Next three steps after the demo

1. Attribute the ~54 mm perpendicular joint-origin offset. The hypothesis on the table is that the
   axis point is taken on a mating cylindrical face rather than at the bore centre, which would make
   the offset look like a radius. Lane A is testing it against the six bore radii.
2. Measure what the page's 500-triangle-per-mesh decimation costs in millimetres against the bundle
   meshes. The bundle's own budget was held to 1.20 mm worst vertex displacement under a stated
   measurement; the page goes coarser without one, and a partner who compares the page to the CAD
   will be the one who notices.
3. Widen the identification to a real torque or current channel so a partner's bench log can be
   identified at 62 Hz, which is the only way the Twin's central claim becomes checkable outside
   this machine.

## Film and page

The packaged film is the 10:52 re-record, taken after the page settled and after the revision panel
was wired. `verified-ran`: the film inside the zip is byte-identical to `docs/demo/film/so101_demo.mp4`
(2,199,551 bytes, sha256 `31ac62e76d43bf35...`). The earlier `so101_demo_new.mp4` (10:40) is not
shipped. The earlier note here about a two-word provenance difference is withdrawn: the shipped
`twin.js` contains no "being regenerated" string, so there was nothing for the film to differ on.

## Security review findings, and where each stands

Five findings were raised; three of them changed what an artifact says rather than what an attacker
can do. All three have since been fixed in source, and each is listed with the code path that would
have to regress and the artifact that would show it. Verified by reading the source and the
artifacts, not by taking the report's word.

1. **Assumed-density disclosure was suppressed in the comparison.** `bundle.json` bodies carry
   `rests_on_an_assumed_density`; `compare.py` read only `assumed_density`, so every body read
   False. **Fixed** at `ai_cad/compiler/compare.py:568`, which reads the short spelling and falls
   back to the bundle's long one. Evidence in the frozen artifact: all seven comparison bodies now
   read True, which is the correct answer and the one the old code could not produce.
   `verified-ran`
2. **`limits_and_effort` passed on provenance, not measurement.** It ended with
   `status = "pass" if source else "warn"`. **Fixed** in `ai_cad/compiler/bundle_checks.py:616`: a
   joint whose inverse-dynamics demand exceeds its `forcerange` now **fails** the check; actuators
   that state no force limit **warn**, because a command range is not an effort limit; and `pass`
   requires travel limits, stated force limits, a source, and every sampled pose under the ceiling.
   The bundle's pass reads "largest demand ... 0.652 N*m on joint_2, 22% of its 2.942 N*m limit,
   measured with contacts disabled". `verified-ran`
3. **The limits provenance stamped a pinned revision it never verified.** `scripts/demo_so101_twin.py`
   wrote `a758567...` unconditionally. **Fixed**: the revision is claimed only for the bytes whose
   sha256 equals `PINNED_LIMITS_SHA256`, and any other file gets a provenance string that says it is
   not that file and names the digest it does have. `verified-read`

The withdrawal that stands: the earlier sentence "the compiled robot moves wrongly by seven
centimetres" is withdrawn. It described the same-q difference without first removing the zero-pose
and base-frame difference, which is exactly what `CONVENTIONS.md` now prevents.

## Freeze state, Sat 14 Nov

- **Package, v1 (superseded by the v1.1 package below, kept so the two can be compared).**
  `docs/demo/so101_demo.zip`, 3,892,730 bytes, 20 files, sha256
  `fff730639bc40ca7e4f7efc924a092fed0bebae4f01ec659291da1ea8920c26f`, built by
  `teardown_export/package_demo.py` from commit `430c77e` (the packager's statement; nothing in this
  repo can check a zip against a commit, so it is recorded as a claim), which copies the artefacts,
  zips them, extracts the zip into a fresh temporary directory and opens that copy from `file://` with
  the network off. The package test is the deliverable, not the folder.
- Frozen bundle tag: **`demo-bundle-v1` at `f202c12`**, and nothing inside `docs/twin/so101/bundle/`
  changed under that tag. The v1.1 tag adds `manifest.json` and the MJCF conventions comment and
  rebakes `report.html`'s timestamp; those changes belong to `demo-bundle-v1.1` at `cb33678`, not to
  v1, and the diff between the two tags is the honest way to see them.
- Live viewer: `python -m robocad.demo so101 --bundle docs/twin/so101/bundle --mode replay` replays
  the bundle's trajectory. **Hold fails and the failure ships as documentation, not as a caveat**:
  573.23 mrad steady error, and the v1.1 diagnostic says what the error is made of. It is **not** the
  force limit that stops the servo: gravity at the held pose is 0.000 to 0.254 N·m against a 2.942 N·m
  limit, while `qfrc_constraint` reaches **3.29 N·m** with **64 contacts** active. The earlier
  explanation here ("all six joints at the 2.942 N·m force limit, because `kp` = 20 asks for 10 N·m")
  was the measurement artefact R1.4 was written to settle: `mj_inverse` with a position servo at
  `ctrl = 0` reports the servo's own saturation as load. Per-joint numbers in
  `docs/twin/so101/live_hold.md`; verdict and the test that pins it in `docs/DECISIONS.md`. Replay
  stays the demo path. `verified-ran`
- Independent verification of the package: `scripts/verify_demo_zip.py` names three numbers before
  computing any of them (printed mass 0.901658836 kg; revision 0.901658836 to 0.955453030 kg; seven
  check rows at 5 pass / 1 fail / 1 skipped), extracts the zip to a fresh directory, and re-derives
  each from the zip's own baked JSON. It also asserts the page opens from `file://` with zero page
  errors and zero non-file requests, that the revision panel renders its seven rows, and that the
  rendered panel prints no Windows path separator. All four pass on this package, exit 0:
  **VERIFIED**. Result in `docs/demo/verify.json`. `verified-ran`. The separator check earned its
  place: the 10:52 package passed the other three and failed that one, because `diff.json` had been
  written with `str(path)`; the artifact was fixed at `cdb1662` and the page rebaked, and the check
  is what forced the rebake rather than a reader noticing a `\` in a document.
- Page rendered from the bundle's own visual meshes at 128,073 triangles, 56 fps, zero network
  requests. The triangle count is `verified-ran` two ways: decoded here out of `page/meshes.js`, where
  each mesh's packed index buffer sums to exactly 128,073 triangles across 259 meshes, and the
  bundle's own 620,093 source triangles from `report.json` `verified-read`.
- Comparison panel states solid upper bound, print model, published figure, the gap between the last
  two, and the conventions note with the 1.69 mm frame-free link-length agreement.
- Torque panel reads its limit from the bundle's actuators, 2.94 N·m, and is not saturated on this
  trajectory: peak 1.26 N·m official against 0.63 N·m compiled.
- **Pushed, on a branch.** `feat/v1.1` is on `origin` at `cb33678` plus the lane's follow-up commits,
  and the tag `demo-bundle-v1.1` points at `cb33678` on both sides (`git ls-remote --tags origin`
  agrees with the local tag). `master` is still local and still ahead of `origin/master`: the sprint
  order says push, and a branch push is reversible whereas moving `master` is not the lane's call. If
  Satyam wants this on `master`, that is his merge, and nothing here has been rebased or forced.
- **Package, v1.1.** `docs/demo/so101_demo.zip`, 3,919,227 bytes, 25 files, sha256
  `46b848e90ff12d5189e009f38a2fb25d4950646d26166a9c9132ac622a067d4b`, rebuilt by Lane B against the
  regenerated bundle. Lane A re-ran `scripts/verify_demo_zip.py --out docs/demo/verify.json` on it:
  the four named checks pass and it prints **VERIFIED**. It is 25 files rather than v1's 20 because
  `manifest.json`, `BENCH_PROTOCOL.md`, `bundle.json`, `model.mjcf` and `robot.joints.yaml` were
  added. `verified-ran`. The **tracked** artifact is the verified one: `git show
  2f2920c:docs/demo/so101_demo.zip` hashes to the same sha256, so the zip in the repository is
  byte-identical to the zip the verifier read, not merely the same size.
- **Two defects found inside the package, and both fixed in the rebuild.** Lane A extracted the
  earlier build (sha256 `86beadf5…`, 22 files) to an empty directory and read only its contents:
  `manifest.json` named five files the package did not carry (`robot.joints.yaml`, `model.mjcf`,
  `model.urdf`, `bundle.json`, `meshes/`), so a consumer following that map found a dead end
  everywhere except `report.json`; and the spoken figure "the jaw frame differs by 70.7 mm" appeared
  nowhere in the package, whose torque payload said only "tens of mm". In the current build every
  entry in the manifest's file map resolves (`robot.joints.yaml`, `model.mjcf`, `bundle.json`,
  `report.json`), the two genuinely absent artifacts are listed under `not_in_package` with a reason
  rather than left to 404, and `torque.js` carries `pose_gate_worst_mm` 70.69 with its five samples.
  The A6 verifier passed all four checks on **both** builds: what caught this was reading the
  manifest rather than running the verifier, which is worth knowing about the verifier. `verified-ran`
- **One wording nit left in the package.** `torque.js`'s `dynamic_reason` still says "tens of mm"
  while `pose_gate_worst_mm` beside it says 70.69, so the package holds the number and does not use
  it in the sentence. True either way, and a rebake to change one clause is not worth the risk this
  late — a rebake means a new digest, and this digest has been verified and recorded. Noted so the
  next bake fixes it. `verified-read`
- **The pose gate now has its own test.** Lane B added `tests/test_package_pose_gate.py` (`4b993eb`),
  which reads the committed zip rather than rebuilding it, so it cannot move the digest above. Four
  assertions: the gate ships beside the verdict it explains, it equals the worst of its own five
  samples, it matches 70.69 mm, and it is larger than the 11.25 mm anchor residual — that last one is
  what would have caught the version of the gate that read 97.37 mm. Lane A ran it on the pulled tree:
  **4 passed**. `verified-ran`
- M2 review recorded as PASS by the lane that did not write it, 4 of 4 criteria, with the official
  URDF's sha256 verified against the pinned digest before the check ran.

## Five things Satyam has to confirm

1. **Wall thickness 1.2 mm** — the print model's first input, and every printed mass scales with it.
2. **Infill 0.20** — the second input; today's revision exists to show what moving it to 0.30 costs.
3. **The 55 g servo mass and its source** (Feetech STS3215 specification) — it drives the comparison
   against the published model and not the compiled masses.
4. **Actuator `kp` = 20 / `kv` = 1** — labelled assumptions, and the reason the live hold fails
   honestly rather than passing quietly.
5. **Publishing `docs/twin/so101/`** — done under the sprint directive; confirming it keeps the
   licence statement and the pinned commit on the page, film and report.

## B5 and U1: one signal-to-noise number, and the page rebuilt as a cockpit

Both were assigned by review after the v1.3 freeze. Neither rebuilds v1.2 and neither creates a tag.

### B5, the two signal-to-noise numbers

**What was wrong.** The twin panel printed "signal to noise ratio of 0.04" in one paragraph and the
identifiability document printed 0.10 for the same physics. Both were real arithmetic on different
denominators: the document divided friction torque at a stated reference speed by the actuator torque
of one encoder count, and the generator divided by the peak speed of whichever log it happened to
describe. Same robot, two answers, depending which log was in hand.

**What it is now.** One definition — friction torque at reference speed divided by the torque of one
encoder count — computed at `REFERENCE_SPEED_RAD_S = 1.9` rad/s in `ai_cad/twin/identification.py`
(`rung3_note`), which names that speed in the sentence it prints so a reader can redo the division.
The page quotes `calibration.position_only.snr` from the summary payload once, in the twin card,
with that label beside it. The rung-3 note that used to carry 0.04 is not rendered anywhere.
`verified-ran`: `pytest tests/test_identification_snr.py -m ""` gives 6 passed, including a test that
the ratio does not move when the log rate changes, which is the bug in one assertion.

**The caveat, plainly.** The generator is fixed; the **frozen artifacts are not**. These four still
contain the old 0.04 sentence, byte for byte, because they were baked before the fix and a rebake
means a new digest on a verified package:

- `docs/demo/so101_demo/identification.json`
- `docs/demo/twin/identification.json`
- `docs/twin/so101/bundle/identification.json`
- `docs/demo/robocad_summary.v1.json`

`verified-ran`: `grep -o "signal to noise ratio of [0-9.]*"` over each of the four prints the 0.04
sentence on all four. Anything reading those four **JSON artifacts** therefore still reads 0.04;
anything reading the **living page** reads 0.10 from the summary payload. The fix reaches the
package at the next bake, and this paragraph is what tells the next person to rebake it.

The stale prose does not reach a reader through the UI, which was checked against the artifact rather
than the tree: the reviewer extracted `demo-bundle-v1.3` and grepped its `index.html` — four `0.04`
occurrences, all JS constants in colour and explode maths, and the SNR sentence reads
`calibration.scenarios`, i.e. 0.10. `[claimed: peer report, gates on f9a8184]`

### U1, the page as a single-screen cockpit

`docs/demo/page/index.html` was replaced. The old page scrolled with a 320 px rail, so at 1280x720
the fourth panel fell below the fold and "show me the checks" was answered by a scroll. The new page
is a fixed grid: top bar (product block and five KPI tiles), centre 3D hero with guide rings and the
wrist/jaw callout, numbered cards down both sides, footer timeline with the revision switch, and a
detail drawer that every card's "i" opens. Every figure comes from one adapter over the existing
payloads (`summary.js`, `SO101_META`, `SO101_TRAJ`, `SO101_REPORT`, `SO101_TORQUE`,
`SO101_REVISION`, `SO101_IDENT`), so the page-text test still traces every number to the summary.

`verified-ran`, the gates:

- `pytest tests/test_page_cockpit_layout.py -m ""` gives **5 passed**. One screen at 1280x720,
  1440x900 and 1920x1080 (`scrollHeight <= innerHeight`, no `.card .body` with
  `scrollHeight > clientHeight`, no horizontal overflow), zero console errors, zero requests that
  are not `file:`, and each of the seven sections flashes the card it maps to.
- `node --test docs/demo/page/sections.test.mjs` gives **11 passed**, including a new test that every
  section in the JS map names an `id=` the shipped page really contains, so the map cannot drift.
- `python scripts/check_page_numbers.py` reports "32 numeric tokens across torque-grp, cmp, checks,
  twin-grp all trace to the summary".
- `pytest tests/test_page_text_matches_summary.py -m ""` gives **2 passed**: the page quotes
  `70.69 mm` in the torque card and never says "tens of mm".
- Full default tier: **859 passed, 314 deselected, 3 warnings in 442.12 s** (the three warnings are
  the pre-existing `InsecureKeyLengthWarning` from `tests/test_hermes_voice.py`).

Screenshots committed: `docs/demo/screens/v1.4/cockpit-1280x720.png`, `cockpit-1440x900.png`,
`cockpit-1920x1080.png`.

**Deviations from the brief, and why.** None of these are "should work"; each is what the payloads
and the freeze actually allow.

- **No package sha or tag on the KPI tile.** The page payloads carry no package digest and
  `SO101_MANIFEST` records no tag. Rather than invent either, the tile reads "manifest.json · no tag
  recorded". The digest of record stays in this document and in the package's `FILES.sha256`.
- **`HULLS` and `OFFICIAL GHOST` are not shipped as toggles.** The payload carries visual meshes only
  (`SO101_MESHES` is 259 `_vis` entries, no collision hulls) and no published-model geometry.
  Shipping them would have been two switches that do nothing. `SELF-COLLISION` and `CoM` took their
  places, and the reason is written into the card's own drawer entry, "06 · what the toggles do".
- **The 70.69 mm marker sits at the end of the scrubber.** The trajectory samples are poses, not
  numbered frames, so there is no honest frame index to plant it at.
- **The turntable frame rate is a property of the machine, not the page.** Three readings on the same
  533,262-triangle payload at 1440x900, each with its renderer, none of them a claim about a
  viewer's laptop: **7 fps** on SwiftShader, a software rasteriser (headless Chromium's default);
  **61 fps** headless on `ANGLE (Intel, Intel(R) UHD Graphics (0x46A8) Direct3D11)`; **61 fps**
  independently on `ANGLE (Intel, Intel(R) UHD Graphics (0x0000A788) Direct3D11)` (reviewer's
  measurement, same flags); and **145 fps** headed on the first. The test asserts on the GPU path
  with `--enable-gpu --use-angle=d3d11 --ignore-gpu-blocklist` and puts the renderer name in its
  failure message, so the next machine to fail says why rather than reporting a number in isolation.
- **Tree and package now diverge, by design.** The packaged page at `docs/demo/so101_demo/` is still
  v1.3's page; v1.3 is frozen and was not rebuilt. The cockpit page exists in the tree only. The
  page-text test reads the tree page, as it always did, so the divergence is expected rather than
  silent.

### The legibility pass, after the design hook flagged the page

The design detector returned 28 findings on the new page, all of one kind: functional text under the
11 px floor and a quiet grey below the 4.5:1 contrast bar. Both were real, and both were mine.

- **Type floor.** Every functional size was between 8 px and 10.5 px (8 px KPI labels, 8.5 px status
  words and rung pills, 9 px card headings and rows). All of it is now **11 px**, and the drawer body
  and card titles 13 px. The one-screen gate was re-run after the change and still passes at all three
  viewports, which was the risk: the page was dense enough that bigger type could have reflowed it.
- **Contrast.** `--faint` was `#5b6878`, which measures **3.2:1** on `--panel` — below AA for body
  text. It is now `#7d8a9b` at **5.2:1**. The card number that used `#3d5265` now uses `--faint`.
- **Two things the bigger type broke, fixed rather than accepted.** The torque rows repeated
  "compiled / published" in every label, so at 11 px all three read "quarter span · compiled / p…";
  the phrase is now a single caption above the rows. The package tile's pill was being clipped by the
  tile's own ellipsis, so the pill is the value line: "no tag recorded" survives intact.

`verified-ran` after the pass: cockpit layout **5 passed**, `check_page_numbers.py` "32 numeric tokens
all trace to the summary", page-text test **2 passed**, `sections.test.mjs` **11 passed**. Screenshots
regenerated. No figure changed; only what the figures are set in.
