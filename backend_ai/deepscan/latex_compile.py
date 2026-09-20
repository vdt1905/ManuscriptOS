"""
FormatForge AI — Local LaTeX Compilation + Auto-Correct (Phase D)
==================================================================

Replaces the unreliable texlive.net round-trip with a self-hosted compile:

    autofix_latex()   — deterministic repair of common LaTeX mistakes, run
                        BEFORE every compile so the preview rarely errors.
    compile_latex()   — write main.tex + assets/ to a temp dir, run *tectonic*
                        (a single-binary LaTeX engine), return the PDF bytes.
    llm_repair_latex()— optional one-shot LLM fix when tectonic still errors.

Tectonic is preferred because it is one static binary, bundles TeX, and fetches
+ caches packages on demand (no multi-GB TeX Live install). If tectonic is not
on PATH, compile_latex() reports that clearly so callers can fall back.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_COMPILE_TIMEOUT_S = int(os.getenv("LATEX_COMPILE_TIMEOUT", "120"))


# ───────────────────────────────────────────────────────────────
#  Auto-correct  (deterministic — no LLM)
# ───────────────────────────────────────────────────────────────

def autofix_latex(src: str) -> tuple[str, list[str]]:
    """Repair common LaTeX mistakes. Returns (fixed_src, notes).

    Conservative by design — only structural fixes that are safe across
    documents. Ported + hardened from the old frontend `sanitizeLatex`.
    """
    notes: list[str] = []
    text = src.strip()

    # 1. Strip markdown code fences the LLM sometimes wraps output in.
    if "```" in text:
        before = text
        text = re.sub(r"```[a-zA-Z]*\n?", "", text).replace("```", "")
        if text != before:
            notes.append("Removed stray markdown code fences.")

    # 2. Split preamble / body around the FIRST \begin{document}.
    begin_doc = re.search(r"\\begin\{document\}", text)
    if begin_doc:
        preamble = text[: begin_doc.start()]
        body = text[begin_doc.end():]
    else:
        # No document environment at all — wrap the whole thing.
        preamble = ""
        body = text
        notes.append("Added missing \\begin{document}/\\end{document}.")

    # Strip ANY stray document-env markers from the body — the single correct
    # pair is re-added during final assembly. (Chunked LLM output sometimes
    # emits duplicate/nested \begin{document} which would break the compile.)
    if re.search(r"\\begin\{document\}|\\end\{document\}", body):
        body = re.sub(r"\\begin\{document\}", "", body)
        body = re.sub(r"\\end\{document\}", "", body)

    # 3. Ensure exactly one \documentclass (keep the first).
    doc_classes = re.findall(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}", preamble)
    if not doc_classes:
        preamble = "\\documentclass[12pt]{article}\n" + preamble
        notes.append("Added missing \\documentclass.")
    elif len(doc_classes) > 1:
        seen = {"n": 0}
        def _keep_first_dc(m: re.Match) -> str:
            seen["n"] += 1
            return m.group(0) if seen["n"] == 1 else ""
        preamble = re.sub(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}", _keep_first_dc, preamble)
        notes.append("Removed duplicate \\documentclass.")

    # 4. Hoist any \usepackage / \usetikzlibrary found in the BODY up to preamble.
    pkg_re = re.compile(r"\\(?:usepackage|usetikzlibrary)(?:\[[^\]]*\])?\{[^}]*\}")
    body_pkgs = pkg_re.findall(body)
    if body_pkgs:
        body = pkg_re.sub("", body)
        preamble = preamble.rstrip() + "\n" + "\n".join(body_pkgs) + "\n"
        notes.append(f"Hoisted {len(body_pkgs)} \\usepackage line(s) into the preamble.")

    # 5. Ensure graphicx is present if the body uses \includegraphics.
    if "\\includegraphics" in body and "graphicx" not in preamble:
        preamble = preamble.rstrip() + "\n\\usepackage{graphicx}\n"
        notes.append("Added missing \\usepackage{graphicx} for figures.")

    # 6. Balance environments in the body (\begin{x} … \end{x}).
    #    'document' excluded — handled by final assembly.
    begins = [e for e in re.findall(r"\\begin\{([^}]+)\}", body) if e != "document"]
    ends = [e for e in re.findall(r"\\end\{([^}]+)\}", body) if e != "document"]
    env_balance: dict[str, int] = {}
    for e in begins:
        env_balance[e] = env_balance.get(e, 0) + 1
    for e in ends:
        env_balance[e] = env_balance.get(e, 0) - 1
    suffix = ""
    for env, bal in env_balance.items():
        if bal > 0:
            suffix += f"\n\\end{{{env}}}" * bal
            notes.append(f"Closed {bal} unclosed \\begin{{{env}}}.")
    body = body + suffix

    # 7. Balance curly braces in the body (best-effort: append missing closers).
    depth = 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
    if depth > 0:
        body = body + ("}" * depth)
        notes.append(f"Balanced {depth} unclosed brace(s).")

    # 8. Ensure \nonstopmode so a recoverable error never hangs the compile.
    if "\\nonstopmode" not in preamble:
        preamble = "\\nonstopmode\n" + preamble

    fixed = f"{preamble.rstrip()}\n\\begin{{document}}\n{body.strip()}\n\\end{{document}}\n"
    return fixed, notes


# ───────────────────────────────────────────────────────────────
#  Compilation result
# ───────────────────────────────────────────────────────────────

@dataclass
class CompileResult:
    ok: bool
    pdf_bytes: bytes | None = None
    log: str = ""
    notes: list[str] = field(default_factory=list)
    engine: str = "tectonic"


def tectonic_available() -> bool:
    return shutil.which("tectonic") is not None


# ───────────────────────────────────────────────────────────────
#  Compile
# ───────────────────────────────────────────────────────────────

def compile_latex(
    latex: str,
    *,
    assets_dir: Path | None = None,
    autofix: bool = True,
) -> CompileResult:
    """Compile *latex* to PDF with tectonic.

    Args:
        latex: the LaTeX source.
        assets_dir: optional dir whose files are copied into the build's
            ``assets/`` subfolder so ``\\includegraphics{assets/figN.png}`` resolves.
        autofix: run autofix_latex() first (recommended).

    Returns:
        CompileResult — ok + pdf_bytes on success, else ok=False + log.
    """
    notes: list[str] = []
    src = latex
    if autofix:
        src, notes = autofix_latex(latex)

    if not tectonic_available():
        return CompileResult(
            ok=False,
            notes=notes,
            engine="tectonic",
            log=(
                "Local LaTeX engine (tectonic) is not installed on the server. "
                "Install tectonic or use the remote-compile fallback."
            ),
        )

    with tempfile.TemporaryDirectory(prefix="texbuild_") as tmp:
        build = Path(tmp)
        (build / "main.tex").write_text(src, encoding="utf-8")

        # Copy figure assets next to main.tex under assets/.
        if assets_dir and Path(assets_dir).is_dir():
            dest_assets = build / "assets"
            dest_assets.mkdir(exist_ok=True)
            for f in Path(assets_dir).iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(dest_assets / f.name))

        try:
            proc = subprocess.run(
                ["tectonic", "-X", "compile", "main.tex",
                 # SyncTeX is off unless --synctex is passed; it is a bare flag,
                 # and tectonic >= 0.17 rejects a value like "--synctex=0".
                 "--outdir", str(build), "--keep-logs"],
                cwd=str(build),
                capture_output=True,
                text=True,
                timeout=_COMPILE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(ok=False, notes=notes,
                                 log=f"Compilation timed out after {_COMPILE_TIMEOUT_S}s.")
        except FileNotFoundError:
            # Older tectonic without the `-X` subcommand interface.
            try:
                proc = subprocess.run(
                    ["tectonic", "main.tex"],
                    cwd=str(build), capture_output=True, text=True,
                    timeout=_COMPILE_TIMEOUT_S,
                )
            except Exception as e:
                return CompileResult(ok=False, notes=notes, log=f"tectonic invocation failed: {e}")

        pdf_path = build / "main.pdf"
        if pdf_path.exists():
            return CompileResult(
                ok=True,
                pdf_bytes=pdf_path.read_bytes(),
                notes=notes,
                log=(proc.stderr or "")[-4000:],
            )

        # Failure — return the tectonic log (stderr is where it writes errors).
        log = (proc.stderr or proc.stdout or "Unknown compilation error.")[-8000:]
        return CompileResult(ok=False, notes=notes, log=log)


# ───────────────────────────────────────────────────────────────
#  Optional LLM repair (one-shot) when tectonic still errors
# ───────────────────────────────────────────────────────────────

def llm_repair_latex(latex: str, error_log: str, model: str | None = None) -> str | None:
    """Ask a Groq agent to fix LaTeX that failed to compile. Returns repaired
    source, or None if repair is unavailable / fails."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from agno.agent import Agent
        from agno.models.groq import Groq as AgnoGroq

        agent = Agent(
            name="LaTeXRepairAgent",
            model=AgnoGroq(id=model or os.getenv("LATEX_MODEL", "openai/gpt-oss-120b"),
                          api_key=api_key),
            instructions=(
                "You fix broken LaTeX so it compiles with pdflatex/tectonic. "
                "Return ONLY the corrected, complete LaTeX document — no markdown "
                "fences, no commentary. Preserve ALL content; only fix syntax."
            ),
            markdown=False,
        )
        prompt = (
            f"The following LaTeX failed to compile.\n\n"
            f"=== ERROR LOG (tail) ===\n{error_log[-2000:]}\n\n"
            f"=== LATEX SOURCE ===\n{latex}\n\n"
            f"Return the corrected full LaTeX document."
        )
        result = agent.run(prompt)
        fixed = (result.content or "").strip()
        if "```" in fixed:
            fixed = re.sub(r"```[a-zA-Z]*\n?", "", fixed).replace("```", "").strip()
        m = re.search(r"(\\documentclass.*\\end\{document\})", fixed, re.DOTALL)
        return m.group(1) if m else (fixed or None)
    except Exception as e:
        logger.warning("LLM LaTeX repair failed: %s", e)
        return None


def compile_with_repair(
    latex: str,
    *,
    assets_dir: Path | None = None,
    allow_llm_repair: bool = True,
) -> CompileResult:
    """Compile; if it fails, optionally try one LLM repair pass and recompile."""
    result = compile_latex(latex, assets_dir=assets_dir, autofix=True)
    if result.ok or not allow_llm_repair:
        return result

    repaired = llm_repair_latex(latex, result.log)
    if not repaired:
        return result

    second = compile_latex(repaired, assets_dir=assets_dir, autofix=True)
    if second.ok:
        second.notes = result.notes + ["Auto-repaired LaTeX with AI after a compile error."]
        return second
    return result  # keep the first (its log is usually the most relevant)
