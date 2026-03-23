from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

from secret_hitler.models import (
    ExecutiveAction,
    GamePhase,
    Party,
    PlayerInfo,
    PolicyType,
    Role,
    Vote,
    WinCondition,
    party_for_role,
)
from secret_hitler.game_state import (
    ChatMessage,
    EnactedPolicyRecord,
    ExecutionRecord,
    GameState,
    InvestigationRecord,
    VoteRecord,
)
from secret_hitler.policy_deck import PolicyDeck
from secret_hitler.player_view import PlayerView, build_player_view
from secret_hitler.player import LLMPlayer, MockPlayer, Player
from secret_hitler.log import GameLog
from secret_hitler.names import PLAYER_POOL

MAX_RETRIES = 3
MAX_ROUNDS = 50  # safety valve


@dataclass
class DiscussionConfig:
    enabled: bool = True
    max_turns_per_phase: int = 25    # hard cap on total speaking turns per discussion phase
    max_silent_waves: int = 2        # end after this many consecutive waves with zero speakers
    per_player_cap: int = 5          # max times one player can speak per phase

    # Per-phase enable/disable
    pre_game: bool = True
    pre_nomination: bool = True
    post_nomination: bool = True
    post_legislation: bool = True
    pre_executive: bool = True
    post_executive: bool = True


