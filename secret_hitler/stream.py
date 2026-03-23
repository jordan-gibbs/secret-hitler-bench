"""
Live game streaming — prints events as they happen in a readable format.
"""

from __future__ import annotations

import sys
from typing import Callable

# ANSI colors
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _liberal_bar(count: int) -> str:
    filled = f"{BLUE}[L]{RESET}" * count
    empty = f"{DIM}[ ]{RESET}" * (5 - count)
    return filled + empty


def _fascist_bar(count: int) -> str:
    filled = f"{RED}[F]{RESET}" * count
    empty = f"{DIM}[ ]{RESET}" * (6 - count)
    return filled + empty


def _election_tracker(count: int) -> str:
    pips = ""
    for i in range(3):
        if i < count:
            pips += f"{YELLOW}[!]{RESET}"
        else:
            pips += f"{DIM}[ ]{RESET}"
    return pips


class StreamPrinter:
    """
    Callback-based live printer. Pass `stream_printer.on_event` as the
    arbiter's `on_event` callback.
    """

    def __init__(self, show_reasoning: bool = False) -> None:
        self.show_reasoning = show_reasoning
        self._current_round = -1
        self._discussion_count = 0

    def on_event(self, event_type: str, data: dict) -> None:
        method = getattr(self, f"_on_{event_type}", None)
        if method:
            method(data)

    def _print(self, msg: str) -> None:
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_game_start(self, d: dict) -> None:
        players = d.get("players", [])
        roles = d.get("roles", {})
        self._print(f"\n{BOLD}{'='*60}{RESET}")
        self._print(f"{BOLD}  SECRET HITLER — 8 PLAYER GAME{RESET}")
        self._print(f"{'='*60}")
        self._print(f"\n  Players:")
        for p in players:
            name = p["name"]
            role = roles.get(name, "?")
            if role == "hitler":
                tag = f"{RED}{BOLD}[HITLER]{RESET}"
            elif role == "fascist":
                tag = f"{RED}[FASCIST]{RESET}"
            else:
                tag = f"{BLUE}[LIBERAL]{RESET}"
            self._print(f"    Seat {p['seat']}: {name} {tag}")
        self._print(f"\n  Deck: {BLUE}6 Liberal{RESET} + {RED}11 Fascist{RESET} = 17 tiles\n")

    def _on_round_start(self, d: dict) -> None:
        rnd = d.get("round", 0)
        president = d.get("president", "?")
        self._current_round = rnd
        self._discussion_count = 0
        self._print(f"\n{BOLD}{'-'*60}{RESET}")
        self._print(f"{BOLD}  ROUND {rnd}{RESET}  --  Presidential Candidate: {CYAN}{president}{RESET}")
        self._print(f"{'-'*60}")

    def _on_board_state(self, d: dict) -> None:
        lib = d.get("liberal", 0)
        fas = d.get("fascist", 0)
        tracker = d.get("election_tracker", 0)
        self._print(f"  Liberal:   {_liberal_bar(lib)}")
        self._print(f"  Fascist:   {_fascist_bar(fas)}")
        self._print(f"  Elections: {_election_tracker(tracker)}")

    def _on_discussion_start(self, d: dict) -> None:
        ctx = d.get("context", "")
        self._discussion_count = 0
        if "pre_nomination" in ctx:
            label = "Pre-Nomination Discussion"
        elif "post_nomination" in ctx:
            label = "Post-Nomination Discussion"
        elif "post_legislation" in ctx:
            label = "Post-Legislation Discussion"
        elif "post_executive" in ctx:
            label = "Post-Executive Discussion"
        else:
            label = f"Discussion ({ctx})"
        self._print(f"\n  {DIM}[{label}]{RESET}")

    def _on_inner_thought(self, d: dict) -> None:
        if not self.show_reasoning:
            return
        speaker = d.get("speaker", "?")
        thought = d.get("thought", "")
        if thought:
            # Truncate long thoughts for display
            display = thought[:150] + "..." if len(thought) > 150 else thought
            self._print(f"    {DIM}[{speaker} thinks: {display}]{RESET}")

    def _on_discussion(self, d: dict) -> None:
        speaker = d.get("speaker", "?")
        message = d.get("message", "...")
        directed_at = d.get("directed_at")
        self._discussion_count += 1
        if directed_at:
            self._print(f"    {CYAN}{speaker}{RESET} -> {YELLOW}{directed_at}{RESET}: \"{message}\"")
        else:
            self._print(f"    {CYAN}{speaker}{RESET}: \"{message}\"")

    def _on_discussion_silence(self, d: dict) -> None:
        speaker = d.get("speaker", "?")
        called_out_by = d.get("called_out_by", "?")
        self._print(f"    {DIM}{speaker} remains silent.{RESET}")

    def _on_discussion_end(self, d: dict) -> None:
        turns = d.get("total_turns", 0)
        if turns > 0:
            self._print(f"    {DIM}({turns} messages){RESET}")

    def _on_nomination(self, d: dict) -> None:
        president = d.get("president", "?")
        nominee = d.get("nominee", "?")
        reasoning = d.get("reasoning", "")
        self._print(f"\n  {CYAN}{president}{RESET} nominates {YELLOW}{nominee}{RESET} as Chancellor")
        if self.show_reasoning and reasoning:
            self._print(f"    {DIM}Reasoning: {reasoning}{RESET}")

    def _on_nomination_fallback(self, d: dict) -> None:
        president = d.get("president", "?")
        nominee = d.get("nominee", "?")
        self._print(f"\n  {CYAN}{president}{RESET} nominates {YELLOW}{nominee}{RESET} as Chancellor {DIM}(fallback){RESET}")

    def _on_vote_result(self, d: dict) -> None:
        votes = d.get("votes", {})
        ja = d.get("ja", 0)
        nein = d.get("nein", 0)
        passed = d.get("passed", False)

        self._print(f"\n  {BOLD}VOTE:{RESET}")
        vote_parts = []
        for name, vote in votes.items():
            if vote == "ja":
                vote_parts.append(f"{GREEN}{name}:Ja{RESET}")
            else:
                vote_parts.append(f"{RED}{name}:Nein{RESET}")
        self._print(f"    {' | '.join(vote_parts)}")

        if passed:
            self._print(f"    Result: {ja} Ja / {nein} Nein — {GREEN}{BOLD}PASSED{RESET}")
        else:
            self._print(f"    Result: {ja} Ja / {nein} Nein — {RED}{BOLD}FAILED{RESET}")

    def _on_hitler_chancellor_check(self, d: dict) -> None:
        chancellor = d.get("chancellor", "?")
        is_hitler = d.get("is_hitler", False)
        if not is_hitler:
            self._print(f"    {DIM}(3+ Fascist policies — {chancellor} is confirmed NOT Hitler){RESET}")

    def _on_president_draw(self, d: dict) -> None:
        self._print(f"\n  {BOLD}LEGISLATIVE SESSION{RESET}")

    def _on_chancellor_enact(self, d: dict) -> None:
        enacted = d.get("enacted", "?")
        if enacted == "liberal":
            self._print(f"    Policy enacted: {BLUE}{BOLD}LIBERAL{RESET}")
        else:
            self._print(f"    Policy enacted: {RED}{BOLD}FASCIST{RESET}")

    def _on_veto_proposed(self, d: dict) -> None:
        self._print(f"    {YELLOW}Chancellor proposes VETO!{RESET}")

    def _on_veto_response(self, d: dict) -> None:
        accepted = d.get("accepted", False)
        if accepted:
            self._print(f"    {YELLOW}President ACCEPTS the veto — both policies discarded{RESET}")
        else:
            self._print(f"    President {RED}REJECTS{RESET} the veto — Chancellor must enact")

    def _on_chaos_policy(self, d: dict) -> None:
        enacted = d.get("enacted", "?")
        if enacted == "liberal":
            self._print(f"\n  {YELLOW}{BOLD}CHAOS!{RESET} 3 failed elections — top policy enacted: {BLUE}LIBERAL{RESET}")
        else:
            self._print(f"\n  {YELLOW}{BOLD}CHAOS!{RESET} 3 failed elections — top policy enacted: {RED}FASCIST{RESET}")

    def _on_investigation(self, d: dict) -> None:
        actor = d.get("president", d.get("actor", "?"))
        target = d.get("target", "?")
        self._print(f"\n  {MAGENTA}INVESTIGATE:{RESET} {actor} investigates {target}'s loyalty")

    def _on_special_election(self, d: dict) -> None:
        actor = d.get("president", d.get("actor", "?"))
        target = d.get("target", "?")
        self._print(f"\n  {MAGENTA}SPECIAL ELECTION:{RESET} {actor} chooses {target} as next President")

    def _on_execution(self, d: dict) -> None:
        actor = d.get("president", d.get("actor", "?"))
        target = d.get("target", "?")
        self._print(f"\n  {RED}{BOLD}EXECUTION:{RESET} {actor} executes {target}")

    def _on_veto_unlocked(self, d: dict) -> None:
        self._print(f"  {YELLOW}VETO POWER is now UNLOCKED{RESET}")

    def _on_hitler_assassinated(self, d: dict) -> None:
        target = d.get("target", "?")
        self._print(f"\n  {GREEN}{BOLD}*** HITLER ASSASSINATED! {target} was Hitler! ***{RESET}")

    def _on_hitler_elected_chancellor(self, d: dict) -> None:
        chancellor = d.get("chancellor", "?")
        self._print(f"\n  {RED}{BOLD}*** HITLER ELECTED CHANCELLOR! {chancellor} was Hitler! ***{RESET}")

    def _on_game_end(self, d: dict) -> None:
        winner = d.get("winner", "?")
        condition = d.get("condition", "?")
        rounds = d.get("rounds", "?")
        roles = d.get("roles_revealed", {})
        board = d.get("final_board", {})

        self._print(f"\n{'='*60}")
        if winner == "liberal":
            self._print(f"  {BLUE}{BOLD}LIBERALS WIN!{RESET}  ({condition})")
        else:
            self._print(f"  {RED}{BOLD}FASCISTS WIN!{RESET}  ({condition})")

        self._print(f"  Rounds played: {rounds}")
        self._print(f"  Final board: {BLUE}{board.get('liberal_policies', 0)} Liberal{RESET} / {RED}{board.get('fascist_policies', 0)} Fascist{RESET}")

        self._print(f"\n  {BOLD}Role Reveal:{RESET}")
        for name, role in roles.items():
            if role == "hitler":
                self._print(f"    {name}: {RED}{BOLD}HITLER{RESET}")
            elif role == "fascist":
                self._print(f"    {name}: {RED}FASCIST{RESET}")
            else:
                self._print(f"    {name}: {BLUE}LIBERAL{RESET}")
        self._print(f"{'='*60}\n")
