"""
Deterministic LaTeX from a labelled DocIR.

Stage 1 already knows what every paragraph is (title, author line, abstract,
heading, body, caption, reference ...). This module turns that into a LaTeX
document directly, so the structure and every word of the manuscript are
guaranteed to survive. The LLM is only used afterwards, paragraph group by
paragraph group, to polish what it is good at (maths, species names), and its
output is discarded whenever it drops content (see agno_router).

Public API:
    build_document(docir, style, raw_docir=None) -> BuiltDocument
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .schemas.docir import DocElement, DocIR, ElementRole, ElementType

# ── Text escaping ────────────────────────────────────────────

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}

# Characters the default fonts cannot show (Greek, symbols) become macros;
# typographic punctuation becomes its TeX spelling.
_UNICODE = {
    "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$", "δ": r"$\delta$",
    "ε": r"$\varepsilon$", "ζ": r"$\zeta$", "η": r"$\eta$", "θ": r"$\theta$",
    "κ": r"$\kappa$", "λ": r"$\lambda$", "μ": r"$\mu$", "µ": r"$\mu$",
    "ν": r"$\nu$", "ξ": r"$\xi$", "π": r"$\pi$", "ρ": r"$\rho$",
    "σ": r"$\sigma$", "τ": r"$\tau$", "φ": r"$\phi$", "χ": r"$\chi$",
    "ψ": r"$\psi$", "ω": r"$\omega$",
    "Δ": r"$\Delta$", "Γ": r"$\Gamma$", "Θ": r"$\Theta$", "Λ": r"$\Lambda$",
    "Σ": r"$\Sigma$", "Φ": r"$\Phi$", "Ψ": r"$\Psi$", "Ω": r"$\Omega$",
    "≤": r"$\leq$", "≥": r"$\geq$", "±": r"$\pm$", "×": r"$\times$",
    "÷": r"$\div$", "≈": r"$\approx$", "≠": r"$\neq$", "∞": r"$\infty$",
    "→": r"$\rightarrow$", "←": r"$\leftarrow$", "↔": r"$\leftrightarrow$",
    "∼": r"$\sim$", "·": r"$\cdot$", "−": r"$-$", "√": r"$\surd$",
    "°": r"$^{\circ}$", "′": r"$^{\prime}$", "″": r"$^{\prime\prime}$",
    "–": "--", "—": "---", "…": r"\ldots{}",
    "‐": "-", "‑": "-", "‒": "--", "―": "---",   # hyphen/dash variants
    "‘": "`", "’": "'", "“": "``", "”": "''",
    "\u00a0": "~", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
    "\u00ad": "", "\u2028": " ", "\u2029": " ",
    "™": r"\texttrademark{}", "®": r"\textregistered{}", "©": r"\copyright{}",
    "€": r"\euro{}", "£": r"\pounds{}", "§": r"\S{}", "¶": r"\P{}",
}

_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2028\u2029]")


def normalize_unicode(latex: str) -> str:
    """Replace characters the fonts cannot print in text that is ALREADY
    LaTeX (no escaping of TeX specials): used on the model's polished output,
    which sometimes brings back a non-breaking hyphen or a Greek letter."""
    return "".join(_UNICODE.get(ch, ch) for ch in latex)


def escape(text: str) -> str:
    """Escape plain text for LaTeX. Idempotent on already-plain text only."""
    out: list[str] = []
    for ch in text:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ch in _UNICODE:
            out.append(_UNICODE[ch])
        else:
            out.append(ch)
    return "".join(out)


# ── Citations ────────────────────────────────────────────────

_NUM_LIST_RE = re.compile(r"^\(?\s*(\d{1,3}(?:\s*[,;–\-]\s*\d{1,3})*)\s*\)?$")
_REF_PREFIX_RE = re.compile(r"^\s*\[?(\d{1,3})[\.\)\]]\s*")


def citation_numbers(text: str) -> list[int]:
    """'1,2' -> [1, 2]; '(9–12)' -> [9, 10, 11, 12]; anything else -> []."""
    m = _NUM_LIST_RE.match(text.strip())
    if not m:
        return []
    nums: list[int] = []
    for part in re.split(r"[,;]", m.group(1)):
        part = part.strip()
        rng = re.match(r"^(\d{1,3})\s*[–\-]\s*(\d{1,3})$", part)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if a <= b <= a + 50:
                nums.extend(range(a, b + 1))
        elif part.isdigit():
            nums.append(int(part))
    return nums


def cite_key(n: int) -> str:
    return f"ref{n}"


_PAREN_CITE_RE = re.compile(r"\((\d{1,3}(?:\s*[,;–\-]\s*\d{1,3})*)\)")
_SUP_CITE_RE = re.compile(r"\d{1,3}(?:\s*[,;–\-]\s*\d{1,3})*")
_FIG_TABLE_PREFIX_RE = re.compile(r"(?:Fig\.?|Figure|Table|Tab\.?|Eq\.?)\s*$", re.IGNORECASE)


# ── Inline rendering (runs -> \textit etc., citations -> \cite) ──

@dataclass
class _Span:
    text: str
    italic: bool = False
    bold: bool = False
    sup: bool = False
    sub: bool = False


def _styled_spans(elem: DocElement) -> Optional[list[_Span]]:
    """Per-run spans when the runs still line up with the content, else None.

    Runs and content drift apart when other passes edited the text (invisible
    characters stripped, lines merged without their runs), in which case the
    caller falls back to plain text rather than mis-place formatting.
    """
    if not elem.runs:
        return None
    spans = [
        _Span(_INVISIBLE_RE.sub("", r.text), bool(r.italic), bool(r.bold),
              bool(r.superscript), bool(r.subscript))
        for r in elem.runs
    ]
    joined = "".join(s.text for s in spans)
    content = _INVISIBLE_RE.sub("", elem.content)
    if joined.strip() != content.strip():
        return None
    # Align to the stripped content (leading/trailing whitespace is dropped).
    lead = len(joined) - len(joined.lstrip())
    trail = len(joined) - len(joined.rstrip())
    return _trim_spans(spans, lead, trail)


def _trim_spans(spans: list[_Span], lead: int, trail: int) -> list[_Span]:
    out: list[_Span] = []
    for s in spans:
        if not s.text:
            continue
        out.append(s)
    # drop `lead` chars from the front
    while lead > 0 and out:
        if len(out[0].text) <= lead:
            lead -= len(out[0].text)
            out.pop(0)
        else:
            out[0].text = out[0].text[lead:]
            lead = 0
    while trail > 0 and out:
        if len(out[-1].text) <= trail:
            trail -= len(out[-1].text)
            out.pop()
        else:
            out[-1].text = out[-1].text[:-trail]
            trail = 0
    return out


def render_inline(elem: DocElement, max_ref: int) -> str:
    """LaTeX for one paragraph's text: formatting from runs, numeric citations
    (parenthetical or superscript) as \\cite{refN} when N is a known entry."""
    content = _INVISIBLE_RE.sub("", elem.content).strip()
    if not content:
        return ""

    # Character-level style flags.
    n = len(content)
    italic = [False] * n
    bold = [False] * n
    sup = [False] * n
    sub = [False] * n
    spans = _styled_spans(elem)
    if spans:
        pos = 0
        for s in spans:
            for i in range(pos, min(n, pos + len(s.text))):
                italic[i], bold[i], sup[i], sub[i] = s.italic, s.bold, s.sup, s.sub
            pos += len(s.text)

    # Citation spans: (start, end, replacement). Found on the text itself,
    # because the offsets recorded before line merging no longer apply.
    #   - parenthetical numerals "(1)", "(6, 7)", "(9–12)" (not "Fig. 2", "Table 1")
    #   - superscript numerals from the runs: survival^{1,2}
    cites: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []

    def add(start: int, end: int, text: str) -> None:
        nums = citation_numbers(text)
        if not nums or any(k < 1 or k > max_ref for k in nums):
            return
        if any(a < end and start < b for a, b in taken):
            return
        taken.append((start, end))
        cites.append((start, end, "\cite{" + ",".join(cite_key(k) for k in nums) + "}"))

    for m in _PAREN_CITE_RE.finditer(content):
        if _FIG_TABLE_PREFIX_RE.search(content[max(0, m.start() - 8):m.start()]):
            continue
        add(m.start(), m.end(), m.group(0))
    if spans:
        pos = 0
        for s in spans:
            if s.sup and _SUP_CITE_RE.fullmatch(s.text.strip()):
                lead = len(s.text) - len(s.text.lstrip())
                add(pos + lead, pos + lead + len(s.text.strip()), s.text.strip())
            pos += len(s.text)
    cites.sort()

    # Emit, grouping runs of equal style, splicing citations in.
    out: list[str] = []
    i = 0
    ci = 0

    def flush(seg_start: int, seg_end: int) -> None:
        j = seg_start
        while j < seg_end:
            k = j
            while (k < seg_end and italic[k] == italic[j] and bold[k] == bold[j]
                   and sup[k] == sup[j] and sub[k] == sub[j]):
                k += 1
            piece = escape(content[j:k])
            if sup[j]:
                piece = "\\textsuperscript{" + piece + "}"
            elif sub[j]:
                piece = "\\textsubscript{" + piece + "}"
            if bold[j] and piece.strip():
                piece = "\\textbf{" + piece + "}"
            if italic[j] and piece.strip():
                piece = "\\textit{" + piece + "}"
            out.append(piece)
            j = k

    while i < n:
        if ci < len(cites) and cites[ci][0] == i:
            start, end, rep = cites[ci]
            out.append(rep)
            i = end
            ci += 1
        else:
            nxt = cites[ci][0] if ci < len(cites) else n
            flush(i, nxt)
            i = nxt
    return "".join(out)


# ── Front matter helpers ─────────────────────────────────────

_EDITORIAL_RE = re.compile(
    r"^(Edited by|Received|Approved|Accepted|Submitted|Published|Revised|"
    r"Communicated by|Contributed by|Author contributions|The authors declare)",
    re.IGNORECASE,
)
_DATE_FRAGMENT_RE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}\)?\.?$")
_MARKER_RE = re.compile(r"^[a-z]$|^\d{1,2}$")


def author_block(author_lines: list[str]) -> str:
    """Join the raw author-zone lines into an \\author{} body.

    Editorial metadata ("Edited by ...", dates) is not part of the author
    block; single-letter affiliation markers become superscripts on the
    following affiliation line; comma/"and" fragments continue the name line.
    """
    lines: list[str] = []
    pending_marker = ""
    for raw in author_lines:
        t = _INVISIBLE_RE.sub("", raw).strip()
        if not t:
            continue
        if _EDITORIAL_RE.match(t) or _DATE_FRAGMENT_RE.match(t):
            continue
        if _MARKER_RE.match(t):
            pending_marker = t
            continue
        if len(t.split()) <= 2 and t[0].islower():   # stray fragment ("as well")
            continue
        if lines and (t.startswith(",") or t.startswith("and ")):
            lines[-1] = lines[-1] + (t if t.startswith(",") else " " + t)
            continue
        if pending_marker:
            t = f"\x01{pending_marker}\x02" + t
            pending_marker = ""
        lines.append(t)
    rendered = []
    for ln in lines:
        s = escape(ln)
        s = re.sub("\x01(.+?)\x02", r"\\textsuperscript{\1}", s)
        # "Sadia Ahmad a ," / "Islam a,b ," -> affiliation markers as superscripts
        s = re.sub(r"(?<=[A-Za-z.])\s+([a-z](?:,[a-z0-9])*|\d)(?=\s*(?:,|$|\s+and\b))",
                   r"\\textsuperscript{\1}", s)
        rendered.append(_break_long_line(s))
    return "\\\\\n".join(rendered)


def _break_long_line(s: str, width: int = 78) -> str:
    r"""\author{} is typeset in an unbreakable box (IEEEtran and article
    alike), so a long affiliation line runs off the column; break it at
    spaces instead."""
    if len(s) <= width:
        return s
    out, line = [], ""
    for word in s.split(" "):
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    out.append(line)
    return "\\\\\n".join(out)


_CAPTION_PREFIX_RE = re.compile(r"^(?:Fig\.?|Figure|Table|Tab\.?)\s*\d+[\.:]?\s*", re.IGNORECASE)


def caption_text(latex: str) -> str:
    """Drop the source's own 'Fig. 3.' prefix: \caption adds the label itself."""
    return _CAPTION_PREFIX_RE.sub("", latex, count=1)


