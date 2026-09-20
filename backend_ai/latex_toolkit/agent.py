"""
LaTeX Toolkit — conversational assistant (Phase H)
===================================================

A single Agno agent (`LaTeXAssistant`) that can drive the toolkit by chat. The
toolkit functions are wrapped as Agno tools that return strings (Agno tools
should return text the model can read back to the user).

Exposed at ``POST /toolkit/chat``.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

from . import tools as T

logger = logging.getLogger(__name__)


# ── Tool wrappers (string-returning, LLM-friendly) ───────────────

def make_table(data: str, has_header: bool = True, caption: str = "") -> str:
    """Convert CSV or pasted grid text into a LaTeX table.

    Args:
        data: the CSV/TSV/grid text to convert.
        has_header: whether the first row is a header.
        caption: optional table caption.
    """
    res = T.table_to_latex(data, has_header=has_header, caption=caption or None)
    return res["latex"]


def make_equation(description: str, display: bool = True) -> str:
    """Convert a description of a math expression into LaTeX.

    Args:
        description: the equation in words or plain text.
        display: True for a displayed equation, False for inline.
    """
    res = T.equation_to_latex(description, display=display)
    return res["wrapped"]


def make_bibtex(references: str, enrich: bool = False) -> str:
    """Convert a block of references into BibTeX.

    Args:
        references: the reference list, one entry per line or blank-line separated.
        enrich: if True, look up missing DOIs/pages from CrossRef (slower).
    """
    res = T.references_to_bibtex(references, enrich=enrich)
    return res["bibtex"]


def list_starter_templates() -> str:
    """List the available starter LaTeX templates (IEEE/ACM/Springer/APA/article)."""
    res = T.list_templates()
    return json.dumps(res)


_TOOLS = [make_table, make_equation, make_bibtex, list_starter_templates]

_INSTRUCTIONS = (
    "You are LaTeXAssistant, an expert LaTeX assistant for researchers. "
    "Help users produce correct, compilable LaTeX. When the user asks for a "
    "table, equation, or bibliography, CALL the matching tool and return its "
    "output inside a fenced ```latex block. Keep explanations short. Never "
    "invent content the user didn't provide; preserve their wording."
)


@lru_cache(maxsize=1)
def get_assistant():
    """Build (once) and return the LaTeXAssistant Agno agent, or None if no key."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from agno.agent import Agent
        from agno.models.groq import Groq as AgnoGroq

        return Agent(
            name="LaTeXAssistant",
            model=AgnoGroq(
                id=os.getenv("TOOLKIT_MODEL") or os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
                api_key=api_key,
            ),
            tools=_TOOLS,
            instructions=_INSTRUCTIONS,
            markdown=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to build LaTeXAssistant: %s", exc)
        return None


def chat(message: str) -> str:
    """Run one turn against the assistant. Returns the assistant's reply text."""
    agent = get_assistant()
    if agent is None:
        return (
            "The LaTeX assistant is unavailable (no GROQ_API_KEY configured). "
            "You can still use the individual toolkit endpoints directly."
        )
    result = agent.run(message)
    return (result.content or "").strip()
