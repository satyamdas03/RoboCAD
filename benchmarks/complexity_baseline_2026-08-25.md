# RoboCAD Complexity Benchmark Report

**Date:** 2026-08-25T00:21:17.131625Z
**Model:** qwen3-coder:latest
**Max retries:** 2

## Summary

- **Total prompts:** 30
- **Successes:** 26
- **Failures:** 4
- **Overall pass rate:** 86.7%
- **Average successful latency:** 29.50 s

### By tier

| Tier | Total | Successes | Failures | Pass rate | Avg latency (s) |
|---|---|---|---|---|---|
| T1 - Primitive | 6 | 5 | 1 | 83.3% | 22.33 |
| T2 - Basic part | 6 | 6 | 0 | 100.0% | 16.98 |
| T3 - Intermediate | 6 | 5 | 1 | 83.3% | 39.38 |
| T4 - Advanced | 6 | 6 | 0 | 100.0% | 35.40 |
| T5 - Expert | 6 | 4 | 2 | 66.7% | 36.08 |

### Failure modes

| Failure mode | Count |
|---|---|
| success | 26 |
| runtime | 3 |
| geometry | 1 |

## Per-prompt results

| ID | Tier | Success | Mode | Attempts | Latency (s) | Params | Est. features | Manifold | Watertight |
|---|---|---|---|---|---|---|---|---|---|
| t1.1 | T1 - Primitive | ✓ | success | 1 | 7.86 | 0 | 1 | ✓ | ✓ |
| t1.2 | T1 - Primitive | ✓ | success | 1 | 8.96 | 2 | 1 | ✓ | ✓ |
| t1.3 | T1 - Primitive | ✗ | runtime | 3 | 37.26 | 0 | 1 | — | — |
| t1.4 | T1 - Primitive | ✓ | success | 2 | 35.96 | 2 | 1 | ✓ | ✓ |
| t1.5 | T1 - Primitive | ✓ | success | 1 | 20.57 | 3 | 2 | ✓ | ✓ |
| t1.6 | T1 - Primitive | ✓ | success | 2 | 38.31 | 4 | 3 | ✓ | ✓ |
| t2.1 | T2 - Basic part | ✓ | success | 1 | 16.64 | 6 | 3 | ✓ | ✓ |
| t2.2 | T2 - Basic part | ✓ | success | 1 | 17.90 | 5 | 5 | ✓ | ✓ |
| t2.3 | T2 - Basic part | ✓ | success | 1 | 15.44 | 5 | 4 | ✓ | ✓ |
| t2.4 | T2 - Basic part | ✓ | success | 1 | 20.70 | 5 | 4 | ✓ | ✓ |
| t2.5 | T2 - Basic part | ✓ | success | 1 | 13.99 | 5 | 3 | ✓ | ✓ |
| t2.6 | T2 - Basic part | ✓ | success | 1 | 17.18 | 6 | 5 | ✓ | ✓ |
| t3.1 | T3 - Intermediate | ✓ | success | 3 | 105.14 | 8 | 8 | ✓ | ✓ |
| t3.2 | T3 - Intermediate | ✓ | success | 1 | 27.41 | 8 | 7 | ✓ | ✓ |
| t3.3 | T3 - Intermediate | ✓ | success | 1 | 18.86 | 5 | 6 | ✓ | ✓ |
| t3.4 | T3 - Intermediate | ✓ | success | 1 | 19.15 | 5 | 4 | ✓ | ✓ |
| t3.5 | T3 - Intermediate | ✗ | runtime | 3 | 94.32 | 0 | 5 | — | — |
| t3.6 | T3 - Intermediate | ✓ | success | 1 | 26.32 | 6 | 7 | ✓ | ✓ |
| t4.1 | T4 - Advanced | ✓ | success | 1 | 27.69 | 8 | 7 | ✓ | ✓ |
| t4.2 | T4 - Advanced | ✓ | success | 1 | 27.83 | 6 | 5 | ✓ | ✓ |
| t4.3 | T4 - Advanced | ✓ | success | 1 | 40.71 | 10 | 13 | ✓ | ✓ |
| t4.4 | T4 - Advanced | ✓ | success | 1 | 32.97 | 10 | 9 | ✓ | ✓ |
| t4.5 | T4 - Advanced | ✓ | success | 1 | 22.14 | 5 | 4 | ✓ | ✓ |
| t4.6 | T4 - Advanced | ✓ | success | 2 | 61.05 | 4 | 7 | ✓ | ✓ |
| t5.1 | T5 - Expert | ✗ | geometry | 3 | 132.25 | 14 | 15 | ✗ | ✗ |
| t5.2 | T5 - Expert | ✓ | success | 1 | 43.00 | 13 | 13 | ✓ | ✓ |
| t5.3 | T5 - Expert | ✓ | success | 1 | 29.64 | 8 | 9 | ✓ | ✓ |
| t5.4 | T5 - Expert | ✓ | success | 1 | 31.44 | 12 | 9 | ✓ | ✓ |
| t5.5 | T5 - Expert | ✓ | success | 1 | 40.25 | 10 | 9 | ✓ | ✓ |
| t5.6 | T5 - Expert | ✗ | runtime | 3 | 67.74 | 0 | 4 | — | — |

