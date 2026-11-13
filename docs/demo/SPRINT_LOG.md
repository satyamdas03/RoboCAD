# Sprint log, deadline Sat 14 Nov 2026 22:00 Sydney

Satyam is unavailable until the deadline. Decisions get made, logged in `docs/DECISIONS.md` with a
one-line reason, and work continues. This log is the shared state between the two sessions; chat is
for decisions only.

## Lanes claimed

- **Lane A, compile path** (M2 YAML, M3 properties and collision, M4 bundle, checks, both diffs):
  build session, `robocad-61`.
- **Lane B, show path** (M6 page, film, synthetic twin, demo package, verifier): monitor session.

Lane B builds on the **official SO-101 MJCF first** and switches to `demo-bundle-v1` the moment
Lane A tags it. No lane waits on the other.

## Entries

Append one every 60 to 90 minutes: done, evidence, blocked, next. Tag evidence verified-ran,
verified-read or claimed. Never claim a lane's output without opening it.

### 2026-11-13 08:00Z, monitor session, Lane B start

- Claimed Lane B.
- Killed the heavy/slow/mujoco baseline run per the sprint instruction. It was at 25 percent with one
  xfail and two xpass, no failures. `BASELINE.md` records the stop and the reason.
- `docs/DECISIONS.md` gains the sprint decisions: publish `docs/twin/so101/` with a NOTICE, M2
  cross-review by the lane that did not write the YAML, CoACD capped at 30 minutes then convex hulls,
  heavy tier stopped for the sprint, and the living page built on three.js directly because no
  Teardown kit exists in this repo.
- Next: fetch the official SO-101 MJCF at the pinned commit, bake a trajectory, and stand up the
  page skeleton so B1 does not wait for the compiler.
