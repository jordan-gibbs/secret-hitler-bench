from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any

from secret_hitler.models import PolicyType, Role, Vote
from secret_hitler.player_view import PlayerView
from secret_hitler.schemas import (
    ChancellorDiscardResponse,
    DiscussionIntentResponse,
    DiscussionResponse,
    ExecutionResponse,
    InvestigateResponse,
    NominationResponse,
    PresidentDiscardResponse,
    SpecialElectionResponse,
    VetoDecisionResponse,
    VetoProposalResponse,
    VoteResponse,
)


class Player(ABC):
    """Abstract interface the arbiter calls for every decision point."""

    def __init__(self, seat: int, name: str, personality: str, role: Role) -> None:
        self.seat = seat
        self.name = name
        self.personality = personality
        self.role = role

    @abstractmethod
    async def nominate_chancellor(
        self, view: PlayerView, eligible: list[str]
    ) -> NominationResponse:
        ...

    @abstractmethod
    async def vote(self, view: PlayerView) -> VoteResponse:
        ...

    @abstractmethod
    async def president_discard(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> PresidentDiscardResponse:
        ...

    @abstractmethod
    async def chancellor_discard(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> ChancellorDiscardResponse:
        ...

    @abstractmethod
    async def chancellor_propose_veto(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> VetoProposalResponse:
        ...

    @abstractmethod
    async def president_respond_to_veto(
        self, view: PlayerView
    ) -> VetoDecisionResponse:
        ...

    @abstractmethod
    async def investigate_loyalty(
        self, view: PlayerView, eligible: list[str]
    ) -> InvestigateResponse:
        ...

    @abstractmethod
    async def call_special_election(
        self, view: PlayerView, eligible: list[str]
    ) -> SpecialElectionResponse:
        ...

    @abstractmethod
    async def execute_player(
        self, view: PlayerView, eligible: list[str]
    ) -> ExecutionResponse:
        ...

    @abstractmethod
    async def discuss(
        self, view: PlayerView, context: str
    ) -> DiscussionResponse:
        ...

    @abstractmethod
    async def discussion_intent(
        self,
        view: PlayerView,
        context: str,
        turn_number: int,
        speakers_this_wave: list[str],
        *,
        is_instigator: bool = False,
        called_out_by: str | None = None,
    ) -> DiscussionIntentResponse:
        ...


class LLMClient(ABC):
    """Abstract LLM service interface. Implement for Anthropic/OpenAI/etc."""

    @abstractmethod
    async def query(
        self,
        system: str,
        messages: list[dict[str, str]],
        user_message: str,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt, get back a JSON string matching response_schema."""
        ...


class LLMPlayer(Player):
    """Player driven by an LLM service."""

    def __init__(
        self,
        seat: int,
        name: str,
        personality: str,
        role: Role,
        llm_client: LLMClient,
        system_prompt: str,
    ) -> None:
        super().__init__(seat, name, personality, role)
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.message_history: list[dict[str, str]] = []
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_calls: int = 0

    async def _query(self, prompt: str, schema: type) -> str:
        response = await self.llm_client.query(
            system=self.system_prompt,
            messages=self.message_history,
            user_message=prompt,
            response_schema=schema.model_json_schema(),
        )
        # Track per-player token usage
        self.total_calls += 1
        self.total_prompt_tokens += getattr(self.llm_client, '_last_prompt_tokens', 0)
        self.total_completion_tokens += getattr(self.llm_client, '_last_completion_tokens', 0)

        # Store a COMPACT version of the prompt in history.
        # Keep critical context lines (danger warnings, confirmed info, next power,
        # action instructions) but strip the full game state dump.
        prompt_lines = prompt.strip().split("\n")
        keep_lines = []
        for line in prompt_lines:
            stripped = line.strip()
            # Keep critical game state warnings
            if any(kw in stripped for kw in [
                "DANGER", "Confirmed NOT Hitler", "Next Fascist policy",
                "DISCUSSION:", "LEGISLATIVE", "EXECUTIVE", "VOTE",
                "Respond with JSON", "Eligible", "nominated", "executed",
                "REMINDER: You are",
            ]):
                keep_lines.append(stripped)
            # Keep the action/schema instruction (last non-JSON lines)
            elif stripped and not stripped.startswith("{") and not stripped.startswith('"'):
                # Check if this is near the end (action instruction)
                idx = prompt_lines.index(line)
                if idx >= len(prompt_lines) - 5:
                    keep_lines.append(stripped)

        compact = "\n".join(keep_lines) if keep_lines else "action"
        self.message_history.append({"role": "user", "content": compact})
        assistant_entry: dict[str, str] = {"role": "assistant", "content": response}
        server_reasoning = getattr(self.llm_client, "last_server_reasoning", None)
        if server_reasoning:
            assistant_entry["reasoning"] = server_reasoning
        self.message_history.append(assistant_entry)
        return response

    async def nominate_chancellor(
        self, view: PlayerView, eligible: list[str]
    ) -> NominationResponse:
        from secret_hitler.prompts import build_nomination_prompt

        prompt = build_nomination_prompt(view, eligible)
        raw = await self._query(prompt, NominationResponse)
        return NominationResponse.model_validate_json(raw)

    async def vote(self, view: PlayerView) -> VoteResponse:
        from secret_hitler.prompts import build_vote_prompt

        prompt = build_vote_prompt(view)
        raw = await self._query(prompt, VoteResponse)
        return VoteResponse.model_validate_json(raw)

    async def president_discard(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> PresidentDiscardResponse:
        from secret_hitler.prompts import build_president_discard_prompt

        prompt = build_president_discard_prompt(view, hand)
        raw = await self._query(prompt, PresidentDiscardResponse)
        return PresidentDiscardResponse.model_validate_json(raw)

    async def chancellor_discard(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> ChancellorDiscardResponse:
        from secret_hitler.prompts import build_chancellor_discard_prompt

        prompt = build_chancellor_discard_prompt(view, hand)
        raw = await self._query(prompt, ChancellorDiscardResponse)
        return ChancellorDiscardResponse.model_validate_json(raw)

    async def chancellor_propose_veto(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> VetoProposalResponse:
        from secret_hitler.prompts import build_veto_proposal_prompt

        prompt = build_veto_proposal_prompt(view, hand)
        raw = await self._query(prompt, VetoProposalResponse)
        return VetoProposalResponse.model_validate_json(raw)

    async def president_respond_to_veto(
        self, view: PlayerView
    ) -> VetoDecisionResponse:
        from secret_hitler.prompts import build_veto_decision_prompt

        prompt = build_veto_decision_prompt(view)
        raw = await self._query(prompt, VetoDecisionResponse)
        return VetoDecisionResponse.model_validate_json(raw)

    async def investigate_loyalty(
        self, view: PlayerView, eligible: list[str]
    ) -> InvestigateResponse:
        from secret_hitler.prompts import build_investigate_prompt

        prompt = build_investigate_prompt(view, eligible)
        raw = await self._query(prompt, InvestigateResponse)
        return InvestigateResponse.model_validate_json(raw)

    async def call_special_election(
        self, view: PlayerView, eligible: list[str]
    ) -> SpecialElectionResponse:
        from secret_hitler.prompts import build_special_election_prompt

        prompt = build_special_election_prompt(view, eligible)
        raw = await self._query(prompt, SpecialElectionResponse)
        return SpecialElectionResponse.model_validate_json(raw)

    async def execute_player(
        self, view: PlayerView, eligible: list[str]
    ) -> ExecutionResponse:
        from secret_hitler.prompts import build_execution_prompt

        prompt = build_execution_prompt(view, eligible)
        raw = await self._query(prompt, ExecutionResponse)
        return ExecutionResponse.model_validate_json(raw)

    async def discuss(
        self, view: PlayerView, context: str
    ) -> DiscussionResponse:
        from secret_hitler.prompts import build_discussion_prompt

        prompt = build_discussion_prompt(view, context)
        raw = await self._query(prompt, DiscussionResponse)
        return DiscussionResponse.model_validate_json(raw)

    async def discussion_intent(
        self,
        view: PlayerView,
        context: str,
        turn_number: int,
        speakers_this_wave: list[str],
        *,
        is_instigator: bool = False,
        called_out_by: str | None = None,
    ) -> DiscussionIntentResponse:
        from secret_hitler.prompts import build_discussion_intent_prompt

        prompt = build_discussion_intent_prompt(
            view, context, turn_number, speakers_this_wave,
            is_instigator=is_instigator,
            called_out_by=called_out_by,
        )
        raw = await self._query(prompt, DiscussionIntentResponse)
        return DiscussionIntentResponse.model_validate_json(raw)


class MockPlayer(Player):
    """Makes random valid choices. Useful for testing the arbiter without an LLM."""

    def __init__(
        self, seat: int, name: str, personality: str, role: Role, seed: int | None = None
    ) -> None:
        super().__init__(seat, name, personality, role)
        self._rng = random.Random(seed)

    async def nominate_chancellor(
        self, view: PlayerView, eligible: list[str]
    ) -> NominationResponse:
        pick = self._rng.choice(eligible)
        return NominationResponse(reasoning="Random pick.", nominee=pick)

    async def vote(self, view: PlayerView) -> VoteResponse:
        v = self._rng.choice(["ja", "nein"])
        return VoteResponse(reasoning="Coin flip.", vote=v)

    async def president_discard(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> PresidentDiscardResponse:
        idx = self._rng.randint(0, len(hand) - 1)
        return PresidentDiscardResponse(reasoning="Random discard.", discard_index=idx)

    async def chancellor_discard(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> ChancellorDiscardResponse:
        idx = self._rng.randint(0, len(hand) - 1)
        return ChancellorDiscardResponse(reasoning="Random discard.", discard_index=idx)

    async def chancellor_propose_veto(
        self, view: PlayerView, hand: list[PolicyType]
    ) -> VetoProposalResponse:
        veto = self._rng.choice([True, False])
        return VetoProposalResponse(reasoning="Maybe veto.", propose_veto=veto)

    async def president_respond_to_veto(
        self, view: PlayerView
    ) -> VetoDecisionResponse:
        accept = self._rng.choice([True, False])
        return VetoDecisionResponse(reasoning="Coin flip.", accept_veto=accept)

    async def investigate_loyalty(
        self, view: PlayerView, eligible: list[str]
    ) -> InvestigateResponse:
        pick = self._rng.choice(eligible)
        return InvestigateResponse(reasoning="Random investigate.", target=pick)

    async def call_special_election(
        self, view: PlayerView, eligible: list[str]
    ) -> SpecialElectionResponse:
        pick = self._rng.choice(eligible)
        return SpecialElectionResponse(reasoning="Random pick.", target=pick)

    async def execute_player(
        self, view: PlayerView, eligible: list[str]
    ) -> ExecutionResponse:
        pick = self._rng.choice(eligible)
        return ExecutionResponse(reasoning="Random execution.", target=pick)

    async def discuss(
        self, view: PlayerView, context: str
    ) -> DiscussionResponse:
        msgs = [
            "Interesting round so far.",
            "I think we should be careful here.",
            "Let's just see what happens.",
            "I have a good feeling about this.",
            "Something feels off to me.",
        ]
        return DiscussionResponse(message=self._rng.choice(msgs))

    async def discussion_intent(
        self,
        view: PlayerView,
        context: str,
        turn_number: int,
        speakers_this_wave: list[str],
        *,
        is_instigator: bool = False,
        called_out_by: str | None = None,
    ) -> DiscussionIntentResponse:
        # Called out? High chance to respond. Instigator? Moderate. Otherwise low.
        if called_out_by:
            speak_prob = 0.7
        elif is_instigator:
            speak_prob = 0.5
        else:
            speak_prob = max(0.1, 0.3 - (turn_number * 0.03))

        if self._rng.random() < speak_prob:
            # Sometimes direct at a random other player
            alive_names = [
                p["name"] for p in view.players
                if p["is_alive"] and p["name"] != view.your_name
            ]
            directed_at = None
            if self._rng.random() < 0.3 and alive_names:
                directed_at = self._rng.choice(alive_names)

            msgs = [
                "Something about that doesn't add up.",
                "I think we should be careful here.",
                "I have a good feeling about this government.",
                "That policy result was suspicious.",
                "I don't trust the last government.",
                "Can we talk about what just happened?",
                "I'm watching and I have concerns.",
            ]
            return DiscussionIntentResponse(
                inner_thought="Mock player thinking...",
                ready_to_proceed=turn_number > 2,
                want_to_speak=True,
                directed_at=directed_at,
                message=self._rng.choice(msgs),
            )
        return DiscussionIntentResponse(
            inner_thought="Nothing to say right now.",
            ready_to_proceed=True,
            want_to_speak=False, directed_at=None, message=None,
        )
