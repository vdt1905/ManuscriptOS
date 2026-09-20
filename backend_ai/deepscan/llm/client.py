"""
FormatForge AI — LLM Client Wrapper
Unified interface for OpenAI / Groq / Ollama.
LLM is ONLY used for:
  1. Converting guideline prose → StyleSpec JSON
  2. Classifying ambiguous paragraphs
  3. Parsing messy references into structured fields
  4. Generating explanation text
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ..config import GROQ_API_KEY, LLM_MODEL, LLM_PROVIDER, OPENAI_API_KEY

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting OpenAI, Groq, and Ollama."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = provider or LLM_PROVIDER
        self.model = model or LLM_MODEL
        self._client: Any = None

        # Resolve API key
        if api_key:
            self._api_key = api_key
        elif self.provider == "openai":
            self._api_key = OPENAI_API_KEY
        elif self.provider == "groq":
            self._api_key = GROQ_API_KEY
        else:
            self._api_key = ""

        self._init_client()

    # ── Client initialisation ────────────────────────────────

    def _init_client(self) -> None:
        """Lazily initialise the underlying SDK client."""
        try:
            if self.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
            elif self.provider == "groq":
                from groq import Groq
                self._client = Groq(api_key=self._api_key)
            elif self.provider == "ollama":
                # Ollama uses the OpenAI-compatible API
                from openai import OpenAI
                self._client = OpenAI(
                    base_url="http://localhost:11434/v1",
                    api_key="ollama",
                )
            else:
                logger.warning("Unknown LLM provider '%s' — client not initialised.", self.provider)
        except Exception as exc:
            logger.error("Failed to initialise LLM client (%s): %s", self.provider, exc)

    # ── Core chat completion ─────────────────────────────────

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request and return the assistant's text.

        Auto-falls back to Groq if the primary provider fails (quota, etc.).
        """
        try:
            return self._do_chat(system_prompt, user_prompt, temperature, max_tokens, json_mode)
        except Exception as primary_exc:
            # Auto-fallback to Groq if primary is OpenAI and Groq key exists
            if self.provider == "openai" and GROQ_API_KEY:
                logger.warning(
                    "Primary LLM (%s) failed: %s — falling back to Groq",
                    self.provider, primary_exc,
                )
                try:
                    fallback = LLMClient(
                        provider="groq",
                        model="openai/gpt-oss-120b",
                        api_key=GROQ_API_KEY,
                    )
                    return fallback._do_chat(
                        system_prompt, user_prompt, temperature, max_tokens, json_mode,
                    )
                except Exception as fb_exc:
                    logger.error("Groq fallback also failed: %s", fb_exc)
                    raise fb_exc from primary_exc
            raise

    def _do_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        """Execute the actual chat completion call."""
        if self._client is None:
            raise RuntimeError(
                f"LLM client not initialised. Provider={self.provider}. "
                "Check your API key in .env."
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode and self.provider in ("openai", "groq"):
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        logger.info(
            "LLM call [%s/%s]  tokens: prompt=%s completion=%s",
            self.provider,
            self.model,
            getattr(response.usage, "prompt_tokens", "?"),
            getattr(response.usage, "completion_tokens", "?"),
        )
        return content.strip()

    # ── Convenience: get JSON from LLM ───────────────────────

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """Call LLM and parse the response as JSON."""
        raw = self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM JSON response: %s\nRaw: %s", exc, raw[:500])
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    # ── Health check ─────────────────────────────────────────

    def is_available(self) -> bool:
        """Quick check whether the LLM client is usable."""
        if self._client is None:
            return False
        try:
            self.chat("Say OK.", "test", max_tokens=5)
            return True
        except Exception:
            return False


# ── Module-level singleton (lazy) ────────────────────────────

_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return the default (singleton) LLM client."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