class GameArbiter:
    def __init__(
        self,
        player_factory: type[Player],
        player_factory_kwargs: dict | None = None,
        seed: int | None = None,
        discussion_config: DiscussionConfig | None = None,
        llm_client=None,
        on_event: Callable[[str, dict], None] | None = None,
        *,
        liberal_llm_client=None,
        fascist_llm_client=None,
    ) -> None:
        self._player_factory = player_factory
        self._player_factory_kwargs = player_factory_kwargs or {}
        self._rng = random.Random(seed)
        self._seed = seed
        self._discussion = discussion_config or DiscussionConfig()
        self._llm_client = llm_client
        self._liberal_llm_client = liberal_llm_client
        self._fascist_llm_client = fascist_llm_client
        self._on_event = on_event
        self.log = GameLog()
        self.state: GameState | None = None
        self.players: list[Player] = []

    def _emit(self, event_type: str, data: dict | None = None) -> None:
        if self._on_event:
            self._on_event(event_type, data or {})

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        # Pick 8 players from the pool
        pool = list(PLAYER_POOL)
        self._rng.shuffle(pool)
        selected = pool[:8]

        # Assign roles: 5 Liberal, 2 Fascist, 1 Hitler
        roles = (
            [Role.LIBERAL] * 5
            + [Role.FASCIST] * 2
            + [Role.HITLER]
        )
        self._rng.shuffle(roles)

        player_infos: list[PlayerInfo] = []
        for seat, (info, role) in enumerate(zip(selected, roles)):
            player_infos.append(
                PlayerInfo(
                    seat=seat,
                    name=info["name"],
                    personality=info["personality"],
                    role=role,
                    party=party_for_role(role),
                )
            )

        deck = PolicyDeck(seed=self._seed)

        self.state = GameState(
            players=player_infos,
            policy_deck=deck,
            presidential_candidate_seat=self._rng.randint(0, 7),
        )

        # Create player agents — supports per-team LLM clients
        from secret_hitler.prompts import build_system_prompt
        self.players = []
        for pi in player_infos:
            # Pick the right LLM client for this player's team
            client = self._llm_client  # default (shared)
            if self._liberal_llm_client and pi.party == Party.LIBERAL:
                client = self._liberal_llm_client
            elif self._fascist_llm_client and pi.party == Party.FASCIST:
                client = self._fascist_llm_client

            if client is not None:
                # LLM player
                player = LLMPlayer(
                    seat=pi.seat,
                    name=pi.name,
                    personality=pi.personality,
                    role=pi.role,
                    llm_client=client,
                    system_prompt=build_system_prompt(pi, self.state),
                )
            else:
                # Mock player (no LLM client for this team)
                player = MockPlayer(
                    seat=pi.seat,
                    name=pi.name,
                    personality=pi.personality,
                    role=pi.role,
                    seed=self._seed,
                )
            self.players.append(player)

        # Log game start
        self.log.add(
            round_number=0,
            phase="setup",
            event_type="game_start",
            data={
                "players": [
                    {"seat": p.seat, "name": p.name}
                    for p in player_infos
                ],
            },
            hidden_data={
                "roles": {p.name: p.role.value for p in player_infos},
                "deck_order": [p.value for p in deck.draw_pile],
            },
        )
        self._emit("game_start", {
            "players": [{"seat": p.seat, "name": p.name} for p in player_infos],
            "roles": {p.name: p.role.value for p in player_infos},
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _view(
        self,
        seat: int,
        *,
        policies_in_hand: list[PolicyType] | None = None,
        eligible_nominees: list[int] | None = None,
    ) -> PlayerView:
        return build_player_view(
            self.state,
            seat,
            policies_in_hand=policies_in_hand,
            eligible_nominees=eligible_nominees,
        )

    def _player_agent(self, seat: int) -> Player:
        return self.players[seat]

    def _name(self, seat: int) -> str:
        return self.state.player_by_seat(seat).name

    def _check_liberal_win(self) -> bool:
        if self.state.liberal_policies >= 5:
            self.state.winner = Party.LIBERAL
            self.state.win_condition = WinCondition.LIBERAL_FIVE_POLICIES
            return True
        return False

    def _check_fascist_win(self) -> bool:
        if self.state.fascist_policies >= 6:
            self.state.winner = Party.FASCIST
            self.state.win_condition = WinCondition.FASCIST_SIX_POLICIES
            return True
        return False

    def _check_hitler_chancellor(self, chancellor_seat: int) -> bool:
        if (
            self.state.fascist_policies >= 3
            and self.state.player_by_seat(chancellor_seat).role == Role.HITLER
        ):
            self.state.winner = Party.FASCIST
            self.state.win_condition = WinCondition.HITLER_ELECTED_CHANCELLOR
            return True
        return False

    def _check_hitler_executed(self, target_seat: int) -> bool:
        if self.state.player_by_seat(target_seat).role == Role.HITLER:
            self.state.winner = Party.LIBERAL
            self.state.win_condition = WinCondition.HITLER_ASSASSINATED
            return True
        return False

    def _enact_policy(self, policy: PolicyType, was_chaos: bool = False) -> None:
        if policy == PolicyType.LIBERAL:
            self.state.liberal_policies += 1
        else:
            self.state.fascist_policies += 1

        self.state.enacted_policies.append(
            EnactedPolicyRecord(
                round_number=self.state.round_number,
                policy=policy,
                was_chaos=was_chaos,
            )
        )

        # Reset election tracker whenever a policy is enacted
        self.state.election_tracker = 0

    def _advance_president(self) -> None:
        if self.state.special_election_return_seat is not None:
            # Returning from a special election
            self.state.presidential_candidate_seat = self.state.next_alive_seat(
                self.state.special_election_return_seat
            )
            self.state.special_election_return_seat = None
        else:
            self.state.presidential_candidate_seat = self.state.next_alive_seat(
                self.state.presidential_candidate_seat
            )

    # ------------------------------------------------------------------
    # Discussion
    # ------------------------------------------------------------------

    async def _run_discussion(
        self, context: str, instigator_seats: list[int] | None = None,
    ) -> None:
        """
        Discussion with continue/move-on voting:
          1. Instigators speak first (serial, with reply chains)
          2. One pass through remaining players
          3. Tally: each player votes "keep talking" or "move on"
             - Passers automatically vote "move on"
             - If majority says "move on" → discussion ends
             - If not → another wave, but ONLY players who spoke AND voted "keep talking"
          4. Hard cap on total turns still applies
        """
        if not self._discussion.enabled:
            return

        phase_key = context.split(":")[0]
        if not getattr(self._discussion, phase_key, True):
            return

        alive = self.state.alive_seats
        phase_caps = {
            "pre_game": 8,
            "pre_nomination": 10,
            "post_nomination": 10,
            "post_legislation": 20,
            "pre_executive": 16,
            "post_executive": 16,
        }
        max_turns = phase_caps.get(phase_key, 10)
        max_waves = 4

        total_turns = 0
        speak_counts: dict[int, int] = {}
        speakers_so_far: list[str] = []
        opted_out: set[int] = set()  # passed or voted "move on" — never asked again
        ready_votes: set[int] = set()  # voted "move on"
        majority = len(alive) // 2 + 1

        self._emit("discussion_start", {"context": context})

        # --- Wave 1: Instigators, then everyone else ---
        instigators = instigator_seats if instigator_seats else self._get_instigators(context)
        for ins_seat in instigators:
            if ins_seat in alive and total_turns < max_turns:
                total_turns = await self._ask_and_record(
                    ins_seat, context, total_turns, speak_counts,
                    speakers_so_far, opted_out, ready_votes,
                    max_turns=max_turns, is_instigator=True,
                )

        # First open pass — everyone not yet asked
        remaining = [s for s in alive if s not in opted_out and s not in {ins for ins in instigators if ins in alive}]
        self._rng.shuffle(remaining)
        for seat in remaining:
            if total_turns >= max_turns:
                break
            total_turns = await self._ask_and_record(
                seat, context, total_turns, speak_counts,
                speakers_so_far, opted_out, ready_votes, max_turns=max_turns,
            )

        # --- Subsequent waves: only engaged players, driven by majority vote ---
        wave = 1
        while wave < max_waves and total_turns < max_turns:
            # Check majority
            if len(ready_votes) >= majority:
                self._emit("discussion", {
                    "speaker": "Table",
                    "message": f"Majority ready to move on ({len(ready_votes)}/{len(alive)}).",
                    "directed_at": None,
                })
                break

            # Who's still engaged? Players who spoke AND didn't vote "move on"
            engaged = [s for s in alive if s not in opted_out]
            if not engaged:
                break

            wave += 1
            self._rng.shuffle(engaged)
            wave_had_speaker = False
            for seat in engaged:
                if total_turns >= max_turns:
                    break
                prev = total_turns
                total_turns = await self._ask_and_record(
                    seat, context, total_turns, speak_counts,
                    speakers_so_far, opted_out, ready_votes, max_turns=max_turns,
                )
                if total_turns > prev:
                    wave_had_speaker = True

            if not wave_had_speaker:
                break  # everyone passed this wave — natural end

        # Final majority check
        if total_turns > 0 and len(ready_votes) < majority:
            self._emit("discussion", {
                "speaker": "Table",
                "message": f"Discussion ended ({total_turns} messages).",
                "directed_at": None,
            })

        if total_turns > 0:
            discussion_end_data = {
                "context": context,
                "total_turns": total_turns,
                "speak_counts": {
                    self._name(s): c for s, c in speak_counts.items() if c > 0
                },
            }
            self.log.add(
                round_number=self.state.round_number,
                phase="discussion",
                event_type="discussion_end",
                data=discussion_end_data,
            )
            self._emit("discussion_end", discussion_end_data)

    async def _ask_and_record(
        self,
        seat: int,
        context: str,
        total_turns: int,
        speak_counts: dict[int, int],
        speakers_so_far: list[str],
        opted_out: set[int],
        ready_votes: set[int],
        *,
        max_turns: int = 25,
        is_instigator: bool = False,
        called_out_by: str | None = None,
    ) -> int:
        """
        Ask one player. They speak or pass, and vote continue/move-on.
        If they direct at someone, that person gets an immediate reply chance.
        Returns updated total_turns.
        """
        # Directed replies always go through even if cap is reached
        if total_turns >= max_turns and not called_out_by:
            return total_turns
        if seat in opted_out and not called_out_by:
            return total_turns

        result = await self._ask_to_speak(
            seat, context, total_turns, speakers_so_far,
            is_instigator=is_instigator,
            called_out_by=called_out_by,
        )

        if result is None:
            # Passed — done, votes "move on"
            opted_out.add(seat)
            ready_votes.add(seat)
            if called_out_by:
                self._record_silence(seat, called_out_by, context)
            return total_turns

        # result = (message, directed_at_seat, speaker_seat, ready_to_proceed)
        total_turns += 1
        speak_counts[seat] = speak_counts.get(seat, 0) + 1
        directed_at_seat = result[1]
        is_ready = result[3] if len(result) > 3 else False

        if is_ready:
            # Spoke but voted "move on" — won't be asked in future waves
            opted_out.add(seat)
            ready_votes.add(seat)

        # Reply chain — ONE level only, no counter-replies
        # (If you were already responding to someone, your directed_at
        # does NOT trigger another chain — prevents ping-pong)
        if directed_at_seat is not None and total_turns < max_turns and not called_out_by:
            # Give target ONE chance to respond (no further chaining)
            reply = await self._ask_to_speak(
                directed_at_seat, context, total_turns, speakers_so_far,
                called_out_by=self._name(seat),
            )
            if reply is None:
                opted_out.add(directed_at_seat)
                ready_votes.add(directed_at_seat)
                self._record_silence(directed_at_seat, self._name(seat), context)
            else:
                total_turns += 1
                speak_counts[directed_at_seat] = speak_counts.get(directed_at_seat, 0) + 1
                reply_ready = reply[3] if len(reply) > 3 else False
                if reply_ready:
                    opted_out.add(directed_at_seat)
                    ready_votes.add(directed_at_seat)

        return total_turns

    def _record_silence(self, seat: int, called_out_by: str, context: str) -> None:
        """Record that a player chose to stay silent when directly addressed."""
        name = self._name(seat)
        silence_msg = f"{name} remains silent."

        self.state.chat_log.append(
            ChatMessage(
                round_number=self.state.round_number,
                speaker_seat=seat,
                message=silence_msg,
                context=context,
            )
        )
        self.log.add(
            round_number=self.state.round_number,
            phase="discussion",
            event_type="discussion_silence",
            actor=name,
            data={
                "message": silence_msg,
                "context": context,
                "called_out_by": called_out_by,
            },
        )
        self._emit("discussion_silence", {
            "speaker": name,
            "called_out_by": called_out_by,
        })

    def _get_instigators(self, context: str) -> list[int]:
        """Return seats of players most relevant to what just happened."""
        results = []
        if "post_legislation" in context:
            # President explains, then chancellor — the core deception moment
            if self.state.last_elected_president is not None:
                results.append(self.state.last_elected_president)
            if self.state.last_elected_chancellor is not None:
                results.append(self.state.last_elected_chancellor)
        elif "post_executive" in context:
            if self.state.last_elected_president is not None:
                results.append(self.state.last_elected_president)
        elif "post_nomination" in context:
            # Nominee gets a chance to pitch before the vote
            results.append(self.state.presidential_candidate_seat)
            # Find the nominee seat from the context string
            for p in self.state.alive_players:
                if p.name in context and p.seat != self.state.presidential_candidate_seat:
                    results.append(p.seat)
                    break
        elif "pre_nomination" in context:
            results.append(self.state.presidential_candidate_seat)
        return results

    async def _gather_reactions(self, event_desc: str) -> None:
        """After a global event, all alive players think in parallel (no speaking)."""
        if not self._discussion.enabled:
            return

        alive = self.state.alive_seats

        async def _get_thought(seat: int) -> None:
            agent = self._player_agent(seat)
            view = self._view(seat)
            try:
                response = await agent.discussion_intent(
                    view, f"react:{event_desc}", 0, [],
                    is_instigator=False, called_out_by=None,
                )
                inner = getattr(response, "inner_thought", None)
                if inner:
                    self.log.add(
                        round_number=self.state.round_number,
                        phase="reaction",
                        event_type="inner_thought",
                        actor=self._name(seat),
                        hidden_data={"thought": inner, "trigger": event_desc},
                    )
                    self._emit("inner_thought", {
                        "speaker": self._name(seat),
                        "thought": inner,
                    })
            except Exception as e:
                logger.warning("Reaction failed for %s: %s", self._name(seat), e)

        await asyncio.gather(*[_get_thought(s) for s in alive])

    def _emit_context_stats(self) -> None:
        """Emit per-player context window stats for the UI."""
        from secret_hitler.player_view import build_player_view
        from secret_hitler.prompts import _format_view

        stats = []
        for p in self.players:
            # For LLM players: use actual tracked tokens
            actual_prompt = getattr(p, 'total_prompt_tokens', 0)
            actual_completion = getattr(p, 'total_completion_tokens', 0)
            calls = getattr(p, 'total_calls', 0)

            # Estimate current context size from what a prompt would look like
            try:
                view = build_player_view(self.state, p.seat)
                view_text = _format_view(view)
                sys_prompt = getattr(p, 'system_prompt', '')
                est_chars = len(sys_prompt) + len(view_text)
            except Exception:
                est_chars = 0

            stats.append({
                "name": p.name,
                "calls": calls,
                "prompt_tokens": actual_prompt,
                "completion_tokens": actual_completion,
                "est_context_tokens": actual_prompt // max(calls, 1) if actual_prompt else est_chars // 4,
            })

        avg_tok = sum(s["est_context_tokens"] for s in stats) // max(len(stats), 1)
        self._emit("context_stats", {
            "players": stats,
            "est_avg_tokens": avg_tok,
        })

    async def _ask_to_speak(
        self,
        seat: int,
        context: str,
        turn_number: int,
        speakers_so_far: list[str],
        *,
        is_instigator: bool = False,
        called_out_by: str | None = None,
    ) -> tuple[str, int | None, int, bool] | None:
        """
        Ask a player if they want to speak. Each call emits immediately
        for real-time streaming.
        Returns (message, directed_at_seat, speaker_seat, ready_to_proceed) or None if silent.
        """
        agent = self._player_agent(seat)
        view = self._view(seat)
        try:
            response = await agent.discussion_intent(
                view, context, turn_number, speakers_so_far,
                is_instigator=is_instigator,
                called_out_by=called_out_by,
            )

            inner_thought = getattr(response, "inner_thought", None)

            if not response.want_to_speak or not response.message:
                # Silent — log thought to file only, don't stream it
                if inner_thought:
                    self.log.add(
                        round_number=self.state.round_number,
                        phase="discussion",
                        event_type="inner_thought",
                        actor=self._name(seat),
                        hidden_data={"thought": inner_thought},
                    )
                return None

            message = response.message.strip()

            # Player is speaking — emit their thought before their message
            if inner_thought:
                self.log.add(
                    round_number=self.state.round_number,
                    phase="discussion",
                    event_type="inner_thought",
                    actor=self._name(seat),
                    hidden_data={"thought": inner_thought},
                )
                self._emit("inner_thought", {
                    "speaker": self._name(seat),
                    "thought": inner_thought,
                })

            # Resolve directed_at to a seat
            directed_at_seat = None
            if response.directed_at:
                try:
                    target = self.state.player_by_name(response.directed_at)
                    if target.is_alive and target.seat != seat:
                        directed_at_seat = target.seat
                except ValueError:
                    pass

            # Record immediately — streams to console in real-time
            self.state.chat_log.append(
                ChatMessage(
                    round_number=self.state.round_number,
                    speaker_seat=seat,
                    message=message,
                    context=context,
                    directed_at_seat=directed_at_seat,
                )
            )
            self.log.add(
                round_number=self.state.round_number,
                phase="discussion",
                event_type="discussion",
                actor=self._name(seat),
                data={
                    "message": message,
                    "context": context,
                    "directed_at": self._name(directed_at_seat) if directed_at_seat else None,
                },
            )
            self._emit("discussion", {
                "speaker": self._name(seat),
                "message": message,
                "directed_at": self._name(directed_at_seat) if directed_at_seat else None,
            })
            speakers_so_far.append(self._name(seat))

            is_ready = getattr(response, "ready_to_proceed", False)
            return message, directed_at_seat, seat, is_ready

        except Exception as e:
            logger.warning("Discussion failed for %s: %s", self._name(seat), e)
            return None

    # ------------------------------------------------------------------
    # Nomination + Election
    # ------------------------------------------------------------------

    async def _nomination_phase(self) -> int | None:
        """Returns the chancellor nominee seat, or None if something breaks."""
        president_seat = self.state.presidential_candidate_seat
        eligible = self.state.eligible_chancellor_nominees(president_seat)

        if not eligible:
            return None

        eligible_names = [self._name(s) for s in eligible]
        view = self._view(president_seat, eligible_nominees=eligible)

        self._emit("thinking", {"player": self._name(president_seat), "action": "nominating Chancellor"})
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._player_agent(president_seat).nominate_chancellor(
                    view, eligible_names
                )
                nominee = self.state.player_by_name(response.nominee)
                if nominee.seat in eligible:
                    self.log.add(
                        round_number=self.state.round_number,
                        phase="nomination",
                        event_type="nomination",
                        actor=self._name(president_seat),
                        data={
                            "president": self._name(president_seat),
                            "nominee": nominee.name,
                            "reasoning": response.reasoning,
                        },
                    )
                    self._emit("nomination", {
                        "president": self._name(president_seat),
                        "nominee": nominee.name,
                        "reasoning": response.reasoning,
                    })
                    return nominee.seat
            except Exception as e:
                logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)

        # Fallback: random valid choice
        fallback = self._rng.choice(eligible)
        self.log.add(
            round_number=self.state.round_number,
            phase="nomination",
            event_type="nomination_fallback",
            actor=self._name(president_seat),
            data={"president": self._name(president_seat), "nominee": self._name(fallback)},
        )
        self._emit("nomination_fallback", {
            "president": self._name(president_seat),
            "nominee": self._name(fallback),
        })
        return fallback

    async def _election_phase(self, president_seat: int, chancellor_seat: int) -> bool:
        """Returns True if the government is elected."""
        alive = self.state.alive_seats

        # Collect votes from all alive players concurrently
        self._emit("thinking", {"player": "All players", "action": "voting"})
        async def _get_vote(seat: int) -> tuple[int, Vote]:
            view = self._view(seat)
            # Inject the current nomination into the view
            view.presidential_candidate = self._name(president_seat)
            view.chancellor_nominee = self._name(chancellor_seat)
            for attempt in range(MAX_RETRIES):
                try:
                    response = await self._player_agent(seat).vote(view)
                    return seat, Vote(response.vote)
                except Exception as e:
                    logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)
            # Fallback
            return seat, Vote.NEIN

        # All players vote simultaneously (rules-accurate: votes are revealed at once)
        results = await asyncio.gather(*[_get_vote(s) for s in alive])
        votes = {seat: vote for seat, vote in results}

        ja_count = sum(1 for v in votes.values() if v == Vote.JA)
        nein_count = sum(1 for v in votes.values() if v == Vote.NEIN)
        passed = ja_count > nein_count  # strict majority

        vote_record = VoteRecord(
            round_number=self.state.round_number,
            president_seat=president_seat,
            chancellor_seat=chancellor_seat,
            votes=votes,
            passed=passed,
        )
        self.state.vote_history.append(vote_record)

        vote_result_data = {
            "president": self._name(president_seat),
            "chancellor": self._name(chancellor_seat),
            "votes": {self._name(s): v.value for s, v in votes.items()},
            "ja": ja_count,
            "nein": nein_count,
            "passed": passed,
        }
        self.log.add(
            round_number=self.state.round_number,
            phase="election",
            event_type="vote_result",
            data=vote_result_data,
        )
        self._emit("vote_result", vote_result_data)

        return passed

    # ------------------------------------------------------------------
    # Legislative Session
    # ------------------------------------------------------------------

    async def _legislative_session(
        self, president_seat: int, chancellor_seat: int
    ) -> PolicyType | None:
        """Run the legislative session. Returns the enacted policy, or None if vetoed."""
        self._emit("thinking", {"player": self._name(president_seat), "action": "drawing policies"})
        # President draws 3
        hand = self.state.policy_deck.draw(3)
        self.log.add(
            round_number=self.state.round_number,
            phase="legislative_president",
            event_type="president_draw",
            actor=self._name(president_seat),
            hidden_data={"drawn": [p.value for p in hand]},
        )
        self._emit("president_draw", {
            "president": self._name(president_seat),
            "cards": [p.value for p in hand],
        })

        # President discards 1
        view = self._view(president_seat, policies_in_hand=hand)
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._player_agent(president_seat).president_discard(
                    view, hand
                )
                idx = response.discard_index
                if 0 <= idx <= 2:
                    break
            except Exception as e:
                logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)
        else:
            idx = 0  # fallback

        discarded = hand.pop(idx)
        self.state.policy_deck.discard(discarded)
        self.log.add(
            round_number=self.state.round_number,
            phase="legislative_president",
            event_type="president_discard",
            actor=self._name(president_seat),
            hidden_data={
                "discarded": discarded.value,
                "passed_to_chancellor": [p.value for p in hand],
            },
        )
        self._emit("president_pass", {
            "president": self._name(president_seat),
            "chancellor": self._name(chancellor_seat),
            "discarded": discarded.value,
            "passed": [p.value for p in hand],
        })

        # Chancellor receives 2
        # Check for veto first (if unlocked)
        if self.state.veto_unlocked:
            chan_view = self._view(chancellor_seat, policies_in_hand=hand)
            try:
                veto_resp = await self._player_agent(chancellor_seat).chancellor_propose_veto(
                    chan_view, hand
                )
                propose_veto = veto_resp.propose_veto
            except Exception as e:
                logger.warning("Veto proposal failed: %s", e)
                propose_veto = False

            if propose_veto:
                self.log.add(
                    round_number=self.state.round_number,
                    phase="legislative_chancellor",
                    event_type="veto_proposed",
                    actor=self._name(chancellor_seat),
                    hidden_data={"hand": [p.value for p in hand]},
                )
                self._emit("veto_proposed")

                # President responds
                pres_view = self._view(president_seat)
                try:
                    veto_decision = await self._player_agent(
                        president_seat
                    ).president_respond_to_veto(pres_view)
                    accept = veto_decision.accept_veto
                except Exception as e:
                    logger.warning("Veto decision failed: %s", e)
                    accept = False

                self.log.add(
                    round_number=self.state.round_number,
                    phase="legislative_chancellor",
                    event_type="veto_response",
                    actor=self._name(president_seat),
                    data={"accepted": accept},
                )
                self._emit("veto_response", {"accepted": accept})

                if accept:
                    # Both policies discarded
                    for p in hand:
                        self.state.policy_deck.discard(p)
                    return None  # no policy enacted

        # Chancellor discards 1, enacts the other
        chan_view = self._view(chancellor_seat, policies_in_hand=hand)
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._player_agent(chancellor_seat).chancellor_discard(
                    chan_view, hand
                )
                idx = response.discard_index
                if 0 <= idx <= 1:
                    break
            except Exception as e:
                logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)
        else:
            idx = 0

        discarded_chan = hand.pop(idx)
        self.state.policy_deck.discard(discarded_chan)
        enacted = hand[0]

        self.log.add(
            round_number=self.state.round_number,
            phase="legislative_chancellor",
            event_type="chancellor_enact",
            actor=self._name(chancellor_seat),
            data={"enacted": enacted.value},
            hidden_data={"discarded": discarded_chan.value},
        )
        self._emit("chancellor_enact", {"enacted": enacted.value})

        return enacted

    # ------------------------------------------------------------------
    # Executive Actions
    # ------------------------------------------------------------------

    async def _executive_action(self, president_seat: int, action: ExecutiveAction) -> None:
        if action == ExecutiveAction.NONE:
            return

        if action == ExecutiveAction.INVESTIGATE_LOYALTY:
            await self._investigate(president_seat)
        elif action == ExecutiveAction.CALL_SPECIAL_ELECTION:
            await self._special_election(president_seat)
        elif action in (ExecutiveAction.EXECUTION, ExecutiveAction.EXECUTION_AND_VETO):
            if action == ExecutiveAction.EXECUTION_AND_VETO:
                self.state.veto_unlocked = True
                self.log.add(
                    round_number=self.state.round_number,
                    phase="executive_action",
                    event_type="veto_unlocked",
                )
                self._emit("veto_unlocked")
            await self._execute(president_seat)

    async def _investigate(self, president_seat: int) -> None:
        eligible_seats = [
            s for s in self.state.alive_seats
            if s != president_seat and s not in self.state.investigated_players
        ]
        if not eligible_seats:
            return

        eligible_names = [self._name(s) for s in eligible_seats]
        view = self._view(president_seat)

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._player_agent(president_seat).investigate_loyalty(
                    view, eligible_names
                )
                target = self.state.player_by_name(response.target)
                if target.seat in eligible_seats:
                    break
            except Exception as e:
                logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)
        else:
            target = self.state.player_by_seat(self._rng.choice(eligible_seats))

        self.state.investigated_players.add(target.seat)
        self.state.investigations.append(
            InvestigationRecord(
                round_number=self.state.round_number,
                investigator_seat=president_seat,
                target_seat=target.seat,
                actual_party=target.party,
            )
        )

        self.log.add(
            round_number=self.state.round_number,
            phase="executive_action",
            event_type="investigation",
            actor=self._name(president_seat),
            data={"target": target.name},
            hidden_data={"actual_party": target.party.value},
        )
        self._emit("investigation", {"president": self._name(president_seat), "target": target.name})

    async def _special_election(self, president_seat: int) -> None:
        eligible_seats = [
            s for s in self.state.alive_seats if s != president_seat
        ]
        eligible_names = [self._name(s) for s in eligible_seats]
        view = self._view(president_seat)

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._player_agent(president_seat).call_special_election(
                    view, eligible_names
                )
                target = self.state.player_by_name(response.target)
                if target.seat in eligible_seats:
                    break
            except Exception as e:
                logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)
        else:
            target = self.state.player_by_seat(self._rng.choice(eligible_seats))

        # Store where to return after the special election
        self.state.special_election_return_seat = self.state.presidential_candidate_seat

        # The chosen player becomes the next presidential candidate
        # We set it so the main loop will use them directly (subtract 1 since
        # _advance_president will call next_alive_seat which adds 1)
        # Actually, we need to set candidate directly. The main loop advances first,
        # so we need a flag. Let's handle it differently:
        # Set the candidate seat directly. The main loop's _advance_president at the
        # top of the next iteration must detect special_election_return_seat is set
        # and skip the normal advance on that NEXT call.
        # But the flow is: at the top of the loop we advance, then we play.
        # For a special election, we want the NEXT iteration to use the target directly.
        # So we set presidential_candidate_seat to the seat BEFORE the target,
        # so that next_alive_seat lands on the target.
        # Actually, the cleanest approach: set a flag that the next round uses a
        # specific seat directly.
        self.state.presidential_candidate_seat = target.seat
        # Mark that we need to NOT advance at the start of the next round
        self._special_election_pending = True

        self.log.add(
            round_number=self.state.round_number,
            phase="executive_action",
            event_type="special_election",
            actor=self._name(president_seat),
            data={"target": target.name},
        )
        self._emit("special_election", {"target": target.name})

    async def _execute(self, president_seat: int) -> None:
        eligible_seats = [
            s for s in self.state.alive_seats if s != president_seat
        ]
        eligible_names = [self._name(s) for s in eligible_seats]
        view = self._view(president_seat)

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._player_agent(president_seat).execute_player(
                    view, eligible_names
                )
                target = self.state.player_by_name(response.target)
                if target.seat in eligible_seats:
                    break
            except Exception as e:
                logger.warning("Player action failed (attempt %d): %s", attempt + 1, e)
        else:
            target = self.state.player_by_seat(self._rng.choice(eligible_seats))

        target.is_alive = False
        self.state.executions.append(
            ExecutionRecord(
                round_number=self.state.round_number,
                executor_seat=president_seat,
                target_seat=target.seat,
            )
        )

        self.log.add(
            round_number=self.state.round_number,
            phase="executive_action",
            event_type="execution",
            actor=self._name(president_seat),
            data={"target": target.name},
            hidden_data={"target_role": target.role.value},
        )
        self._emit("execution", {"president": self._name(president_seat), "target": target.name})

        # Check if Hitler was killed
        if self._check_hitler_executed(target.seat):
            self.log.add(
                round_number=self.state.round_number,
                phase="executive_action",
                event_type="hitler_assassinated",
                data={"target": target.name},
            )
            self._emit("hitler_assassinated", {"target": target.name})

    # ------------------------------------------------------------------
    # Chaos (Election Tracker)
    # ------------------------------------------------------------------

    def _handle_chaos(self) -> None:
        policy = self.state.policy_deck.pop_top()
        self._enact_policy(policy, was_chaos=True)

        # Reset election tracker (already done by _enact_policy)
        # Clear term limits
        self.state.last_elected_president = None
        self.state.last_elected_chancellor = None

        self.log.add(
            round_number=self.state.round_number,
            phase="election",
            event_type="chaos_policy",
            data={"enacted": policy.value},
        )
        self._emit("chaos_policy", {"enacted": policy.value})

        # Check deck
        self.state.policy_deck._reshuffle_if_needed(3)

    # ------------------------------------------------------------------
    # Main Game Loop
    # ------------------------------------------------------------------

    async def run_game(self) -> GameLog:
        self._setup()
        self._special_election_pending = False
        first_round = True

        # --- Pre-game chatter (brief, no instigators) ---
        if self._discussion.enabled and self._discussion.pre_game:
            await self._run_discussion("pre_game", instigator_seats=[])

        while not self.state.game_over and self.state.round_number < MAX_ROUNDS:
            self.state.round_number += 1

            # --- Advance presidential candidate ---
            if first_round:
                # First round uses the randomly selected starting candidate
                first_round = False
            elif self._special_election_pending:
                # Special election: presidential_candidate_seat was already set
                self._special_election_pending = False
            else:
                self._advance_president()

            president_seat = self.state.presidential_candidate_seat
            self.state.phase = GamePhase.NOMINATION

            self._emit("round_start", {
                "round": self.state.round_number,
                "president": self._name(president_seat),
            })
            self._emit_context_stats()
            self._emit("board_state", {
                "liberal": self.state.liberal_policies,
                "fascist": self.state.fascist_policies,
                "election_tracker": self.state.election_tracker,
            })

            # --- Pre-nomination discussion ---
            await self._run_discussion("pre_nomination")

            # --- Nomination ---
            chancellor_seat = await self._nomination_phase()
            if chancellor_seat is None:
                # No valid nominees (shouldn't happen with 8 players)
                continue

            # --- Post-nomination discussion ---
            await self._run_discussion(
                f"post_nomination:{self._name(president_seat)}_nominated_{self._name(chancellor_seat)}"
            )

            # --- Election ---
            self.state.phase = GamePhase.ELECTION
            passed = await self._election_phase(president_seat, chancellor_seat)

            if not passed:
                # Election failed
                self.state.election_tracker += 1
                if self.state.election_tracker >= 3:
                    self._handle_chaos()
                    if self._check_liberal_win() or self._check_fascist_win():
                        break
                continue

            # --- Election passed ---
            self.state.last_elected_president = president_seat
            self.state.last_elected_chancellor = chancellor_seat

            # Hitler chancellor check (after 3+ fascist policies)
            if self._check_hitler_chancellor(chancellor_seat):
                self.log.add(
                    round_number=self.state.round_number,
                    phase="election",
                    event_type="hitler_elected_chancellor",
                    data={"chancellor": self._name(chancellor_seat)},
                )
                self._emit("hitler_elected_chancellor", {"chancellor": self._name(chancellor_seat)})
                break

            if self.state.fascist_policies >= 3:
                self.log.add(
                    round_number=self.state.round_number,
                    phase="election",
                    event_type="hitler_chancellor_check",
                    data={
                        "chancellor": self._name(chancellor_seat),
                        "is_hitler": False,
                    },
                )
                self._emit("hitler_chancellor_check", {
                    "chancellor": self._name(chancellor_seat),
                    "is_hitler": False,
                })

            # --- Legislative session ---
            self.state.phase = GamePhase.LEGISLATIVE_PRESIDENT
            enacted = await self._legislative_session(president_seat, chancellor_seat)

            if enacted is None:
                # Veto was accepted
                self.state.election_tracker += 1
                if self.state.election_tracker >= 3:
                    self._handle_chaos()
                    if self._check_liberal_win() or self._check_fascist_win():
                        break
                continue

            self._enact_policy(enacted)
            self._emit_context_stats()

            if self._check_liberal_win() or self._check_fascist_win():
                break

            # --- Post-legislation debrief (always, both teams) ---
            await self._run_discussion("post_legislation")

            # --- Executive action (only for fascist policies) ---
            if enacted == PolicyType.FASCIST:
                action = self.state.get_executive_action(self.state.fascist_policies)
                if action != ExecutiveAction.NONE:
                    # Pre-executive discussion — table weighs in before the president acts
                    await self._run_discussion(f"pre_executive:{action.value}")

                    self.state.phase = GamePhase.EXECUTIVE_ACTION
                    await self._executive_action(president_seat, action)

                    if self.state.game_over:
                        break

                    # Post-executive discussion — react to what just happened
                    await self._run_discussion(f"post_executive:{action.value}")

            # Reshuffle if needed
            self.state.policy_deck._reshuffle_if_needed(3)

        # --- Game over ---
        self.state.phase = GamePhase.GAME_OVER
        end_data = {
            "winner": self.state.winner.value if self.state.winner else "none",
            "condition": self.state.win_condition.value if self.state.win_condition else "none",
            "rounds": self.state.round_number,
            "roles_revealed": {
                p.name: p.role.value for p in self.state.players
            },
            "final_board": {
                "liberal_policies": self.state.liberal_policies,
                "fascist_policies": self.state.fascist_policies,
            },
        }
        self.log.add(
            round_number=self.state.round_number,
            phase="game_over",
            event_type="game_end",
            data=end_data,
        )
        self._emit("game_end", end_data)

        return self.log
