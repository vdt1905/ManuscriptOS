"""
LaTeX Toolkit — shared LaTeX helpers (Phase H)
================================================

Deterministic, dependency-light building blocks reused by every toolkit tool:

    escape_latex()      — escape text so it is safe in a LaTeX body.
    preamble_for()      — journal-style preamble (IEEE / ACM / Springer / APA / article).
    grid_to_tabular()   — a 2-D grid of strings → a ``tabular`` environment.
    docir_to_latex()    — a parsed DocIR document → a full, compilable LaTeX string,
                          reusing the figure/table handling proven in the deepscan pipeline.

Keeping these here (rather than importing deepscan internals) makes the toolkit a
self-contained, independently shippable product surface.
"""

from __future__ import annotations

import re

# ──────────────────────────────────────────────────────────────
#  Escaping
# ──────────────────────────────────────────────────────────────

# Applied in ONE pass (regex + lookup): sequential str.replace re-escaped the
# braces that the \textbackslash{} replacement itself inserted.
_ESCAPES: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_ESCAPE_RE = re.compile(r"[\\&%$#_{}~^]")


def escape_latex(text: str | None) -> str:
    """Escape LaTeX special characters in plain prose. Safe for table cells,
    captions, and body text. Does NOT attempt to preserve intentional math —
    callers that need math should pass it through verbatim."""
    if not text:
        return ""
    return _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group()], text)


# ──────────────────────────────────────────────────────────────
#  Journal-style preambles
# ──────────────────────────────────────────────────────────────

_COMMON_PACKAGES = (
    "\\usepackage[utf8]{inputenc}\n"
    "\\usepackage[T1]{fontenc}\n"
    "\\usepackage{graphicx}\n"
    "\\graphicspath{{assets/}{./}}\n"
    "\\usepackage{amsmath,amssymb}\n"
    "\\usepackage{booktabs}\n"
    "\\usepackage{hyperref}\n"
    "\\usepackage{url}\n"
)

# Each preamble is a complete header up to (but not including) \begin{document}.
# We avoid requiring third-party class files (IEEEtran, acmart, sn-jnl) that may
# not be in tectonic's bundle — instead we approximate each style with the stock
# `article`/`IEEEtran`-like layout so every document compiles out of the box.
_PREAMBLES: dict[str, str] = {
    "article": (
        "\\documentclass[11pt]{article}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        + _COMMON_PACKAGES
    ),
    "ieee": (
        # Two-column, 10pt — IEEE look without requiring IEEEtran.cls.
        "\\documentclass[10pt,twocolumn]{article}\n"
        "\\usepackage[margin=0.75in]{geometry}\n"
        + _COMMON_PACKAGES
    ),
    "acm": (
        "\\documentclass[10pt,twocolumn]{article}\n"
        "\\usepackage[margin=0.75in]{geometry}\n"
        + _COMMON_PACKAGES
    ),
    "springer": (
        "\\documentclass[11pt]{article}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        + _COMMON_PACKAGES
    ),
    "apa": (
        # APA7 manuscript: 12pt, 1in margins, double spaced.
        "\\documentclass[12pt]{article}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        "\\usepackage{setspace}\n"
        "\\doublespacing\n"
        + _COMMON_PACKAGES
    ),
}

# Friendly aliases.
_STYLE_ALIASES = {
    "ieeetran": "ieee",
    "ieee-conference": "ieee",
    "acmart": "acm",
    "sn": "springer",
    "springer-nature": "springer",
    "apa7": "apa",
    "default": "article",
    "": "article",
}


def normalize_style(style: str | None) -> str:
    s = (style or "article").strip().lower()
    s = _STYLE_ALIASES.get(s, s)
    return s if s in _PREAMBLES else "article"


def preamble_for(style: str | None) -> str:
    """Return a complete LaTeX preamble (through the last \\usepackage) for the
    requested journal style. Unknown styles fall back to plain `article`."""
    return _PREAMBLES[normalize_style(style)]


def available_styles() -> list[str]:
    return list(_PREAMBLES.keys())


# ──────────────────────────────────────────────────────────────
#  Tables
# ──────────────────────────────────────────────────────────────

def grid_to_tabular(
    rows: list[list[str]],
    *,
    header: bool = True,
    caption: str | None = None,
    label: str | None = None,
    align: str | None = None,
) -> str:
    """Render a 2-D grid of cell strings into a booktabs ``tabular`` (optionally
    wrapped in a ``table`` float when a caption/label is given).

    Args:
        rows: list of rows, each a list of cell strings. Ragged rows are padded.
        header: treat the first row as a header (bold + a midrule beneath it).
        caption / label: when either is set, wrap in a ``table`` float.
        align: column spec like ``"lcr"``; defaults to all-left ``"l"*ncols``.
    """
    rows = [r for r in rows if any((c or "").strip() for c in r)] or rows
    if not rows:
        return "% (empty table)\n"

    ncols = max(len(r) for r in rows)
    align_spec = (align or ("l" * ncols))[:ncols].ljust(ncols, "l")

    def _row(cells: list[str], bold: bool) -> str:
        padded = list(cells) + [""] * (ncols - len(cells))
        rendered = []
        for c in padded:
            cell = escape_latex(c)
            if bold and cell:
                cell = f"\\textbf{{{cell}}}"
            rendered.append(cell)
        return " & ".join(rendered) + " \\\\"

    lines = [f"\\begin{{tabular}}{{{align_spec}}}", "\\toprule"]
    for i, r in enumerate(rows):
        is_head = header and i == 0
        lines.append(_row(r, bold=is_head))
        if is_head:
            lines.append("\\midrule")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    tabular = "\n".join(lines)

    if caption or label:
        inner = ["\\begin{table}[ht]", "\\centering", tabular]
        if caption:
            inner.append(f"\\caption{{{escape_latex(caption)}}}")
        if label:
            inner.append(f"\\label{{{label}}}")
        inner.append("\\end{table}")
        return "\n".join(inner)
    return tabular


