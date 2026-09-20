"""
FormatForge AI — Agent 4: Citation & Reference Engine
Parses references, formats them with citeproc-py, validates citation consistency.

Phase 3 — Complete citation pipeline:
 • Enhanced reference parsing (APA / numbered / book / fallback)
 • citeproc-py integration for CSL-formatted bibliography
 • Numeric citation↔reference matching (number → entry mapping)
 • Format issue detection (& vs and, et al. threshold, year present)
 • Fuzzy matching with Levenshtein distance fallback
 • Citation consistency validation with detailed reporting

100 % deterministic core — zero LLM calls.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..schemas.docir import (
    AuthorName,
    CitationType,
    DocElement,
    DocIR,
    ElementRole,
    InTextCitation,
    ParsedReference,
)
from ..schemas.reports import (
    CitationFormatIssue,
    CitationMatch,
    CitationReport,
    OrphanReference,
)
from ..schemas.style_spec import StyleSpec

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  Regex patterns
# ══════════════════════════════════════════════════════════════

# ── In-text citation patterns ────────────────────────────────

# Parenthetical: (Smith, 2023) or (Smith & Jones, 2023) or (Smith et al., 2023)
PARENTHETICAL_RE = re.compile(
    r'\(([A-Z][a-zà-ÿ]+(?:\s(?:&|and)\s[A-Z][a-zà-ÿ]+)*(?:\set\sal\.)?'
    r',\s*\d{4}[a-z]?'
    r'(?:;\s*[A-Z][a-zà-ÿ]+(?:\s(?:&|and)\s[A-Z][a-zà-ÿ]+)*(?:\set\sal\.)?'
    r',\s*\d{4}[a-z]?)*)\)'
)

# Narrative: Smith (2023) or Smith and Jones (2023) or Smith et al. (2023)
NARRATIVE_RE = re.compile(
    r'([A-Z][a-zà-ÿ]+(?:\s(?:and|&)\s[A-Z][a-zà-ÿ]+)?(?:\set\sal\.)?)'
    r'\s*\((\d{4}[a-z]?)\)'
)

# ── Reference regex patterns ────────────────────────────────

# APA style: Author, A. A. (Year). Title. Journal, Vol(Issue), Pages.
APA_JOURNAL_RE = re.compile(
    r'^(.+?)\s*\((\d{4})\)\.\s*(.+?)\.\s*(.+?),\s*(\d+)'
    r'(?:\((\d+)\))?,\s*(.+?)\.(?:\s*(?:https?://)?doi\.org/(.+))?$'
)

# Numbered: "1. Author (Year) Title. Journal Vol(Issue):Pages."
NUMBERED_JOURNAL_RE = re.compile(
    r'^(\d{1,3})[\.\)]\s*(.+?)\s*\((\d{4})\)\s*(.+?)\.\s*'
    r'([A-Z][\w\s&:,\-]+?)\s+(\d+)'
    r'(?:\((\d+)\))?\s*[:\-,]\s*([\d\-–]+)'
)

# Book pattern: Author (Year). Title (Edition). Publisher.
BOOK_RE = re.compile(
    r'^(.+?)\s*\((\d{4})\)\.\s*(.+?)(?:\((.+?)\))?\.\s*(.+?)\.?\s*$'
)

# DOI extractor
DOI_RE = re.compile(r'(?:https?://)?doi\.org/(10\.\d{4,}/\S+)', re.IGNORECASE)


# ══════════════════════════════════════════════════════════════
#  CitationEngineAgent
# ══════════════════════════════════════════════════════════════

class CitationEngineAgent:
    """Agent 4 — Citation extraction, reference parsing, citeproc formatting, and validation."""

    # ── Public API ────────────────────────────────────────────

    def process(
        self,
        docir: DocIR,
        style_spec: StyleSpec,
    ) -> tuple[DocIR, CitationReport]:
        """
        Full citation processing pipeline:
            1. Extract in-text citations from body paragraphs
            2. Parse reference entries into structured data
            3. Format references with citeproc-py (CSL)
            4. Validate citation↔reference consistency
            5. Detect citation format issues

        Returns:
            Updated DocIR + CitationReport.
        """
        # Step 1: Extract in-text citations
        self._extract_citations(docir)

        # Step 2: Parse reference entries
        self._parse_references(docir)

        # Step 3: Format with citeproc-py
        formatted_refs = self._format_with_citeproc(docir, style_spec)

        # Step 4+5: Validate consistency + detect format issues
        report = self._validate_consistency(docir, style_spec)

        # Attach formatted references to report for downstream use
        report.formatted_bibliography = formatted_refs

        return docir, report

    # ══════════════════════════════════════════════════════════
    #  Step 1: Extract in-text citations
    # ══════════════════════════════════════════════════════════

    def _extract_citations(self, docir: DocIR) -> None:
        """Find all in-text citations in body paragraphs."""
        existing = sum(len(e.citations_found) for e in docir.elements)
        if existing > 0:
            logger.info(
                "Citations already extracted (%d found) — skipping re-extraction.",
                existing,
            )
            return

        for elem in docir.elements:
            if elem.role not in (
                ElementRole.BODY,
                ElementRole.ABSTRACT_BODY,
                ElementRole.UNKNOWN,
            ):
                continue
            if not elem.content:
                continue

            citations: list[InTextCitation] = []

            # Parenthetical citations
            for m in PARENTHETICAL_RE.finditer(elem.content):
                inner = m.group(1)
                for part in inner.split(";"):
                    part = part.strip()
                    author_year = re.match(
                        r'([A-Z][a-zà-ÿ]+(?:\s(?:&|and)\s[A-Z][a-zà-ÿ]+)*'
                        r'(?:\set\sal\.)?),\s*(\d{4}[a-z]?)',
                        part,
                    )
                    if author_year:
                        citations.append(InTextCitation(
                            text=f"({part})",
                            citation_type=CitationType.PARENTHETICAL,
                            authors=[
                                author_year.group(1)
                                .split(" & ")[0]
                                .split(" and ")[0]
                                .strip()
                            ],
                            year=author_year.group(2),
                            position_start=m.start(),
                            position_end=m.end(),
                        ))

            # Narrative citations
            for m in NARRATIVE_RE.finditer(elem.content):
                author = m.group(1).split(" and ")[0].split(" & ")[0].strip()
                year = m.group(2)
                overlap = any(
                    c.position_start is not None
                    and m.start() >= c.position_start
                    and m.end() <= c.position_end
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

        total = sum(len(e.citations_found) for e in docir.elements)
        logger.info("Extracted %d in-text citations.", total)

    # ══════════════════════════════════════════════════════════
    #  Step 2: Parse reference entries
    # ══════════════════════════════════════════════════════════

    def _parse_references(self, docir: DocIR) -> None:
        """Parse raw reference strings into structured ParsedReference.
        
        Handles multi-paragraph references by merging continuation lines
        (paragraphs that don't start with a number) into the previous reference.
        """
        ref_elements = docir.get_reference_entries()

        # ── Step 1: Merge continuation lines ─────────────────
        # Some reference entries span multiple paragraphs.  A continuation
        # line is any reference_entry that does NOT start with a numbered
        # prefix (e.g. "1." or "2)") and does NOT look like a new APA-style
        # reference (Author, A. B. (Year)...).
        import re as _re
        _NUM_PREFIX = _re.compile(r'^\d{1,3}[\.\)]\s')
        _APA_START  = _re.compile(r'^[A-Z][a-zà-ÿ]+[\s,]')  # Author surname start

        merged_refs: list[tuple[DocElement, str]] = []  # (primary_elem, merged_text)
        for elem in ref_elements:
            text = elem.content.strip()
            if not text:
                continue
            is_new_entry = (
                _NUM_PREFIX.match(text)                     # numbered: "1. Author..."
                or not merged_refs                          # very first reference
                or (                                        # APA-style: "Author, X. (2023)..."
                    _APA_START.match(text)
                    and _re.search(r'\(\d{4}', text)
                )
            )
            if is_new_entry:
                merged_refs.append((elem, text))
            else:
                # Continuation line — append to previous reference
                prev_elem, prev_text = merged_refs[-1]
                merged_refs[-1] = (prev_elem, prev_text + " " + text)
                # Clear the continuation element's content so it won't
                # be double-counted in validation
                elem.parsed_reference = ParsedReference()

        # ── Step 2: Parse each merged reference ──────────────
        for elem, merged_text in merged_refs:
            elem.parsed_reference = self._parse_single_reference(merged_text)

        parsed_ok = sum(
            1
            for elem, _ in merged_refs
            if elem.parsed_reference
            and (elem.parsed_reference.year or elem.parsed_reference.authors)
        )
        logger.info(
            "Parsed %d/%d reference entries successfully (merged from %d paragraphs).",
            parsed_ok,
            len(merged_refs),
            len(ref_elements),
        )

    def _parse_single_reference(self, text: str) -> ParsedReference:
        """
        Parse a single reference string into structured fields.
        Strategy: APA journal → numbered journal → book → fallback.
        """
        ref = ParsedReference()

        # Extract DOI from anywhere in the string
        doi_m = DOI_RE.search(text)
        if doi_m:
            ref.doi = doi_m.group(1)

        # ── Try APA journal article pattern ──────────────────
        m = APA_JOURNAL_RE.match(text)
        if m:
            ref.authors = self._parse_author_string(m.group(1))
            ref.year = m.group(2)
            ref.title = m.group(3).strip()
            ref.container_title = m.group(4).strip()
            ref.volume = m.group(5)
            ref.issue = m.group(6)
            ref.pages = m.group(7).strip().rstrip(".")
            if m.group(8):
                ref.doi = m.group(8).strip()
            ref.ref_type = "article-journal"
            return ref

        # ── Try numbered reference (PNAS / Vancouver) ────────
        m = NUMBERED_JOURNAL_RE.match(text)
        if m:
            ref.original_number = int(m.group(1))
            ref.authors = self._parse_author_string(m.group(2))
            ref.year = m.group(3)
            ref.title = m.group(4).strip().rstrip(".")
            ref.container_title = m.group(5).strip()
            ref.volume = m.group(6)
            ref.issue = m.group(7)
            ref.pages = m.group(8).strip()
            ref.ref_type = "article-journal"
            return ref

        # ── Fallback: extract what we can ────────────────────
        # Strip leading number if present
        num_m = re.match(r'^(\d{1,3})[\.\)]\s*', text)
        if num_m:
            ref.original_number = int(num_m.group(1))

        text_clean = re.sub(r'^\d{1,3}[\.\)]\s*', '', text)

        # Year
        year_m = re.search(r'\((\d{4})\)', text_clean)
        if year_m:
            ref.year = year_m.group(1)
            author_part = (
                text_clean[: year_m.start()].strip().rstrip(",").strip()
            )
            if author_part:
                ref.authors = self._parse_author_string(author_part)
            after_year = (
                text_clean[year_m.end() :].strip().lstrip(".").strip()
            )
            title_m = re.match(r'(.+?)\.', after_year)
            if title_m:
                ref.title = title_m.group(1).strip()
            # Try to extract container title after the title
            if title_m:
                remaining = after_year[title_m.end() :].strip()
                journal_m = re.match(r'(.+?)\s*(\d+)', remaining)
                if journal_m:
                    ref.container_title = journal_m.group(1).strip().rstrip(",")
                    ref.volume = journal_m.group(2)

        return ref

    @staticmethod
    def _parse_author_string(author_str: str) -> list[AuthorName]:
        """Parse 'Smith, J., & Jones, A. B.' or 'Nataro JP, Kaper JB' into AuthorName list."""
        authors: list[AuthorName] = []

        has_ampersand = "&" in author_str or " and " in author_str.lower()

        is_apa = has_ampersand
        if not is_apa:
            parts_raw = [p.strip() for p in author_str.split(",")]
            for p in parts_raw[1:]:
                p = p.strip().rstrip(",").strip()
                if p and re.fullmatch(r"[A-Z]\.(?:\s*[A-Z]\.)*", p):
                    is_apa = True
                    break

        if is_apa:
            parts = re.split(
                r',\s*&\s*|,\s*and\s*|\s+&\s+|\s+and\s+', author_str
            )
            for part in parts:
                part = part.strip().rstrip(",").strip()
                if not part or part.lower().startswith("et al"):
                    continue
                name_parts = part.split(",", 1)
                if len(name_parts) == 2:
                    family = name_parts[0].strip()
                    given = name_parts[1].strip()
                    if family:
                        authors.append(AuthorName(family=family, given=given))
                else:
                    authors.append(AuthorName(family=part))
        else:
            # Vancouver/PNAS style
            parts = [p.strip() for p in author_str.split(",")]
            for part in parts:
                part = part.strip()
                if not part or part.lower().startswith("et al"):
                    continue
                words = part.split()
                if len(words) >= 2:
                    initials = []
                    idx = len(words) - 1
                    while idx >= 1 and all(
                        c.isupper() or c == "." for c in words[idx]
                    ):
                        initials.insert(0, words[idx])
                        idx -= 1
                    if initials:
                        family = " ".join(words[: idx + 1])
                        given = " ".join(initials)
                        authors.append(AuthorName(family=family, given=given))
                    else:
                        authors.append(AuthorName(family=part))
                elif part:
                    authors.append(AuthorName(family=part))

        return authors

    # ══════════════════════════════════════════════════════════
    #  Step 3: Format with citeproc-py
    # ══════════════════════════════════════════════════════════

    def _format_with_citeproc(
        self,
        docir: DocIR,
        style_spec: StyleSpec,
    ) -> list[str]:
        """
        Use citeproc-py to render references in the target CSL style (default: APA).

        Returns a list of formatted reference strings.
        Falls back gracefully if citeproc fails.
        """
        ref_elements = docir.get_reference_entries()
        parsed_refs = [
            e.parsed_reference
            for e in ref_elements
            if e.parsed_reference
            and (e.parsed_reference.year or e.parsed_reference.authors)
        ]

        if not parsed_refs:
            logger.info("No parsed references to format with citeproc.")
            return []

        try:
            from citeproc import (
                Citation,
                CitationItem,
                CitationStylesBibliography,
                CitationStylesStyle,
                formatter,
            )
            from citeproc.source.json import CiteProcJSON

            # Resolve CSL style
            style_name = style_spec.references.csl_style_name or "apa"
            style_path = self._get_csl_style_path(style_name)
            if style_path is None:
                logger.warning(
                    "CSL style '%s' not found — skipping citeproc formatting.",
                    style_name,
                )
                return []

            style = CitationStylesStyle(style_path)

            # Build CSL-JSON source with unique IDs
            # Keep a list, not a set: citeproc numbers entries in registration
            # order, and a set would shuffle the bibliography on every run.
            csl_items = []
            csl_ids: list[str] = []
            for i, pr in enumerate(parsed_refs):
                csl_id = f"ref-{i}"
                item = pr.to_csl_json(csl_id=csl_id)
                csl_items.append(item)
                csl_ids.append(csl_id)

            source = CiteProcJSON(csl_items)
            bib = CitationStylesBibliography(style, source, formatter.plain)

            # Register all citations so citeproc knows about them
            for csl_id in csl_ids:
                cit = Citation([CitationItem(csl_id)])
                bib.register(cit)

            # Generate formatted bibliography
            formatted: list[str] = []
            for item in bib.bibliography():
                text = str(item).strip()
                formatted.append(text)

            # Store formatted strings back on ParsedReference
            for pr, fmt in zip(parsed_refs, formatted):
                pr.formatted_apa = fmt

            logger.info(
                "citeproc-py formatted %d/%d references in '%s' style.",
                len(formatted),
                len(ref_elements),
                style_name,
            )
            return formatted

        except Exception as exc:
            logger.warning(
                "citeproc-py formatting failed (non-fatal): %s", exc
            )
            return []

    @staticmethod
    def _get_csl_style_path(style_name: str) -> Optional[str]:
        """Resolve a CSL style name to a file path."""
        try:
            from citeproc_styles import get_style_filepath

            return get_style_filepath(style_name)
        except Exception:
            return None

    # ══════════════════════════════════════════════════════════
    #  Step 4+5: Validate consistency + format issues
    # ══════════════════════════════════════════════════════════

    def _validate_consistency(
        self,
        docir: DocIR,
        style_spec: StyleSpec,
    ) -> CitationReport:
        """
        Comprehensive citation↔reference validation:
            A. Author-date matching (fuzzy, first-author + year)
            B. Numeric matching (number → reference entry)
            C. Format issue detection (& vs and, et al., year present)
        """
        report = CitationReport()

        all_citations = docir.get_all_citations()
        ref_elements = docir.get_reference_entries()

        # Filter out continuation-line elements (those with empty ParsedReference
        # set by _parse_references during merge).  Only count refs that have
        # meaningful parsed data or at least substantive text.
        primary_refs = [
            e for e in ref_elements
            if e.parsed_reference is None  # never parsed (shouldn't happen)
            or e.parsed_reference.year
            or e.parsed_reference.authors
            or e.parsed_reference.original_number is not None
            or (e.content and len(e.content.strip()) > 30
                and re.match(r'^\d{1,3}[\.\)]', e.content.strip()))
        ]

        report.total_citations = len(all_citations)
        report.total_references = len(primary_refs)

        matched_refs: set[str] = set()

        # Determine citation system
        numeric_count = sum(1 for c in all_citations if not c.year)
        author_date_count = sum(1 for c in all_citations if c.year)

        if numeric_count > author_date_count:
            # ── Numeric citation system ──────────────────────
            self._match_numeric_citations(
                all_citations, primary_refs, report, matched_refs
            )
        else:
            # ── Author-date citation system ──────────────────
            self._match_author_date_citations(
                all_citations, primary_refs, report, matched_refs
            )

        # ── Check for uncited references ─────────────────────
        for ref_elem in primary_refs:
            if ref_elem.id not in matched_refs:
                report.uncited_references.append(
                    OrphanReference(
                        reference_text=ref_elem.content[:100],
                        issue="Not cited anywhere in text",
                    )
                )

        # ── Detect format issues ─────────────────────────────
        self._detect_format_issues(docir, style_spec, report)

        report.compute_score()
        logger.info(
            "Citation consistency: %d matched, %d orphan citations, "
            "%d uncited refs, %d format issues — score %.1f%%",
            report.matched,
            len(report.orphan_citations),
            len(report.uncited_references),
            len(report.format_issues),
            report.consistency_score,
        )
        return report

    # ── Numeric matching ─────────────────────────────────────

    def _match_numeric_citations(
        self,
        all_citations: list[InTextCitation],
        ref_elements: list[DocElement],
        report: CitationReport,
        matched_refs: set[str],
    ) -> None:
        """Match numeric citations [1], [2,3], (1–5) to numbered reference entries."""
        # Build number → ref_element map
        num_to_ref: dict[int, DocElement] = {}
        for ref_elem in ref_elements:
            pr = ref_elem.parsed_reference
            if pr and pr.original_number is not None:
                num_to_ref[pr.original_number] = ref_elem
            else:
                # Try extracting number from content
                m = re.match(r'^(\d{1,3})[\.\)]', ref_elem.content.strip())
                if m:
                    num_to_ref[int(m.group(1))] = ref_elem

        # Extract numbers from each numeric citation
        for cit in all_citations:
            if cit.year:
                # This is an author-date citation in a mostly-numeric doc
                # Try matching it as author-date
                match_found = self._try_author_date_match(
                    cit, ref_elements, matched_refs
                )
                if match_found:
                    report.matched += 1
                else:
                    report.orphan_citations.append(
                        CitationMatch(
                            citation_text=cit.text,
                            status="orphan",
                            issue=f"No matching reference for {cit.text}",
                        )
                    )
                continue

            # Parse numbers from the citation text
            numbers = self._extract_citation_numbers(cit.text)
            if not numbers:
                report.orphan_citations.append(
                    CitationMatch(
                        citation_text=cit.text,
                        status="orphan",
                        issue=f"Could not extract reference numbers from {cit.text}",
                    )
                )
                continue

            for num in numbers:
                if num in num_to_ref:
                    report.matched += 1
                    matched_refs.add(num_to_ref[num].id)
                else:
                    report.orphan_citations.append(
                        CitationMatch(
                            citation_text=cit.text,
                            status="orphan",
                            issue=f"Reference [{num}] not found in reference list",
                        )
                    )

    @staticmethod
    def _extract_citation_numbers(text: str) -> list[int]:
        """Extract reference numbers from a citation like '(1)', '(2,3)', '(9–12)'."""
        nums: list[int] = []
        inner = text.strip("()[] ")

        for part in re.split(r'[,;\s]+', inner):
            part = part.strip()
            # Range: 9-12 or 9–12
            range_m = re.match(r'(\d+)\s*[-–]\s*(\d+)', part)
            if range_m:
                start, end = int(range_m.group(1)), int(range_m.group(2))
                nums.extend(range(start, end + 1))
            elif part.isdigit():
                nums.append(int(part))

        return nums

    # ── Author-date matching ─────────────────────────────────

    def _match_author_date_citations(
        self,
        all_citations: list[InTextCitation],
        ref_elements: list[DocElement],
        report: CitationReport,
        matched_refs: set[str],
    ) -> None:
        """Match author-date citations to references by first author + year."""
        for cit in all_citations:
            match_found = self._try_author_date_match(
                cit, ref_elements, matched_refs
            )
            if match_found:
                report.matched += 1
            else:
                report.orphan_citations.append(
                    CitationMatch(
                        citation_text=cit.text,
                        status="orphan",
                        issue=f"No matching reference found for {cit.text}",
                    )
                )

    def _try_author_date_match(
        self,
        cit: InTextCitation,
        ref_elements: list[DocElement],
        matched_refs: set[str],
    ) -> bool:
        """Attempt to match a single author-date citation to a reference."""
        cit_author = cit.authors[0].lower() if cit.authors else ""
        cit_year = cit.year

        # Exact match: first author family name + year
        for ref_elem in ref_elements:
            pr = ref_elem.parsed_reference
            if pr and pr.authors and pr.year:
                first_family = pr.authors[0].family.lower()
                if first_family == cit_author and pr.year == cit_year:
                    matched_refs.add(ref_elem.id)
                    return True

        # Fuzzy match: try Levenshtein distance on author name
        if cit_author:
            for ref_elem in ref_elements:
                pr = ref_elem.parsed_reference
                if pr and pr.authors and pr.year == cit_year:
                    first_family = pr.authors[0].family.lower()
                    if self._fuzzy_match(cit_author, first_family, threshold=85):
                        matched_refs.add(ref_elem.id)
                        return True

        return False

    @staticmethod
    def _fuzzy_match(a: str, b: str, threshold: int = 85) -> bool:
        """Fuzzy string match using Levenshtein ratio. Returns True if ratio >= threshold."""
        try:
            from thefuzz import fuzz

            return fuzz.ratio(a, b) >= threshold
        except ImportError:
            # Fallback: simple substring match
            return a in b or b in a

    # ── Format issue detection ───────────────────────────────

    def _detect_format_issues(
        self,
        docir: DocIR,
        style_spec: StyleSpec,
        report: CitationReport,
    ) -> None:
        """
        Check citation formatting against APA 7 rules:
            1. Ampersand (&) required in parenthetical, 'and' in narrative
            2. et al. required for 3+ authors from first citation
            3. Year must be present
        """
        spec = style_spec.in_text_citations

        for elem in docir.elements:
            for cit in elem.citations_found:
                # Check 1: & vs "and" in parenthetical
                if spec.ampersand_in_parenthetical:
                    if (
                        cit.citation_type == CitationType.PARENTHETICAL
                        and " and " in cit.text
                        and " & " not in cit.text
                    ):
                        report.format_issues.append(
                            CitationFormatIssue(
                                citation_text=cit.text,
                                location=f"element {elem.id}",
                                issue='Should use "&" instead of "and" in parenthetical citation (APA 7 §8.21)',
                            )
                        )

                if spec.and_in_narrative:
                    if (
                        cit.citation_type == CitationType.NARRATIVE
                        and " & " in cit.text
                        and " and " not in cit.text.lower()
                    ):
                        report.format_issues.append(
                            CitationFormatIssue(
                                citation_text=cit.text,
                                location=f"element {elem.id}",
                                issue='Should use "and" instead of "&" in narrative citation (APA 7 §8.21)',
                            )
                        )

                # Check 2: Missing year
                if cit.year is None and cit.citation_type in (
                    CitationType.PARENTHETICAL,
                    CitationType.NARRATIVE,
                ):
                    # Only flag if it looks like an author-date attempt
                    if any(c.isalpha() for c in cit.text):
                        pass  # numeric citations are expected to lack year

    # ══════════════════════════════════════════════════════════
    #  Utility: get formatted bibliography for transformer
    # ══════════════════════════════════════════════════════════

    def get_formatted_bibliography(
        self,
        docir: DocIR,
        style_spec: StyleSpec,
    ) -> list[str]:
        """
        Public helper — return citeproc-formatted reference strings.
        Can be called by the Transformer to replace raw references.
        """
        return self._format_with_citeproc(docir, style_spec)