def heading_text(text: str) -> str:
    """Drop any numbering the source carried; LaTeX numbers sections itself."""
    return re.sub(r"^(?:[IVXLC]+|[A-Za-z]|\d+(?:\.\d+)*)[\.\)]\s+", "", text.strip())


# ── Document assembly ────────────────────────────────────────

@dataclass
class Block:
    """One unit of the body. `kind` is section | para | figure | table | raw.
    Only `para` blocks are offered to the LLM for polishing."""
    kind: str
    latex: str
    words: int = 0


@dataclass
class BuiltDocument:
    title: str = ""
    author: str = ""
    abstract: str = ""
    keywords: str = ""
    blocks: list[Block] = field(default_factory=list)
    bibliography: str = ""
    ref_count: int = 0
    # figure number -> caption text, for figures that have an image
    captions: dict[int, str] = field(default_factory=dict)

    def body(self) -> str:
        return "\n\n".join(b.latex for b in self.blocks if b.latex)


def _word_count(s: str) -> int:
    return len(s.split())


def _figure_only_caption(caption: str) -> str:
    """A caption with no image in the source: keep it as a labelled float so
    it appears in place (and compiles) instead of vanishing into body text."""
    return (
        "\\begin{figure}[htbp]\n\\centering\n"
        f"\\caption{{{caption}}}\n\\end{{figure}}"
    )


