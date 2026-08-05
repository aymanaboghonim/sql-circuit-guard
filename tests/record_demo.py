"""Record a short browser video of the Gradio app using Playwright."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import threading
import time

from playwright.sync_api import sync_playwright

from src.app import create_ui


def run_server():
    app = create_ui()
    app.launch(server_name="127.0.0.1", server_port=7862, quiet=True)


def record_demo():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="assets/", record_video_size={"width": 1280, "height": 720}
        )
        page = context.new_page()

        page.goto("http://127.0.0.1:7862")
        page.wait_for_selector("text=SQL-Circuit-Guard", timeout=15000)
        time.sleep(2)

        # Type natural language query
        query_input = page.locator("textarea").first
        query_input.fill("Show me the top 5 artists by total album count.")
        time.sleep(1.5)

        # Click Execute Circuit
        execute_btn = page.locator("button:has-text('Execute Circuit')")
        execute_btn.click()

        # Wait for results
        page.wait_for_selector("text=Circuit Diagnostics", timeout=20000)
        time.sleep(3)

        # Switch to Schema tab
        schema_tab = page.get_by_role("tab", name="Database Schema Explorer")
        schema_tab.click()
        time.sleep(3)

        browser.close()


if __name__ == "__main__":
    record_demo()
