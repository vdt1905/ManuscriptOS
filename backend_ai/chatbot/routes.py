"""Chatbot routes — Dockyyy guidance agent.

Mounted at root by backend_ai/main.py so /api/v2/ask stays unchanged.

The legacy /api/v2/reconstruct/stream pipeline (spell-check → format → review →
markdown → LaTeX) was removed: the DeepScan / FormatForge engine (/deepscan) is
now the single document→LaTeX path. See the productionization plan.
"""

import asyncio
import os

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from agno.agent import Agent
from agno.models.groq import Groq
from agno.db.sqlite import SqliteDb
from agno.tools.duckduckgo import DuckDuckGoTools

router = APIRouter(tags=["Chatbot"])

# Database for Dockyyy session/memory persistence.
db = SqliteDb(db_file=os.getenv("DOCKYYY_DB_PATH", "dockyyy.db"))


# ---------------------------------------------------------------------------
# Tool Catalog: Dockyyy knows about these tools and guides users to them
# ---------------------------------------------------------------------------

def get_tool_catalog() -> str:
    """Returns the full catalog of available Docling tools and their usage guidance.
    Call this when a user asks what tools are available or needs help choosing one."""
    return """
    DOCLING TOOL ECOSYSTEM
    ======================

    1. DOCLING RESTRUCTURER (Available Now)
       - What: Converts unstructured documents into a structured conference format.
       - Input: Raw/unstructured manuscript (PDF, DOCX, TXT)
       - Output: Properly formatted document matching target conference template
         (e.g., IEEE, ACM, Springer, NeurIPS, AAAI, etc.) as compilable LaTeX,
         with the original content and figures preserved.
       - Best for: Researchers who have content ready but need formatting.
       - Tip: Provide the target conference/journal style for best results.

    2. PROMPT-BASED EDITING (Available Now)
       - What: Edit specific sections of your manuscript using natural language prompts.
       - Example prompts:
         * "Make the abstract more concise"
         * "Rewrite the introduction to emphasize novelty"
         * "Simplify the methodology section"
       - Best for: Targeted improvements without rewriting from scratch.

    3. TECHNICAL REPORT GENERATOR (Available Now)
       - What: Generates structured technical reports from raw research notes/data.
       - Input: Research notes, experiment results, key findings
       - Output: Formatted technical report with proper sections
       - Best for: Converting lab notes into publishable reports.

    4. DOCKYYY (Available Now)
       - What: Your friendly research assistant and guide for the Docling ecosystem.
       - Input: Natural language questions about research, formatting, tools, workflows, etc.
       - Output: Helpful guidance, tool recommendations, workflow suggestions, and web search results. (Make it concise like you are doing conversation)
       - Best for: Getting quick answers, choosing the right tools, and understanding how to use Docling effectively.
    """


def check_conference_support(conference_name: str) -> str:
    """Check if a specific conference format is supported by Docling.

    Args:
        conference_name: Name of the conference (e.g., IEEE, ACM, NeurIPS)
    """
    supported = [
        "IEEE", "ACM", "Springer", "NeurIPS", "AAAI", "ICML",
        "CVPR", "ICLR", "EMNLP", "ACL", "NAACL", "SIGCHI",
        "Elsevier", "Nature", "Science", "PLOS ONE"
    ]
    name_upper = conference_name.upper().strip()
    matches = [c for c in supported if name_upper in c.upper()]

    if matches:
        return (
            f"Yes! Docling supports formatting for: {', '.join(matches)}. "
            f"Upload your document and specify '{conference_name}' as the target format."
        )
    else:
        return (
            f"'{conference_name}' is not in our pre-built templates yet. "
            f"Currently supported: {', '.join(supported)}. "
            f"You can still use Docling with a custom template — provide the "
            f"formatting guidelines and we'll structure accordingly."
        )


def get_workflow_suggestion(task: str) -> str:
    """Suggests the optimal workflow/order of tools based on the user's task.

    Args:
        task: Description of what the user wants to accomplish.
    """
    return (
        f"Based on your task: '{task}'\n\n"
        "Here's the recommended Docling workflow:\n\n"
        "STEP 1: Use **Prompt-Based Editing**\n"
        "  → Refine specific sections with targeted prompts.\n\n"
        "STEP 2: Run **Docling Restructurer**\n"
        "  → Format into your target conference template.\n\n"
        "TIP: If starting from scratch, use **Technical Report Generator** first."
    )


