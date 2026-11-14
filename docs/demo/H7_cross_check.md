# H7: Lane A checks Lane B's spoken numbers

Lane B sent the H6 narration lines to be checked against the artifacts that ship, not against the
screen. Each line below names the artifact and the field it reads. Method: load the artifact's JSON,
read the field, round it to the precision she speaks, and compare. Rounding is the convention she
stated, and number words are spelled out in the spoken lines by design, so no digit is compared
against a spelled word.

Rule she stated, and rule applied: spoken values are rounded from the raw figure, not copied.

| # | Spoken line (excerpt) | Artifact | Field | Artifact value | Spoken | Verdict |
|---|---|---|---|---|---|---|
| 1 | "7 bodies and 6 joints" | `bundle/report.json` | `totals.bodies`, `totals.joints` | 7, 6 | 7, 6 | matches |
| 2 | "5 checks pass, 1 fail and 1 is skipped" | `bundle/report.json` | `checks[].status` counts | 5 pass, 1 fail, 1 skipped, 0 warn | same | matches |
| 3 | "hulls overlap 7.9 mm at rest" | `bundle/report.json` | `checks[self_collision].measured.deepest_m` | -0.007938773299899294 m | 7.9 mm | matches |
| 4 | "2.50 mm median and 11.25 mm worst case" | `docs/demo/twin/p0a_confirmation.json` | `result.median_mm`, `result.max_mm` | 2.5, 11.25 | 2.50, 11.25 | matches |
| 5 | "0.902 kg against 0.632 kg published" | `bundle/bundle.json`, `bundle/comparison.json` | `total_mass_kg`, `theirs_total_kg` | 0.9016588355893798, 0.6320060009999999 | 0.902, 0.632 | matches |
| 6 | "solid upper bound of 1.332 kg" | `bundle/bundle.json` | `total_solid_mass_kg` | 1.3320123928506593 | 1.332 | matches |
| 7 | "one point two millimetre walls at twenty percent infill" | `bundle/bundle.json` | `print_model` | `1.20 mm wall over 20% infill` | same | matches |
| 8 | "0.767 newton metres against 0.538" | `docs/demo/twin/p0_torque_matched.json` | `static_gravity[0].compiled_peak_nm`, `.official_peak_nm` | 0.767, 0.538 | 0.767, 0.538 | matches |
| 9 | "the jaw frame differs by 70.7 mm" | `docs/demo/twin/p0_torque_matched.json` | `pose_gate.worst_mm` | 70.69 | 70.7 | matches |
| 10 | "7 links changed, 0 added and 0 removed" | `revision_f030/diff.json` | `len(links)` with mass moved, `added`, `removed` | 7 links heavier, `[]`, `[]` | 7, 0, 0 | matches |
| 11 | "1 of 2 rungs recovered once a current channel was added" | `docs/demo/twin/identification.json` | rungs with `rung == 5`: `reached` | **2 of 2 `reached: true`** | 1 of 2 | **mismatch, see below** |

`verified-ran`: rows 1 to 10 were produced by loading the named JSON and printing the field, not by
reading the page or trusting this table. Row 11 is the reason this file exists.

## Two lines that do not survive the check

**1. Revision mass, "0.902 kg to 0.956 kg".** The artifact's `totals.mass_after_kg` is
**0.9554530302470398**. Rounded to the three decimals she speaks, that is **0.955**, not 0.956. The
before figure is right (0.9016588355893798 → 0.902). Suggested line: "0.902 kg to 0.955 kg". The
delta she does not speak is +0.0538 kg, +5.97%, so either the two masses or the delta, never all
three, or a listener who adds them up hears a rounding error that is not there.

**2. Identification, "1 of 2 rungs recovered once a current channel was added".** The artifact has two
current-channel rungs, `62 Hz with a current channel, shoulder_lift` and `62 Hz with a current channel,
elbow_flex`, and **both carry `reached: true`**. There is a defensible way to get to "1 of 2" — the
25% tolerance the stop reason names, applied to the *damping* error, where `elbow_flex` reads 24.86%
and `shoulder_lift` reads 45.53% — but that is not what the word "rung" means anywhere else in the
same panel, where a rung's outcome is its `reached` flag. Two readings, one sentence, and the artifact
only supports one of them:

- if she means `reached`: **"both current-channel rungs recovered"** (2 of 2);
- if she means the damping tolerance: **"one of the two current-channel rungs recovered damping inside
  the 25% tolerance, and both recovered Coulomb"**, which is the honest sentence but a long one to
  speak.

Either is checkable. "1 of 2 rungs" as written is not, and it is the line that carries the Twin's
central claim, so it is the one that should not be approximate.

## What this check does not cover

Rows 8 and 9 are static-gravity peak figures read from a payload; they are not the dynamic torque
curves, and `p0_torque_matched.json` itself carries `pose_gate.passes: false`, which is why her line
says the dynamic comparison is not comparable yet. That qualifier is present in the spoken line and is
the reason it survives review. Nothing here re-derives her numbers from the models: this checks the
narration against the artifact, and `scripts/verify_demo_zip.py` checks the artifact against the zip.
