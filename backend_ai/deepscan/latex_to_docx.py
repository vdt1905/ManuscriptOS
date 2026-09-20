"""
LaTeX -> DOCX that looks like the compiled PDF.

pandoc does the structural conversion (title, authors, abstract, headings,
paragraphs, figures), but on its own it drops \\cite{} (no bibliography
database), ignores thebibliography numbering and IEEEkeywords, leaves sections
unnumbered and uses Word's default blue Calibri styles. This module
pre-processes the LaTeX so pandoc sees plain, already-rendered text for those,
then restyles the resulting DOCX per journal style (fonts, sizes, spacing, and
IEEE's two-column body).

Public API:
    latex_to_docx(latex, style, out_path, assets_dir=None) -> None
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


# ── LaTeX pre-processing ─────────────────────────────────────

def _braced(src: str, start: int) -> tuple[str, int]:
    """Return (content, end) of the balanced {...} group opening at src[start]."""
    assert src[start] == "{"
    depth = 0
    i = start
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1:i], i + 1
        i += 1
    return src[start + 1:], len(src)


def _bibliography(latex: str) -> tuple[str, dict[str, int]]:
    """Replace thebibliography with numbered plain paragraphs.

    Returns the new LaTeX and a cite-key -> number map (entry order, which is
    how IEEE-style numeric references are numbered).
    """
    m = re.search(r"\\begin\{thebibliography\}\{[^}]*\}(.*?)\\end\{thebibliography\}", latex, re.DOTALL)
    if not m:
        return latex, {}
    parts = re.split(r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}", m.group(1))
    keys: dict[str, int] = {}
    items: list[str] = []
    for n, i in enumerate(range(1, len(parts), 2), start=1):
        keys[parts[i].strip()] = n
        items.append(f"\\noindent [{n}] " + parts[i + 1].strip())
    block = "\\section*{References}\n\n" + "\n\n".join(items)
    return latex[:m.start()] + block + latex[m.end():], keys


def _citations(latex: str, keys: dict[str, int]) -> str:
    """\\cite{ref1,ref3} -> [1], [3]  (IEEE numeric style); unknown keys kept."""
    def repl(m: re.Match) -> str:
        out = []
        for k in m.group(1).split(","):
            k = k.strip()
            out.append(f"[{keys[k]}]" if k in keys else f"[{k}]")
        return ", ".join(out)
    return re.sub(r"\\cite[tp]?\*?(?:\[[^\]]*\])?\{([^}]*)\}", repl, latex)


def _keywords(latex: str) -> str:
    return re.sub(
        r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}",
        lambda m: "\\noindent\\textbf{\\textit{Index Terms}---" + m.group(1).strip() + "}",
        latex, flags=re.DOTALL,
    )


def _number_sections(latex: str, style: str) -> str:
    """Write the section numbers into the headings (pandoc's own numbering
    doesn't match journal styles). Starred sections stay unnumbered."""
    ieee = style.lower() == "ieee"
    counters = [0, 0, 0]
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"\\(section|subsection|subsubsection)(\*?)\{", latex):
        if m.start() < pos:
            continue
        title, end = _braced(latex, m.end() - 1)
        level = {"section": 0, "subsection": 1, "subsubsection": 2}[m.group(1)]
        out.append(latex[pos:m.start()])
        if m.group(2):  # starred: keep as is
            out.append(latex[m.start():end])
        else:
            counters[level] += 1
            for j in range(level + 1, 3):
                counters[j] = 0
            if ieee:
                label = (_ROMAN[counters[0] - 1] + "." if level == 0 and counters[0] <= len(_ROMAN)
                         else chr(64 + counters[1]) + "." if level == 1 and counters[1] <= 26
                         else f"{counters[level]})")
            else:
                label = ".".join(str(c) for c in counters[:level + 1]) + ("." if level == 0 else "")
            if ieee and level == 0:
                title = title.upper()
            out.append(f"\\{m.group(1)}*{{{label} {title}}}")
        pos = end
    out.append(latex[pos:])
    return "".join(out)


def prepare(latex: str, style: str) -> str:
    latex, keys = _bibliography(latex)
    latex = _citations(latex, keys)
    latex = _keywords(latex)
    latex = _number_sections(latex, style)
    return latex


# ── DOCX styling ─────────────────────────────────────────────

# per style: body font size, line spacing, title size, columns, margins (in)
_LOOK = {
    "ieee":      dict(size=10, spacing=1.0, title=24, cols=2, margin=0.75, indent=0.14),
    "apa7":      dict(size=12, spacing=2.0, title=14, cols=1, margin=1.0, indent=0.5),
    "mla":       dict(size=12, spacing=2.0, title=12, cols=1, margin=1.0, indent=0.5),
    "chicago":   dict(size=12, spacing=2.0, title=14, cols=1, margin=1.0, indent=0.5),
    "vancouver": dict(size=12, spacing=1.5, title=16, cols=1, margin=1.0, indent=0.0),
}
_DEFAULT_LOOK = dict(size=12, spacing=1.15, title=18, cols=1, margin=1.0, indent=0.0)


