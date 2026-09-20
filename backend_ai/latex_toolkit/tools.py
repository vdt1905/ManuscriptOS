"""
LaTeX Toolkit — tool functions (Phase H)
=========================================

Each function here is a *pure tool*: it takes plain arguments and returns plain
data (dicts / strings), with no FastAPI or Agno coupling. That lets us expose the
same function two ways:

    • as a REST endpoint   (backend_ai/latex_toolkit/routes.py)
    • as an Agno tool       (backend_ai/latex_toolkit/agent.py — the chat assistant)

Tools:
    table_to_latex        — CSV / pasted grid → tabular
    equation_to_latex     — natural-language / plain math → LaTeX (LLM)
    references_to_bibtex  — reference block → .bib  (see bibtex.py)
    document_to_latex     — DOCX / PDF / TXT file → full LaTeX document
    latex_export          — LaTeX → PDF / DOCX / Markdown bytes
    list_templates / get_template — starter .tex library
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .bibtex import references_to_bibtex as _references_to_bibtex
from .latex_utils import (
    available_styles,
    docir_to_latex,
    grid_to_tabular,
    normalize_style,
    parse_csv_text,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# ──────────────────────────────────────────────────────────────
#  table_to_latex
# ──────────────────────────────────────────────────────────────

def table_to_latex(
    data: str,
    *,
    has_header: bool = True,
    caption: str | None = None,
    label: str | None = None,
    delimiter: str | None = None,
    align: str | None = None,
) -> dict:
    """Convert CSV / TSV / pasted grid text into a LaTeX ``tabular`` (wrapped in a
    ``table`` float when a caption/label is supplied).

    Returns ``{latex, rows, cols}``.
    """
    rows = parse_csv_text(data, delimiter=delimiter)
    if not rows:
        return {"latex": "% (no table data provided)\n", "rows": 0, "cols": 0}
    latex = grid_to_tabular(
        rows, header=has_header, caption=caption, label=label, align=align
    )
    return {"latex": latex, "rows": len(rows), "cols": max(len(r) for r in rows)}


# ──────────────────────────────────────────────────────────────
#  equation_to_latex   (LLM)
# ──────────────────────────────────────────────────────────────

def equation_to_latex(description: str, *, display: bool = True) -> dict:
    """Convert a natural-language or plain-text equation into LaTeX math.

    e.g. "sum from i=1 to n of i squared" → ``\\sum_{i=1}^{n} i^{2}``.
    Returns ``{latex, wrapped}`` where ``wrapped`` is inside an equation/inline env.
    Falls back to a lightly-massaged version of the input if no LLM is available.
    """
    description = (description or "").strip()
    if not description:
        return {"latex": "", "wrapped": ""}

    latex = _equation_via_llm(description)
    if not latex:
        latex = _equation_fallback(description)

    if display:
        wrapped = f"\\begin{{equation}}\n{latex}\n\\end{{equation}}"
    else:
        wrapped = f"${latex}$"
    return {"latex": latex, "wrapped": wrapped}


def _equation_via_llm(description: str) -> str | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from agno.agent import Agent
        from agno.models.groq import Groq as AgnoGroq

        agent = Agent(
            name="EquationAgent",
            model=AgnoGroq(
                id=os.getenv("TOOLKIT_MODEL") or os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
                api_key=api_key,
            ),
            instructions=(
                "You convert a description of a mathematical expression into a "
                "single line of LaTeX math (the part that goes between $...$). "
                "Return ONLY the LaTeX math, no $ delimiters, no \\begin{equation}, "
                "no markdown fences, no explanation."
            ),
            markdown=False,
        )
        result = agent.run(description)
        out = (result.content or "").strip()
        out = re.sub(r"```[a-zA-Z]*\n?", "", out).replace("```", "").strip()
        out = out.strip("$").strip()
        return out or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("equation LLM conversion failed: %s", exc)
        return None


def _equation_fallback(description: str) -> str:
    """Very small deterministic transform for when no LLM is configured."""
    s = description
    s = re.sub(r"\bsqrt\s*\(([^)]+)\)", r"\\sqrt{\1}", s)
    s = s.replace("*", r" \cdot ")
    s = re.sub(r"\b(alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|omega)\b",
               r"\\\1", s)
    s = re.sub(r"\^(\w+)", r"^{\1}", s)
    return s


# ──────────────────────────────────────────────────────────────
#  references_to_bibtex   (delegates to bibtex.py)
# ──────────────────────────────────────────────────────────────

def references_to_bibtex(references: str, *, enrich: bool = False) -> dict:
    """Convert a block of references into BibTeX. See bibtex.references_to_bibtex."""
    return _references_to_bibtex(references, enrich=enrich)


# ──────────────────────────────────────────────────────────────
#  document_to_latex   (Word / PDF / TXT → LaTeX)
# ──────────────────────────────────────────────────────────────

def document_to_latex(file_path: str | Path, *, style: str = "article") -> dict:
    """Parse a DOCX / PDF / TXT file into a full, compilable LaTeX document via the
    deepscan IngestAgent + the deterministic DocIR→LaTeX serializer.

    Returns ``{latex, assets, style, elements}``. ``assets`` are image filenames
    the document references (written next to the source under ``<stem>_assets/`` by
    the ingest layer when image extraction is wired; v1 emits names only).
    """
    from ..deepscan.agents.ingest import IngestAgent

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    docir = IngestAgent().parse(path)
    latex, assets = docir_to_latex(docir, style=normalize_style(style))
    return {
        "latex": latex,
        "assets": assets,
        "style": normalize_style(style),
        "elements": len(docir.elements),
    }


# ──────────────────────────────────────────────────────────────
#  latex_export   (LaTeX → PDF / DOCX / Markdown)
# ──────────────────────────────────────────────────────────────

def latex_export(latex: str, *, to: str = "pdf", assets_dir: str | Path | None = None) -> dict:
    """Export LaTeX to another format.

    - ``to="pdf"``  → tectonic (reuses deepscan.latex_compile).
    - ``to="docx"`` / ``to="md"`` → pandoc via pypandoc.

    Returns ``{ok, fmt, data (bytes) | None, mimetype, log, notes}``.
    """
    to = (to or "pdf").lower().lstrip(".")
    if to == "pdf":
        from ..deepscan.latex_compile import compile_with_repair

        adir = Path(assets_dir) if assets_dir else None
        result = compile_with_repair(latex, assets_dir=adir, allow_llm_repair=True)
        return {
            "ok": result.ok,
            "fmt": "pdf",
            "data": result.pdf_bytes if result.ok else None,
            "mimetype": "application/pdf",
            "log": result.log,
            "notes": result.notes,
        }

    if to in ("docx", "md", "markdown"):
        target = "docx" if to == "docx" else "markdown"
        ext = "docx" if to == "docx" else "md"
        mimetype = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if to == "docx" else "text/markdown"
        )
        try:
            import tempfile

            import pypandoc
            with tempfile.TemporaryDirectory(prefix="pandoc_") as tmp:
                out_path = Path(tmp) / f"out.{ext}"
                pypandoc.convert_text(
                    latex, target, format="latex", outputfile=str(out_path),
                    extra_args=["--standalone"] if to == "docx" else [],
                )
                data = out_path.read_bytes()
            return {"ok": True, "fmt": to, "data": data, "mimetype": mimetype,
                    "log": "", "notes": []}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "fmt": to, "data": None, "mimetype": mimetype,
                    "log": f"pandoc export failed (is pandoc installed?): {exc}",
                    "notes": []}

    return {"ok": False, "fmt": to, "data": None, "mimetype": "application/octet-stream",
            "log": f"Unsupported export target: {to}", "notes": []}


# ──────────────────────────────────────────────────────────────
#  template library
# ──────────────────────────────────────────────────────────────

def list_templates() -> dict:
    """List available starter .tex templates."""
    items = []
    if TEMPLATES_DIR.is_dir():
        for f in sorted(TEMPLATES_DIR.glob("*.tex")):
            items.append({
                "id": f.stem,
                "name": f.stem.replace("_", " ").title(),
                "filename": f.name,
            })
    return {"templates": items, "styles": available_styles()}


def get_template(template_id: str) -> dict:
    """Return the raw .tex content of a starter template by id."""
    safe = re.sub(r"[^A-Za-z0-9_\-]", "", template_id or "")
    path = TEMPLATES_DIR / f"{safe}.tex"
    if not path.is_file():
        raise FileNotFoundError(f"No template '{template_id}'")
    return {"id": safe, "filename": path.name, "latex": path.read_text(encoding="utf-8")}
