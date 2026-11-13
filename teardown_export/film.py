"""Record the 20 to 30 second film from the living page, frame by frame, then encode it.

Recording the page rather than the simulator is deliberate: the film then shows exactly what a
viewer will see when they open the same file, including the provenance line, the panels and the
SYNTHETIC watermark. Frames are driven by the page's own SO101_PAGE hook, so the film is
deterministic and can be re-recorded after any change.

The page is opened with the browser context offline, and the recorder refuses to encode if the
canvas never draws anything, because a film of a blank canvas is worse than no film.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile


def _canvas_is_drawn(png: bytes) -> bool:
    """A cheap check that the 3D canvas has content: the file must not be a flat single colour.

    Comparing compressed sizes is enough: an empty 1280x800 canvas compresses to a few kilobytes,
    a rendered robot to far more.
    """
    return len(png) > 40000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("page", help="path to index.html")
    parser.add_argument("out", help="output .mp4 path")
    parser.add_argument("--seconds", type=float, default=24.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--frame-start", type=int, default=0)
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    page_uri = pathlib.Path(args.page).resolve().as_uri()
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = pathlib.Path(tempfile.mkdtemp(prefix="so101film_"))

    total = int(args.seconds * args.fps)
    shot_paths: list[pathlib.Path] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 800}, offline=True,
                                      device_scale_factor=1)
        page = context.new_page()
        page.goto(page_uri, wait_until="load")
        page.wait_for_function("window.SO101_PAGE !== undefined", timeout=30000)
        page.evaluate("window.SO101_PAGE.pause()")
        frames = page.evaluate("window.SO101_PAGE.frames")

        # check the canvas itself, not the whole page: the side panels always draw, so a page
        # screenshot is large even when WebGL produced nothing
        page.evaluate("window.SO101_PAGE.setFrame(0)")
        probe = frames_dir / "canvas_probe.png"
        page.screenshot(path=str(probe))
        # a canvas element screenshot can come back empty in headless Chromium even when the page
        # composites correctly, so judge the stage region of a full page screenshot by contrast
        import numpy as np
        from PIL import Image

        stage = page.evaluate(
            "(()=>{const r=document.getElementById('stage').getBoundingClientRect();"
            "return [r.x|0, r.y|0, r.width|0, r.height|0]})()")
        img = Image.open(probe).convert("L").crop((stage[0], stage[1], stage[0]+stage[2], stage[1]+stage[3]))
        drawn = float(np.asarray(img).std()) > 5.0
        probe.unlink(missing_ok=True)
        if not drawn:
            browser.close()
            shutil.rmtree(frames_dir, ignore_errors=True)
            print("refusing to encode: the WebGL canvas never drew content", file=sys.stderr)
            return 2

        for i in range(total):
            page_frame = (args.frame_start + int(i * frames / total)) % frames
            page.evaluate(f"window.SO101_PAGE.setFrame({page_frame})")
            shot = frames_dir / f"f{i:05d}.png"
            page.screenshot(path=str(shot))
            shot_paths.append(shot)
        browser.close()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 3

    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-framerate", str(args.fps),
        "-i", str(frames_dir / "f%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        return 4

    if not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)

    size = out_path.stat().st_size
    print(f"{out_path} written, {size/1e6:.1f} MB, {total} frames at {args.fps} fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
