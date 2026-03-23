from __future__ import annotations

import random

from secret_hitler.models import PolicyType


class PolicyDeck:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.draw_pile: list[PolicyType] = (
            [PolicyType.LIBERAL] * 6 + [PolicyType.FASCIST] * 11
        )
        self._rng.shuffle(self.draw_pile)
        self.discard_pile: list[PolicyType] = []

    def _reshuffle_if_needed(self, minimum: int = 3) -> None:
        if len(self.draw_pile) < minimum:
            self.draw_pile.extend(self.discard_pile)
            self.discard_pile.clear()
            self._rng.shuffle(self.draw_pile)

    def draw(self, count: int = 3) -> list[PolicyType]:
        self._reshuffle_if_needed(count)
        drawn = self.draw_pile[:count]
        self.draw_pile = self.draw_pile[count:]
        return drawn

    def discard(self, policy: PolicyType) -> None:
        self.discard_pile.append(policy)

    def peek_top(self) -> PolicyType:
        self._reshuffle_if_needed(1)
        return self.draw_pile[0]

    def pop_top(self) -> PolicyType:
        self._reshuffle_if_needed(1)
        return self.draw_pile.pop(0)

    @property
    def draw_size(self) -> int:
        return len(self.draw_pile)

    @property
    def discard_size(self) -> int:
        return len(self.discard_pile)
