"""Record a clean, professional end-to-end demo video of the Gradio app with proper viewport sizing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import threading
import time

from playwright.sync_api import sync_playwright

from src.app import create_ui


def run_server():
    app = create_ui()
    app.launch(server_name="127.0.0.1", server_port=7864, quiet=True)


def record_demo():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use exact dimensions matching Gradio container to eliminate whitespace
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir="assets/",
            record_video_size={"width": 1280, "height": 800},
        )
        page = context.new_page()

        page.goto("http://127.0.0.1:7864")
        page.wait_for_selector("text=SQL-Circuit-Guard", timeout=15000)
        time.sleep(2.5)

        # 1. Click Quick Example 1
        ex1_btn = page.locator("button:has-text('Top 5 Artists by Albums')")
        ex1_btn.click()
        time.sleep(1)

        execute_btn = page.locator("button:has-text('Execute Circuit')")
        execute_btn.click()
        page.wait_for_selector("text=Circuit Diagnostics", timeout=20000)
        time.sleep(3.5)

        # 2. Click Quick Example 2
        ex2_btn = page.locator("button:has-text('List Top 10 Invoices by Total')")
        ex2_btn.click()
        time.sleep(1)
        execute_btn.click()
        page.wait_for_selector("text=Circuit Diagnostics", timeout=20000)
        time.sleep(3.5)

        # 3. Switch to Schema tab
        schema_tab = page.get_by_role("tab", name="Database Schema Explorer")
        schema_tab.click()
        time.sleep(3.5)

        # 4. Switch back to Query tab
        query_tab = page.get_by_role("tab", name="Query Execution & Circuit")
        query_tab.click()
        time.sleep(2)

        browser.close()


if __name__ == "__main__":
    record_demo()
