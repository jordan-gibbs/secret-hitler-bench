"""
Secret Hitler Bench — Web UI Server

Usage:
    python server.py
    python server.py --port 8080
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from secret_hitler.arbiter import DiscussionConfig, GameArbiter
from secret_hitler.game_db import create_record, get_stats, load_all_games, save_game
from secret_hitler.model_config import list_models, get_model
from secret_hitler.models import Party
from secret_hitler.player import LLMPlayer, MockPlayer

app = FastAPI(title="Secret Hitler Bench")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


_cached_openrouter_models: list[dict] | None = None

@app.get("/api/models")
async def api_models():
    global _cached_openrouter_models

    # Return cached if available
    if _cached_openrouter_models is not None:
        return _cached_openrouter_models

    # Try to fetch live from OpenRouter
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    raw = resp.json().get("data", [])
                    result = []
                    seen = set()
                    for m in raw:
                        mid = m["id"]
                        params = m.get("supported_parameters", [])
                        if "tools" not in params:
                            continue
                        if m.get("context_length", 0) < 8000:
                            continue
                        base = mid.split(":")[0]
                        if base in seen:
                            continue
                        seen.add(base)
                        price_in = float(m["pricing"].get("prompt", "0")) * 1_000_000
                        price_out = float(m["pricing"].get("completion", "0")) * 1_000_000
                        result.append({
                            "id": mid,
                            "name": m.get("name", mid),
                            "context_window": m.get("context_length", 0),
                            "supports_reasoning": "reasoning" in params,
                            "supports_json_schema": "response_format" in params,
                            "notes": f"${price_in:.2f}/${price_out:.2f} per M tok. {m.get('context_length',0)//1000}K ctx.",
                        })
                    result.sort(key=lambda x: x["name"])
                    _cached_openrouter_models = result
                    return result
        except Exception as e:
            logging.warning("Failed to fetch OpenRouter models: %s", e)

    # Fallback to local registry
    models = list_models()
    return [
        {
            "id": m.id,
            "name": m.name,
            "context_window": m.context_window,
            "supports_reasoning": m.supports_reasoning,
            "supports_json_schema": m.supports_json_schema,
            "notes": m.notes,
        }
        for m in models
    ]


@app.get("/api/stats")
async def api_stats():
    return get_stats()


@app.get("/api/history")
async def api_history():
    games = load_all_games()
    return [g.to_dict() for g in games]


def _make_client(model_id: str, reasoning: bool, effort: str):
    """Create an OpenRouter client for a model, or None for mock."""
    if not model_id or model_id == "mock":
        return None
    from secret_hitler.llm_client import OpenRouterClient
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    return OpenRouterClient(
        api_key=api_key,
        model=model_id,
        enable_reasoning=reasoning,
        reasoning_effort=effort,
        request_delay=0.3,
    )


@app.websocket("/ws/game")
async def game_websocket(ws: WebSocket):
    await ws.accept()
    clients_to_close = []

    # Use a queue so the sync callback can enqueue events
    # and we drain them between game steps
    event_queue: asyncio.Queue = asyncio.Queue()

    try:
        config_raw = await ws.receive_text()
        config = json.loads(config_raw)

        liberal_model = config.get("liberal_model", "mock")
        fascist_model = config.get("fascist_model", "mock")
        seed = config.get("seed")
        discussion = config.get("discussion", True)
        reasoning = config.get("reasoning", False)
        reasoning_effort = config.get("reasoning_effort", "medium")

        disc = DiscussionConfig(enabled=discussion)

        # Sync callback puts events on the queue
        def on_event_sync(event_type: str, data: dict):
            event_queue.put_nowait({"type": event_type, "data": data})

        # Drain queued events to the WebSocket
        async def flush_events():
            while not event_queue.empty():
                event = event_queue.get_nowait()
                try:
                    await ws.send_json(event)
                except Exception:
                    pass

        # Build per-team clients
        liberal_client = None
        fascist_client = None
        use_llm = False

        try:
            liberal_client = _make_client(liberal_model, reasoning, reasoning_effort)
            fascist_client = _make_client(fascist_model, reasoning, reasoning_effort)
        except ValueError as e:
            await ws.send_json({"type": "error", "data": {"message": str(e)}})
            await ws.close()
            return

        if liberal_client:
            clients_to_close.append(liberal_client)
        if fascist_client:
            clients_to_close.append(fascist_client)

        use_llm = liberal_client is not None or fascist_client is not None

        if use_llm:
            arbiter = GameArbiter(
                player_factory=LLMPlayer if (liberal_client and fascist_client) else _get_mixed_factory(liberal_client, fascist_client),
                seed=seed,
                discussion_config=disc,
                on_event=on_event_sync,
                liberal_llm_client=liberal_client,
                fascist_llm_client=fascist_client,
            )
        else:
            arbiter = GameArbiter(
                player_factory=MockPlayer,
                player_factory_kwargs={"seed": seed},
                seed=seed,
                discussion_config=disc,
                on_event=on_event_sync,
            )

        await ws.send_json({"type": "game_starting", "data": {
            "liberal_model": liberal_model,
            "fascist_model": fascist_model,
            "seed": seed,
        }})

        # Run the game in a background task, flushing events continuously.
        # CRITICAL: cancel the game if the WebSocket disconnects.
        game_task = asyncio.create_task(arbiter.run_game())

        try:
            while not game_task.done():
                await flush_events()
                # Check if client is still connected
                try:
                    await asyncio.wait_for(ws.receive_text(), timeout=0.05)
                    # If we receive "stop", cancel the game
                    game_task.cancel()
                    break
                except asyncio.TimeoutError:
                    pass  # normal — no message from client, keep polling
                except WebSocketDisconnect:
                    logging.info("Client disconnected, cancelling game")
                    game_task.cancel()
                    return
        except Exception:
            game_task.cancel()
            raise

        if game_task.cancelled():
            try:
                await ws.send_json({"type": "game_complete", "data": {"cancelled": True}})
            except Exception:
                pass
            return

        # Wait for the task to fully complete
        try:
            log = await game_task
        except Exception as e:
            logging.exception("Game task failed")
            try:
                await ws.send_json({"type": "error", "data": {"message": str(e)}})
            except Exception:
                pass
            return

        await flush_events()
        summary = log.summary()

        # Collect usage from both clients
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "total_requests": 0, "failed_requests": 0}
        for c in clients_to_close:
            u = c.usage_summary()
            for k in total_usage:
                total_usage[k] += u.get(k, 0)
        total_usage["total_tokens"] = total_usage["prompt_tokens"] + total_usage["completion_tokens"]

        if use_llm:
            await ws.send_json({"type": "usage", "data": total_usage})

        # Save to game DB
        state = arbiter.state
        if state and state.winner:
            record = create_record(
                liberal_model=liberal_model,
                fascist_model=fascist_model,
                seed=seed,
                winner=state.winner.value,
                win_condition=state.win_condition.value if state.win_condition else "unknown",
                rounds=state.round_number,
                liberal_policies=state.liberal_policies,
                fascist_policies=state.fascist_policies,
                players={p.name: p.role.value for p in state.players},
                discussion_enabled=discussion,
                reasoning_enabled=reasoning,
            )
            save_game(record)
            await ws.send_json({"type": "game_saved", "data": record.to_dict()})

        await ws.send_json({"type": "game_complete", "data": summary})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.exception("Game error")
        try:
            await ws.send_json({"type": "error", "data": {"message": str(e)}})
        except Exception:
            pass
    finally:
        for c in clients_to_close:
            try:
                await c.close()
            except Exception:
                pass


def _get_mixed_factory(liberal_client, fascist_client):
    """When one team is LLM and the other is mock, we still use LLMPlayer
    as factory since the arbiter handles per-team client assignment.
    MockPlayer seats get a dummy client that won't be called because
    the arbiter will assign the real client based on party."""
    # If at least one team has an LLM, use LLMPlayer for all.
    # The arbiter's per-team client logic will assign the right client.
    # For the mock team, we still need an LLM client placeholder.
    # Actually, we need a different approach: use LLMPlayer for LLM seats
    # and MockPlayer for mock seats. The arbiter setup handles this
    # by checking if a client is available per party.
    return LLMPlayer


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    # Suppress noisy logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()
    print(f"\n  Secret Hitler Bench UI: http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port)
