"""
FormatForge AI — Agent 3: Structure Detector
Labels every DocIR element with a semantic role (title, heading, body, etc.).

Phase 1 — Multi-pass heuristic detection:
  Pass 1  Style-name detection (Word built-in styles)
  Pass 2  Section keyword matching (Results, Discussion, Methods, …)
  Pass 3  Reference section detection (numbered + alphabetical)
  Pass 4  Title detection (position-based)
  Pass 5  Author / affiliation detection
  Pass 6  Abstract detection (positional)
  Pass 7  Keywords detection
  Pass 8  Fill remaining UNKNOWN → BODY
  Pass 9  Extract in-text citations (numeric + author-date)
  Pass 10 (optional) LLM fallback for remaining UNKNOWN
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..schemas.docir import (
    CitationType,
    DocElement,
    DocIR,
    ElementRole,
    ElementType,
    InTextCitation,
)

logger = logging.getLogger(__name__)

# ── Section heading keywords ──────────────────────────────────

SECTION_KEYWORDS: dict[str, ElementRole] = {
    "abstract": ElementRole.ABSTRACT_LABEL,
    "introduction": ElementRole.HEADING_1,
    "background": ElementRole.HEADING_1,
    "literature review": ElementRole.HEADING_1,
    "related work": ElementRole.HEADING_1,
    "theoretical framework": ElementRole.HEADING_1,
    "methods": ElementRole.HEADING_1,
    "methodology": ElementRole.HEADING_1,
    "materials and methods": ElementRole.HEADING_1,
    "experimental methods": ElementRole.HEADING_1,
    "experimental procedures": ElementRole.HEADING_1,
    "study design": ElementRole.HEADING_2,
    "participants": ElementRole.HEADING_2,
    "procedure": ElementRole.HEADING_2,
    "measures": ElementRole.HEADING_2,
    "data analysis": ElementRole.HEADING_2,
    "data collection": ElementRole.HEADING_2,
    "results": ElementRole.HEADING_1,
    "findings": ElementRole.HEADING_1,
    "results and discussion": ElementRole.HEADING_1,
    "discussion": ElementRole.HEADING_1,
    "general discussion": ElementRole.HEADING_1,
    "conclusion": ElementRole.HEADING_1,
    "conclusions": ElementRole.HEADING_1,
    "summary": ElementRole.HEADING_1,
    "significance": ElementRole.HEADING_1,
    "implications": ElementRole.HEADING_2,
    "limitations": ElementRole.HEADING_2,
    "future work": ElementRole.HEADING_2,
    "future directions": ElementRole.HEADING_2,
    "future research": ElementRole.HEADING_2,
    "data availability": ElementRole.HEADING_2,
    "ethical considerations": ElementRole.HEADING_2,
    "acknowledgements": ElementRole.HEADING_1,
    "acknowledgments": ElementRole.HEADING_1,
    "references": ElementRole.REFERENCE_LABEL,
    "bibliography": ElementRole.REFERENCE_LABEL,
    "works cited": ElementRole.REFERENCE_LABEL,
    "appendix": ElementRole.APPENDIX,
    "appendix a": ElementRole.APPENDIX,
    "appendix b": ElementRole.APPENDIX,
    "appendix c": ElementRole.APPENDIX,
    "appendices": ElementRole.APPENDIX,
    "supplementary material": ElementRole.APPENDIX,
    "supplementary materials": ElementRole.APPENDIX,
    "supporting information": ElementRole.APPENDIX,
}

# Compiled keyword regex for quick look-up
KEYWORDS_PATTERN = re.compile(r"^keywords?\s*[:\-–]", re.IGNORECASE)

# Affiliation / institution patterns
AFFILIATION_RE = re.compile(
    r"(?:university|department|school|institute|college|laboratory|"
    r"center|centre|faculty|hospital|academy|national\s+institutes?|"
    r"research\s+council)",
    re.IGNORECASE,
)

# Numbered reference at start of line:  "1. Author" or "1 Author"
NUMBERED_REF_RE = re.compile(r"^\d{1,3}[\.\)]\s*[A-Z]")

# ── Citation regex patterns ───────────────────────────────────

# Numeric:  (1)  (2, 3)  (1–5)  (1, 2, 5–8)
NUMERIC_CITATION_RE = re.compile(
    r"\((\d{1,3}(?:\s*[,;–\-]\s*\d{1,3})*)\)"
)
# Bare numeral list as it appears in a superscript run: "1", "1,2", "3–5"
SUPERSCRIPT_CITATION_RE = re.compile(r"\d{1,3}(?:\s*[,;–\-]\s*\d{1,3})*")

# Author-date parenthetical:  (Smith, 2023)  (Smith & Jones, 2023; Doe, 2021)
AUTHOR_DATE_PAREN_RE = re.compile(
    r"\(([A-Z][a-zà-ÿ]+(?:\s(?:&|and)\s[A-Z][a-zà-ÿ]+)*(?:\set\sal\.)?"
    r",\s*\d{4}[a-z]?"
    r"(?:;\s*[A-Z][a-zà-ÿ]+(?:\s(?:&|and)\s[A-Z][a-zà-ÿ]+)*(?:\set\sal\.)?"
    r",\s*\d{4}[a-z]?)*)\)"
)

# Author-date narrative:  Smith (2023)  Smith and Jones (2023)
AUTHOR_DATE_NARR_RE = re.compile(
    r"([A-Z][a-zà-ÿ]+(?:\s(?:and|&)\s[A-Z][a-zà-ÿ]+)?(?:\set\sal\.)?)"
    r"\s*\((\d{4}[a-z]?)\)"
)

# Figure / table cross-references (to ignore during numeric-citation extraction)
FIG_TABLE_PREFIX_RE = re.compile(r"(?:Fig\.?|Figure|Table|Tab\.?|Eq\.?)\s*$", re.IGNORECASE)


class StructureDetectorAgent:
    """Agent 3 — Detect and label the structural roles of document elements."""

    def __init__(self, use_llm: bool = False):
        """
        Args:
            use_llm: If True, run LLM fallback for remaining UNKNOWN elements.
        """
        self.use_llm = use_llm

    # ── Public API ───────────────────────────────────────────

    def detect(self, docir: DocIR) -> DocIR:
        """
        Label every element in the DocIR with a semantic role.

        Returns the same DocIR with `role` & `role_confidence` updated.
        """
        elements = docir.elements
        if not elements:
            return docir

        # Multi-pass detection (order matters)
        self._pass0_clean_content(elements)
        self._pass1_style_names(elements)
        self._pass2_section_keywords(elements)
        self._pass3_reference_section(elements)
        self._pass4_title_detection(elements)
        self._pass5_author_affiliation(elements)
        self._pass6_abstract_detection(elements)
        self._pass7d_page_artifacts(elements)       # before keywords — suppresses misclassifiable artifacts
        self._pass7_keywords_detection(elements)
        self._pass7b_caption_detection(elements)
        self._pass7c_front_matter_zone_correction(elements)
        self._pass8_fill_remaining(elements)

        # LLM batch correction — correct misclassified fragments
        if self.use_llm:
            self._pass8b_llm_batch_correction(elements)

        self._pass9_extract_citations(elements)

        if self.use_llm:
            self._pass10_llm_fallback(elements)

        labelled = sum(1 for e in elements if e.role != ElementRole.UNKNOWN)
        total = len(elements)
        logger.info(
            "Structure detection complete — %d/%d elements labelled (%.0f%%)",
            labelled, total, 100 * labelled / total if total else 0,
        )
        return docir

    # ── Pass 0: Clean invisible Unicode from element content ──

    _INVISIBLE_RE = re.compile(
        r'[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2028\u2029\u034f\u061c\u180e\ufff9\ufffa\ufffb]'
    )

    def _pass0_clean_content(self, elements: list[DocElement]) -> None:
        """Strip zero-width and invisible Unicode characters from all element content."""
        count = 0
        for elem in elements:
            if elem.type != ElementType.PARAGRAPH:
                continue
            cleaned = self._INVISIBLE_RE.sub('', elem.content)
            if cleaned != elem.content:
                elem.content = cleaned
                count += 1
        if count:
            logger.info("Content cleanup: removed invisible chars from %d elements", count)

    # ── Pass 1: Word style-name detection ────────────────────

    def _pass1_style_names(self, elements: list[DocElement]) -> None:
        """Use built-in Word style names (Title, Heading 1, …) when available."""
        for elem in elements:
            if elem.type != ElementType.PARAGRAPH:
                continue
            style = (elem.original_style_name or "").lower()

            if "title" in style and "subtitle" not in style:
                elem.role = ElementRole.TITLE
                elem.role_confidence = 0.92
            elif "heading" in style:
                level = self._extract_heading_level(style)
                elem.role = self._heading_role(level)
                elem.role_confidence = 0.88
            elif "abstract" in style:
                elem.role = ElementRole.ABSTRACT_BODY
                elem.role_confidence = 0.85

    # ── Pass 2: Section keyword matching ─────────────────────

    def _pass2_section_keywords(self, elements: list[DocElement]) -> None:
        """Match short standalone paragraphs to known section names."""
        for elem in elements:
            if elem.type != ElementType.PARAGRAPH:
                continue
            if elem.role != ElementRole.UNKNOWN:
                continue

            text = elem.content.strip()
            if not text:
                continue

            word_count = len(text.split())
            text_lower = text.lower().strip()

            # Try exact match (with/without trailing period)
            for candidate in (text_lower, text_lower.rstrip(".")):
                if word_count <= 8 and candidate in SECTION_KEYWORDS:
                    elem.role = SECTION_KEYWORDS[candidate]
                    elem.role_confidence = 0.85
                    break

            # ACKNOWLEDGMENTS header (sometimes all-caps with period)
            if elem.role == ElementRole.UNKNOWN:
                upper = text.upper().rstrip(".")
                if upper in ("ACKNOWLEDGMENTS", "ACKNOWLEDGEMENTS") and word_count <= 3:
                    elem.role = ElementRole.HEADING_1
                    elem.role_confidence = 0.85

    # ── Pass 3: Reference section ────────────────────────────

    def _pass3_reference_section(self, elements: list[DocElement]) -> None:
        """Detect reference-label and mark subsequent entries."""

        # 1. Find the first element already labelled as REFERENCE_LABEL
        ref_label_idx = self._find_role_index(elements, ElementRole.REFERENCE_LABEL)

        # 2. If not found, try to locate by numbered-reference pattern
        if ref_label_idx is None:
            ref_label_idx = self._detect_reference_start_by_pattern(elements)

        if ref_label_idx is None:
            return

        # 3. Mark entries after the label
        for i in range(ref_label_idx + 1, len(elements)):
            elem = elements[i]
            if elem.type != ElementType.PARAGRAPH:
                continue
            text = elem.content.strip()
            if not text:
                continue
            # Stop at another major heading / appendix
            if elem.role in (
                ElementRole.HEADING_1, ElementRole.HEADING_2,
                ElementRole.APPENDIX, ElementRole.ABSTRACT_LABEL,
            ):
                break
            if elem.role == ElementRole.UNKNOWN:
                elem.role = ElementRole.REFERENCE_ENTRY
                elem.role_confidence = 0.75

    def _detect_reference_start_by_pattern(
        self, elements: list[DocElement]
    ) -> Optional[int]:
        """Walk backwards from end to find block of numbered references.

        Handles PDF-to-DOCX documents where each reference may span multiple
        paragraphs (continuation lines between numbered entries).
        """
        ref_indices: list[int] = []
        gap = 0  # non-matching lines since last numbered ref

        for i in range(len(elements) - 1, -1, -1):
            elem = elements[i]
            if elem.type != ElementType.PARAGRAPH:
                continue
            text = elem.content.strip()
            if not text:
                continue

            if NUMBERED_REF_RE.match(text):
                ref_indices.append(i)
                gap = 0
            elif ref_indices:
                # Already found some refs — track the gap
                gap += 1
                if gap > 6:
                    break
                # Stop at section headings
                text_lower = text.lower().rstrip(".")
                if text_lower in SECTION_KEYWORDS:
                    break

        if len(ref_indices) >= 3:
            first_ref_idx = min(ref_indices)
            # Look for a label paragraph just above
            for j in range(max(0, first_ref_idx - 5), first_ref_idx):
                jtext = elements[j].content.strip().lower().rstrip(".")
                if jtext in ("references", "bibliography", "works cited"):
                    elements[j].role = ElementRole.REFERENCE_LABEL
                    elements[j].role_confidence = 0.80
                    return j
            # No label found → use the index before first ref as virtual label
            return first_ref_idx - 1

        return None

    # ── Pass 4: Title detection ──────────────────────────────

    def _pass4_title_detection(self, elements: list[DocElement]) -> None:
        """Identify the paper title from the first paragraphs."""

        # Skip if a title is already detected (e.g. from style names)
        if any(e.role == ElementRole.TITLE for e in elements):
            return

        # Find the first heading / abstract / reference label
        first_heading_idx = self._first_section_index(elements)
        search_limit = min(first_heading_idx, 15)  # only look in first 15 elements

        title_started = False
        for i in range(search_limit):
            elem = elements[i]
            if elem.type != ElementType.PARAGRAPH or elem.role != ElementRole.UNKNOWN:
                continue
            text = elem.content.strip()
            if not text:
                if title_started:
                    break  # blank line ends title
                continue

            if not title_started:
                # First non-empty UNKNOWN paragraph
                if not self._looks_like_author(text):
                    elem.role = ElementRole.TITLE
                    elem.role_confidence = 0.70
                    title_started = True
                else:
                    break  # very first thing is author-like → no title detected
            else:
                # Title continuation (wrapped lines common in PDF→DOCX)
                if self._looks_like_author(text):
                    break
                words = text.split()
                if len(words) <= 20 and not text[0].isdigit():
                    elem.role = ElementRole.TITLE
                    elem.role_confidence = 0.60
                else:
                    break

    # ── Pass 5: Author & affiliation ─────────────────────────

    def _pass5_author_affiliation(self, elements: list[DocElement]) -> None:
        """Detect author names and institutional affiliations after the title."""

        # Find title zone end
        title_end = -1
        for i, elem in enumerate(elements):
            if elem.role == ElementRole.TITLE:
                title_end = i
        if title_end < 0:
            return

        first_heading_idx = self._first_section_index(elements, after=title_end + 1)
        author_zone_end = min(title_end + 30, first_heading_idx)

        consecutive_misses = 0
        for i in range(title_end + 1, author_zone_end):
            elem = elements[i]
            if elem.type != ElementType.PARAGRAPH or elem.role != ElementRole.UNKNOWN:
                continue
            text = elem.content.strip()
            if not text:
                continue

            matched = False

            # Author names (short, comma-separated, proper nouns)
            if self._looks_like_author(text):
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.60
                matched = True

            # Comma-starting fragments = continuation of author list
            elif text.startswith(",") or text.startswith("and "):
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.55
                matched = True

            # Affiliation (university / department / institute …)
            elif AFFILIATION_RE.search(text):
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.55
                matched = True

            # Single-character superscript markers: "a", "b", "1"
            elif len(text) <= 2 and (text.isalpha() or text.isdigit()):
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.40
                matched = True

            # Editor / date metadata
            elif re.match(
                r"^(Edited by|Received|Approved|Accepted|Submitted|Published|"
                r"Revised|To whom|Corresponding|\*|†)",
                text, re.IGNORECASE,
            ):
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.50
                matched = True

            # Email addresses or ORCID
            elif "@" in text or "orcid" in text.lower():
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.50
                matched = True

            # Date-ending line: "..., 2014)" or "... 2023"
            elif re.match(r".*\b\d{4}\)?\.?\s*$", text) and len(text.split()) <= 8:
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.45
                matched = True

            if matched:
                consecutive_misses = 0
            else:
                consecutive_misses += 1
                # Stop after 2 consecutive non-matching paragraphs
                if consecutive_misses >= 2:
                    break

    # ── Pass 6: Abstract detection ───────────────────────────

    @staticmethod
    def _looks_like_keywords(text: str) -> bool:
        """'Keywords: a; b' or a pipe-separated term list ('a | b | c')."""
        if KEYWORDS_PATTERN.match(text):
            return True
        if "|" in text:
            parts = [p.strip() for p in text.split("|")]
            return 3 <= len(parts) <= 12 and all(len(p.split()) <= 6 for p in parts if p)
        return False

    def _pass6_abstract_detection(self, elements: list[DocElement]) -> None:
        """Identify abstract paragraphs between front-matter and first heading.

        The abstract ends at the keywords line when there is one: journals such
        as PNAS put the introduction straight after the keywords with no
        heading, and without this stop the whole introduction became abstract.
        """

        # End of title / author zone
        front_matter_end = 0
        for i, elem in enumerate(elements):
            if elem.role in (ElementRole.TITLE, ElementRole.AUTHOR_INFO):
                front_matter_end = i

        # Find first non-abstract heading after front matter
        first_heading_idx = self._first_section_index(
            elements, after=front_matter_end + 1, skip_abstract_label=True,
        )
        if first_heading_idx <= front_matter_end + 1:
            return  # nothing between front matter and heading

        # If an ABSTRACT_LABEL exists, mark paragraphs after it
        abstract_label_idx = None
        for i in range(front_matter_end + 1, first_heading_idx):
            if elements[i].role == ElementRole.ABSTRACT_LABEL:
                abstract_label_idx = i
                break

        start = (abstract_label_idx + 1) if abstract_label_idx is not None else (front_matter_end + 1)

        abstract_started = False
        for i in range(start, first_heading_idx):
            elem = elements[i]
            if elem.type != ElementType.PARAGRAPH or elem.role != ElementRole.UNKNOWN:
                continue
            text = elem.content.strip()
            if not text:
                continue
            # Skip very short lines unless abstract already started
            if len(text.split()) < 4 and not abstract_started:
                continue
            # Keywords end the abstract; what follows is body (introduction).
            if self._looks_like_keywords(text):
                if abstract_started:
                    break
                continue

            elem.role = ElementRole.ABSTRACT_BODY
            elem.role_confidence = 0.55 if abstract_label_idx else 0.45
            abstract_started = True

    # ── Pass 7: Keywords ─────────────────────────────────────

    def _pass7_keywords_detection(self, elements: list[DocElement]) -> None:
        """Detect keyword lines (e.g. 'Keywords: term1 | term2 | …')."""
        for elem in elements:
            if elem.type != ElementType.PARAGRAPH:
                continue
            text = elem.content.strip()
            if not text:
                continue

            if KEYWORDS_PATTERN.match(text):
                elem.role = ElementRole.KEYWORDS
                elem.role_confidence = 0.85
                continue

            # Pipe-separated terms between front-matter and first heading
            if elem.role in (ElementRole.UNKNOWN, ElementRole.ABSTRACT_BODY) and self._looks_like_keywords(text):
                elem.role = ElementRole.KEYWORDS
                elem.role_confidence = 0.60

    # ── Pass 7b: Figure / Table caption detection ────────────

    # Regex patterns for captions
    _FIGURE_CAPTION_RE = re.compile(
        r"^(?:Fig\.?|Figure)\s*\d+", re.IGNORECASE,
    )
    _TABLE_CAPTION_RE = re.compile(
        r"^(?:Table|Tab\.?)\s*\d+", re.IGNORECASE,
    )

    def _pass7b_caption_detection(self, elements: list[DocElement]) -> None:
        """Detect figure and table captions (e.g. 'Fig. 1. …', 'Table 2. …').

        In line-per-paragraph documents (PDF conversions) a caption spans
        several lines; the continuation lines are claimed too, up to the first
        line that ends a sentence and is visibly shorter than the column (the
        same paragraph-end cue ParagraphMerger uses), so the whole caption
        stays together instead of its tail becoming body text.
        """
        lengths = sorted(len(e.content.strip()) for e in elements
                         if e.type == ElementType.PARAGRAPH and len(e.content.strip()) > 10)
        median = lengths[len(lengths) // 2] if lengths else 0
        fragmented = len(lengths) > 50 and median < 110

        i = 0
        while i < len(elements):
            elem = elements[i]
            i += 1
            if elem.type != ElementType.PARAGRAPH:
                continue
            # Only reassign UNKNOWN or BODY (pass 8 hasn't run yet, so mostly UNKNOWN)
            if elem.role not in (ElementRole.UNKNOWN, ElementRole.BODY):
                continue
            text = elem.content.strip()
            if not text:
                continue

            if self._FIGURE_CAPTION_RE.match(text):
                elem.role = ElementRole.FIGURE_CAPTION
                elem.role_confidence = 0.85
            elif self._TABLE_CAPTION_RE.match(text):
                elem.role = ElementRole.TABLE_CAPTION
                elem.role_confidence = 0.85
            else:
                continue

            if not fragmented:
                continue
            role = elem.role
            prev = text
            for _ in range(15):
                if re.search(r"[.!?]\s*$", prev) and len(prev) < median * 0.82:
                    break                      # short sentence-ending line: caption done
                if i >= len(elements):
                    break
                nxt = elements[i]
                cand = nxt.content.strip()
                if (nxt.type != ElementType.PARAGRAPH or not cand
                        or nxt.role not in (ElementRole.UNKNOWN, ElementRole.BODY)
                        or self._FIGURE_CAPTION_RE.match(cand)
                        or self._TABLE_CAPTION_RE.match(cand)):
                    break
                nxt.role = role
                nxt.role_confidence = 0.60
                prev = cand
                i += 1

    # ── Pass 7c: Front-matter zone correction ────────────────

    def _pass7c_front_matter_zone_correction(self, elements: list[DocElement]) -> None:
        """
        Correct misclassified elements in the narrow author-info zone.

        Only extends author_info classification for a few elements after
        the last detected author_info — handles comma-starting fragments,
        dates, and superscript markers that pass 5 missed.
        
        Does NOT reclassify body text deeper in the document.
        """
        # Find the last author_info element from previous passes
        last_author_idx = -1
        last_title_idx = -1
        for i, elem in enumerate(elements):
            if elem.role == ElementRole.TITLE:
                last_title_idx = i
            if elem.role == ElementRole.AUTHOR_INFO:
                last_author_idx = i

        if last_author_idx < 0 and last_title_idx < 0:
            return

        start_idx = max(last_title_idx, last_author_idx) + 1

        # Only extend for a small window (up to 8 elements after last author)
        # to catch missed fragments without reclassifying body text
        window_end = min(start_idx + 8, len(elements))

        extended = 0
        for i in range(start_idx, window_end):
            elem = elements[i]
            if elem.type != ElementType.PARAGRAPH:
                continue
            text = elem.content.strip()
            if not text:
                continue

            # Skip elements already confidently classified
            if elem.role_confidence >= 0.60:
                break  # hit something confidently classified → stop extending

            # Only reclassify UNKNOWN or very low-confidence body
            if elem.role not in (ElementRole.UNKNOWN, ElementRole.BODY):
                break

            # Heuristic: author-zone continuation fragments
            # - Starts with comma (",")
            # - Date patterns ("December 2, 2014")
            # - Very short (< 3 words)
            # - Email addresses
            words = text.split()
            is_author_continuation = (
                text.startswith(",") or
                text.startswith("and ") or
                len(words) <= 3 or
                re.match(r".*\d{4}\)?$", text) or  # ends with year
                "@" in text or
                re.match(r"^(To whom|Corresponding|E-mail|Email)", text, re.IGNORECASE)
            )

            if is_author_continuation:
                elem.role = ElementRole.AUTHOR_INFO
                elem.role_confidence = 0.50
                extended += 1
            else:
                break  # hit something that looks like real content

        if extended:
            logger.info(
                "Front-matter zone correction: extended author_info by %d elements after idx %d",
                extended, start_idx - 1,
            )

    # ── Pass 7d: Page artifacts (headers / footers / DOIs) ──

    # Patterns for page headers/footers produced by PDF-to-DOCX tools
    _PAGE_ARTIFACT_RE = re.compile(
        r'(?:'
        r'^\d{3,6}\s*\|.*(?:pnas|doi|org)'        # "5504 | www.pnas.org..."
        r'|^www\.\w+\.org/cgi/doi'                 # "www.pnas.org/cgi/doi..."
        r'|^\d{3,6}\s+\w+\s+et\s+al\.?\s*$'       # "5504 Alsharif et al."
        r'|^Downloaded\s+(?:from|by)\s'             # "Downloaded from ..."
        r'|^(?:This\s+article|Freely\s+available).*(?:www\.\w+\.org|open\s+access)'  # footnote links
        r'|^\d{4}/pnas\.\d+'                        # "1073/pnas.1422986112" URL fragment
        r'|^\w[\w\s]{0,30}\s+et\s+al\.?\s+(?:PNAS|Proc|Nature|Science|Cell|Lancet|BMJ|JAMA|\|)'  # "Alsharif et al. PNAS"
        r')',
        re.IGNORECASE,
    )
    # Case-sensitive: standalone ALL-CAPS word ≥5 chars (journal section headers like MICROBIOLOGY)
    _ALLCAPS_ARTIFACT_RE = re.compile(r'^[A-Z]{5,}\s*$')

    # Patterns for journal footnotes/metadata that should not appear in body text
    _FOOTNOTE_ARTIFACT_RE = re.compile(
        r'(?:'
        r'^Author\s+contributions?:'                # "Author contributions: G.A...."
        r'|^The\s+authors?\s+declare\s+no\s+(?:competing\s+)?(?:conflict|interest)'  # "The authors declare no conflict of interest"
        r'|^This\s+article\s+is\s+a\s+\w+\s+Direct\s+Submission'  # "This article is a PNAS Direct Submission"
        r'|^(?:\d+\s+)?To\s+whom\s+correspondence\s+should'  # "To whom correspondence..." (with or without leading digit)
        r'|^(?:Data\s+deposition|Data\s+availability)'  # Data deposition statements
        r'|^(?:Published\s+(?:online|under)|Received\s+for\s+publication)'  # Publication metadata
        r'|^(?:Supporting\s+Information|Supplementary\s+Material|See\s+Commentary)\s'  # SI references
        r'|^(?:This\s+article\s+contains\s+supporting\s+information)'  # SI variant
        r'|^(?:Copyright|©|\(c\))\s+\d{4}'         # Copyright lines
        r'|^Corresponding\s+author'                  # Corresponding author line
        r'|^Conflict\s+of\s+interest\s+statement'   # Conflict of interest header variant
        r'|^Funding[:\s]'                            # Funding statements
        r'|^Acknowledgments?[:\s].*(?:grant|funded|supported|NIH|NSF)'  # Acknowledgments with funding
        r')',
        re.IGNORECASE,
    )

    # Standalone footnote marker (1 or 2 digits alone on a line)
    _FOOTNOTE_MARKER_RE = re.compile(r'^\d{1,2}\s*$')

    # Patterns for continuation lines after Author contributions (initials + verbs)
    _AUTHOR_CONTRIB_CONTINUATION_RE = re.compile(
        r'^(?:[A-Z]\.\w{0,3}\.?,?\s*(?:and\s+)?)+.*'
        r'(?:performed\s+research|contributed|analyzed\s+data|wrote\s+the\s+paper|'
        r'designed\s+research|analytic\s+tools|reagents)',
        re.IGNORECASE,
    )

    def _pass7d_page_artifacts(self, elements: list[DocElement]) -> None:
        """Detect and suppress page headers, footers, DOI lines, and journal footnotes."""
        # Roles that should never be overridden by artifact detection
        _SAFE_ROLES = frozenset({
            ElementRole.TITLE, ElementRole.HEADING_1, ElementRole.HEADING_2,
            ElementRole.HEADING_3, ElementRole.ABSTRACT_LABEL,
        })
        count = 0
        suppressed_indices: set[int] = set()

        # ── First pass: match explicit patterns ──
        for idx, elem in enumerate(elements):
            if elem.type != ElementType.PARAGRAPH:
                continue
            if elem.role in _SAFE_ROLES:
                continue
            text = elem.content.strip()
            if not text:
                continue
            is_artifact = (
                self._PAGE_ARTIFACT_RE.search(text)
                or self._ALLCAPS_ARTIFACT_RE.search(text)
                or self._FOOTNOTE_ARTIFACT_RE.search(text)
                or self._FOOTNOTE_MARKER_RE.search(text)
                or self._AUTHOR_CONTRIB_CONTINUATION_RE.search(text)
            )
            if is_artifact:
                elem.role = ElementRole.UNKNOWN
                elem.role_confidence = 0.95
                elem.content = ""
                suppressed_indices.add(idx)
                count += 1

        # ── Second pass: zone suppression ──
        # After a suppressed footnote element, also suppress nearby short
        # continuation lines (low-confidence, non-heading) until a heading
        # or long paragraph is reached.  Max look-ahead: 5 elements.
        zone_starts = sorted(suppressed_indices)
        for start_idx in zone_starts:
            for offset in range(1, 6):
                nxt = start_idx + offset
                if nxt >= len(elements) or nxt in suppressed_indices:
                    continue
                e = elements[nxt]
                if e.type != ElementType.PARAGRAPH:
                    continue
                # Stop zone suppression at headings or structural elements
                if e.role in _SAFE_ROLES:
                    break
                # Stop at confident roles (headings detected by other passes)
                if e.role_confidence >= 0.70:
                    break
                txt = e.content.strip()
                if not txt:
                    continue
                # Only suppress short continuation lines (< 200 chars)
                if len(txt) > 200:
                    break
                # Check if it looks like a continuation of author contributions
                # or other metadata (short, contains initials, etc.)
                if (self._AUTHOR_CONTRIB_CONTINUATION_RE.search(txt)
                        or len(txt) < 100 and e.role_confidence < 0.50):
                    e.role = ElementRole.UNKNOWN
                    e.role_confidence = 0.95
                    e.content = ""
                    suppressed_indices.add(nxt)
                    count += 1
                else:
                    break  # Stop zone if we hit a real content paragraph

        if count:
            logger.info("Page artifact detection: suppressed %d header/footer/footnote lines", count)

    # ── Pass 8: Fill remaining → BODY ────────────────────────

    def _pass8_fill_remaining(self, elements: list[DocElement]) -> None:
        """Assign BODY to all remaining UNKNOWN paragraphs with content."""
        in_references = False
        for elem in elements:
            if elem.role == ElementRole.REFERENCE_LABEL:
                in_references = True
                continue
            if in_references and elem.role in (
                ElementRole.HEADING_1, ElementRole.HEADING_2, ElementRole.APPENDIX,
            ):
                in_references = False

            if elem.type != ElementType.PARAGRAPH:
                continue

            if elem.role == ElementRole.UNKNOWN:
                text = elem.content.strip()
                if not text:
                    elem.role_confidence = 0.0
                elif in_references:
                    elem.role = ElementRole.REFERENCE_ENTRY
                    elem.role_confidence = 0.60
                else:
                    elem.role = ElementRole.BODY
                    elem.role_confidence = 0.30

    # ── Pass 8b: LLM batch correction ────────────────────────

    def _pass8b_llm_batch_correction(self, elements: list[DocElement]) -> None:
        """
        Send batches of paragraph fragments to the LLM for role correction.
        
        Targets the front-matter area (first ~40 paragraphs) and any
        low-confidence body paragraphs, where heuristic detection struggles
        most with PDF-to-DOCX fragmented documents.
        """
        try:
            from ..llm.client import get_llm_client
            client = get_llm_client()
        except Exception as exc:
            logger.warning("LLM batch correction unavailable: %s", exc)
            return

        # Collect paragraph elements with their indices
        para_items: list[tuple[int, DocElement]] = []
        for i, elem in enumerate(elements):
            if elem.type == ElementType.PARAGRAPH and elem.content.strip():
                para_items.append((i, elem))

        if len(para_items) < 10:
            return

        # ── Batch 1: Front-matter (first 40 paragraph fragments) ──
        front_matter = para_items[:40]
        self._llm_correct_batch(client, elements, front_matter, "front-matter")

        # ── Batch 2: Low-confidence body paragraphs (scattered) ───
        low_conf = [
            (i, e) for i, e in para_items[40:]
            if e.role_confidence < 0.40 and e.role in (ElementRole.BODY, ElementRole.UNKNOWN)
        ]
        if low_conf:
            self._llm_correct_batch(client, elements, low_conf[:30], "low-confidence")

    def _llm_correct_batch(
        self,
        client,
        all_elements: list[DocElement],
        batch: list[tuple[int, DocElement]],
        batch_name: str,
    ) -> None:
        """Send a batch of paragraphs to LLM for role classification."""
        if not batch:
            return

        # Build context string showing numbered lines with current roles
        lines = []
        for seq, (idx, elem) in enumerate(batch):
            text = elem.content.strip()[:150]
            role = elem.role.value
            conf = f"{elem.role_confidence:.2f}"
            lines.append(f"{seq}: [{role} conf={conf}] {text}")

        context_str = "\n".join(lines)

        system_prompt = (
            "You are an expert in academic paper structure. You are given a list of "
            "paragraph fragments from a PDF-to-DOCX conversion where each PDF line "
            "became a separate paragraph. Each line shows: index, current detected role "
            "(with confidence), and text preview.\n\n"
            "Your task: Correct the role of each paragraph. Valid roles are:\n"
            "title, author_info, abstract_label, abstract_body, keywords, "
            "heading_1, heading_2, heading_3, body, reference_label, "
            "reference_entry, table_caption, figure_caption, appendix, unknown\n\n"
            "Return JSON: {\"corrections\": [{\"index\": <int>, \"role\": \"<role>\", "
            "\"confidence\": <0.0-1.0>}, ...]}. Only include entries that NEED correction. "
            "If a role is already correct, omit it."
        )

        user_prompt = (
            f"Classify/correct these {batch_name} paragraph fragments from a "
            f"research paper:\n\n{context_str}\n\n"
            "Return JSON with corrections only."
        )

        try:
            result = client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=2000,
            )

            corrections = result.get("corrections", [])
            applied = 0
            for corr in corrections:
                seq_idx = corr.get("index")
                new_role_str = corr.get("role", "")
                new_conf = float(corr.get("confidence", 0.5))

                if seq_idx is None or seq_idx >= len(batch):
                    continue

                _elem_idx, elem = batch[seq_idx]
                try:
                    new_role = ElementRole(new_role_str)
                    # The LLM only fills gaps the heuristics left: unknown
                    # elements and weakly-labelled body text. It must not
                    # overrule a heuristic label (author zone, keywords,
                    # captions...) however confident it claims to be -- it
                    # relabelled editorial front matter as body text that way.
                    if elem.role == ElementRole.UNKNOWN or (
                        elem.role == ElementRole.BODY and elem.role_confidence < 0.40
                    ):
                        old_role = elem.role.value
                        elem.role = new_role
                        elem.role_confidence = new_conf
                        applied += 1
                        logger.debug(
                            "LLM corrected P[%d] %s → %s (%.2f)",
                            _elem_idx, old_role, new_role_str, new_conf,
                        )
                except ValueError:
                    pass

            logger.info(
                "LLM batch correction (%s): %d corrections applied out of %d suggested",
                batch_name, applied, len(corrections),
            )
        except Exception as exc:
            logger.warning("LLM batch correction failed (%s): %s", batch_name, exc)

    # ── Pass 9: Citation extraction ──────────────────────────

    def _pass9_extract_citations(self, elements: list[DocElement]) -> None:
        """Extract in-text citations from body and abstract paragraphs."""
        total_citations = 0

        for elem in elements:
            if elem.role not in (
                ElementRole.BODY, ElementRole.ABSTRACT_BODY,
            ):
                continue
            if not elem.content:
                continue

            citations: list[InTextCitation] = []

            # ── Numeric citations: (1), (2, 3), (1–5) ───────
            for m in NUMERIC_CITATION_RE.finditer(elem.content):
                inner = m.group(1).strip()
                # Ignore figure / table cross-references
                pre_text = elem.content[max(0, m.start() - 8): m.start()]
                if FIG_TABLE_PREFIX_RE.search(pre_text):
                    continue
                # Ignore standalone 4-digit years (could be date, not citation)
                if re.fullmatch(r"\d{4}", inner):
                    continue

                citations.append(InTextCitation(
                    text=m.group(0),
                    citation_type=CitationType.PARENTHETICAL,
                    authors=[],
                    year=None,
                    position_start=m.start(),
                    position_end=m.end(),
                ))

            # ── Superscript numerals: survival^{1,2} ─────────
            # PDF-to-DOCX keeps these as superscript runs, so the text alone
            # ("survival 1,2.") gives no clue; look at the runs instead.
            cursor = 0
            for run in elem.runs:
                if not run.text:
                    continue
                pos = elem.content.find(run.text, cursor)
                if pos < 0:
                    continue
                cursor = pos + len(run.text)
                sup = run.text.strip()
                if run.superscript and SUPERSCRIPT_CITATION_RE.fullmatch(sup):
                    citations.append(InTextCitation(
                        text=sup,
                        citation_type=CitationType.PARENTHETICAL,
                        authors=[],
                        year=None,
                        position_start=pos,
                        position_end=pos + len(run.text),
                    ))

            # ── Author-date parenthetical: (Smith, 2023) ────
            for m in AUTHOR_DATE_PAREN_RE.finditer(elem.content):
                inner = m.group(1)
                for part in inner.split(";"):
                    part = part.strip()
                    ay = re.match(
                        r"([A-Z][a-zà-ÿ]+(?:\s(?:&|and)\s[A-Z][a-zà-ÿ]+)*"
                        r"(?:\set\sal\.)?),\s*(\d{4}[a-z]?)",
                        part,
                    )
                    if ay:
                        citations.append(InTextCitation(
                            text=f"({part})",
                            citation_type=CitationType.PARENTHETICAL,
                            authors=[ay.group(1).split(" & ")[0].split(" and ")[0].strip()],
                            year=ay.group(2),
                            position_start=m.start(),
                            position_end=m.end(),
                        ))

            # ── Author-date narrative: Smith (2023) ──────────
            for m in AUTHOR_DATE_NARR_RE.finditer(elem.content):
                author = m.group(1).split(" and ")[0].split(" & ")[0].strip()
                year = m.group(2)
                overlap = any(
                    c.position_start is not None
                    and c.position_start <= m.start() < (c.position_end or 0)
                    for c in citations
                )
                if not overlap:
                    citations.append(InTextCitation(
                        text=f"{m.group(1)} ({year})",
                        citation_type=CitationType.NARRATIVE,
                        authors=[author],
                        year=year,
                        position_start=m.start(),
                        position_end=m.end(),
                    ))

            elem.citations_found = citations
            total_citations += len(citations)

        logger.info("Extracted %d in-text citations.", total_citations)

    # ── Pass 10: LLM fallback (optional) ─────────────────────

    def _pass10_llm_fallback(self, elements: list[DocElement]) -> None:
        """Use LLM to classify remaining UNKNOWN elements."""
        unknowns = [
            (i, e) for i, e in enumerate(elements)
            if e.role == ElementRole.UNKNOWN and e.content.strip()
        ]
        if not unknowns:
            return

        try:
            from ..llm.client import get_llm_client
            from ..llm.prompts import STRUCTURE_CLASSIFY_SYSTEM, STRUCTURE_CLASSIFY_USER

            client = get_llm_client()

            for idx, elem in unknowns[:20]:  # limit LLM calls
                ctx_start = max(0, idx - 2)
                ctx_end = min(len(elements), idx + 3)
                context_lines = []
                for j in range(ctx_start, ctx_end):
                    prefix = ">>> " if j == idx else "    "
                    context_lines.append(
                        f"{prefix}[{elements[j].role.value}] "
                        f"{elements[j].content[:100]}"
                    )
                context = "\n".join(context_lines)

                font_info = f"{elem.formatting.font_name or '?'} " \
                            f"{elem.formatting.font_size_pt or '?'}pt"
                if elem.formatting.bold:
                    font_info += " bold"
                if elem.formatting.italic:
                    font_info += " italic"

                user_prompt = STRUCTURE_CLASSIFY_USER.format(
                    context=context,
                    target=elem.content[:200],
                    style_name=elem.original_style_name or "Normal",
                    font_info=font_info,
                )

                try:
                    result = client.chat_json(
                        system_prompt=STRUCTURE_CLASSIFY_SYSTEM,
                        user_prompt=user_prompt,
                        temperature=0.1,
                        max_tokens=100,
                    )
                    role_str = result.get("role", "unknown")
                    confidence = float(result.get("confidence", 0.5))
                    try:
                        elem.role = ElementRole(role_str)
                        elem.role_confidence = confidence
                    except ValueError:
                        pass
                except Exception as exc:
                    logger.debug("LLM classify failed for %s: %s", elem.id, exc)
        except Exception as exc:
            logger.warning("LLM fallback unavailable: %s", exc)

    # ── Helper utilities ─────────────────────────────────────

    @staticmethod
    def _extract_heading_level(style: str) -> int:
        m = re.search(r"(\d)", style)
        return int(m.group(1)) if m else 1

    @staticmethod
    def _heading_role(level: int) -> ElementRole:
        mapping = {
            1: ElementRole.HEADING_1,
            2: ElementRole.HEADING_2,
            3: ElementRole.HEADING_3,
            4: ElementRole.HEADING_4,
            5: ElementRole.HEADING_5,
        }
        return mapping.get(level, ElementRole.HEADING_1)

    @staticmethod
    def _find_role_index(elements: list[DocElement], role: ElementRole) -> Optional[int]:
        """Return the index of the first element with the given role, or None."""
        for i, e in enumerate(elements):
            if e.role == role:
                return i
        return None

    def _first_section_index(
        self,
        elements: list[DocElement],
        after: int = 0,
        skip_abstract_label: bool = False,
    ) -> int:
        """Return index of the first heading / label after *after*, or len(elements)."""
        heading_roles = {
            ElementRole.HEADING_1, ElementRole.HEADING_2, ElementRole.HEADING_3,
            ElementRole.HEADING_4, ElementRole.HEADING_5,
            ElementRole.REFERENCE_LABEL, ElementRole.ABSTRACT_LABEL,
            ElementRole.APPENDIX,
        }
        for i in range(after, len(elements)):
            if elements[i].role in heading_roles:
                if skip_abstract_label and elements[i].role == ElementRole.ABSTRACT_LABEL:
                    continue
                return i
        return len(elements)

    @staticmethod
    def _looks_like_author(text: str) -> bool:
        """Heuristic: does this text look like an author-name line?"""
        if len(text) <= 2:
            return True
        words = text.split()
        if len(words) > 25:
            return False
        # "Smith, J." or "Smith, J. A." pattern
        if re.search(r"[A-Z][a-z]+,?\s+[A-Z]\.", text):
            return True
        # Superscript-like markers adjacent to names  ("Sadia Ahmad a")
        if re.search(r"[a-z]\s*,\s*[A-Z]", text) and len(words) <= 15:
            return True
        # Trailing single-char superscript: "Ghadah Alsharif a", "Mohammad Islam b"
        if (re.search(r"[A-Z][a-z]+\s+[a-z]$", text)
                and 2 <= len(words) <= 8):
            return True
        # "and" connecting proper names
        if " and " in text and len(words) <= 15:
            if re.search(r"[A-Z][a-z]+ (?:and|&) [A-Z][a-z]+", text):
                return True
        return False

    @staticmethod
    def _is_heading_like(elem: DocElement) -> bool:
        """Quick check if element looks like a heading."""
        heading_roles = {
            ElementRole.HEADING_1, ElementRole.HEADING_2, ElementRole.HEADING_3,
            ElementRole.HEADING_4, ElementRole.HEADING_5,
            ElementRole.REFERENCE_LABEL, ElementRole.ABSTRACT_LABEL,
        }
        if elem.role in heading_roles:
            return True
        if elem.formatting.bold and len(elem.content.split()) <= 10:
            return True
        return False
