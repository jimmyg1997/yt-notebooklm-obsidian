#!/usr/bin/env python3
"""Capture dashboard screenshots for docs/USER_WALKTHROUGH.md and README.

Requires: dashboard running at http://127.0.0.1:8787, playwright installed in .venv.

Usage:
    ./run_dashboard.sh   # in another terminal
    .venv/bin/python scripts/capture_dashboard_screenshots.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "screenshots"
BASE = "http://127.0.0.1:8787"


async def main() -> None:
    from playwright.async_api import async_playwright
    from dashboard.services.vault_scanner import encode_vault_id

    sample = ROOT / "data" / "proswpikesshmeiwseismathshs" / "vault"
    if not sample.is_dir():
        print("Sample vault missing; run pipeline or ingest first.", file=sys.stderr)
        sys.exit(1)
    vault_id = encode_vault_id(sample.resolve())
    OUT.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        async def shot(name: str, full: bool = False) -> None:
            await page.screenshot(path=str(OUT / name), full_page=full)
            print(f"  {name}")

        await page.goto(BASE, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1200)
        await shot("01-dashboard-home.png", full=True)
        await page.locator('input[value="manual"]').click()
        await page.wait_for_timeout(300)
        await shot("05-ingest-new-vault-form.png")
        await page.goto(BASE, wait_until="networkidle")
        await page.locator("#vault-grid").scroll_into_view_if_needed()
        await page.locator("#vault-grid").screenshot(path=str(OUT / "06-vault-cards.png"))
        print("  06-vault-cards.png")
        await page.locator("[data-action='edit']").first.click()
        await page.wait_for_timeout(500)
        await page.locator("#vault-edit-modal .modal-card").screenshot(path=str(OUT / "07-edit-vault-modal.png"))
        print("  07-edit-vault-modal.png")

        await page.goto(f"{BASE}/explorer?vault={vault_id}", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        topics = page.locator('.tree-item[data-folder="Topics/διατροφή"]')
        if await topics.count():
            await topics.click()
            await page.wait_for_timeout(600)
        await shot("08-explorer-topics-tree.png")

        for label in ("00 - Index", "Index"):
            item = page.locator("#note-list .note-item").filter(has_text=label).first
            if await item.count():
                await item.click()
                await page.wait_for_timeout(1000)
                await shot("09-explorer-index-note.png")
                break

        item = page.locator("#note-list .note-item").filter(has_text="διατροφή").first
        if await item.count():
            await item.click()
            await page.wait_for_timeout(1000)
            await shot("10-explorer-topic-note.png")

        item = page.locator("#note-list .note-item").filter(has_text="Insulin").first
        if await item.count():
            await item.click()
            await page.wait_for_timeout(1500)
            await page.evaluate("document.getElementById('note-content')?.scrollTo(0, 350)")
            await page.locator(".pane.note-pane").screenshot(path=str(OUT / "11-explorer-video-note-frames.png"))
            print("  11-explorer-video-note-frames.png")

        await shot("02-explorer-note.png")
        await page.locator('.pane-tab[data-tab="graph"]').click()
        await page.wait_for_timeout(3000)
        await shot("03-explorer-graph.png")
        await page.select_option("#graph-scope", "theme")
        await page.wait_for_timeout(2500)
        await shot("04-graph-theme-scope.png")
        await page.select_option("#graph-scope", "full")
        await page.wait_for_timeout(2500)
        await shot("13-graph-full-scope.png")
        await page.select_option("#ui-lang", "en")
        await page.locator('.pane-tab[data-tab="note"]').click()
        await page.wait_for_timeout(800)
        await shot("12-explorer-english-ui.png")

        await browser.close()
    print(f"Done — {len(list(OUT.glob('*.png')))} PNG files in docs/screenshots/")


if __name__ == "__main__":
    asyncio.run(main())
