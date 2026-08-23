"""Record a video demo of the RoboCAD Kinetic Precision UI."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ASSETS_DIR.mkdir(exist_ok=True)
VIDEO_DIR = ASSETS_DIR / "video_temp"
VIDEO_DIR.mkdir(exist_ok=True)

OUTPUT_VIDEO = ASSETS_DIR / "robocad_kinetic_precision_demo.webm"


def main():
    # Clean old temp videos
    for f in VIDEO_DIR.glob("*.webm"):
        f.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto(FRONTEND_URL)

        print("[1/10] Opened frontend")
        page.wait_for_selector("text=Backend online", timeout=30000)

        # Expand Structural category and pick Base Plate seed
        print("[2/10] Selecting 'Base Plate' component seed")
        page.locator("button:has-text('Structural')").first.click()
        time.sleep(0.5)
        page.locator("button:has-text('Base Plate')").first.click()
        time.sleep(1)

        # Click Generate
        print("[3/10] Generating design")
        page.locator("button:has-text('Generate')").first.click()

        # Wait for manifold validation text to appear
        print("[4/10] Waiting for generation to complete")
        page.wait_for_selector("text=Manifold", timeout=120000)

        # Wait for the 3D viewer canvas to render the model
        print("[5/10] Model generated, waiting for viewer")
        time.sleep(2)

        # Click on the center of the 3D viewer to guess a face parameter
        print("[6/10] Clicking a face in the viewer")
        viewer = page.locator("canvas").first
        box = viewer.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            time.sleep(2)

        # Scroll to parameter panel
        print("[7/10] Scrolling to parameter panel")
        page.locator("h3:has-text('Parameters')").first.scroll_into_view_if_needed()
        time.sleep(1)

        # Edit thickness parameter if present, otherwise first numeric input
        thickness_input = page.locator("tr:has-text('thickness') input").first
        if thickness_input.count() > 0:
            print("[8/10] Editing thickness parameter")
            thickness_input.fill("6")
            thickness_input.press("Tab")
            time.sleep(0.5)
            page.locator("button:has-text('Regenerate from parameters')").first.click()
            print("[8/10] Waiting for parameter regeneration")
            page.wait_for_selector("text=Manifold", timeout=120000)
            time.sleep(2)

        # Scroll to manufacturing report
        print("[9/10] Scrolling to manufacturing report")
        page.locator("h3:has-text('Manufacturing Report')").first.scroll_into_view_if_needed()
        time.sleep(2)

        # Final pause and close
        print("[10/10] Finalizing video")
        time.sleep(3)

        context.close()
        browser.close()

    # Playwright saves the video with a random filename; find and rename it
    videos = list(VIDEO_DIR.glob("*.webm"))
    if videos:
        latest = max(videos, key=lambda p: p.stat().st_mtime)
        latest.replace(OUTPUT_VIDEO)
        print(f"Demo saved to: {OUTPUT_VIDEO}")
        size_mb = OUTPUT_VIDEO.stat().st_size / (1024 * 1024)
        print(f"Size: {size_mb:.2f} MB")
    else:
        print("No video file found.")


if __name__ == "__main__":
    main()
