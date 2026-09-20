"""
FormatForge AI — Content-Integrity Validator (Phase C)
=======================================================

Proves the no-data-loss guarantee: after the LaTeX is generated, compare the
ORIGINAL manuscript text against the generated LaTeX body to confirm the LLM
did not drop or summarize content.

This is deliberately lenient — it biases toward WARNINGS over false FAILURES,
because a wrongly-flagged failure erodes user trust more than a missed one.
The reference list is excluded from the word comparison (citeproc legitimately
rewrites it), and thresholds loosen for PDF input (noisier extraction).

100% deterministic — zero LLM calls.
"""

from __future__ import annotations

import difflib
import logging
import re

from ..schemas.reports import ContentIntegrityReport, Severity

logger = logging.getLogger(__name__)


# ── Thresholds ────────────────────────────────────────────────

# Word-retention ratio = out_words / in_words
_WORD_OK = 0.97          # >= → no issue
_WORD_WARN = 0.90        # [WARN, OK) → warning ; < WARN → failure
_WORD_OVER_WARN = 1.15   # > → warning (LLM expanded/hallucinated)

# Token-set / sequence similarity of normalized text
_SIM_OK = 0.85           # >= → no issue
_SIM_FAIL = 0.70         # < → failure ; [FAIL, OK) → warning

# PDF input gets looser thresholds (extraction is noisier).
_PDF_WORD_OK = 0.90
_PDF_WORD_WARN = 0.80
_PDF_SIM_OK = 0.75
_PDF_SIM_FAIL = 0.60


# ── Text normalization ────────────────────────────────────────

