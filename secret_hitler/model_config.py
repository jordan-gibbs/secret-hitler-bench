"""
Model registry for OpenRouter-supported models.

Each ModelConfig captures the quirks, capabilities, and defaults needed
to make a given model work reliably in the Secret Hitler bench.
Hot-swap models by changing the model key passed to the OpenRouter client.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
    # OpenRouter model ID (e.g. "anthropic/claude-sonnet-4.6")
    id: str
    # Human-friendly short name
    name: str
    # Context window (tokens)
    context_window: int
    # Max output tokens
    max_output: int
    # Whether the model supports reasoning/thinking tokens
    supports_reasoning: bool = False
    # Whether the model supports response_format: json_schema
    supports_json_schema: bool = False
    # Whether the model supports response_format: json_object
    supports_json_object: bool = True
    # Whether the model supports tool/function calling
    supports_tools: bool = True
    # Whether the model supports temperature (o-series doesn't)
    supports_temperature: bool = True
    # Whether the model supports system messages
    supports_system_message: bool = True
    # Default reasoning effort when reasoning is enabled
    default_reasoning_effort: str | None = None
    # Recommended max_tokens for this model (some need explicit setting)
    recommended_max_tokens: int | None = None
    # Provider-specific notes
    notes: str = ""


# ---------------------------------------------------------------------------
# Top 10 models (2025-2026) — curated for the Secret Hitler bench
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, ModelConfig] = {}


def _register(cfg: ModelConfig) -> None:
    MODEL_REGISTRY[cfg.id] = cfg
    # Also register by short name for convenience
    short = cfg.id.split("/", 1)[1] if "/" in cfg.id else cfg.id
    MODEL_REGISTRY[short] = cfg


# 1. Claude Sonnet 4.6 — latest Claude, 1M context, full feature support
_register(ModelConfig(
    id="anthropic/claude-sonnet-4.6",
    name="Claude Sonnet 4.6",
    context_window=1_000_000,
    max_output=128_000,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Best all-around. Reasoning min 1024 budget tokens.",
))

# 2. OpenAI o3 — best OpenAI reasoning model
_register(ModelConfig(
    id="openai/o3",
    name="OpenAI o3",
    context_window=200_000,
    max_output=100_000,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    supports_temperature=False,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="No temperature support. Use reasoning.effort instead.",
))

# 3. Gemini 2.5 Pro — 1M context, strong reasoning
_register(ModelConfig(
    id="google/gemini-2.5-pro",
    name="Gemini 2.5 Pro",
    context_window=1_048_576,
    max_output=65_536,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Google reasoning via thinkingLevel mapping.",
))

# 4. GPT-4.1 — 1M context non-reasoning workhorse
_register(ModelConfig(
    id="openai/gpt-4.1",
    name="GPT-4.1",
    context_window=1_047_576,
    max_output=32_768,
    supports_reasoning=False,
    supports_json_schema=True,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Best GPT non-reasoning model. 1M context.",
))

# 5. DeepSeek R1-0528 — best value reasoning model
_register(ModelConfig(
    id="deepseek/deepseek-r1-0528",
    name="DeepSeek R1",
    context_window=163_840,
    max_output=65_536,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="high",
    recommended_max_tokens=4096,
    notes="Fully open reasoning tokens. Very cheap.",
))

# 6. Claude Opus 4.6 — highest capability Claude
_register(ModelConfig(
    id="anthropic/claude-opus-4.6",
    name="Claude Opus 4.6",
    context_window=1_000_000,
    max_output=128_000,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Most capable model. Expensive. Reasoning min 1024 budget.",
))

# 7. Gemini 2.5 Flash — best value Google model
_register(ModelConfig(
    id="google/gemini-2.5-flash",
    name="Gemini 2.5 Flash",
    context_window=1_048_576,
    max_output=65_535,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="low",
    recommended_max_tokens=4096,
    notes="Great value. 1M context with reasoning.",
))

# 8. Grok 4 Fast — 2M context, reasoning, cheap
_register(ModelConfig(
    id="x-ai/grok-4-fast",
    name="Grok 4 Fast",
    context_window=2_000_000,
    max_output=30_000,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Largest context window (2M). Very cheap.",
))

# 9. DeepSeek V3.2 — best value non-reasoning workhorse
_register(ModelConfig(
    id="deepseek/deepseek-v3.2",
    name="DeepSeek V3.2",
    context_window=163_840,
    max_output=16_384,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="low",
    recommended_max_tokens=4096,
    notes="Cheapest high-quality model at $0.26/$0.38 per M.",
))

# 10. Qwen 3.5 397B — largest open-weight model
_register(ModelConfig(
    id="qwen/qwen3.5-397b-a17b",
    name="Qwen 3.5 397B",
    context_window=262_144,
    max_output=65_536,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Largest open-weight model. Full features.",
))


# ---------------------------------------------------------------------------
# Ultra-cheap paid models (under $0.10/M input)
# ---------------------------------------------------------------------------

_register(ModelConfig(
    id="openai/gpt-5-nano",
    name="GPT-5 Nano",
    context_window=400_000,
    max_output=16_384,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    supports_temperature=True,
    default_reasoning_effort="low",
    recommended_max_tokens=4096,
    notes="Ultra cheap. $0.05/$0.40 per M. 400K context. Reasoning.",
))

_register(ModelConfig(
    id="openai/gpt-oss-20b",
    name="GPT-OSS 20B",
    context_window=131_072,
    max_output=16_384,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Ultra cheap. $0.03/$0.11 per M. Open-source GPT.",
))

_register(ModelConfig(
    id="qwen/qwen3.5-9b",
    name="Qwen 3.5 9B",
    context_window=256_000,
    max_output=16_384,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="low",
    recommended_max_tokens=4096,
    notes="Ultra cheap. $0.05/$0.15 per M. 256K context.",
))

_register(ModelConfig(
    id="qwen/qwen3.5-flash-02-23",
    name="Qwen 3.5 Flash",
    context_window=1_000_000,
    max_output=65_536,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="low",
    recommended_max_tokens=4096,
    notes="Cheap. $0.07/$0.26 per M. 1M context. Reasoning.",
))

_register(ModelConfig(
    id="nvidia/nemotron-nano-9b-v2",
    name="Nemotron Nano 9B",
    context_window=131_072,
    max_output=16_384,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Ultra cheap. $0.04/$0.16 per M. Reasoning.",
))

_register(ModelConfig(
    id="mistralai/mistral-nemo",
    name="Mistral Nemo",
    context_window=131_072,
    max_output=16_384,
    supports_reasoning=False,
    supports_json_schema=False,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Ultra cheap. $0.02/$0.04 per M. 131K context.",
))

# ---------------------------------------------------------------------------
# Bonus: cheap / free models useful for testing
# ---------------------------------------------------------------------------

_register(ModelConfig(
    id="google/gemini-3.1-flash-lite-preview",
    name="Gemini 3.1 Flash Lite",
    context_window=1_048_576,
    max_output=65_536,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="low",
    recommended_max_tokens=4096,
    notes="Cheapest Gemini. $0.25/$1.50 per M. 1M context. Fast.",
))

_register(ModelConfig(
    id="google/gemini-3-flash-preview",
    name="Gemini 3 Flash",
    context_window=1_048_576,
    max_output=65_536,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Fast Gemini 3. $0.50/$1.50 per M. 1M context.",
))

_register(ModelConfig(
    id="openai/gpt-4.1-mini",
    name="GPT-4.1 Mini",
    context_window=1_047_576,
    max_output=32_768,
    supports_reasoning=False,
    supports_json_schema=True,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Cheap GPT for testing. $0.40/$1.60 per M.",
))

_register(ModelConfig(
    id="openai/gpt-4.1-nano",
    name="GPT-4.1 Nano",
    context_window=1_047_576,
    max_output=32_768,
    supports_reasoning=False,
    supports_json_schema=True,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Cheapest GPT. $0.10/$0.40 per M. Good for rapid iteration.",
))

_register(ModelConfig(
    id="meta-llama/llama-3.3-70b-instruct:free",
    name="Llama 3.3 70B (free)",
    context_window=65_536,
    max_output=16_384,
    supports_reasoning=False,
    supports_json_schema=False,
    supports_json_object=False,
    recommended_max_tokens=4096,
    notes="Free tier. Rate limited. No JSON mode — use prompt-based JSON.",
))

_register(ModelConfig(
    id="qwen/qwen3-4b:free",
    name="Qwen 3 4B (free)",
    context_window=40_960,
    max_output=8_192,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Free tier. Small but capable. Good for testing.",
))

_register(ModelConfig(
    id="nvidia/nemotron-3-super-120b-a12b:free",
    name="Nemotron 120B (free)",
    context_window=262_144,
    max_output=16_384,
    supports_reasoning=True,
    supports_json_schema=False,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Free tier. 120B params, reasoning capable. Best free option.",
))

_register(ModelConfig(
    id="mistralai/mistral-small-3.1-24b-instruct:free",
    name="Mistral Small 3.1 (free)",
    context_window=128_000,
    max_output=16_384,
    supports_reasoning=False,
    supports_json_schema=False,
    supports_json_object=True,
    recommended_max_tokens=4096,
    notes="Free tier. Solid 24B model.",
))

_register(ModelConfig(
    id="openai/o4-mini",
    name="OpenAI o4-mini",
    context_window=200_000,
    max_output=100_000,
    supports_reasoning=True,
    supports_json_schema=True,
    supports_json_object=True,
    supports_temperature=False,
    default_reasoning_effort="medium",
    recommended_max_tokens=4096,
    notes="Cheap reasoning. No temperature. $1.10/$4.40 per M.",
))


def get_model(model_id: str) -> ModelConfig:
    """Look up a model by full ID or short name. Auto-creates config for unknown models."""
    if model_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_id]
    # Try case-insensitive match
    lower = model_id.lower()
    for key, cfg in MODEL_REGISTRY.items():
        if key.lower() == lower:
            return cfg
    # Auto-create a sensible default config for any OpenRouter model
    short = model_id.split("/", 1)[1] if "/" in model_id else model_id
    is_free = model_id.endswith(":free")
    cfg = ModelConfig(
        id=model_id,
        name=short,
        context_window=131_072,
        max_output=16_384,
        supports_reasoning=False,
        supports_json_schema=False,  # conservative — fallback will find what works
        supports_json_object=True,
        recommended_max_tokens=4096,
        notes=f"Auto-detected from OpenRouter.{' Free tier.' if is_free else ''}",
    )
    _register(cfg)
    return cfg


def list_models() -> list[ModelConfig]:
    """Return deduplicated list of all registered models."""
    seen: set[str] = set()
    result: list[ModelConfig] = []
    for cfg in MODEL_REGISTRY.values():
        if cfg.id not in seen:
            seen.add(cfg.id)
            result.append(cfg)
    return result