## Failure details

### t1.3 (T1 - Primitive)

**Prompt:** A solid cone 30 mm base diameter and 40 mm tall.

**Failure mode:** runtime

**Error:** Generated code failed to execute.

```
Traceback (most recent call last):
  File "C:\Users\point\projects\RoboCAD\output\benchmarks\baseline_2026-08-25\t1.3\generated_2b244b9d.py", line 8, in <module>
    Cone(radius=base_diameter/2, height=height)
    ~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: Cone.__init__() got an unexpected keyword argument 'radius'

```

### t3.5 (T3 - Intermediate)

**Prompt:** A parallel gripper jaw 50 mm × 20 mm × 10 mm with a 45° V-groove on the gripping face, two M2 mounting holes on the back face, and 2 mm edge fillets.

**Failure mode:** runtime

**Error:** Generated code failed to execute.

```
Traceback (most recent call last):
  File "C:\Users\point\projects\RoboCAD\output\benchmarks\baseline_2026-08-25\t3.5\generated_057ab701.py", line 29, in <module>
    triangle = Triangle(
        first_side=thickness * 0.8,
        second_side=thickness * 0.8,
        included_angle=v_groove_angle
    )
TypeError: Triangle.__init__() got an unexpected keyword argument 'first_side'

```

### t5.1 (T5 - Expert)

**Prompt:** Design a differential-drive robot chassis assembly: two NEMA-17 motor mounts constrained to a 100 mm wheelbase, a 20 mm caster clearance, a Raspberry Pi 5 mounting plate with four M3 holes, and wheel hubs with 6 mm shaft bores. Ensure all parts are editable parametric features, validate the assembly mates, and run a static load check on the base plate.

**Failure mode:** geometry

**Error:** Model is not watertight.

```
Validation failed:
Model is not watertight.
Warnings:
Model may not be manifold.
```

### t5.6 (T5 - Expert)

**Prompt:** Design a Stewart platform base: a triangular base plate with six 8 mm ball-joint mounting holes evenly spaced on a 120 mm pitch circle, 5 mm thick, with 3 mm fillets on all edges.

**Failure mode:** runtime

**Error:** Generated code failed to execute.

```
Traceback (most recent call last):
  File "C:\Program Files\Python314\Lib\site-packages\build123d\topology\three_d.py", line 367, in fillet
    new_shape = self._make_3d_result(fillet_builder.Shape())
                                     ~~~~~~~~~~~~~~~~~~~~^^
OCP.OCP.Standard.Standard_Failure: There are no suitable edges for chamfer or fillet

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\point\projects\RoboCAD\output\benchmarks\baseline_2026-08-25\t5.6\generated_8304290c.py", line 24, in <module>
    fillet(edge, radius=fillet_radius)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Program Files\Python314\Lib\site-packages\build123d\operations_generic.py", line 432, in fillet
    new_part = target.fillet(radius, list(object_list))
  File "C:\Program Files\Python314\Lib\site-packages\build123d\topology\three_d.py", line 371, in fillet
    raise ValueError(
    ...<2 lines>...
    ) from err
ValueError: Failed creating a fillet with radius of 3.0, try a smaller value or use max_fillet() to find the largest valid fillet radius

```
