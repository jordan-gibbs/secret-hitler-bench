from __future__ import annotations

from dataclasses import dataclass, field

from secret_hitler.models import (
    ExecutiveAction,
    FASCIST_BOARD_POWERS_8P,
    GamePhase,
    Party,
    PlayerInfo,
    PolicyType,
    Role,
    Vote,
    WinCondition,
)
from secret_hitler.policy_deck import PolicyDeck


@dataclass
class VoteRecord:
    round_number: int
    president_seat: int
    chancellor_seat: int
    votes: dict[int, Vote]  # seat -> vote
    passed: bool


@dataclass
class EnactedPolicyRecord:
    round_number: int
    policy: PolicyType
    was_chaos: bool


@dataclass
class InvestigationRecord:
    round_number: int
    investigator_seat: int
    target_seat: int
    actual_party: Party


@dataclass
class ExecutionRecord:
    round_number: int
    executor_seat: int
    target_seat: int


@dataclass
class ChatMessage:
    round_number: int
    speaker_seat: int
    message: str
    context: str  # e.g. "pre_nomination", "post_nomination", "post_legislation"
    directed_at_seat: int | None = None


@dataclass
class GameState:
    players: list[PlayerInfo]
    policy_deck: PolicyDeck

    liberal_policies: int = 0
    fascist_policies: int = 0
    election_tracker: int = 0

    # Rotation tracking
    presidential_candidate_seat: int = 0
    last_elected_president: int | None = None
    last_elected_chancellor: int | None = None

    # Special election bookkeeping
    special_election_return_seat: int | None = None

    veto_unlocked: bool = False
    investigated_players: set[int] = field(default_factory=set)

    winner: Party | None = None
    win_condition: WinCondition | None = None
    round_number: int = 0
    phase: GamePhase = GamePhase.NIGHT

    # History logs
    vote_history: list[VoteRecord] = field(default_factory=list)
    enacted_policies: list[EnactedPolicyRecord] = field(default_factory=list)
    investigations: list[InvestigationRecord] = field(default_factory=list)
    executions: list[ExecutionRecord] = field(default_factory=list)
    chat_log: list[ChatMessage] = field(default_factory=list)

    @property
    def alive_players(self) -> list[PlayerInfo]:
        return [p for p in self.players if p.is_alive]

    @property
    def alive_seats(self) -> list[int]:
        return [p.seat for p in self.players if p.is_alive]

    def player_by_seat(self, seat: int) -> PlayerInfo:
        return self.players[seat]

    def player_by_name(self, name: str) -> PlayerInfo:
        for p in self.players:
            if p.name == name:
                return p
        raise ValueError(f"No player named {name!r}")

    def eligible_chancellor_nominees(self, president_seat: int) -> list[int]:
        alive = self.alive_seats
        ineligible = {president_seat}

        alive_count = len(alive)

        if alive_count > 5:
            # Both last elected president and chancellor are term-limited
            if self.last_elected_president is not None:
                ineligible.add(self.last_elected_president)
            if self.last_elected_chancellor is not None:
                ineligible.add(self.last_elected_chancellor)
        else:
            # 5 or fewer alive: only last elected chancellor is term-limited
            if self.last_elected_chancellor is not None:
                ineligible.add(self.last_elected_chancellor)

        return [s for s in alive if s not in ineligible]

    def get_executive_action(self, fascist_count: int) -> ExecutiveAction:
        if fascist_count < 1 or fascist_count > 5:
            return ExecutiveAction.NONE
        return FASCIST_BOARD_POWERS_8P[fascist_count - 1]

    def next_alive_seat(self, from_seat: int) -> int:
        total = len(self.players)
        seat = (from_seat + 1) % total
        while not self.players[seat].is_alive:
            seat = (seat + 1) % total
        return seat

    @property
    def game_over(self) -> bool:
        return self.winner is not None