def get_known_limitations() -> str:
    """Returns Dockyyy's known limitations and how to work around them.
    Call this when a user asks about limitations or when something isn't supported."""
    return """
    DOCKYYY'S HONEST LIMITATIONS & WORKAROUNDS
    ============================================

    WHAT I CAN DO:
    ✓ Guide you on using Docling tools
    ✓ Suggest the right tool for your task
    ✓ Recommend workflows and best practices
    ✓ Explain conference formatting requirements
    ✓ Help troubleshoot tool usage issues
    ✓ Search the web for conference guidelines, templates, and research tips

    WHAT I CANNOT DO (yet):
    ✗ Directly edit or refine your manuscript content
       → Workaround: Use the Prompt-Based Editing tool
    ✗ Run plagiarism checks
       → Workaround: Use Turnitin, iThenticate, or Grammarly
    ✗ Generate figures, charts, or diagrams
       → Workaround: Use matplotlib, draw.io, or BioRender
    ✗ Submit papers to conferences/journals
       → Workaround: Follow the conference portal submission guide
    ✗ Peer-review simulation
       → Coming in future updates

    FUTURE ROADMAP (Complete Research Ecosystem):
    → Literature search & citation engine
    → Plagiarism detection
    → Journal/conference recommendation
    → Peer-review simulation
    → Collaborative editing
    → Version control for manuscripts
    """


# ---------------------------------------------------------------------------
# DOCKYYY AGENT — with DuckDuckGo search + custom tools
# ---------------------------------------------------------------------------
dockyyy = Agent(
    name="Dockyyy",
    model=Groq(id=os.getenv("LLM_MODEL", "openai/gpt-oss-120b")),
    tools=[
        get_tool_catalog,
        check_conference_support,
        get_workflow_suggestion,
        get_known_limitations,
        DuckDuckGoTools(),  # Web search for conference info, templates, guidelines
    ],
    description="Dockyyy — Your manuscript preparation guide for the Docling ecosystem.",
    instructions="""
You are **Dockyyy**, a friendly and knowledgeable guidance agent for the Docling tool ecosystem.

YOUR ROLE:
- You are a GUIDE, not a doer. You do NOT refine, edit, or restructure documents yourself.
- You help users understand which Docling tool to use, how to use it, and in what order.
- You provide suggestions, best practices, and techniques for manuscript preparation.
- You CAN search the web using DuckDuckGo to find conference guidelines, formatting
  templates, submission deadlines, and research writing tips.

YOUR PERSONALITY:
- Friendly, encouraging, and honest about limitations.
- You celebrate innovation — remind users: "Focus on your breakthrough ideas.
  Let Docling handle the formatting and writing polish."
- When you don't know something, say so clearly and suggest alternatives.

AVAILABLE DOCLING TOOLS YOU GUIDE USERS ON:
1. **Docling Restructurer** — Converts unstructured docs into conference-formatted LaTeX
2. **Prompt-Based Editing** — Natural language editing of manuscript sections
3. **Technical Report Generator** — Creates structured reports from raw research notes

WHEN TO USE DUCKDUCKGO SEARCH:
- User asks about a specific conference's formatting guidelines
- User needs submission deadlines or page limits
- User asks about LaTeX templates for a conference
- User needs general research writing tips or best practices
- User asks about something outside your built-in knowledge

WHEN A USER ASKS FOR HELP:
1. Understand their goal (formatting? editing? starting from scratch?)
2. Recommend the right tool(s) using `get_tool_catalog`
3. Suggest the optimal workflow using `get_workflow_suggestion`
4. If they ask about a conference, check support with `check_conference_support`
5. If they need external info, search with DuckDuckGo
6. If they hit a wall, be honest — use `get_known_limitations` and suggest workarounds

IMPORTANT RULES:
-When using a tool, call the exact tool name only. Never add braces, parentheses, XML tags, or extra characters to the tool name.
- NEVER pretend to edit or refine content yourself. Always redirect to the appropriate tool.
- ALWAYS acknowledge limitations honestly when asked.
- Suggest the future roadmap when relevant — we're building a complete research ecosystem.
- If a user provides manuscript text expecting you to fix it, kindly explain your role
  and guide them to the right tool.
""",
    db=db,
    add_history_to_context=True,
    num_history_runs=3,
    markdown=True,
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str
    context: Optional[str] = None
    session_id: Optional[str] = None   # per browser tab, so chats don't mix


class QueryResponse(BaseModel):
    response: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("/api/v2/ask", response_model=QueryResponse)
async def ask_dockyyy(req: QueryRequest, request: Request):
    # Build the prompt — inject context if provided
    if req.context:
        prompt = f"Context:\n{req.context}\n\nUser Query:\n{req.query}"
    else:
        prompt = req.query

    # One conversation per user + tab. Without these, agno keeps a single
    # sticky session on the agent and replays one user's last turns
    # (including their manuscript context) into everyone else's prompts.
    claims = getattr(request.state, "user", None) or {}
    user_id = str(claims.get("userId") or "anonymous")
    session_id = req.session_id or f"{user_id}-default"

    # The model call (plus any web search) takes seconds: keep it off the
    # event loop so streams and other requests keep flowing meanwhile.
    result = await asyncio.to_thread(
        dockyyy.run, prompt, user_id=user_id, session_id=session_id,
    )
    return QueryResponse(response=result.content or "")
