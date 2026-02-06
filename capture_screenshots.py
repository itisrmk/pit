#!/usr/bin/env python3
"""Screenshot capture script for PIT Dashboard."""

import asyncio
import subprocess
import time
from pathlib import Path

from playwright.async_api import async_playwright


async def capture_dashboard():
    """Capture screenshots of the dashboard."""
    
    # Start streamlit
    print("🚀 Starting Streamlit server...")
    proc = subprocess.Popen(
        ["streamlit", "run", "pit-dashboard.py", "--server.headless", "true", "--server.port", "8501"],
        cwd="/Users/rahulkashyap/.openclaw/workspace/pit",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    try:
        # Wait for server to be ready
        print("⏳ Waiting for server to start...")
        time.sleep(8)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            
            screenshots_dir = Path("/Users/rahulkashyap/.openclaw/workspace/pit/assets/dashboard")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Navigate to dashboard
            print("📸 Capturing Overview page...")
            await page.goto("http://localhost:8501")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            await page.screenshot(path=str(screenshots_dir / "01-overview.png"), full_page=True)
            print(f"  ✅ Saved: {screenshots_dir / '01-overview.png'}")
            
            # Capture Timeline page
            print("📸 Capturing Timeline page...")
            # Click on Timeline nav
            await page.click("text=📈 Timeline")
            await asyncio.sleep(3)
            await page.screenshot(path=str(screenshots_dir / "02-timeline.png"), full_page=True)
            print(f"  ✅ Saved: {screenshots_dir / '02-timeline.png'}")
            
            # Capture Diff View
            print("📸 Capturing Diff View...")
            await page.click("text=🔍 Diff View")
            await asyncio.sleep(3)
            await page.screenshot(path=str(screenshots_dir / "03-diff.png"), full_page=True)
            print(f"  ✅ Saved: {screenshots_dir / '03-diff.png'}")
            
            # Capture Replay
            print("📸 Capturing Replay page...")
            await page.click("text=🧪 Replay")
            await asyncio.sleep(3)
            await page.screenshot(path=str(screenshots_dir / "04-replay.png"), full_page=True)
            print(f"  ✅ Saved: {screenshots_dir / '04-replay.png'}")
            
            await browser.close()
            
        print("\n✅ All screenshots captured!")
        return screenshots_dir
        
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    screenshots_dir = asyncio.run(capture_dashboard())
    print(f"\n📁 Screenshots saved to: {screenshots_dir}")
