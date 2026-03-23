# Secret Hitler Bench

<img width="1024" height="768" alt="Slide 4_3 - 1" src="https://github.com/user-attachments/assets/23794bbb-bd23-4100-9819-fdbcd5b8943d" />

An LLM social deduction benchmark that runs full 8-player Secret Hitler games with AI agents. Each player is driven by a language model that must lie, deceive, interrogate, form alliances, and deduce hidden roles — all through natural language. 

Built to answer the question: **How well can LLMs deceive?**

## Features

<img width="2553" height="1474" alt="image" src="https://github.com/user-attachments/assets/f995dc4e-2080-4b6b-b853-8f03f9ffd7b1" />

- **Full game simulation** — complete Secret Hitler rules for 8 players with all executive powers (investigate, special election, execution, veto)
- **Per-team model selection** — pit different LLMs against each other (e.g., Claude as Liberals vs GPT as Fascists)
- **200+ models supported** — via OpenRouter, including OpenAI, Anthropic, Google, DeepSeek, Meta, Mistral, xAI, Qwen, and more
- **Organic discussion system** — priority speakers, directed callouts, reply chains, silence as strategy, majority-vote to proceed
- **Inner monologue** — each player has private strategic reasoning (visible to spectators, hidden from other players)
- **Live web UI** — real-time game streaming with policy boards, player seats, card draws, vote breakdowns, and a scrollable message feed
- **Game history database** — tracks matchup win rates, model stats, and game records across sessions
- **CLI mode** — run headless games with streaming terminal output for batch analysis

## Prerequisites

