# Third-party notices

Every dependency RoboCAD ships or links against, with the licence it carries. Versions are the ones
installed on the development machine on 2026-11-13; the ranges live in `pyproject.toml` and
`requirements.txt`.

RoboCAD itself: the compile layer is Apache-2.0 (`LICENSE`). The calibration engine in
`ai_cad/twin/` is proprietary and source-available only under its own licence file. Nothing in this
list changes either of those.

## Runtime

| Package | Version | Licence |
|---|---|---|
| build123d | 0.11.1 | Apache-2.0 |
| pydantic | 2.13.4 | MIT |
| numpy | 2.4.4 | BSD-3-Clause |
| trimesh | 5.0.0 | MIT |
| manifold3d | 3.5.2 | Apache-2.0 |
| rtree | 1.4.1 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| coacd | 1.0.14 | MIT |
| mujoco | 3.11.0 | Apache-2.0 |
| anthropic | 1.1.0 | MIT |

`numpy`'s metadata declares `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`, because bundled
components carry their own terms. All are permissive and compatible with Apache-2.0.

## Web backend, optional

| Package | Version | Licence |
|---|---|---|
| fastapi | 0.137.1 | MIT |
| uvicorn | 0.49.0 | BSD-3-Clause |
| python-multipart | 0.0.20 | Apache-2.0 |
| python-dotenv | 1.2.1 | BSD-3-Clause |
| livekit-agents | 1.6.4 | Apache-2.0 |
| livekit-api | 1.1.0 | Apache-2.0 |

## Development

| Package | Version | Licence |
|---|---|---|
| pytest | 9.1.0 | MIT |
| pytest-timeout | 2.4.0 | MIT |
| playwright | 1.58.0 | Apache-2.0 |
| setuptools | 80.9.0 | MIT |
| sentence-transformers | 5.2.0 | Apache-2.0 |

`sentence-transformers` is declared in `requirements-dev.txt` and is optional: it powers the local
offline embedding classifier in a frozen Labs path. It is not imported on the Twin critical path, and
the default test tier passes without it.

## Frontend

| Package | Licence | Note |
|---|---|---|
| three.js | MIT | Pinned, vendored as a single classic script for the offline living page. The version and file live with the page generator; the report at M6 records both. |
| React | MIT | Existing app only. The generated page does not depend on it. |
| GSAP | Standard "no charge" licence | Only if a generated page animates with it. Recorded at M6 with the pinned version; not required for a page to work. |

## Not installed, not claimed

Gazebo, ROS 2, Isaac Sim, usd-core and pxr are not installed and are not listed as supported. If one
is added, it gets a row here, an install test, and a load output pasted into the milestone report
before any document mentions it.

## Robot models

Third-party robot CAD and meshes used for case studies are not redistributed unless their licence
allows it and Satyam has approved publishing the derived model. Each case study names the upstream
project, its licence, and what was derived from it.

| Case study | Upstream | Licence | What ships here |
|---|---|---|---|
| SO-101 | TheRobotStudio/SO-ARM100, `STEP/SO101/SO101 Assembly.step`, pinned `a758567c3978dfeefe282ede0500085a48fe8f78` | Apache-2.0 | `docs/twin/so101/`: link groups and joint axes inferred from the geometry, and the notice that says so. No upstream geometry, mesh or binary is redistributed. |

The SO-101 directory ships on Satyam's direct authorisation (2026-11-13), recorded in
`docs/DECISIONS.md` with the reasoning and the pinned revision.
