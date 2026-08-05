"""Record a professional, polished end-to-end demo video of the Gradio app."""

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


def record_professional_demo():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="assets/",
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        page.goto("http://127.0.0.1:7864")
        page.wait_for_selector("text=SQL-Circuit-Guard", timeout=15000)
        time.sleep(2.5)

        # Step 1: Click Quick Click Example button 1 (Top 5 Artists)
        ex1_btn = page.locator("button:has-text('Top 5 Artists by Albums')")
        ex1_btn.click()
        time.sleep(1.5)

        # Click Execute Circuit
        execute_btn = page.locator("button:has-text('Execute Circuit')")
        execute_btn.click()
        page.wait_for_selector("text=Circuit Diagnostics", timeout=20000)
        time.sleep(3.5)

        # Step 2: Switch to Database Schema Explorer tab
        schema_tab = page.get_by_role("tab", name="Database Schema Explorer")
        schema_tab.click()
        time.sleep(3)

        # Step 3: Switch back and toggle Langfuse tracing off, then run query 3
        query_tab = page.get_by_role("tab", name="Query Execution & Circuit")
        query_tab.click()
        time.sleep(1.5)

        ex3_btn = page.locator("button:has-text('Count Tracks per Genre')")
        ex3_btn.click()
        time.sleep(1)

        # Uncheck Langfuse toggle
        langfuse_checkbox = page.locator("input[type='checkbox']").first
        langfuse_checkbox.uncheck()
        time.sleep(1.5)

        execute_btn.click()
        page.wait_for_selector("text=Circuit Diagnostics", timeout=20000)
        time.sleep(4)

        browser.close()


if __name__ == "__main__":
    record_professional_demo()