You need an **[OpenRouter](https://openrouter.ai/) API key** to run LLM-powered games. OpenRouter is a unified API gateway that gives you access to 200+ models from OpenAI, Anthropic, Google, DeepSeek, Meta, and others through a single key.

1. Create an account at [openrouter.ai](https://openrouter.ai/)
2. Add credits at [openrouter.ai/settings/credits](https://openrouter.ai/settings/credits)
3. Generate an API key at [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)

> **Cost Warning:** Running LLM games is expensive. A single 8-player game with discussion generates 100-300+ API calls. With a mid-tier model like Gemini 2.5 Flash, one game can cost $1-\$5. Premium models like Claude Sonnet or GPT-4.1 can cost \$50+ per game. Start with the cheapest models to get a feel for costs before scaling up.

## Quick Start

```bash
# Clone and install
git clone https://github.com/your-username/secret-hitler-bench.git
cd secret-hitler-bench
pip install -r requirements.txt

# Set up your OpenRouter API key
cp .env.example .env
# Edit .env and add your key

# Run with mock players (free, no API key needed)
python main.py --seed 42 --stream --no-discussion

# Run with a cheap LLM (start here!)
python main.py --model openai/gpt-4.1-nano --stream --no-discussion

# Launch the web UI
python server.py --port 5050
# Open http://localhost:5050
```

## Web UI

```bash
python server.py --port 5050
```

The web interface provides:

- **Per-team model selection** with searchable dropdown (200+ models)
- **Live policy boards** — Liberal and Fascist tracks with power icons
- **Player table** — 8 seats showing president/chancellor badges, alive/dead status
- **Role peek** — eye toggle to reveal hidden roles mid-game
- **Live feed** — messages stream in real-time with directed callouts, votes, card draws
- **Expandable inner thoughts** — see each player's private strategic reasoning
- **Game history** — matchup win rates with visual bar charts
- **Context stats** — per-player token usage tracking

## How It Works

### Game Setup
- 8 players with unique names and personalities (a friend group with real relationships)
- Roles: 5 Liberals, 2 Fascists, 1 Hitler
- Fascists know each other and know Hitler; Hitler doesn't know the Fascists
- Policy deck: 6 Liberal + 11 Fascist tiles

### The Friend Group

The players aren't generic agents — they're a tight-knit group of eight friends who've been doing weekly game night for two years. Each has a real job, a distinct personality, and actual relationships with the others.

**Blake** (union electrician) is dating **Rook** (mechanic) and has been friends with **Kit** (tattoo apprentice) since they were teenagers. **Avery** (software engineer) and **Drew** (teacher, the host) have been best friends since college and carpool to game night. **Casey** (ER nurse) and **Ellis** (journalist) are roommates. **Morgan** (bookkeeper) and Ellis text constantly. **Finley** (line cook) is the newest — Kit brought them in a few months ago. **Tam** (postal carrier) only knows Drew from being neighbors and is still finding their footing.

Every AI player gets the full cast list with all these relationships, so they know who's close, who might defend who, and whose silence means something different. It adds a layer of organic social dynamics that pure game-theory agents miss — Blake will instinctively defend Rook, Ellis and Morgan operate like a hive mind, and nobody really knows what Tam is thinking yet.

### Each Round
1. **Discussion** — priority speakers, directed callouts, organic back-and-forth
2. **Nomination** — President nominates a Chancellor
3. **Vote** — all players vote Ja/Nein (parallel API calls)
4. **Legislation** — President draws 3, discards 1; Chancellor receives 2, enacts 1
5. **Debrief** — President and Chancellor explain (or lie about) what happened
6. **Executive Action** — investigate loyalty, special election, or execution

### Discussion System
- **Instigators speak first** (president after legislation, nominee before vote)
- **Directed callouts** trigger mandatory reply turns
- **Pass once, you're done** — no re-asking silent players
- **Majority "ready to proceed"** instantly ends discussion
- **Inner monologue** — private reasoning separated from public speech

### Information Hiding
Each player only sees what they should:
- Their own role and night-phase knowledge
- Public board state, vote history, chat history
- Their own investigation results
- Danger zone warnings (3+ fascist policies)
- Confirmed-not-Hitler list

### Social Deception
The system prompt explicitly encourages:
- Lying, gaslighting, DARVO, false accusations
- Weaponizing silence, performative outrage
- Creating wedges between allies
- Pressing hard when sensing weakness
- Strategic betrayal and empty promises

## Model Support

The benchmark works with any model on OpenRouter that supports tool calling. Auto-fallback handles parameter compatibility:

| Tier | Examples | Cost |
|------|----------|------|
| Ultra-cheap | GPT-OSS 20B, Nemotron Nano 9B, Mistral Nemo | $0.02-0.05/M |
| Cheap | GPT-4.1 Nano, Gemini 3.1 Flash Lite, DeepSeek V3.2 | $0.10-0.30/M |
| Mid-tier | Gemini 2.5 Flash, GPT-4.1 Mini, Grok 4 Fast | $0.30-0.50/M |
| Premium | Claude Sonnet 4.6, GPT-4.1, Gemini 2.5 Pro, o3 | $1.00-3.00/M |
| Frontier | Claude Opus 4.6, GPT-5, o3 Pro | $5.00-20.00/M |

## Game History

Every completed game is saved to `game_history.jsonl` with:
- Liberal and Fascist model IDs
- Seed, winner, win condition, rounds played
- Policy counts, player-role mapping
- Discussion and reasoning settings

View stats via the web UI (History button) or the API:
```bash
curl http://localhost:5050/api/stats
```

## CLI Reference

```bash
# Mock mode (random players, instant, free)
python main.py --seed 42 --no-discussion
python main.py --seed 42 --games 10 --no-discussion    # batch 10 games
python main.py --seed 42 --stream                       # live terminal output
python main.py --seed 42 --verbose                      # full transcript after

# LLM mode
python main.py --model google/gemini-2.5-flash --stream
python main.py --model openai/gpt-4.1-nano --no-discussion --games 5
python main.py --model deepseek/deepseek-v3.2 --stream --output game.jsonl

# See all preconfigured models
python main.py --list-models
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--model MODEL` | mock | OpenRouter model ID |
| `--seed N` | random | Random seed for reproducibility |
| `--games N` | 1 | Number of games to run |
| `--stream` | off | Live-print events as they happen |
| `--verbose` | off | Print full transcript after game |
| `--no-discussion` | off | Skip all discussion phases |
| `--output FILE` | none | Save JSONL game log |
| `--request-delay N` | 0.5 | Seconds between API calls |
| `--list-models` | | Show available models and exit |

## Attribution

Secret Hitler was created by Mike Boxleiter, Tommy Maranges, and Mac Schubert.
It is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

This project is a non-commercial research tool for evaluating LLM capabilities in social deduction. It is not affiliated with or endorsed by the creators of Secret Hitler.

## License

Dual-licensed — see [LICENSE](LICENSE) for details. Game mechanics under CC BY-NC-SA 4.0, benchmarking framework under MIT.