def parse_csv_text(text: str, delimiter: str | None = None) -> list[list[str]]:
    """Parse pasted CSV/TSV/grid text into a list of rows using stdlib csv with
    delimiter sniffing. Falls back to comma, then whitespace-aligned columns."""
    import csv
    import io

    text = (text or "").strip("\n")
    if not text.strip():
        return []

    if delimiter:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        return [list(r) for r in reader]

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        reader = csv.reader(io.StringIO(text), dialect)
        rows = [list(r) for r in reader]
        if rows and max(len(r) for r in rows) > 1:
            return rows
    except Exception:
        pass

    # Fallback: comma split, else split on runs of 2+ spaces.
    rows = []
    for line in text.splitlines():
        if "," in line:
            rows.append([c.strip() for c in line.split(",")])
        else:
            rows.append([c.strip() for c in re.split(r"\s{2,}|\t", line.strip())])
    return rows


# ──────────────────────────────────────────────────────────────
#  DocIR → LaTeX
# ──────────────────────────────────────────────────────────────

def _figure_env(image_rel_path: str, caption: str | None) -> str:
    cap = f"\\caption{{{escape_latex(caption)}}}\n" if caption else ""
    return (
        "\\begin{figure}[ht]\n"
        "\\centering\n"
        f"\\includegraphics[width=0.8\\linewidth]{{{image_rel_path}}}\n"
        f"{cap}"
        "\\end{figure}"
    )


# Heading role → LaTeX sectioning command.
_HEADING_CMD = {
    "heading_1": "section",
    "heading_2": "subsection",
    "heading_3": "subsubsection",
    "heading_4": "paragraph",
    "heading_5": "subparagraph",
}


def docir_to_latex(docir, style: str | None = "article") -> tuple[str, list[str]]:
    """Serialize a parsed DocIR document into a complete, compilable LaTeX string.

    This is the deterministic core of ``word_to_latex`` / ``pdf_to_latex`` — it
    never calls an LLM, so content can't be summarised away. Returns
    ``(latex, asset_filenames)`` where asset_filenames are referenced image files
    the caller should make available under ``assets/``.

    The import of DocIR enums is local so this module stays importable even if the
    deepscan package layout changes.
    """
    from ..deepscan.schemas.docir import ElementRole, ElementType  # local import

    body_lines: list[str] = []
    assets: list[str] = []
    title_text: str | None = None
    abstract_parts: list[str] = []
    in_references = False
    ref_items: list[str] = []

    for elem in docir.elements:
        role = getattr(elem, "role", None)
        etype = getattr(elem, "type", None)
        content = (elem.content or "").strip()

        # Tables ------------------------------------------------
        if etype == ElementType.TABLE and elem.table_data:
            grid = [[c.text for c in row] for row in elem.table_data.rows]
            body_lines.append(grid_to_tabular(
                grid,
                header=True,
                caption=getattr(elem, "caption", None),
            ))
            body_lines.append("")
            continue

        # Images ------------------------------------------------
        if etype == ElementType.IMAGE or getattr(elem, "image_path", None):
            img = getattr(elem, "image_path", None)
            if img:
                fname = img.replace("\\", "/").split("/")[-1]
                assets.append(fname)
                body_lines.append(_figure_env(f"assets/{fname}", getattr(elem, "caption", None)))
                body_lines.append("")
            continue

        if not content:
            continue

        # Title -------------------------------------------------
        if role == ElementRole.TITLE and title_text is None:
            title_text = content
            continue

        # Abstract ----------------------------------------------
        if role == ElementRole.ABSTRACT_BODY:
            abstract_parts.append(escape_latex(content))
            continue
        if role == ElementRole.ABSTRACT_LABEL:
            continue  # the abstract environment supplies its own label

        # References --------------------------------------------
        if role == ElementRole.REFERENCE_LABEL:
            in_references = True
            continue
        if role == ElementRole.REFERENCE_ENTRY:
            in_references = True
            ref_items.append(escape_latex(content))
            continue

        # Headings ----------------------------------------------
        role_val = getattr(role, "value", role)
        if role_val in _HEADING_CMD:
            cmd = _HEADING_CMD[role_val]
            body_lines.append(f"\\{cmd}{{{escape_latex(content)}}}")
            body_lines.append("")
            continue

        # Plain body paragraph ----------------------------------
        if not in_references:
            body_lines.append(escape_latex(content))
            body_lines.append("")

    # Assemble -------------------------------------------------
    parts = [preamble_for(style).rstrip(), ""]
    if title_text:
        parts.append(f"\\title{{{escape_latex(title_text)}}}")
        parts.append("\\date{}")
    parts.append("\\begin{document}")
    if title_text:
        parts.append("\\maketitle")
    if abstract_parts:
        parts.append("\\begin{abstract}")
        parts.append("\n".join(abstract_parts))
        parts.append("\\end{abstract}")
    parts.append("")
    parts.extend(body_lines)

    if ref_items:
        parts.append("")
        parts.append("\\begin{thebibliography}{99}")
        for item in ref_items:
            parts.append(f"\\bibitem{{}} {item}")
        parts.append("\\end{thebibliography}")

    parts.append("\\end{document}")
    parts.append("")
    return "\n".join(parts), assets
