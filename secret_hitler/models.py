from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(Enum):
    LIBERAL = "liberal"
    FASCIST = "fascist"
    HITLER = "hitler"


class Party(Enum):
    LIBERAL = "liberal"
    FASCIST = "fascist"


class PolicyType(Enum):
    LIBERAL = "liberal"
    FASCIST = "fascist"


class Vote(Enum):
    JA = "ja"
    NEIN = "nein"


class GamePhase(Enum):
    NIGHT = "night"
    NOMINATION = "nomination"
    ELECTION = "election"
    LEGISLATIVE_PRESIDENT = "legislative_president"
    LEGISLATIVE_CHANCELLOR = "legislative_chancellor"
    EXECUTIVE_ACTION = "executive_action"
    GAME_OVER = "game_over"


class ExecutiveAction(Enum):
    NONE = "none"
    INVESTIGATE_LOYALTY = "investigate_loyalty"
    CALL_SPECIAL_ELECTION = "call_special_election"
    EXECUTION = "execution"
    EXECUTION_AND_VETO = "execution_and_veto"


class WinCondition(Enum):
    LIBERAL_FIVE_POLICIES = "liberal_five_policies"
    HITLER_ASSASSINATED = "hitler_assassinated"
    FASCIST_SIX_POLICIES = "fascist_six_policies"
    HITLER_ELECTED_CHANCELLOR = "hitler_elected_chancellor"


# 7-8 player fascist board: indexed by (fascist_policies_enacted - 1)
# Slot 6 (index 5) is fascist victory, handled by win-condition check before this is consulted.
FASCIST_BOARD_POWERS_8P: list[ExecutiveAction] = [
    ExecutiveAction.NONE,                     # 1st fascist policy
    ExecutiveAction.INVESTIGATE_LOYALTY,       # 2nd fascist policy
    ExecutiveAction.CALL_SPECIAL_ELECTION,     # 3rd fascist policy
    ExecutiveAction.EXECUTION,                # 4th fascist policy
    ExecutiveAction.EXECUTION_AND_VETO,       # 5th fascist policy
]


def party_for_role(role: Role) -> Party:
    if role == Role.LIBERAL:
        return Party.LIBERAL
    return Party.FASCIST


@dataclass
class PlayerInfo:
    seat: int
    name: str
    personality: str
    role: Role
    party: Party
    is_alive: bool = True