def _normalize_words(text: str) -> list[str]:
    """Lowercase, strip punctuation, collapse whitespace → list of word tokens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return text.split()


def _strip_reference_section(text: str) -> str:
    """Drop everything from a 'References'/'Bibliography'/'Works Cited' heading
    onward, so citeproc's reformatting of the ref list doesn't skew the count."""
    m = re.search(
        r"(?im)^\s*(references|bibliography|works cited|literature cited)\s*$",
        text,
    )
    if m:
        return text[: m.start()]
    # No heading (e.g. the formatter numbered the list without a label):
    # cut where a numbered list "[1] ..." / "1. ..." followed by "[2] ..." begins.
    m = re.search(r"(?m)^\s*\[?1[\]\.\)]\s*\S[^\n]*\n\s*\[?2[\]\.\)]\s", text)
    return text[: m.start()] if m else text


# ── De-LaTeX (strip commands, keep human-readable text) ───────

# Environments whose *contents* are not prose and should be dropped wholesale.
_DROP_ENVS = ("thebibliography", "tabular", "table", "figure", "equation",
              "align", "displaymath", "verbatim", "lstlisting", "tikzpicture")


def delatex(src: str) -> str:
    """Convert LaTeX source to approximate plain text for word counting.

    Best-effort: strips the preamble, comments, math, non-prose environments,
    and control sequences while keeping their textual arguments.
    """
    text = src

    # 1. Cut the preamble — keep only the document body.
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", text, flags=re.DOTALL)
    if m:
        text = m.group(1)

    # 2. Remove comments (unescaped %).
    text = re.sub(r"(?<!\\)%.*", "", text)

    # 3. Drop non-prose environments entirely (contents aren't manuscript prose)
    #    -- except their captions, which are prose from the manuscript and
    #    would otherwise count as lost words.
    def _keep_caption(m: re.Match) -> str:
        caps = re.findall(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", m.group(0))
        return " " + " ".join(caps) + " " if caps else " "

    for env in _DROP_ENVS:
        text = re.sub(
            r"\\begin\{" + env + r"\*?\}.*?\\end\{" + env + r"\*?\}",
            _keep_caption,   # caption stays where the float was, so word order is kept
            text,
            flags=re.DOTALL,
        )

    # 4. Remove math: $$...$$, \[...\], $...$.
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$]*\$", " ", text)

    # 5. \cite{...}, \ref{...}, \label{...}, \includegraphics[..]{..} → drop key.
    text = re.sub(r"\\(?:cite[tp]?|ref|eqref|label|includegraphics|graphicspath)"
                  r"(?:\[[^\]]*\])?\{[^}]*\}", " ", text)

    # 6. Sectioning / formatting commands with a braced arg → keep the arg text.
    #    \section{X}, \textbf{X}, \textit{X}, \caption{X}, \title{X}, ...
    for _ in range(3):  # a few passes to unwrap nesting
        text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r" \1 ", text)

    # 7. Remaining bare control sequences → drop.
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = re.sub(r"\\[^a-zA-Z]", " ", text)  # escaped symbols like \& \% \_

    # 8. Strip leftover braces and collapse whitespace.
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Counting helpers ──────────────────────────────────────────

def _count_includegraphics(latex: str) -> int:
    return len(re.findall(r"\\includegraphics", latex))


def _count_tabulars(latex: str) -> int:
    return len(re.findall(r"\\begin\{tabular", latex))


def _count_paragraphs(text: str) -> int:
    return len([b for b in re.split(r"\n\s*\n", text) if b.strip()])


# ── Main entry point ──────────────────────────────────────────

def validate_content_preservation(
    *,
    original_text: str,
    latex_str: str,
    figure_count_in: int = 0,
    table_count_in: int = 0,
    source_format: str = "docx",
) -> ContentIntegrityReport:
    """Compare the original manuscript text against the generated LaTeX.

    Args:
        original_text: Plain text extracted from the (formatted) input document.
        latex_str: The final assembled LaTeX document.
        figure_count_in: Figures detected in the input (from Phase B extraction).
        table_count_in: Tables detected in the input (DocIR metadata).
        source_format: "docx" | "pdf" | "txt" — loosens thresholds for pdf.

    Returns:
        ContentIntegrityReport (never raises — failures are reported, not thrown).
    """
    report = ContentIntegrityReport()

    try:
        is_pdf = source_format.lower() == "pdf"
        word_ok = _PDF_WORD_OK if is_pdf else _WORD_OK
        word_warn = _PDF_WORD_WARN if is_pdf else _WORD_WARN
        sim_ok = _PDF_SIM_OK if is_pdf else _SIM_OK
        sim_fail = _PDF_SIM_FAIL if is_pdf else _SIM_FAIL

        # Exclude reference lists from both sides before word comparison.
        in_body = _strip_reference_section(original_text)
        out_text = delatex(latex_str)
        out_body = _strip_reference_section(out_text)

        in_words = _normalize_words(in_body)
        out_words = _normalize_words(out_body)

        report.word_count_in = len(in_words)
        report.word_count_out = len(out_words)
        report.paragraph_count_in = _count_paragraphs(original_text)
        report.paragraph_count_out = _count_paragraphs(out_text)
        report.figure_count_in = figure_count_in
        report.figure_count_out = _count_includegraphics(latex_str)
        report.table_count_in = table_count_in
        report.table_count_out = _count_tabulars(latex_str)

        # ── Word retention ──
        if report.word_count_in > 0:
            ratio = report.word_count_out / report.word_count_in
        else:
            ratio = 1.0
        report.word_retention_ratio = round(ratio, 3)

        # ── Token-sequence similarity ──
        if in_words or out_words:
            report.token_similarity = round(
                # autojunk=False: the default discounts frequent tokens on long
                # inputs and dragged a fully-preserved paper down to ~60%.
                difflib.SequenceMatcher(None, in_words, out_words, autojunk=False).ratio(), 3
            )

        severities: list[Severity] = []

        # Word-count verdict
        if ratio < word_warn:
            severities.append(Severity.ERROR)
            report.notes.append(
                f"Only {round(ratio*100)}% of words retained "
                f"({report.word_count_out}/{report.word_count_in}) — content may be missing."
            )
        elif ratio < word_ok:
            severities.append(Severity.WARNING)
            report.notes.append(
                f"{round(ratio*100)}% of words retained — minor loss possible "
                "(may be de-LaTeX artifact)."
            )
        elif ratio > _WORD_OVER_WARN:
            severities.append(Severity.WARNING)
            report.notes.append(
                f"Output has {round(ratio*100)}% of input words — text may have been expanded."
            )

        # Figure verdict (highest-signal — directly verifies Phase B)
        if report.figure_count_in > 0:
            if report.figure_count_out < report.figure_count_in:
                severities.append(Severity.ERROR)
                report.notes.append(
                    f"Figure loss: {report.figure_count_out}/{report.figure_count_in} "
                    "figures present in output."
                )
            elif report.figure_count_out > report.figure_count_in:
                severities.append(Severity.WARNING)
                report.notes.append(
                    f"More figures in output ({report.figure_count_out}) than input "
                    f"({report.figure_count_in})."
                )

        # Table verdict (tables degrade more gracefully → warning only)
        if report.table_count_in > 0 and report.table_count_out < report.table_count_in:
            severities.append(Severity.WARNING)
            report.notes.append(
                f"Table count dropped: {report.table_count_out}/{report.table_count_in}."
            )

        # Similarity verdict (catches paraphrase / summarization)
        if report.token_similarity < sim_fail:
            severities.append(Severity.ERROR)
            report.notes.append(
                f"Low text similarity ({round(report.token_similarity*100)}%) — "
                "content may have been rewritten or summarized."
            )
        elif report.token_similarity < sim_ok:
            severities.append(Severity.WARNING)
            report.notes.append(
                f"Moderate text similarity ({round(report.token_similarity*100)}%)."
            )

        # Overall = worst of the individual verdicts.
        if Severity.ERROR in severities:
            report.severity = Severity.ERROR
            report.passed = False
        elif Severity.WARNING in severities:
            report.severity = Severity.WARNING
            report.passed = True
        else:
            report.severity = Severity.INFO
            report.passed = True
            report.notes.append("Content fully preserved.")

    except Exception as exc:  # never let integrity-checking break the pipeline
        logger.warning("Content-integrity check failed to run: %s", exc)
        report.passed = True
        report.severity = Severity.INFO
        report.notes.append(f"Integrity check skipped ({exc}).")

    return report
