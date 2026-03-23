"""
OpenRouter async LLM client.

Supports:
- Model hot-swapping at any time
- Structured JSON output (json_schema / json_object / prompt-based fallback)
- Reasoning models (effort, budget tokens, include_reasoning)
- Retry with exponential backoff on rate limits and transient errors
- Response healing plugin for non-streaming
- Provider routing preferences
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from secret_hitler.model_config import ModelConfig, get_model
from secret_hitler.player import LLMClient

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
CHAT_ENDPOINT = f"{OPENROUTER_BASE}/chat/completions"

# Retry config
MAX_RETRIES = 8
RETRY_BASE_DELAY = 2.0  # seconds
RETRY_MAX_DELAY = 30.0
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass
class UsageStats:
    """Tracks token usage across the session."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_requests: int = 0
    failed_requests: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class OpenRouterClient(LLMClient):
    """
    Async OpenRouter client that implements the LLMClient ABC.

    Usage:
        client = OpenRouterClient(
            api_key="sk-or-...",
            model="anthropic/claude-sonnet-4.6",
        )
        response = await client.query(
            system="You are helpful.",
            messages=[],
            user_message="Hello",
            response_schema={"type": "object", ...},
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "anthropic/claude-sonnet-4.6",
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        enable_reasoning: bool = False,
        app_name: str = "SecretHitlerBench",
        app_url: str = "",
        timeout: float = 60.0,
        request_delay: float = 0.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY env var "
                "or pass api_key parameter."
            )

        self._model_id = model
        self._model_config = get_model(model)
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort
        self._enable_reasoning = enable_reasoning
        self._app_name = app_name
        self._app_url = app_url
        self._timeout = timeout
        self._request_delay = request_delay  # delay between requests (for rate limiting)

        self.usage = UsageStats()
        self._working_fallback_level = 0  # remembers the last level that worked
        self.last_server_reasoning: str | None = None

        self._http: httpx.AsyncClient | None = None

    @property
    def model_config(self) -> ModelConfig:
        return self._model_config

    def set_model(self, model: str) -> ModelConfig:
        """Hot-swap the model. Returns the new ModelConfig."""
        self._model_config = get_model(model)
        self._model_id = self._model_config.id
        logger.info("Switched model to %s", self._model_id)
        return self._model_config

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self._app_url,
                    "X-OpenRouter-Title": self._app_name,
                },
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Build request body
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        system: str,
        messages: list[dict[str, str]],
        user_message: str,
    ) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []

        if system and self._model_config.supports_system_message:
            msgs.append({"role": "system", "content": system})

        for m in messages:
            msgs.append({"role": m["role"], "content": m["content"]})

        # If model doesn't support system messages, prepend to first user msg
        if system and not self._model_config.supports_system_message:
            user_message = f"[System Instructions]\n{system}\n\n[User]\n{user_message}"

        msgs.append({"role": "user", "content": user_message})
        return msgs

    def _build_response_format(
        self, response_schema: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if response_schema is None:
            return None

        cfg = self._model_config

        # Best: json_schema mode (strict structured output)
        if cfg.supports_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": self._clean_schema_for_openrouter(response_schema),
                },
            }

        # Fallback: json_object mode (model produces JSON, schema in prompt)
        if cfg.supports_json_object:
            return {"type": "json_object"}

        # No native JSON support — rely on prompt-based instruction
        return None

    def _clean_schema_for_openrouter(self, schema: dict) -> dict:
        """
        Strip Pydantic-specific fields that OpenRouter's strict mode rejects.
        Ensures additionalProperties: false on all objects.
        """
        cleaned = dict(schema)
        # Remove top-level Pydantic metadata
        for key in ("title", "$defs", "definitions"):
            cleaned.pop(key, None)

        # Ensure additionalProperties: false for strict mode
        if cleaned.get("type") == "object":
            cleaned["additionalProperties"] = False

        # Recursively clean properties
        if "properties" in cleaned:
            for prop_name, prop_schema in cleaned["properties"].items():
                cleaned["properties"][prop_name] = self._clean_schema_for_openrouter(
                    prop_schema
                )

        return cleaned

    def _build_body(
        self,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any] | None,
        schema_in_prompt: bool,
        *,
        fallback_level: int = 0,
    ) -> dict[str, Any]:
        """
        Build the request body. fallback_level controls parameter simplification:
          0 = full features (json_schema + plugins + require_parameters)
          1 = drop json_schema strict, use json_object + plugins
          2 = drop plugins, json_object only
          3 = drop response_format entirely, rely on prompt-based JSON
        """
        cfg = self._model_config

        # Level 4: absolute bare minimum
        if fallback_level >= 4:
            return {
                "model": self._model_id,
                "messages": messages,
                "max_tokens": self._max_tokens or cfg.recommended_max_tokens or 4096,
            }

        body: dict[str, Any] = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": self._max_tokens or cfg.recommended_max_tokens or 4096,
        }

        # Temperature — only if explicitly set by the user
        if self._temperature is not None and fallback_level <= 2 and cfg.supports_temperature:
            body["temperature"] = self._temperature

        # Structured output — progressively simplified
        if response_schema is not None and fallback_level < 3:
            if fallback_level == 0 and cfg.supports_json_schema:
                body["response_format"] = self._build_response_format(response_schema)
            elif fallback_level <= 1 and (cfg.supports_json_object or cfg.supports_json_schema):
                body["response_format"] = {"type": "json_object"}
            elif fallback_level == 2:
                body["response_format"] = {"type": "json_object"}

        # Reasoning — never sent. Models use their own defaults.
        # Our inner_thought schema field handles strategic reasoning manually.

        # Require parameters — only level 0
        if fallback_level == 0:
            body["provider"] = {"require_parameters": True}

        return body

    # ------------------------------------------------------------------
    # Parse response
    # ------------------------------------------------------------------

    def _extract_content(self, data: dict[str, Any]) -> tuple[str, str | None]:
        """Extract text content and server reasoning from an OpenRouter response.
        Returns (content, server_reasoning)."""
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"Empty choices in response: {data}")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        # Capture server-level reasoning tokens (from reasoning models)
        server_reasoning = message.get("reasoning")
        if not server_reasoning:
            # Try reasoning_details array
            details_list = message.get("reasoning_details", [])
            if details_list:
                parts = [
                    d.get("text", "") for d in details_list
                    if d.get("type") in ("reasoning.text", "reasoning.summary")
                    and d.get("text")
                ]
                server_reasoning = "\n".join(parts) if parts else None

        # Track usage (global + per-request for player-level tracking)
        usage = data.get("usage", {})
        self._last_prompt_tokens = usage.get("prompt_tokens", 0)
        self._last_completion_tokens = usage.get("completion_tokens", 0)
        if usage:
            self.usage.prompt_tokens += self._last_prompt_tokens
            self.usage.completion_tokens += self._last_completion_tokens
            token_details = usage.get("completion_tokens_details", {})
            self.usage.reasoning_tokens += token_details.get("reasoning_tokens", 0)

        return content or "", server_reasoning

    def _extract_json(self, raw: str) -> str:
        """
        Extract JSON from the response, handling markdown fences and
        other common LLM wrapping patterns.
        """
        text = raw.strip()

        # Try direct parse first
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        patterns = [
            r"```json\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
            r"\{.*\}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                candidate = match.group(1) if match.lastindex else match.group(0)
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue

        # Last resort: return as-is and let caller handle the error
        return text

    # ------------------------------------------------------------------
    # Main query method
    # ------------------------------------------------------------------

    async def query(
        self,
        system: str,
        messages: list[dict[str, str]],
        user_message: str,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        """
        Send a prompt to OpenRouter and return the response content.

        If response_schema is provided, the response will be valid JSON
        matching that schema (via json_schema mode, json_object mode,
        or prompt-based fallback).
        """
        cfg = self._model_config
        http = await self._get_http()

        # Try with progressively simpler parameters on 404
        # 0: json_schema + require_parameters
        # 1: json_object
        # 2: json_object (no require_params)
        # 3: prompt-based JSON (no response_format)
        # 4: bare minimum (model + messages + max_tokens only)
        # Start from the last level that worked to avoid repeating failures
        for fallback_level in range(self._working_fallback_level, 5):
            # Build prompt — inject schema into prompt text at fallback level 3
            schema_in_prompt = (
                response_schema is not None
                and (fallback_level >= 3 or (not cfg.supports_json_schema and not cfg.supports_json_object))
            )

            actual_user_message = user_message
            if schema_in_prompt:
                schema_str = json.dumps(response_schema, indent=2)
                actual_user_message += (
                    f"\n\nYou MUST respond with valid JSON matching this schema:\n"
                    f"```json\n{schema_str}\n```\n"
                    f"Respond with ONLY the JSON object, no other text."
                )

            msgs = self._build_messages(system, messages, actual_user_message)
            body = self._build_body(
                msgs, response_schema if not schema_in_prompt else None,
                schema_in_prompt, fallback_level=fallback_level,
            )

            # Log what we're sending for debugging
            params_sent = []
            if "response_format" in body:
                params_sent.append(f"response_format={body['response_format'].get('type','?')}")
            if "plugins" in body:
                params_sent.append("plugins")
            if "reasoning" in body:
                params_sent.append("reasoning")
            if "provider" in body:
                params_sent.append("require_params")
            if "temperature" in body:
                params_sent.append("temperature")
            logger.debug("Fallback %d: params=[%s]", fallback_level, ", ".join(params_sent))

            result = await self._try_request(http, body, response_schema)
            if result is not None:
                # Remember this level so we skip broken levels next time
                if fallback_level > self._working_fallback_level:
                    logger.info("Model %s works at fallback level %d. Locking in.", self._model_id, fallback_level)
                    self._working_fallback_level = fallback_level
                return result

            if self._last_status == 404:
                logger.warning(
                    "Fallback %d failed (404). Params: [%s]. Trying simpler...",
                    fallback_level, ", ".join(params_sent),
                )
                continue

            # For other errors, use normal retry logic
            break

        # If all fallback levels failed, raise
        raise RuntimeError(
            f"OpenRouter: all 4 fallback levels failed for model '{self._model_id}'. "
            f"This model may not support any structured output. "
            f"Last status: {self._last_status}"
        )

    async def _try_request(
        self,
        http: httpx.AsyncClient,
        body: dict[str, Any],
        response_schema: dict[str, Any] | None,
    ) -> str | None:
        """
        Try sending a request with retries. Returns content on success,
        None on 404 (so caller can try fallback), raises on other failures.
        """
        self._last_status = 0
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            if self._request_delay > 0:
                await asyncio.sleep(self._request_delay)

            self.usage.total_requests += 1
            try:
                resp = await http.post(CHAT_ENDPOINT, json=body)
                self._last_status = resp.status_code

                if resp.status_code == 200:
                    data = resp.json()
                    if "error" in data:
                        error_msg = data["error"].get("message", str(data["error"]))
                        logger.warning("OpenRouter error in body: %s", error_msg)
                        raise ValueError(f"OpenRouter error: {error_msg}")

                    raw_content, server_reasoning = self._extract_content(data)
                    self.last_server_reasoning = server_reasoning

                    if response_schema is not None:
                        return self._extract_json(raw_content)
                    return raw_content

                if resp.status_code == 404:
                    # "No endpoints found" — signal caller to try fallback
                    logger.warning("404 from OpenRouter: %s", resp.text[:200])
                    return None

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    self.usage.failed_requests += 1
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    logger.warning(
                        "Status %d (attempt %d/%d). Retrying in %.1fs.",
                        resp.status_code, attempt + 1, MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable, non-404 error
                self.usage.failed_requests += 1
                raise ValueError(
                    f"OpenRouter request failed: HTTP {resp.status_code}: {resp.text[:500]}"
                )

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                self.usage.failed_requests += 1
                last_error = e
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                logger.warning("Network error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, e)
                await asyncio.sleep(delay)
                continue

        raise RuntimeError(
            f"OpenRouter request failed after {MAX_RETRIES} retries. Last error: {last_error}"
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def check_key(self) -> dict:
        """Check API key status and remaining credits."""
        http = await self._get_http()
        resp = await http.get(f"{OPENROUTER_BASE}/key")
        resp.raise_for_status()
        return resp.json()

    def usage_summary(self) -> dict:
        return {
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "reasoning_tokens": self.usage.reasoning_tokens,
            "total_tokens": self.usage.total_tokens,
            "total_requests": self.usage.total_requests,
            "failed_requests": self.usage.failed_requests,
        }
