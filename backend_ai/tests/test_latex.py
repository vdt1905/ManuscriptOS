"""Unit tests for the deterministic LaTeX pipeline (run by CI: pytest backend_ai/tests)."""

from backend_ai.deepscan.agents.content_integrity import delatex
from backend_ai.deepscan.latex_builder import (
    _break_long_line,
    author_block,
    caption_text,
    citation_numbers,
    escape,
    heading_text,
)
from backend_ai.latex_toolkit.latex_utils import escape_latex


def test_escape_specials_and_unicode():
    assert escape("50% & $5 #1 a_b") == r"50\% \& \$5 \#1 a\_b"
    assert escape("β-gal ΔgrlA 5 µm – x") == r"$\beta$-gal $\Delta$grlA 5 $\mu$m -- x"
    # non-breaking hyphen (common in PDFs) becomes a plain hyphen
    assert escape("EHEC‑specific") == "EHEC-specific"


def test_toolkit_escape_is_single_pass():
    # The braces inserted by \textbackslash{} must not be escaped again.
    assert escape_latex("a\\b & 100% {x}") == r"a\textbackslash{}b \& 100\% \{x\}"


def test_citation_numbers():
    assert citation_numbers("1,2") == [1, 2]
    assert citation_numbers("(6, 7)") == [6, 7]
    assert citation_numbers("(9–12)") == [9, 10, 11, 12]
    assert citation_numbers("Fig. 2") == []


def test_author_block_drops_editorial_lines():
    block = author_block([
        "Ghadah Alsharif a",
        ", Sadia Ahmad a , and Anne Krachler",
        "a",
        "Institute of X, University of Y",
        "Edited by Someone, approved March 25, 2015 (received for review",
        "December 2, 2014)",
        "as well",
    ])
    assert "Edited by" not in block
    assert "as well" not in block
    assert r"\textsuperscript{a}Institute" in block


def test_heading_and_caption_prefixes_are_removed():
    assert heading_text("II. RESULTS") == "RESULTS"
    assert heading_text("1.2 Data") == "Data"
    assert caption_text("Fig. 3. Something") == "Something"
    assert caption_text("Table 1: Rates") == "Rates"


def test_long_author_lines_are_broken():
    assert _break_long_line("word " * 40).count("\\\\") >= 2


def test_integrity_counts_caption_text():
    tex = (
        "\\begin{document}Body text."
        "\\begin{figure}\\caption{Caption words here}\\end{figure}"
        "\\end{document}"
    )
    text = delatex(tex)
    assert "Body text." in text
    assert "Caption words here" in text
