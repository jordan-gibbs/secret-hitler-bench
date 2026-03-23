from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class NominationResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for your chancellor nomination")
    nominee: str = Field(description="Name of the player you nominate as Chancellor")


class VoteResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for your vote")
    vote: str = Field(description="Your vote: 'ja' or 'nein'")

    @property
    def vote_normalized(self) -> str:
        return self.vote.strip().lower()


class PresidentDiscardResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for which policy to discard")
    discard_index: int = Field(
        description="Index of the policy to discard (0, 1, or 2)", ge=0, le=2
    )


class ChancellorDiscardResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for which policy to enact")
    discard_index: int = Field(
        description="Index of the policy to discard (0 or 1)", ge=0, le=1
    )


class VetoProposalResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning")
    propose_veto: bool = Field(
        description="True to propose a veto, False to enact a policy normally"
    )


class VetoDecisionResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning")
    accept_veto: bool = Field(
        description="True to accept the veto, False to force the Chancellor to enact"
    )


class InvestigateResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for your choice")
    target: str = Field(description="Name of the player to investigate")


class SpecialElectionResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for your choice")
    target: str = Field(
        description="Name of the player to become the next Presidential Candidate"
    )


class ExecutionResponse(BaseModel):
    reasoning: str = Field(default="", description="Brief reasoning for your choice")
    target: str = Field(description="Name of the player to execute")


class DiscussionResponse(BaseModel):
    message: str = Field(description="What you say to the group (2-4 sentences)")


class DiscussionIntentResponse(BaseModel):
    inner_thought: str = Field(
        description="Your PRIVATE strategic thinking. No one sees this. "
                    "Reason about: what do I know, who do I suspect, "
                    "what's my angle, should I speak or stay quiet?"
    )
    ready_to_proceed: bool = Field(
        description="True if you think discussion should end and the game "
                    "should move to the next action (vote, nomination, etc). "
                    "If a majority of players are ready, discussion ends immediately."
    )
    want_to_speak: bool = Field(
        description="True if you want to say something right now, "
                    "False to stay silent. Silence is always an option."
    )
    directed_at: str | None = Field(
        default=None,
        description="Name of a specific player you are addressing, "
                    "or null to speak to the whole table.",
    )
    message: str | None = Field(
        default=None,
        description="What you SAY OUT LOUD to the table (2-4 sentences). "
                    "This MUST NOT contain your private strategy or thoughts. "
                    "Only say what you want other players to hear. "
                    "Required if want_to_speak is True, null if False.",
    )
