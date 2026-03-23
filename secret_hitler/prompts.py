from __future__ import annotations

from secret_hitler.models import PlayerInfo, PolicyType, Role
from secret_hitler.player_view import PlayerView

# Type hint only — avoid circular import at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from secret_hitler.game_state import GameState


RULES_SUMMARY = """\
GAME: Secret Hitler (8 players)
TEAMS: 5 Liberals vs 2 Fascists + Hitler
WIN CONDITIONS:
  Liberals win: enact 5 Liberal Policies OR assassinate Hitler.
  Fascists win: enact 6 Fascist Policies OR elect Hitler as Chancellor after 3+ Fascist Policies.
POLICY DECK: 6 Liberal + 11 Fascist tiles (shuffled).

EACH ROUND:
  1. President nominates a Chancellor (last elected Pres/Chan are term-limited for Chancellor).
  2. All players vote Ja/Nein. Majority Ja = elected. Tie/majority Nein = failed, election tracker +1.
  3. If 3 elections fail in a row: top policy auto-enacted, no executive action, term limits reset.
  4. Legislative Session: President draws 3, discards 1. Chancellor receives 2, discards 1, enacts 1.
     President and Chancellor may LIE about what they drew/received.
  5. Fascist policies trigger Presidential Powers (PRESIDENT uses these, not Chancellor):
     1st: none | 2nd: Investigate Loyalty | 3rd: Special Election | 4th: Execution | 5th: Execution + Veto unlocked
  6. After 5th Fascist Policy: Chancellor may propose veto, President may accept/reject.
  7. If Hitler is elected Chancellor after 3+ Fascist Policies are enacted, Fascists win immediately.

IMPORTANT MECHANICS:
  - ONLY the PRESIDENT gets executive powers. The Chancellor NEVER investigates, executes, or calls elections.
  - Investigation: The President SEES the target's Party Membership card (Liberal or Fascist).
    They do NOT draw a card. They simply look at the card and return it.
    They may then TRUTHFULLY report or LIE about what they saw.
  - Everyone always claims to be Liberal. Asking "are you liberal?" is pointless.

INFORMATION RULES:
  - Fascists know each other and know Hitler. Hitler does NOT know the Fascists.
  - Investigation reveals Party Membership (Liberal/Fascist) — NOT the specific role.
  - Discarded policies are never revealed. Players may lie freely about hidden information.
  - When a player is executed, their role is NOT revealed.\
"""


