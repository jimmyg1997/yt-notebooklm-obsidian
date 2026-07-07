"""Browser E2E: Graph tab must switch and render vis-network canvas."""
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module")
def sample_vault_id():
    candidate = Path(__file__).resolve().parent.parent / "data" / "proswpikesshmeiwseismathshs" / "vault"
    if not candidate.is_dir():
        pytest.skip("sample vault missing")
    from dashboard.services.vault_scanner import encode_vault_id

    return encode_vault_id(candidate)


def test_graph_js_has_no_invalid_optional_assignments():
    graph_js = Path(__file__).resolve().parent.parent / "dashboard" / "static" / "graph.js"
    text = graph_js.read_text(encoding="utf-8")
    assert "?.onclick =" not in text


def test_graph_tab_switches_and_renders(sample_vault_id):
    base = "http://127.0.0.1:8787"
    url = f"{base}/explorer?vault={sample_vault_id}"
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1200)

        assert page.evaluate("typeof window.VaultGraph !== 'undefined'"), "VaultGraph must load"
        assert not errors, f"Page errors: {errors}"

        page.locator('.pane-tab[data-tab="graph"]').click()
        page.wait_for_timeout(3500)

        state = page.evaluate(
            """() => ({
                activeTab: window.VaultGraph.activeTab,
                graphHidden: document.getElementById('graph-panel').hidden,
                graphActive: document.getElementById('graph-panel').classList.contains('is-active'),
                display: getComputedStyle(document.getElementById('graph-panel')).display,
                hasCanvas: !!document.querySelector('#graph-canvas canvas'),
                stats: document.getElementById('graph-stats').textContent || '',
            })"""
        )
        browser.close()

    assert state["activeTab"] == "graph"
    assert state["graphHidden"] is False
    assert state["graphActive"] is True
    assert state["display"] != "none"
    assert state["hasCanvas"] or "notes" in state["stats"].lower() or "σημειώσεις" in state["stats"].lower()
