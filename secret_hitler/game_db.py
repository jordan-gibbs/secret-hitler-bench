"""
Game history database — JSONL file that tracks every game result.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "game_history.jsonl"


@dataclass
class GameRecord:
    game_id: str
    timestamp: str
    liberal_model: str
    fascist_model: str
    seed: int | None
    winner: str
    win_condition: str
    rounds: int
    liberal_policies: int
    fascist_policies: int
    players: dict  # {name: role}
    discussion_enabled: bool
    reasoning_enabled: bool

    def to_dict(self) -> dict:
        return asdict(self)


def save_game(record: GameRecord, path: Path = DB_PATH) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def load_all_games(path: Path = DB_PATH) -> list[GameRecord]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                records.append(GameRecord(**d))
            except (json.JSONDecodeError, TypeError):
                continue
    return records


def get_stats(path: Path = DB_PATH) -> dict:
    games = load_all_games(path)
    if not games:
        return {"total_games": 0, "matchups": [], "model_stats": {}}

    # Aggregate by matchup
    matchups: dict[tuple[str, str], dict] = {}
    model_stats: dict[str, dict] = {}

    for g in games:
        key = (g.liberal_model, g.fascist_model)
        if key not in matchups:
            matchups[key] = {
                "liberal_model": g.liberal_model,
                "fascist_model": g.fascist_model,
                "games": 0,
                "liberal_wins": 0,
                "fascist_wins": 0,
                "avg_rounds": 0,
                "total_rounds": 0,
                "win_conditions": {},
            }
        m = matchups[key]
        m["games"] += 1
        m["total_rounds"] += g.rounds
        m["avg_rounds"] = m["total_rounds"] / m["games"]
        if g.winner == "liberal":
            m["liberal_wins"] += 1
        else:
            m["fascist_wins"] += 1
        m["win_conditions"][g.win_condition] = m["win_conditions"].get(g.win_condition, 0) + 1

        # Per-model stats
        for model_id in [g.liberal_model, g.fascist_model]:
            if model_id not in model_stats:
                model_stats[model_id] = {"games": 0, "wins_as_liberal": 0, "wins_as_fascist": 0, "total_games_liberal": 0, "total_games_fascist": 0}
            ms = model_stats[model_id]
            ms["games"] += 1
            if model_id == g.liberal_model:
                ms["total_games_liberal"] += 1
                if g.winner == "liberal":
                    ms["wins_as_liberal"] += 1
            if model_id == g.fascist_model:
                ms["total_games_fascist"] += 1
                if g.winner == "fascist":
                    ms["wins_as_fascist"] += 1

    return {
        "total_games": len(games),
        "matchups": list(matchups.values()),
        "model_stats": model_stats,
        "recent_games": [g.to_dict() for g in games[-20:]],
    }


def create_record(
    liberal_model: str,
    fascist_model: str,
    seed: int | None,
    winner: str,
    win_condition: str,
    rounds: int,
    liberal_policies: int,
    fascist_policies: int,
    players: dict,
    discussion_enabled: bool = False,
    reasoning_enabled: bool = False,
) -> GameRecord:
    return GameRecord(
        game_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc).isoformat(),
        liberal_model=liberal_model,
        fascist_model=fascist_model,
        seed=seed,
        winner=winner,
        win_condition=win_condition,
        rounds=rounds,
        liberal_policies=liberal_policies,
        fascist_policies=fascist_policies,
        players=players,
        discussion_enabled=discussion_enabled,
        reasoning_enabled=reasoning_enabled,
    )