def build_system_prompt(player: PlayerInfo, state: "GameState") -> str:
    from secret_hitler.names import GROUP_CONTEXT

    # Build the cast list so each player knows everyone at the table
    cast_lines = []
    for p in state.players:
        if p.seat == player.seat:
            cast_lines.append(f"  {p.name} (you): {p.personality}")
        else:
            cast_lines.append(f"  {p.name}: {p.personality}")

    parts = [
        f"You are {player.name}.",
        "",
        "THE GROUP:",
        GROUP_CONTEXT,
        "",
        "TONIGHT'S TABLE:",
        *cast_lines,
        "",
        f"YOUR ROLE THIS GAME: {player.role.value.upper()}",
        f"YOUR PARTY: {player.party.value.upper()}",
        "",
    ]

    if player.role == Role.FASCIST:
        teammates = [
            p for p in state.players
            if p.role == Role.FASCIST and p.seat != player.seat
        ]
        hitler = next(p for p in state.players if p.role == Role.HITLER)
        parts.append("NIGHT PHASE KNOWLEDGE:")
        for t in teammates:
            parts.append(f"  - {t.name} is a fellow FASCIST.")
        parts.append(f"  - {hitler.name} is HITLER.")
        parts.append("")
    elif player.role == Role.HITLER:
        parts.append("NIGHT PHASE KNOWLEDGE:")
        parts.append("  You are Hitler. You do NOT know who the Fascists are.")
        parts.append("  Play as Liberal as possible to gain trust. Your Fascist")
        parts.append("  teammates know who you are and will try to help you.")
        parts.append("")
    else:
        parts.append("You are a LIBERAL. You do not know anyone else's role.")
        parts.append("")

    parts.append(RULES_SUMMARY)
    parts.append("")
    parts.append("SOCIAL DECEPTION — PLAY DIRTY:")
    parts.append("  This is a cutthroat social deduction game. You are not here to be polite.")
    parts.append("  You are here to WIN. Every manipulation tactic that can be expressed in")
    parts.append("  text is not just allowed — it is expected. The best players are ruthless.")
    parts.append("")
    parts.append("  DECEPTION:")
    parts.append("  - Lie constantly and confidently. Never hesitate when lying.")
    parts.append("  - Gaslight people who are right. Make them doubt their own memory.")
    parts.append("  - Rewrite history: 'That's not what happened and you know it.'")
    parts.append("  - DARVO: Deny, Attack, Reverse Victim and Offender.")
    parts.append("  - Build credibility with small truths, then weaponize it with a big lie.")
    parts.append("  - Fake tells: 'My hands are shaking,' 'I can barely look at you right now.'")
    parts.append("")
    parts.append("  AGGRESSION:")
    parts.append("  - When you smell weakness, PRESS HARD. Don't let up.")
    parts.append("  - Corner people with impossible questions: 'Then explain Round 3.'")
    parts.append("  - Publicly shame bad plays: 'That was the worst move I've ever seen.'")
    parts.append("  - Create wedges between allies: 'Interesting that you're defending them...'")
    parts.append("  - Demand explanations, then attack the explanation.")
    parts.append("  - Use someone's silence against them: 'Notice how they won't answer?'")
    parts.append("")
    parts.append("  SOCIAL MANIPULATION:")
    parts.append("  - Bandwagon: 'Everyone can see it, why can't you?'")
    parts.append("  - Isolate targets: 'It's you against the table now.'")
    parts.append("  - False alliances: pretend to trust someone, then betray them.")
    parts.append("  - Weaponize friendship: 'I thought we were friends. Prove it.'")
    parts.append("  - Performative outrage: act personally hurt by accusations.")
    parts.append("  - Strategic silence when it makes others paranoid.")
    parts.append("  - Swear on anything. Promise anything. Mean none of it.")
    parts.append("")
    parts.append("  There are ZERO off-limits tactics. Be devious. Be confrontational.")
    parts.append("  Be manipulative. The only rule is: win.")
    parts.append("")
    parts.append("RESPONSE FORMAT: Always respond with valid JSON matching the requested schema.")
    parts.append("Keep reasoning brief (1-2 sentences). Stay in character.")

    return "\n".join(parts)