def _set_font(style_obj, size: Optional[float] = None, *, bold=None, italic=None) -> None:
    f = style_obj.font
    f.name = "Times New Roman"
    f.color.rgb = RGBColor(0, 0, 0)
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    rpr = style_obj.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), "Times New Roman")
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        fonts.attrib.pop(qn(attr), None)


def _cols(sect_pr, n: int, continuous: bool) -> None:
    cols = sect_pr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sect_pr.append(cols)
    cols.set(qn("w:num"), str(n))
    cols.set(qn("w:space"), "360")          # 0.25in gutter
    typ = sect_pr.find(qn("w:type"))
    if continuous:
        if typ is None:
            typ = OxmlElement("w:type")
            sect_pr.insert(0, typ)
        typ.set(qn("w:val"), "continuous")


def restyle(path: Path, style: str) -> None:
    look = _LOOK.get(style.lower(), _DEFAULT_LOOK)
    doc = Document(str(path))
    styles = {s.name: s for s in doc.styles}

    for name in ("Normal", "Body Text", "First Paragraph", "Compact", "Image Caption",
                 "Captioned Figure", "Figure", "Abstract", "Author", "Date", "Bibliography"):
        if name in styles:
            _set_font(styles[name], look["size"])
    for name in ("Body Text", "First Paragraph", "Abstract"):
        if name in styles:
            pf = styles[name].paragraph_format
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            pf.line_spacing = look["spacing"]
            pf.space_before = Pt(0)
            pf.space_after = Pt(0 if look["spacing"] > 1.0 else 2)
    if "Body Text" in styles:
        styles["Body Text"].paragraph_format.first_line_indent = Inches(look["indent"])

    if "Title" in styles:
        _set_font(styles["Title"], look["title"], bold=style.lower() != "ieee")
        styles["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if "Author" in styles:
        styles["Author"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if "Abstract Title" in styles:
        _set_font(styles["Abstract Title"], look["size"], bold=True, italic=style.lower() == "ieee")
    if "Image Caption" in styles:
        _set_font(styles["Image Caption"], max(look["size"] - 2, 8))
        styles["Image Caption"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for lvl, name in enumerate(("Heading 1", "Heading 2", "Heading 3")):
        if name not in styles:
            continue
        st = styles[name]
        _set_font(st, look["size"] + (1 if lvl == 0 and style.lower() != "ieee" else 0),
                  bold=style.lower() != "ieee", italic=(style.lower() == "ieee" and lvl > 0))
        pf = st.paragraph_format
        pf.space_before = Pt(8)
        pf.space_after = Pt(4)
        if style.lower() == "ieee" and lvl == 0:
            pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
            st.font.small_caps = True

    if style.lower() == "ieee" and "Abstract" in styles:
        _set_font(styles["Abstract"], look["size"] - 1, bold=True)

    for section in doc.sections:
        m = Inches(look["margin"])
        section.left_margin = section.right_margin = m
        section.top_margin = section.bottom_margin = m

    # Two-column body under a full-width title block (IEEE).
    if look["cols"] > 1:
        body = doc.element.body
        paras = doc.paragraphs
        last_front = None
        for i, p in enumerate(paras):
            if p.style.name in ("Title", "Subtitle", "Author", "Date"):
                last_front = i
        if last_front is not None:
            front_ppr = paras[last_front]._p.get_or_add_pPr()
            front_sect = OxmlElement("w:sectPr")
            final_sect = body.find(qn("w:sectPr"))
            if final_sect is not None:           # same page size/margins for both sections
                for child in final_sect:
                    if child.tag in (qn("w:pgSz"), qn("w:pgMar")):
                        front_sect.append(_clone(child))
            _cols(front_sect, 1, continuous=False)
            front_ppr.append(front_sect)
            if final_sect is not None:
                _cols(final_sect, look["cols"], continuous=True)

    doc.save(str(path))


def _clone(el):
    from copy import deepcopy
    return deepcopy(el)


# ── Entry point ──────────────────────────────────────────────

def latex_to_docx(latex: str, style: str, out_path: Path, assets_dir: Optional[Path] = None) -> None:
    """Convert *latex* to a styled DOCX at *out_path* (raises on pandoc failure)."""
    import pypandoc

    src = prepare(latex, style)
    resource = [str(assets_dir.parent)] if assets_dir else []
    with tempfile.TemporaryDirectory(prefix="tex2docx_") as tmp:
        if assets_dir and assets_dir.is_dir():
            # the LaTeX refers to images as assets/<file>
            (Path(tmp) / "assets").mkdir()
            for f in assets_dir.iterdir():
                if f.is_file():
                    (Path(tmp) / "assets" / f.name).write_bytes(f.read_bytes())
        resource.insert(0, tmp)
        pypandoc.convert_text(
            src, "docx", format="latex", outputfile=str(out_path),
            extra_args=["--standalone", "--resource-path=" + ";".join(resource) if resource else "--standalone"],
            cworkdir=tmp,
        )
    restyle(out_path, style)
