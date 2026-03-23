"""
Secret Hitler LLM Bench — Run an 8-player game simulation.

Usage:
    python main.py                                    # MockPlayer (random)
    python main.py --seed 42 --games 10               # Multiple seeded games
    python main.py --model anthropic/claude-sonnet-4.6 # LLM-driven game
    python main.py --model deepseek/deepseek-r1-0528 --reasoning  # With reasoning
    python main.py --list-models                      # Show available models
    python main.py --no-discussion                    # Skip discussion phases
    python main.py --output game.jsonl --verbose      # Full log + transcript
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from secret_hitler.arbiter import DiscussionConfig, GameArbiter
from secret_hitler.player import LLMPlayer, MockPlayer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Secret Hitler LLM Bench",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode
    parser.add_argument(
        "--model", type=str, default=None,
        help="OpenRouter model ID (e.g. 'anthropic/claude-sonnet-4.6'). "
             "Omit to use MockPlayer (random choices).",
    )
    parser.add_argument(
        "--list-models", action="store_true",
        help="List all preconfigured models and exit.",
    )

    # Game config
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--games", type=int, default=1, help="Number of games to run")
    parser.add_argument("--no-discussion", action="store_true", help="Skip discussion phases")
    parser.add_argument("--stream", action="store_true", help="Live-print game events as they happen")

    # LLM config
    parser.add_argument(
        "--api-key", type=str, default=None,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var).",
    )
    parser.add_argument(
        "--reasoning", action="store_true",
        help="Enable reasoning/thinking tokens (for supported models).",
    )
    parser.add_argument(
        "--reasoning-effort", type=str, default=None,
        choices=["low", "medium", "high"],
        help="Reasoning effort level.",
    )
    parser.add_argument(
        "--temperature", type=float, default=None,
        help="Sampling temperature (default: 0.7).",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=None,
        help="Max output tokens per LLM call.",
    )
    parser.add_argument(
        "--request-delay", type=float, default=0.5,
        help="Delay between API requests in seconds (default: 0.5, use higher for free models).",
    )

    # Output
    parser.add_argument("--output", type=str, default=None, help="Output JSONL log file")
    parser.add_argument("--verbose", action="store_true", help="Print human-readable transcript")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    return parser.parse_args()


def list_models_and_exit() -> None:
    from secret_hitler.model_config import list_models

    models = list_models()
    print(f"\n{'Model ID':<45} {'Name':<22} {'Ctx':>8} {'Reason':>6} {'JSON':>6} {'Notes'}")
    print("-" * 120)
    for m in models:
        reason = "yes" if m.supports_reasoning else "-"
        json_s = "yes" if m.supports_json_schema else ("obj" if m.supports_json_object else "-")
        ctx = f"{m.context_window // 1000}K"
        print(f"  {m.id:<43} {m.name:<22} {ctx:>8} {reason:>6} {json_s:>6}  {m.notes}")
    print()
    sys.exit(0)


async def run_single_game(
    seed: int | None,
    discussion_config: DiscussionConfig,
    verbose: bool = False,
    stream: bool = False,
    model: str | None = None,
    llm_client=None,
) -> dict:
    # Set up streaming callback
    on_event = None
    if stream:
        from secret_hitler.stream import StreamPrinter
        printer = StreamPrinter(show_reasoning=True)
        on_event = printer.on_event

    if model and llm_client:
        arbiter = GameArbiter(
            player_factory=LLMPlayer,
            seed=seed,
            discussion_config=discussion_config,
            llm_client=llm_client,
            on_event=on_event,
        )
    else:
        arbiter = GameArbiter(
            player_factory=MockPlayer,
            player_factory_kwargs={"seed": seed},
            seed=seed,
            discussion_config=discussion_config,
            on_event=on_event,
        )

    log = await arbiter.run_game()
    summary = log.summary()

    if verbose and not stream:
        print(log.to_readable())
        print()

    return {"summary": summary, "log": log}


async def main() -> None:
    args = parse_args()

    if args.list_models:
        list_models_and_exit()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Build discussion config
    if args.no_discussion:
        disc = DiscussionConfig(enabled=False)
    else:
        disc = DiscussionConfig()

    # Build LLM client if a model is specified
    llm_client = None
    if args.model:
        from secret_hitler.llm_client import OpenRouterClient

        api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("Error: --api-key or OPENROUTER_API_KEY env var required when using --model.")
            sys.exit(1)

        llm_client = OpenRouterClient(
            api_key=api_key,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
            enable_reasoning=args.reasoning,
            request_delay=args.request_delay,
        )

        cfg = llm_client.model_config
        print(f"Model: {cfg.name} ({cfg.id})")
        print(f"  Context: {cfg.context_window // 1000}K | "
              f"Reasoning: {'yes' if cfg.supports_reasoning else 'no'} | "
              f"JSON Schema: {'yes' if cfg.supports_json_schema else 'no'}")
        if args.reasoning and cfg.supports_reasoning:
            effort = args.reasoning_effort or cfg.default_reasoning_effort or "medium"
            print(f"  Reasoning enabled (effort: {effort})")
        print()

    # Run games
    results = []
    wins: dict[str, int] = {"liberal": 0, "fascist": 0}
    conditions: dict[str, int] = {}

    try:
        for i in range(args.games):
            game_seed = (args.seed + i) if args.seed is not None else None
            result = await run_single_game(
                game_seed, disc,
                verbose=args.verbose,
                stream=args.stream,
                model=args.model,
                llm_client=llm_client,
            )
            summary = result["summary"]
            results.append(result)

            winner = summary.get("winner", "none")
            condition = summary.get("win_condition", "none")
            wins[winner] = wins.get(winner, 0) + 1
            conditions[condition] = conditions.get(condition, 0) + 1

            print(
                f"Game {i+1}: {winner.upper()} wins "
                f"via {condition} "
                f"(round {summary.get('rounds', '?')})"
            )

        # Aggregate stats
        if args.games > 1:
            print(f"\n{'='*50}")
            print(f"Results across {args.games} games:")
            for team, count in sorted(wins.items()):
                if count > 0:
                    pct = count / args.games * 100
                    print(f"  {team.upper()}: {count} ({pct:.0f}%)")
            print("Win conditions:")
            for cond, count in sorted(conditions.items()):
                print(f"  {cond}: {count}")

        # LLM usage stats
        if llm_client:
            usage = llm_client.usage_summary()
            print(f"\nLLM Usage:")
            print(f"  Total requests:  {usage['total_requests']}")
            print(f"  Failed requests: {usage['failed_requests']}")
            print(f"  Prompt tokens:   {usage['prompt_tokens']:,}")
            print(f"  Completion:      {usage['completion_tokens']:,}")
            if usage['reasoning_tokens']:
                print(f"  Reasoning:       {usage['reasoning_tokens']:,}")
            print(f"  Total tokens:    {usage['total_tokens']:,}")

    finally:
        if llm_client:
            await llm_client.close()

    # Save log
    if args.output:
        out_path = Path(args.output)
        all_logs = []
        for r in results:
            all_logs.append(r["log"].to_jsonl())
        out_path.write_text("\n---\n".join(all_logs), encoding="utf-8")
        print(f"\nLog saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