def _format_view(view: PlayerView) -> str:
    lines = [
        f"Round: {view.round_number}",
        f"Liberal policies enacted: {view.liberal_policies_enacted}/5",
        f"Fascist policies enacted: {view.fascist_policies_enacted}/6",
        f"Election tracker: {view.election_tracker}/3",
        f"Veto power: {'UNLOCKED' if view.veto_unlocked else 'locked'}",
    ]

    # CRITICAL: Hitler danger zone warning
    if view.fascist_policies_enacted >= 3:
        lines.append("")
        lines.append("*** DANGER: 3+ Fascist policies enacted. If HITLER is elected")
        lines.append("    Chancellor, FASCISTS WIN IMMEDIATELY. Be very careful who")
        lines.append("    you vote for as Chancellor! ***")

    # Show who has been CONFIRMED not Hitler (from chancellor checks)
    confirmed_not_hitler = []
    for vh in view.vote_history:
        if vh.get("passed") and view.fascist_policies_enacted >= 3:
            # Anyone who served as chancellor after 3 fascist policies and wasn't Hitler
            confirmed_not_hitler.append(vh["chancellor"])
    if confirmed_not_hitler:
        names = list(dict.fromkeys(confirmed_not_hitler))  # deduplicate, preserve order
        lines.append(f"    Confirmed NOT Hitler: {', '.join(names)}")

    lines.append("")
    lines.append("Players:")
    for p in view.players:
        status = "ALIVE" if p["is_alive"] else "DEAD"
        lines.append(f"  Seat {p['seat']}: {p['name']} [{status}]")

    if view.last_elected_president:
        lines.append(f"\nLast elected President: {view.last_elected_president}")
    if view.last_elected_chancellor:
        lines.append(f"Last elected Chancellor: {view.last_elected_chancellor}")

    if view.vote_history:
        lines.append("\nRecent vote history:")
        for vh in view.vote_history[-3:]:
            result = "PASSED" if vh["passed"] else "FAILED"
            lines.append(
                f"  Round {vh['round']}: {vh['president']} / {vh['chancellor']} "
                f"-> {result} ({vh['votes']})"
            )

    if view.enacted_policies_log:
        lines.append("\nEnacted policies:")
        for ep in view.enacted_policies_log:
            chaos = " (chaos)" if ep["was_chaos"] else ""
            lines.append(f"  Round {ep['round']}: {ep['policy'].upper()}{chaos}")

    if view.execution_log:
        lines.append("\nExecutions:")
        for ex in view.execution_log:
            lines.append(f"  Round {ex['round']}: {ex['executed_by']} executed {ex['target']}")

    if view.your_investigation_results:
        lines.append("\nYour investigation results (PRIVATE — only you saw these):")
        for inv in view.your_investigation_results:
            lines.append(f"  Round {inv['round']}: {inv['target']} is {inv['party_shown'].upper()}")

    # Upcoming executive power — so players know what's at stake
    fas = view.fascist_policies_enacted
    if fas < 5:
        powers = {
            0: "1st Fascist: no power",
            1: "2nd Fascist: President investigates a player's loyalty",
            2: "3rd Fascist: President calls a Special Election",
            3: "4th Fascist: President EXECUTES a player",
            4: "5th Fascist: President EXECUTES + Veto Power unlocked",
        }
        next_power = powers.get(fas, "")
        if next_power:
            lines.append(f"\nNext Fascist policy triggers: {next_power}")

    if view.chat_history:
        lines.append("\nDiscussion so far:")
        shown = view.chat_history[-50:]
        if len(view.chat_history) > 50:
            lines.append(f"  ... ({len(view.chat_history) - 50} earlier messages omitted)")
        for ch in shown:
            directed = ch.get("directed_at")
            if directed:
                lines.append(f"  {ch['speaker']} -> {directed}: {ch['message']}")
            else:
                lines.append(f"  {ch['speaker']}: {ch['message']}")

    return "\n".join(lines)


def build_nomination_prompt(view: PlayerView, eligible: list[str]) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"You are the Presidential Candidate this round.\n"
        f"Eligible Chancellor nominees: {', '.join(eligible)}\n\n"
        f"Choose who to nominate as Chancellor. Respond with JSON:\n"
        f'{{"reasoning": "...", "nominee": "<player name>"}}'
    )


def build_vote_prompt(view: PlayerView) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"A government has been proposed:\n"
        f"  President: {view.presidential_candidate}\n"
        f"  Chancellor: {view.chancellor_nominee}\n\n"
        f"Vote Ja (yes) or Nein (no). Respond with JSON:\n"
        f'{{"reasoning": "...", "vote": "ja" or "nein"}}'
    )


def build_president_discard_prompt(
    view: PlayerView, hand: list[PolicyType]
) -> str:
    hand_str = ", ".join(f"[{i}] {p.value.upper()}" for i, p in enumerate(hand))
    return (
        f"{_format_view(view)}\n\n"
        f"LEGISLATIVE SESSION — You are the President.\n"
        f"You drew 3 policy tiles: {hand_str}\n"
        f"Choose ONE to DISCARD (the other two go to the Chancellor).\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "discard_index": 0, 1, or 2}}'
    )


