"""Zip a GEDA Bridge bundle directory into a single downloadable asset."""
from __future__ import annotations

import zipfile
from pathlib import Path

from ai_cad.geda_bridge.models import BundlePaths


def package_bundle(bundle_dir: Path, output_zip: Path | None = None) -> Path:
    """Zip every file under ``bundle_dir`` into ``output_zip``.

    If ``output_zip`` is omitted, ``{bundle_dir}.zip`` is used.
    Returns the path to the created zip file.
    """
    bundle_dir = Path(bundle_dir)
    if output_zip is None:
        output_zip = bundle_dir.with_suffix(".zip")
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(bundle_dir).as_posix()
                zf.write(path, arcname)

    return output_zip


def package_bundle_paths(paths: BundlePaths, output_zip: Path | None = None) -> BundlePaths:
    """Zip the bundle described by ``paths`` and attach the zip path."""
    zip_path = package_bundle(paths.directory, output_zip)
    paths.zip = zip_path
    return paths
