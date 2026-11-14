"""Export the shipped demo's twin summary as the artifact both repos read.

The voice and the blade must describe the package a person downloads, not a copy of it that has
drifted. So: unpack the archive `verify.json` names, check its digest on the way in, build the summary
with the same code the CLI runs, and write both verbatim. The JSON is unmodified CLI output on
purpose -- a fixture that is reshaped to suit a test is a test of the reshaping.

The archive digest travels in a sidecar in `sha256sum` format, so any tool that checks a checksum can
check this one, and a fixture whose zip has been replaced is detectable rather than silently stale.

    python scripts/export_summary_fixture.py
    python scripts/export_summary_fixture.py --out-dir ../Hi-EV/tests/fixtures
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robocad.twin_cli import ArchiveError, build_summary, sha256_file, unpack_zip  # noqa: E402

FIXTURE = "robocad_summary.v1.json"
SIDECAR = "robocad_summary.v1.sha256"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", default=str(ROOT / "docs" / "demo" / "so101_demo.zip"))
    parser.add_argument("--verify-json", default=str(ROOT / "docs" / "demo" / "verify.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "docs" / "demo"))
    parser.add_argument("--json", action="store_true", help="print the paths as JSON")
    args = parser.parse_args(argv)

    zip_path = Path(args.zip)
    verify = json.loads(Path(args.verify_json).read_text(encoding="utf-8"))
    expected = str(verify.get("sha256") or "").strip()
    if not expected:
        print(f"{args.verify_json} names no sha256: refusing to export an unverified archive")
        return 2

    # unpack refuses a digest mismatch on its own; passing the digest forward is what makes this
    # export provably about the archive verify.json accepted. Its refusal is the caller's error to
    # see as a sentence, not a traceback.
    work = Path(tempfile.mkdtemp(prefix="robocad-fixture-"))
    try:
        unpacked = unpack_zip(zip_path, work / "demo", verify_sha=expected)
        summary = build_summary(Path(unpacked["bundle"]))
    except (ArchiveError, FileNotFoundError) as error:
        print(str(error))
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = out_dir / FIXTURE
    fixture.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    # `sha256sum` format: digest, two spaces, the name the consumer knows it by.
    (out_dir / SIDECAR).write_text(f"{expected}  {zip_path.name}\n", encoding="utf-8")

    sections = [key for key in ("check_counts", "masses", "residuals", "torque", "revision",
                                "calibration") if key in summary]
    report = {
        "fixture": fixture.resolve().as_posix(),
        "sidecar": (out_dir / SIDECAR).resolve().as_posix(),
        "zip": zip_path.resolve().as_posix(),
        "zip_sha256": expected,
        # Re-read from the file just written, not from the archive: what a consumer will parse.
        "zip_sha256_recorded": sha256_file(zip_path),
        "schema_version": summary.get("schema_version"),
        "sections": sections,
        "missing_sections": [key for key in ("check_counts", "masses", "residuals", "torque",
                                             "revision", "calibration") if key not in summary],
        "synthetic_count": summary.get("synthetic_count"),
        "bytes": fixture.stat().st_size,
    }
    if args.json:
        print(json.dumps(report))
    else:
        print(f"{report['fixture']} {report['bytes']} bytes from {zip_path.name} {expected[:12]}")
        print(f"sections: {', '.join(sections) or 'none'}")
        if report["missing_sections"]:
            print(f"missing: {', '.join(report['missing_sections'])}"
                  " (the archive predates the payloads those sections read)")
        print(f"synthetic figures: {report['synthetic_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
