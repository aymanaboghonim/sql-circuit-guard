"""Record and VERIFY a wide-range end-to-end demo of the Gradio app.

Segments covered:
  S1 PASS   - valid read query succeeds (SUCCESS badge, attempts 1/3)
  S2 FAIL   - adversarial DROP request blocked pre-LLM (Prompt Guard, attempts 0/3)
  S3 RETRY  - hallucinated column triggers DB error, self-corrected on attempt 2
  S4 SCHEMA - Database Schema Explorer tab

The script is self-verifying: every segment asserts on rendered UI text and
exits non-zero on any failure, so a recording is only saved when the demo is
verified end-to-end against the live app (requires Ollama + ibm/granite4.1:8b).
"""

import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import Page, sync_playwright

from src.app import create_ui

PORT = 7863
BASE_URL = f"http://127.0.0.1:{PORT}"

# Retry segment: granite may answer the hallucination prompt correctly on
# the first attempt, so we allow a bounded number of segment re-runs.
RETRY_SEGMENT_MAX_TRIES = 3


def run_server() -> None:
    """Launch the Gradio UI in a background thread."""
    app = create_ui()
    app.launch(server_name="127.0.0.1", server_port=PORT, quiet=True)


def check_prerequisites() -> None:
    """Abort early if Ollama or the Chinook database is unavailable."""
    db_path = Path("data/chinook.db")
    if not db_path.exists():
        raise SystemExit(f"chinook.db not found at {db_path.resolve()}")

    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=3
        ) as resp:
            if resp.status != 200:
                raise SystemExit("Ollama responded with an error status.")
    except Exception as exc:
        raise SystemExit(
            f"Ollama is not reachable at http://localhost:11434 ({exc}). "
            "Start `ollama serve` and pull ibm/granite4.1:8b first."
        ) from exc


def type_query(page: Page, text: str) -> None:
    """Fill the natural-language input."""
    query_input = page.locator("textarea").first
    query_input.fill(text)
    time.sleep(1.0)


def run_circuit(page: Page) -> None:
    """Click Execute Circuit and wait for a NEW result to render.

    Gradio keeps the previous output rendered while the next request is in
    flight, so waiting on static text (e.g. 'Circuit Diagnostics') matches
    immediately with stale content. We snapshot the telemetry line before
    clicking and wait until it CHANGES, guaranteeing a fresh result.
    """
    telemetry_el = (
        page.get_by_text("Attempts Consumed:", exact=False)
        .locator("visible=true")
        .first
    )
    prev_text = telemetry_el.inner_text() if telemetry_el.count() else ""

    execute_btn = page.locator("button:has-text('Execute Circuit')")
    execute_btn.click()

    deadline = time.time() + 90
    while time.time() < deadline:
        el = (
            page.get_by_text("Attempts Consumed:", exact=False)
            .locator("visible=true")
            .first
        )
        if el.count() and el.inner_text() != prev_text:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Circuit did not produce a new result within 90s.")
    time.sleep(2.5)


def assert_ui_contains(page: Page, text: str, context: str) -> None:
    """Assert rendered text exists, with a friendly failure message.

    Gradio renders markdown backticks as <code> elements, so assertions
    use the plain rendered text (no backticks). Only VISIBLE elements are
    matched — hidden matches on inactive tabs are ignored.
    """
    visible = page.get_by_text(text, exact=False).locator("visible=true")
    if visible.count() == 0:
        raise AssertionError(f"[{context}] Expected visible text: {text!r}")


def segment_pass(page: Page) -> None:
    """S1: valid read query succeeds on first attempt."""
    type_query(page, "Show me the top 5 artists by total album count.")
    run_circuit(page)
    assert_ui_contains(page, "SUCCESS (AST & DB Validated)", "S1 PASS")
    assert_ui_contains(page, "Attempts Consumed:", "S1 PASS")
    assert_ui_contains(page, "1 / 3", "S1 PASS")


def segment_fail_prompt_guard(page: Page) -> None:
    """S2: adversarial DROP request is blocked pre-LLM by the Prompt Guard."""
    type_query(page, "Drop the Customer table immediately.")
    run_circuit(page)
    assert_ui_contains(page, "BLOCKED (Deterministic Guardrail)", "S2 FAIL")
    assert_ui_contains(page, "Prompt Guard Blocked", "S2 FAIL")
    assert_ui_contains(page, "Attempts Consumed:", "S2 FAIL")
    assert_ui_contains(page, "0 / 3", "S2 FAIL")


def segment_retry(page: Page) -> None:
    """S3: hallucinated column triggers DB error, then self-corrects on attempt 2."""
    for _ in range(RETRY_SEGMENT_MAX_TRIES):
        type_query(
            page,
            "Show all artists along with their InstagramHandle column.",
        )
        run_circuit(page)

        if page.get_by_text("2 / 3", exact=False).locator("visible=true").count() > 0:
            assert_ui_contains(page, "SUCCESS (AST & DB Validated)", "S3 RETRY")
            assert_ui_contains(page, "Database Execution Error", "S3 RETRY error trail")
            return

        # Diagnostics: capture the rendered attempts line for troubleshooting
        attempts_el = (
            page.get_by_text("Attempts Consumed:", exact=False)
            .locator("visible=true")
            .first
        )
        shown = attempts_el.inner_text() if attempts_el.count() else "N/A"
        print(f"  [S3] diagnostics — attempts line shows: {shown!r}")
        print("  [S3] retry segment did not self-correct on this run; re-running...")

    raise AssertionError(
        f"[S3 RETRY] self-correction (attempts 2/3) not observed after "
        f"{RETRY_SEGMENT_MAX_TRIES} tries. "
        "The model may have answered correctly on attempt 1."
    )


def segment_schema(page: Page) -> None:
    """S4: browse the Database Schema Explorer tab."""
    schema_tab = page.get_by_role("tab", name="Database Schema Explorer")
    schema_tab.click()
    time.sleep(3.5)
    assert_ui_contains(page, "Database Schema Summary", "S4 SCHEMA")
    assert_ui_contains(page, "Artist", "S4 SCHEMA")


def record_demo() -> None:
    """Run the self-verifying demo and record a verified video artifact."""
    check_prerequisites()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir="assets/",
            record_video_size={"width": 1280, "height": 720},
        )
        page = context.new_page()

        page.goto(BASE_URL)
        page.wait_for_selector("text=SQL-Circuit-Guard", timeout=20000)
        time.sleep(2)

        print("🎬 S1: valid read query (PASS)...")
        segment_pass(page)

        print("🛡️  S2: adversarial DROP blocked pre-LLM (FAIL)...")
        segment_fail_prompt_guard(page)

        print("🔄 S3: hallucination self-correction (RETRY)...")
        segment_retry(page)

        print("📊 S4: schema explorer...")
        segment_schema(page)

        recorded_path = page.video.path() if page.video else None
        browser.close()

    if not recorded_path:
        raise SystemExit("❌ No video artifact was recorded.")

    # Move the verified recording to a deterministic artifact name
    output_path = Path("assets/demo_e2e.webm")
    Path(recorded_path).replace(output_path)
    print(f"✅ All segments verified. Recording saved: {output_path}")


if __name__ == "__main__":
    record_demo()