def _table_block(elem: DocElement) -> str:
    td = elem.table_data
    if not td or not td.rows:
        return ""
    ncols = max(len(r) for r in td.rows)
    spec = "|" + "|".join(["l"] * ncols) + "|"
    lines = [f"\\begin{{tabular}}{{{spec}}}", "\\hline"]
    for r_i, row in enumerate(td.rows):
        cells = []
        for c in row:
            txt = escape(_INVISIBLE_RE.sub("", c.text).strip())
            if r_i == 0 or c.bold:
                txt = "\\textbf{" + txt + "}"
            cells.append(txt)
        cells += [""] * (ncols - len(cells))
        lines.append(" & ".join(cells) + " \\\\")
        lines.append("\\hline")
    lines.append("\\end{tabular}")
    cap = f"\\caption{{{escape(elem.caption)}}}\n" if elem.caption else ""
    return "\\begin{table}[htbp]\n\\centering\n" + cap + "\n".join(lines) + "\n\\end{table}"


def build_document(docir: DocIR, style: str, raw_docir: Optional[DocIR] = None) -> BuiltDocument:
    """Assemble a BuiltDocument from a labelled (and line-merged) DocIR.

    `raw_docir` (pre-merge) gives the individual author-zone lines, which the
    merge step collapses into one string that cannot be split reliably.
    """
    doc = BuiltDocument()
    live = [e for e in docir.elements
            if e.type != ElementType.PARAGRAPH or e.content.strip()]

    refs = [e for e in live if e.role == ElementRole.REFERENCE_ENTRY]
    doc.ref_count = len(refs)

    # Title
    titles = [e.content.strip() for e in live if e.role == ElementRole.TITLE]
    doc.title = escape(" ".join(titles))

    # Authors (from the un-merged lines when available)
    src = raw_docir or docir
    author_lines = [e.content for e in src.elements if e.role == ElementRole.AUTHOR_INFO]
    doc.author = author_block(author_lines)

    # Abstract, keywords
    abstract_parts = [render_inline(e, doc.ref_count) for e in live
                      if e.role == ElementRole.ABSTRACT_BODY]
    doc.abstract = "\n\n".join(p for p in abstract_parts if p)
    kw = " ".join(e.content.strip() for e in live if e.role == ElementRole.KEYWORDS)
    kw = re.sub(r"^\s*(index terms|keywords?)\s*[:\-–—]\s*", "", kw, flags=re.IGNORECASE)
    kw = ", ".join(p.strip() for p in re.split(r"\s*[|;]\s*", kw) if p.strip())
    doc.keywords = escape(kw)

    # Body
    front = {ElementRole.TITLE, ElementRole.AUTHOR_INFO, ElementRole.ABSTRACT_LABEL,
             ElementRole.ABSTRACT_BODY, ElementRole.KEYWORDS,
             ElementRole.REFERENCE_LABEL, ElementRole.REFERENCE_ENTRY}
    level_cmd = {ElementRole.HEADING_1: "section", ElementRole.HEADING_2: "subsection",
                 ElementRole.HEADING_3: "subsubsection", ElementRole.APPENDIX: "section"}
    skip_next_caption = False
    for idx, e in enumerate(live):
        if e.role in front:
            continue
        if e.type == ElementType.TABLE:
            tb = _table_block(e)
            if tb:
                doc.blocks.append(Block("table", tb))
            continue
        if e.type != ElementType.PARAGRAPH:
            continue
        text = e.content.strip()
        if e.figure_number:
            # An image lives in this paragraph: leave the token the figure
            # injector understands; the next caption (if any) belongs to it.
            n = e.figure_number
            nxt = live[idx + 1] if idx + 1 < len(live) else None
            if nxt is not None and nxt.role == ElementRole.FIGURE_CAPTION:
                doc.captions[n] = caption_text(escape(_INVISIBLE_RE.sub("", nxt.content).strip()))
                skip_next_caption = True
            doc.blocks.append(Block("raw", f"[[FIGURE_{n}]]"))
            if text and e.role not in (ElementRole.FIGURE_CAPTION, ElementRole.FIGURE):
                doc.blocks.append(Block("para", render_inline(e, doc.ref_count), _word_count(text)))
            continue
        if e.role in level_cmd:
            doc.blocks.append(Block("section", f"\\{level_cmd[e.role]}{{{escape(heading_text(text))}}}"))
        elif e.role == ElementRole.FIGURE_CAPTION:
            if skip_next_caption:
                skip_next_caption = False
                continue
            doc.blocks.append(Block("figure", _figure_only_caption(caption_text(render_inline(e, doc.ref_count)))))
        elif e.role == ElementRole.TABLE_CAPTION:
            doc.blocks.append(Block("raw", "\\noindent\\textbf{" + render_inline(e, doc.ref_count) + "}"))
        elif e.role == ElementRole.FIGURE:
            continue
        else:  # body, block quote, unknown-but-has-text
            latex = render_inline(e, doc.ref_count)
            if e.role == ElementRole.BLOCK_QUOTE:
                latex = "\\begin{quote}\n" + latex + "\n\\end{quote}"
            doc.blocks.append(Block("para", latex, _word_count(text)))

    # References, in source order so \cite{refN} means entry N.
    if refs:
        items = []
        for i, e in enumerate(refs, start=1):
            body = _REF_PREFIX_RE.sub("", _INVISIBLE_RE.sub("", e.content).strip())
            items.append(f"\\bibitem{{{cite_key(i)}}} {escape(body)}")
        width = "99" if len(refs) < 100 else "999"
        doc.bibliography = (
            f"\\begin{{thebibliography}}{{{width}}}\n" + "\n\n".join(items) + "\n\\end{thebibliography}"
        )
    return doc


def assemble(doc: BuiltDocument, preamble: str, style: str, body: Optional[str] = None) -> str:
    """Full .tex text from a BuiltDocument plus a style preamble. `body`
    overrides doc.body() (used after figure injection)."""
    parts = [preamble.rstrip(), "\\begin{document}", ""]
    if doc.title:
        parts.append(f"\\title{{{doc.title}}}")
    if doc.author:
        parts.append("\\author{" + doc.author + "}")
    if doc.title or doc.author:
        parts.append("\\maketitle")
    parts.append("")
    if doc.abstract:
        parts += ["\\begin{abstract}", doc.abstract, "\\end{abstract}", ""]
    if doc.keywords:
        if style.lower() == "ieee":
            parts += ["\\begin{IEEEkeywords}", doc.keywords, "\\end{IEEEkeywords}", ""]
        else:
            parts += ["\\noindent\\textbf{Keywords:} " + doc.keywords, ""]
    parts.append(doc.body() if body is None else body)
    if doc.bibliography:
        parts += ["", doc.bibliography]
    parts += ["", "\\end{document}", ""]
    return "\n".join(parts)
