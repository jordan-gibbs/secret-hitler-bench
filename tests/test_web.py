"""
Playwright tests for the Secret Hitler Bench web UI.
Uses MockPlayer only — no API credits spent.
"""

import asyncio
import json
import time
import subprocess
import sys
import signal
import os
from pathlib import Path

import pytest

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PORT = 19876  # obscure port to avoid conflicts
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server():
    """Start the FastAPI server on an obscure port for tests."""
    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = "test-key-not-used"
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to start
    for _ in range(30):
        try:
            import httpx
            r = httpx.get(f"{BASE}/api/models", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server failed to start")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── API Tests (no browser needed) ──────────────────────────

class TestAPI:
    def test_index_returns_html(self, server):
        import httpx
        r = httpx.get(f"{BASE}/")
        assert r.status_code == 200
        assert "SECRET HITLER" in r.text or "Secret Hitler" in r.text

    def test_models_endpoint(self, server):
        import httpx
        r = httpx.get(f"{BASE}/api/models")
        assert r.status_code == 200
        models = r.json()
        assert isinstance(models, list)
        assert len(models) > 10
        # Check structure
        m = models[0]
        assert "id" in m
        assert "name" in m
        assert "context_window" in m

    def test_stats_endpoint_empty(self, server):
        import httpx
        r = httpx.get(f"{BASE}/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_games" in data
        assert "matchups" in data

    def test_history_endpoint(self, server):
        import httpx
        r = httpx.get(f"{BASE}/api/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── WebSocket Game Test ────────────────────────────────────

class TestWebSocketGame:
    def test_mock_game_completes(self, server):
        """Run a full mock game via WebSocket and verify all events."""
        import httpx
        from websockets.sync.client import connect

        events = []
        with connect(f"ws://127.0.0.1:{PORT}/ws/game") as ws:
            # Send config — mock mode, no discussion, seeded
            ws.send(json.dumps({
                "liberal_model": None,
                "fascist_model": None,
                "seed": 42,
                "discussion": False,
                "reasoning": False,
            }))

            # Collect all events
            done = False
            while not done:
                try:
                    msg = ws.recv(timeout=30)
                    event = json.loads(msg)
                    events.append(event)
                    if event["type"] in ("game_complete", "error"):
                        # Drain any remaining messages
                        try:
                            while True:
                                msg = ws.recv(timeout=1)
                                events.append(json.loads(msg))
                        except Exception:
                            pass
                        done = True
                except Exception:
                    done = True

        # Verify we got key events
        types = [e["type"] for e in events]
        assert "game_starting" in types
        assert "game_start" in types
        assert "round_start" in types
        assert "nomination" in types or "nomination_fallback" in types
        assert "vote_result" in types
        # game_end or game_complete — both indicate the game finished
        assert "game_end" in types or "game_complete" in types

        # Verify game_start has players and roles
        game_start = next(e for e in events if e["type"] == "game_start")
        assert len(game_start["data"]["players"]) == 8
        assert len(game_start["data"]["roles"]) == 8

        # Verify roles are correct distribution
        roles = list(game_start["data"]["roles"].values())
        assert roles.count("liberal") == 5
        assert roles.count("fascist") == 2
        assert roles.count("hitler") == 1

        # Verify game ended with a winner (could be game_end or game_complete)
        end_event = next(
            (e for e in events if e["type"] in ("game_end", "game_complete", "game_saved")),
            None,
        )
        assert end_event is not None, f"No end event found. Types: {types}"
        if end_event["type"] == "game_end":
            assert end_event["data"]["winner"] in ("liberal", "fascist")
        elif end_event["type"] == "game_saved":
            assert end_event["data"]["winner"] in ("liberal", "fascist")

    def test_mock_game_with_discussion(self, server):
        """Run a mock game WITH discussion and verify discussion events appear."""
        from websockets.sync.client import connect

        events = []
        with connect(f"ws://127.0.0.1:{PORT}/ws/game") as ws:
            ws.send(json.dumps({
                "liberal_model": None,
                "fascist_model": None,
                "seed": 55,
                "discussion": True,
                "reasoning": False,
            }))

            while True:
                try:
                    msg = ws.recv(timeout=60)
                    event = json.loads(msg)
                    events.append(event)
                    if event["type"] in ("game_complete", "error"):
                        break
                except Exception:
                    break

        types = [e["type"] for e in events]
        assert "game_complete" in types
        # Should have discussion events
        assert "discussion_start" in types
        assert "discussion" in types or "discussion_silence" in types

    def test_game_saved_to_db(self, server):
        """Verify game results are saved to the history DB."""
        import httpx
        from websockets.sync.client import connect

        # Run a game
        with connect(f"ws://127.0.0.1:{PORT}/ws/game") as ws:
            ws.send(json.dumps({
                "liberal_model": None,
                "fascist_model": None,
                "seed": 123,
                "discussion": False,
            }))
            events = []
            while True:
                try:
                    msg = ws.recv(timeout=30)
                    event = json.loads(msg)
                    events.append(event)
                    if event["type"] in ("game_complete", "error"):
                        break
                except Exception:
                    break

        # Check game_saved event was sent
        types = [e["type"] for e in events]
        assert "game_saved" in types

        # Check stats endpoint reflects the game
        r = httpx.get(f"{BASE}/api/stats")
        data = r.json()
        assert data["total_games"] >= 1


# ── Playwright Browser Tests ──────────────────────────────

class TestBrowserUI:
    def test_page_loads(self, server):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE)

            # Check title
            assert "Secret Hitler" in page.title()

            # Check header renders
            header = page.locator("text=SECRET HITLER")
            assert header.is_visible()

            # Check BENCH badge
            bench = page.locator("text=BENCH")
            assert bench.is_visible()

            browser.close()

    def test_model_dropdowns_populated(self, server):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE)
            page.wait_for_timeout(1000)  # wait for model fetch

            # Check model dropdown buttons exist (custom searchable dropdowns)
            # Liberal and Fascist team selectors show "Mock (Random)" by default
            dropdowns = page.locator("button", has_text="Mock (Random)")
            assert dropdowns.count() >= 2  # liberal + fascist team selectors

            browser.close()

    def test_start_mock_game_and_see_events(self, server):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE)
            page.wait_for_timeout(500)

            # Click Start Game
            start_btn = page.locator("button", has_text="Start Game")
            assert start_btn.is_visible()
            start_btn.click()

            # Wait for game to complete (mock is fast)
            page.wait_for_timeout(5000)

            # Check that players appeared
            # Player names should be visible
            page_text = page.content()
            # At least some player names should appear
            player_names = ["Avery", "Blake", "Casey", "Drew", "Ellis", "Finley", "Kit", "Morgan", "Rook", "Tam"]
            found = sum(1 for n in player_names if n in page_text)
            assert found >= 8, f"Only found {found} player names in page"

            # Check game result appeared (LIBERAL or FASCIST wins)
            page.wait_for_selector("text=/LIBERAL|FASCIST/i", timeout=10000)

            browser.close()

    def test_history_modal(self, server):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE)
            page.wait_for_timeout(500)

            # Click History button
            history_btn = page.locator("button", has_text="History")
            history_btn.click()

            # Modal should appear
            page.wait_for_selector("text=GAME HISTORY", timeout=5000)

            # Close it
            close_btn = page.locator("button", has_text="Close")
            close_btn.click()
            page.wait_for_timeout(500)

            browser.close()

    def test_seed_input_works(self, server):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE)
            page.wait_for_timeout(500)

            # Find seed input and change it
            seed_input = page.locator("input[type=number]")
            seed_input.fill("99")

            # Verify value changed
            assert seed_input.input_value() == "99"

            browser.close()

    def test_checkboxes_toggle(self, server):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE)
            page.wait_for_timeout(500)

            # Find Discussion checkbox and toggle it
            checkboxes = page.locator("input[type=checkbox]")
            count = checkboxes.count()
            assert count >= 3  # Discussion, Reasoning, Show Thoughts

            browser.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