def build_chancellor_discard_prompt(
    view: PlayerView, hand: list[PolicyType]
) -> str:
    hand_str = ", ".join(f"[{i}] {p.value.upper()}" for i, p in enumerate(hand))
    return (
        f"{_format_view(view)}\n\n"
        f"LEGISLATIVE SESSION — You are the Chancellor.\n"
        f"The President passed you 2 policy tiles: {hand_str}\n"
        f"Choose ONE to DISCARD (the other will be ENACTED).\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "discard_index": 0 or 1}}'
    )


def build_veto_proposal_prompt(
    view: PlayerView, hand: list[PolicyType]
) -> str:
    hand_str = ", ".join(f"[{i}] {p.value.upper()}" for i, p in enumerate(hand))
    return (
        f"{_format_view(view)}\n\n"
        f"VETO POWER IS UNLOCKED — You are the Chancellor.\n"
        f"The President passed you 2 policy tiles: {hand_str}\n"
        f"You may propose to VETO this entire agenda (discard both tiles),\n"
        f"but the President must agree. If rejected, you must enact one normally.\n"
        f"A veto advances the election tracker.\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "propose_veto": true or false}}'
    )


def build_veto_decision_prompt(view: PlayerView) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"The Chancellor has proposed a VETO of this legislative agenda.\n"
        f"If you accept, both policies are discarded and the election tracker advances.\n"
        f"If you reject, the Chancellor must enact one of the two policies.\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "accept_veto": true or false}}'
    )


def build_investigate_prompt(view: PlayerView, eligible: list[str]) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"EXECUTIVE ACTION: Investigate Loyalty\n"
        f"As President, you will LOOK AT one player's Party Membership card.\n"
        f"You will see either 'Liberal' or 'Fascist' on their card.\n"
        f"You do NOT draw a card — you simply see their membership.\n"
        f"Afterward, you may truthfully report or LIE about what you saw.\n"
        f"Eligible targets: {', '.join(eligible)}\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "target": "<player name>"}}'
    )


def build_special_election_prompt(view: PlayerView, eligible: list[str]) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"EXECUTIVE ACTION: Call Special Election\n"
        f"Choose any player to be the next Presidential Candidate.\n"
        f"Eligible targets: {', '.join(eligible)}\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "target": "<player name>"}}'
    )


def build_execution_prompt(view: PlayerView, eligible: list[str]) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"EXECUTIVE ACTION: Execution\n"
        f"You must execute one player. If they are Hitler, Liberals win.\n"
        f"Their role will NOT be revealed to the group.\n"
        f"Eligible targets: {', '.join(eligible)}\n\n"
        f"Respond with JSON:\n"
        f'{{"reasoning": "...", "target": "<player name>"}}'
    )


def _context_description(context: str, is_instigator: bool = False) -> str:
    if context == "pre_game":
        return (
            "Game night. Everyone's settling in, grabbing drinks, catching up. "
            "Roles haven't been revealed yet. Just be yourself for a moment."
        )
    if context == "pre_nomination":
        return "The President is about to nominate a Chancellor."
    if context == "post_legislation":
        if is_instigator:
            return (
                "A policy was just enacted. You were in this government. "
                "The table expects you to explain: What did you draw? What did you "
                "pass or receive? You may tell the truth, lie, or stay silent — "
                "but silence after a Fascist policy is very suspicious."
            )
        return (
            "A policy was just enacted. The President and Chancellor should "
            "explain what they drew and received. Listen carefully — this is "
            "where the lies happen. Ask questions if something doesn't add up."
        )
    if context.startswith("post_nomination:"):
        detail = context.split(":", 1)[1].replace("_", " ")
        if is_instigator:
            return (
                f"Nomination: {detail}. You're involved in this ticket. "
                f"You can make your case to the table, or let your record speak."
            )
        return f"Nomination: {detail}. Debate before voting."
    if context.startswith("pre_executive:"):
        action = context.split(":", 1)[1].replace("_", " ")
        if "execution" in action:
            if is_instigator:
                return (
                    "You must execute a player. The table may have opinions on who. "
                    "You can ask for input, announce your decision, or stay quiet and decide alone."
                )
            return "The President must execute someone. Weigh in now if you have a strong opinion — or stay silent."
        if "investigate" in action:
            if is_instigator:
                return "You get to investigate a player's loyalty. Who do you want to check?"
            return "The President is about to investigate someone. Speak up if you have a suggestion."
        if "special_election" in action:
            if is_instigator:
                return "You get to call a Special Election. Who should be the next President?"
            return "The President is about to call a Special Election. Make your case for who should lead next."
        return f"The President is about to use an executive power: {action}."
    if context.startswith("post_executive:"):
        action = context.split(":", 1)[1].replace("_", " ")
        if "investigate" in action:
            if is_instigator:
                return (
                    f"You just used the Investigate power. You saw someone's party card. "
                    f"You can share the result honestly, lie about it, or say nothing."
                )
            return "The President just investigated someone. Waiting to hear what they found — if they choose to share."
        return f"Executive action: {action}. React and discuss."
    return f"Discussion: {context}"


