# Try it yourself

`README.md` in this directory is the 3 minute script and ships inside `so101_demo.zip`, so it cannot
name commands that need a checkout: a recipient has the archive, not the repository. This page is
the other half. Everything below runs from a RoboCAD checkout.

Two of the three commands need the SO-101 STEP file, which is **not** in this repository. It is
`STEP/SO101/SO101 Assembly.step` from TheRobotStudio/SO-ARM100 at
`a758567c3978dfeefe282ede0500085a48fe8f78`, Apache-2.0, 20,496,014 bytes; `docs/THIRD_PARTY.md`
records why it is not shipped and what derived assets are. Without it, `summary` and `unpack` still
run against the bundle and the archive.

```
# 1. what the voice reads: one JSON document, every figure labelled with what kind of claim it is
python -m robocad twin summary --bundle docs/twin/so101/bundle --json

# 2. the archive a recipient gets, checked against the digest verify.json records
python -m robocad twin unpack --zip docs/demo/so101_demo.zip --out <fresh dir> \
    --verify-sha f86c28f703f84ccfcb3269233ad7a0ef88e2843172387728f5af7c01b6b569f3

# 3. change the infill to 30 percent, recompile, and say what the robot now weighs
python -m robocad twin revise \
    --step "STEP/SO101/SO101 Assembly.step" \
    --before docs/twin/so101/bundle \
    --out docs/twin/so101/revision_cli \
    --joints docs/twin/so101/bundle/robot.joints.yaml \
    --infill 0.30 \
    --servo-mass-kg 0.055 \
    --servo-source "Feetech STS3215 product specification: weight 55 +/- 1 g" \
    --json-progress
```

## What the third command does, and why each flag is there

`revise` recompiles the same STEP file at a print model the caller names, writes the new bundle to
`--out/bundle`, diffs it against `--before` link by link using `ai_cad/compiler/revision.py`, and
writes `diff.json` and `diff.md` beside it. It reports the modelled printed mass before and after.
That is the whole revision: one stated assumption changed, everything else held fixed and printed.

- `--joints` adopts the travel limits the frozen bundle already carries. Omitting it leaves limits
  unknown rather than inventing them, and the effort check then has nothing to compare against.
- `--servo-mass-kg` with `--servo-source` is the datasheet mass of one actuator. Without it the
  servo's CAD envelope — an empty box — is counted as printed plastic, and the two bundles disagree
  about the solid bound for a reason that has nothing to do with infill.
- `--infill` is bounded 0.1 to 1.0 and `--wall-mm` 0.8 to 3.0. Both refusals are exit code 2 and
  happen before the compiler starts.

The run announces the assumption first, as a `tooling:print_model` line ahead of the compiler's own
stages:

```
{"stage": "tooling:print_model", "pct": 0, "msg": "print model: 1.20 mm wall, 0.30 infill"}
```

and ends with the spoken line — printed mass before, after, percent, then the solid bound, which does
not move and is printed to show that it does not.

## Two refusals worth knowing about

1. **A print model no printer could hold.** `--infill 0.05` (no printable part behind the number),
   `--infill 1.4` (solid, which the solid bound already reports), `--wall-mm 0.4` (a wall that does
   not survive a print), `--wall-mm 4` (no infilled interior to model). Exit 2, nothing compiled.

2. **A diff whose solid bound moved.** Wall thickness and infill cannot change the solid: it is the
   CAD volume at a stated density. If the two compiles disagree about it, something else differs
   between them, and the printed mass would be that difference plus the revision rather than the
   revision. `revise` refuses to present that as a revision — exit 3 — and still writes `diff.md`
   carrying the reason, because a refused diff is evidence.

Nothing in any of these commands talks to hardware. The wall and infill figures are the assumptions
the frozen bundle states, not measurements of a printed part: see "Real versus synthetic" in
`README.md`.
