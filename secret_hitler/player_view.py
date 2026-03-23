from __future__ import annotations

from dataclasses import dataclass, field

from secret_hitler.models import GamePhase, PolicyType, Role, Vote
from secret_hitler.game_state import GameState


@dataclass
class PlayerView:
    # Identity
    your_seat: int
    your_name: str
    your_role: str          # "liberal", "fascist", or "hitler"
    your_party: str         # "liberal" or "fascist"

    # Night-phase knowledge (fascists only)
    known_fascists: list[str] = field(default_factory=list)
    known_hitler: str | None = None

    # Public board state
    players: list[dict] = field(default_factory=list)  # [{seat, name, is_alive}]
    liberal_policies_enacted: int = 0
    fascist_policies_enacted: int = 0
    election_tracker: int = 0
    veto_unlocked: bool = False
    round_number: int = 0
    phase: str = ""

    # Election context
    presidential_candidate: str | None = None
    chancellor_nominee: str | None = None
    last_elected_president: str | None = None
    last_elected_chancellor: str | None = None
    eligible_chancellor_nominees: list[str] = field(default_factory=list)

    # Legislative context (only populated for president/chancellor during their turn)
    policies_in_hand: list[str] = field(default_factory=list)

    # Private investigation results this player received
    your_investigation_results: list[dict] = field(default_factory=list)

    # Public history
    chat_history: list[dict] = field(default_factory=list)
    vote_history: list[dict] = field(default_factory=list)
    enacted_policies_log: list[dict] = field(default_factory=list)
    execution_log: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "your_seat": self.your_seat,
            "your_name": self.your_name,
            "your_role": self.your_role,
            "your_party": self.your_party,
            "known_fascists": self.known_fascists,
            "known_hitler": self.known_hitler,
            "players": self.players,
            "liberal_policies_enacted": self.liberal_policies_enacted,
            "fascist_policies_enacted": self.fascist_policies_enacted,
            "election_tracker": self.election_tracker,
            "veto_unlocked": self.veto_unlocked,
            "round_number": self.round_number,
            "phase": self.phase,
            "presidential_candidate": self.presidential_candidate,
            "chancellor_nominee": self.chancellor_nominee,
            "last_elected_president": self.last_elected_president,
            "last_elected_chancellor": self.last_elected_chancellor,
            "eligible_chancellor_nominees": self.eligible_chancellor_nominees,
            "policies_in_hand": self.policies_in_hand,
            "your_investigation_results": self.your_investigation_results,
            "chat_history": self.chat_history,
            "vote_history": self.vote_history,
            "enacted_policies_log": self.enacted_policies_log,
            "execution_log": self.execution_log,
        }


def build_player_view(
    state: GameState,
    seat: int,
    *,
    policies_in_hand: list[PolicyType] | None = None,
    eligible_nominees: list[int] | None = None,
) -> PlayerView:
    me = state.player_by_seat(seat)

    # Role-specific night-phase knowledge
    known_fascists: list[str] = []
    known_hitler: str | None = None
    if me.role == Role.FASCIST:
        # Fascists know each other and know Hitler
        for p in state.players:
            if p.seat == seat:
                continue
            if p.role == Role.FASCIST:
                known_fascists.append(p.name)
            elif p.role == Role.HITLER:
                known_hitler = p.name
    # Hitler does NOT know the fascists in 7-8 player games

    # Helper to resolve seat -> name safely
    def _name(s: int | None) -> str | None:
        if s is None:
            return None
        return state.player_by_seat(s).name

    # Public player list
    players_public = [
        {"seat": p.seat, "name": p.name, "is_alive": p.is_alive}
        for p in state.players
    ]

    # Eligible nominees (only shown to president during nomination)
    eligible_names: list[str] = []
    if eligible_nominees is not None:
        eligible_names = [state.player_by_seat(s).name for s in eligible_nominees]

    # Policies in hand (only for president/chancellor during legislative phase)
    hand_strs: list[str] = []
    if policies_in_hand is not None:
        hand_strs = [p.value for p in policies_in_hand]

    # Investigation results this player has received
    my_investigations = [
        {
            "round": inv.round_number,
            "target": state.player_by_seat(inv.target_seat).name,
            "party_shown": inv.actual_party.value,
        }
        for inv in state.investigations
        if inv.investigator_seat == seat
    ]

    # Vote history (fully public after votes are revealed)
    vote_hist = [
        {
            "round": vr.round_number,
            "president": state.player_by_seat(vr.president_seat).name,
            "chancellor": state.player_by_seat(vr.chancellor_seat).name,
            "votes": {
                state.player_by_seat(s).name: v.value
                for s, v in vr.votes.items()
            },
            "passed": vr.passed,
        }
        for vr in state.vote_history
    ]

    # Enacted policies log (public)
    policy_log = [
        {
            "round": ep.round_number,
            "policy": ep.policy.value,
            "was_chaos": ep.was_chaos,
        }
        for ep in state.enacted_policies
    ]

    # Execution log (public — but role is NOT revealed)
    exec_log = [
        {
            "round": ex.round_number,
            "executed_by": state.player_by_seat(ex.executor_seat).name,
            "target": state.player_by_seat(ex.target_seat).name,
        }
        for ex in state.executions
    ]

    # Chat history (public) — full history, never truncated
    chat_hist = []
    for cm in state.chat_log:
        entry: dict = {
            "round": cm.round_number,
            "speaker": state.player_by_seat(cm.speaker_seat).name,
            "message": cm.message,
            "context": cm.context,
        }
        if cm.directed_at_seat is not None:
            entry["directed_at"] = state.player_by_seat(cm.directed_at_seat).name
        chat_hist.append(entry)

    return PlayerView(
        your_seat=seat,
        your_name=me.name,
        your_role=me.role.value,
        your_party=me.party.value,
        known_fascists=known_fascists,
        known_hitler=known_hitler,
        players=players_public,
        liberal_policies_enacted=state.liberal_policies,
        fascist_policies_enacted=state.fascist_policies,
        election_tracker=state.election_tracker,
        veto_unlocked=state.veto_unlocked,
        round_number=state.round_number,
        phase=state.phase.value,
        presidential_candidate=_name(state.presidential_candidate_seat),
        chancellor_nominee=None,  # set by arbiter when relevant
        last_elected_president=_name(state.last_elected_president),
        last_elected_chancellor=_name(state.last_elected_chancellor),
        eligible_chancellor_nominees=eligible_names,
        policies_in_hand=hand_strs,
        your_investigation_results=my_investigations,
        chat_history=chat_hist,
        vote_history=vote_hist,
        enacted_policies_log=policy_log,
        execution_log=exec_log,
    )
