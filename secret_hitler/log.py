from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class LogEvent:
    round_number: int
    phase: str
    event_type: str
    actor: str | None = None
    data: dict = field(default_factory=dict)
    hidden_data: dict | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GameLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def add(
        self,
        round_number: int,
        phase: str,
        event_type: str,
        actor: str | None = None,
        data: dict | None = None,
        hidden_data: dict | None = None,
    ) -> None:
        self.events.append(
            LogEvent(
                round_number=round_number,
                phase=phase,
                event_type=event_type,
                actor=actor,
                data=data or {},
                hidden_data=hidden_data,
            )
        )

    def to_jsonl(self) -> str:
        lines = [json.dumps(asdict(e), default=str) for e in self.events]
        return "\n".join(lines)

    def to_readable(self) -> str:
        lines: list[str] = []
        current_round = -1
        for e in self.events:
            if e.round_number != current_round:
                current_round = e.round_number
                lines.append(f"\n{'='*60}")
                lines.append(f"  ROUND {current_round}")
                lines.append(f"{'='*60}")

            actor_str = f" [{e.actor}]" if e.actor else ""
            lines.append(f"  {e.event_type}{actor_str}")

            for k, v in e.data.items():
                lines.append(f"    {k}: {v}")

        return "\n".join(lines)

    def summary(self) -> dict:
        game_end = next(
            (e for e in self.events if e.event_type == "game_end"), None
        )
        game_start = next(
            (e for e in self.events if e.event_type == "game_start"), None
        )
        return {
            "winner": game_end.data.get("winner") if game_end else None,
            "win_condition": game_end.data.get("condition") if game_end else None,
            "rounds": max((e.round_number for e in self.events), default=0),
            "roles": game_end.data.get("roles_revealed") if game_end else None,
            "total_events": len(self.events),
            "players": game_start.data.get("players") if game_start else None,
        }