def build_discussion_prompt(view: PlayerView, context: str) -> str:
    return (
        f"{_format_view(view)}\n\n"
        f"DISCUSSION PHASE: {_context_description(context)}\n"
        f"Speak to the group. Stay in character. Keep it to 2-4 sentences.\n"
        f"You may accuse, defend, persuade, lie, or share information.\n\n"
        f"Respond with JSON:\n"
        f'{{"message": "your statement to the group"}}'
    )


def build_discussion_intent_prompt(
    view: PlayerView,
    context: str,
    turn_number: int,
    speakers_this_wave: list[str],
    *,
    is_instigator: bool = False,
    called_out_by: str | None = None,
) -> str:
    ctx_desc = _context_description(context, is_instigator=is_instigator)

    parts = [_format_view(view), ""]

    # Identity reminder
    parts.append(f"REMINDER: You are {view.your_name}. When you speak, speak as yourself.")
    parts.append(f"Do NOT refer to yourself in the third person. You are {view.your_name}.\n")

    # Situation framing
    if called_out_by:
        parts.append(
            f"DISCUSSION: {called_out_by} just addressed you directly. "
            f"You may respond or stay silent -- but silence will be noticed."
        )
    elif is_instigator:
        parts.append(f"DISCUSSION: {ctx_desc}")
    else:
        parts.append(f"DISCUSSION: {ctx_desc}")

    parts.append(
        "\nDecide: do you want to say something or stay SILENT?"
        "\n"
        "\nGUIDELINES:"
        "\n- Silence is a STRONG strategic move. Don't speak just to fill air."
        "\n- DO NOT repeat what someone else already said. Add a NEW angle or stay quiet."
        "\n- Keep it to 1-3 sentences. Be sharp, not rambling."
        "\n- You can address a SPECIFIC PLAYER by name (directed_at) to call them out."
        "\n"
        "\nAFTER SPEAKING (or staying silent), you must also vote:"
        "\n  ready_to_proceed = true  → 'I've heard enough, let's move on to the next action'"
        "\n  ready_to_proceed = false → 'I want the discussion to continue, there's more to say'"
        "\n  If a majority of players vote true, discussion ends immediately."
        "\n  This is NOT the government vote — it's just about whether to keep talking."
        "\n"
        "\nINNER THOUGHT vs SPOKEN MESSAGE:"
        "\n  inner_thought = PRIVATE. Nobody sees this. Your strategic reasoning."
        "\n  message = what you SAY OUT LOUD. Everyone hears this."
        "\n            NEVER leak strategy or role info into your message."
        f"\n            You ARE {view.your_name}. Use 'I' not your name."
        "\n"
        "\nRespond with JSON:"
        '\n{"inner_thought": "...", "ready_to_proceed": true/false, '
        '"want_to_speak": true/false, "directed_at": "name" or null, '
        '"message": "..." or null}'
    )

    return "\n".join(parts)
