"""
FormatForge AI — Paragraph Merger
Detects and merges fragmented paragraphs from PDF-to-DOCX conversions.

PDF-to-DOCX tools often create one paragraph per visible line, yielding
documents with hundreds of 60-char paragraphs.  This module groups those
fragments back into logical paragraphs based on:
  • Same semantic role (BODY, ABSTRACT_BODY, etc.)
  • Sentence-continuation heuristics (no final period, starts lowercase)
  • Hyphenated word reconstruction ("re-" + "port" → "report")
  • Line-length statistics (detects "all lines ≈ same width" pattern)
"""

from __future__ import annotations

import logging
import re
import statistics
from typing import Optional

from ..schemas.docir import DocElement, DocIR, ElementRole, ElementType

logger = logging.getLogger(__name__)

# Roles whose consecutive fragments should be merged
_MERGEABLE_ROLES = frozenset({
    ElementRole.BODY,
    ElementRole.ABSTRACT_BODY,
    ElementRole.TITLE,
    ElementRole.AUTHOR_INFO,
    ElementRole.KEYWORDS,
    ElementRole.REFERENCE_ENTRY,
    ElementRole.FIGURE_CAPTION,
})

# Sentence-ending punctuation
_SENTENCE_END = re.compile(r'[.!?:;]\s*$')

# Starts with lowercase or continuation word
_STARTS_LOWER = re.compile(r'^[a-z]')

# Hyphenated line break: word ends with "-" at line boundary
_HYPHEN_BREAK = re.compile(r'-\s*$')

# Numbered reference start: "1. Author" or "27) Name"
_NUM_REF_START = re.compile(r'^\d{1,3}[\.\)]\s')

# Section heading patterns
_HEADING_ROLES = frozenset({
    ElementRole.HEADING_1,
    ElementRole.HEADING_2,
    ElementRole.HEADING_3,
    ElementRole.REFERENCE_LABEL,
    ElementRole.ABSTRACT_LABEL,
    ElementRole.APPENDIX,
})


class ParagraphMerger:
    """
    Merge fragmented paragraphs detected from PDF-to-DOCX conversions.
    
    Works at the DocIR level — groups consecutive elements of the same
    mergeable role into single elements.  The transformer then outputs
    one paragraph per logical group instead of one per PDF line.
    
    Two-phase approach:
      1. build_merge_plan() → list of index groups (which DocIR para indices merge)
      2. apply_merge_plan() → produces merged DocIR  
      
    The transformer uses the plan to also merge the actual DOCX paragraphs.
    """

    def __init__(self, force_merge: bool = False):
        """
        Args:
            force_merge: If True, always merge. If False, auto-detect
                         whether the document is fragmented.
        """
        self.force_merge = force_merge
        self._median_line_length: float = 65.0  # updated during build_merge_plan

    # ── Public API ───────────────────────────────────────────

    def build_merge_plan(self, docir: DocIR) -> list[list[int]]:
        """
        Analyse the DocIR and return a merge plan.
        
        Returns:
            List of groups, where each group is a list of paragraph indices
            (in doc.paragraphs order) that should be merged together.
            Only groups with 2+ indices are returned (single paragraphs omitted).
            Empty list if no merging needed.
        """
        if not self.force_merge and not self._is_fragmented(docir):
            logger.info("Document does NOT appear fragmented — skipping merge.")
            return []

        logger.info("Document appears fragmented — building merge plan…")

        # Compute median line length for paragraph-boundary detection
        para_lengths = []
        for elem in docir.elements:
            if elem.type == ElementType.PARAGRAPH:
                text = elem.content.strip()
                if text and len(text) > 10:
                    para_lengths.append(len(text))
        if para_lengths:
            self._median_line_length = statistics.median(para_lengths)
        logger.info("Median line length: %.0f chars", self._median_line_length)

        # Build paragraph-index list (only PARAGRAPH type elements)
        para_elements: list[tuple[int, DocElement]] = []
        p_idx = 0
        for elem in docir.elements:
            if elem.type == ElementType.PARAGRAPH:
                para_elements.append((p_idx, elem))
                p_idx += 1

        # Index → DocElement lookup for fast access
        idx_to_elem: dict[int, DocElement] = {p: e for p, e in para_elements}

        # Group consecutive mergeable elements
        groups: list[list[int]] = []
        current_group: list[int] = []
        current_role: Optional[ElementRole] = None

        for p_idx, elem in para_elements:
            role = elem.role
            text = elem.content.strip()

            # Non-mergeable roles break groups
            if role in _HEADING_ROLES or role not in _MERGEABLE_ROLES:
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = []
                current_role = None
                continue

            # Empty paragraphs: only break non-body groups.
            # In fragmented PDFs, stray empty paras shouldn't break body groups.
            if not text:
                if current_role not in (ElementRole.BODY, ElementRole.ABSTRACT_BODY):
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = []
                    current_role = None
                continue

            # Start or continue group
            if current_role is None:
                current_group = [p_idx]
                current_role = role
            elif role == current_role and self._should_merge_by_role(
                current_role,
                [idx_to_elem[current_group[-1]]],
                elem,
            ):
                current_group.append(p_idx)
            else:
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = [p_idx]
                current_role = role

        if len(current_group) >= 2:
            groups.append(current_group)

        total_merged = sum(len(g) for g in groups)
        logger.info(
            "Merge plan: %d groups covering %d paragraphs (of %d total)",
            len(groups), total_merged, p_idx,
        )
        return groups

    def apply_merge_plan(self, docir: DocIR, plan: list[list[int]]) -> DocIR:
        """
        Apply a merge plan to the DocIR, producing a merged copy.
        
        Merged elements get combined text; subordinate elements get
        their content cleared and role set to UNKNOWN.
        """
        if not plan:
            return docir

        new_docir = docir.model_copy(deep=True)

        # Build a map of para_index → element for the new docir
        para_map: dict[int, DocElement] = {}
        p_idx = 0
        for elem in new_docir.elements:
            if elem.type == ElementType.PARAGRAPH:
                para_map[p_idx] = elem
                p_idx += 1

        for group in plan:
            if len(group) < 2:
                continue
            primary_idx = group[0]
            primary = para_map.get(primary_idx)
            if primary is None:
                continue

            # Collect texts, runs and citations from all elements in group
            texts = []
            members = [primary]
            all_citations = list(primary.citations_found)
            texts.append(primary.content.strip())

            for sub_idx in group[1:]:
                sub = para_map.get(sub_idx)
                if sub is None:
                    continue
                texts.append(sub.content.strip())
                members.append(sub.model_copy(deep=True))
                all_citations.extend(sub.citations_found)
                # Clear subordinate
                sub.content = ""
                sub.role = ElementRole.UNKNOWN
                sub.role_confidence = 0.0

            # Merge text (and runs the same way, so italics/superscripts survive)
            primary.content = self._join_texts(texts)
            primary.runs = self._join_runs(members)
            primary.citations_found = all_citations

        return new_docir

    def merge(self, docir: DocIR) -> DocIR:
        """
        Detect fragmentation and merge if needed.
        Convenience method that combines build_merge_plan + apply_merge_plan.
        """
        plan = self.build_merge_plan(docir)
        if not plan:
            return docir
        return self.apply_merge_plan(docir, plan)

    # ── Fragmentation detection ──────────────────────────────

    @staticmethod
    def _is_fragmented(docir: DocIR) -> bool:
        """
        Heuristic: document is fragmented if most paragraphs are
        short (< 100 chars) and similar in length.
        """
        para_lengths = []
        for elem in docir.elements:
            if elem.type != ElementType.PARAGRAPH:
                continue
            text = elem.content.strip()
            if text:
                para_lengths.append(len(text))

        if len(para_lengths) < 20:
            return False

        median_len = statistics.median(para_lengths)
        short_count = sum(1 for l in para_lengths if l < 100)
        short_ratio = short_count / len(para_lengths)

        # Fragmented if >60% of paragraphs are under 100 chars
        # and median length is under 80 chars
        is_frag = short_ratio > 0.60 and median_len < 80

        logger.info(
            "Fragmentation check: median=%d, short_ratio=%.1f%%, fragmented=%s",
            median_len, short_ratio * 100, is_frag,
        )
        return is_frag

    # ── Core merge logic ─────────────────────────────────────

    def _should_merge_by_role(
        self,
        role: ElementRole,
        prev_elems: list[DocElement],
        candidate: DocElement,
    ) -> bool:
        """Decide if *candidate* should merge into the current group."""
        if not prev_elems:
            return True

        last = prev_elems[-1]
        last_text = last.content.strip()
        cand_text = candidate.content.strip()

        # ── Title: always merge consecutive title lines ──────
        if role == ElementRole.TITLE:
            return True

        # ── Author info: merge consecutive author lines ──────
        if role == ElementRole.AUTHOR_INFO:
            return True

        # ── Keywords: merge keyword lines ────────────────────
        if role == ElementRole.KEYWORDS:
            return True

        # ── Reference entries: only merge continuation lines ─
        if role == ElementRole.REFERENCE_ENTRY:
            if _NUM_REF_START.match(cand_text):
                return False
            if re.match(r'^[A-Z][a-zà-ÿ]+[\s,]', cand_text) and re.search(r'\(\d{4}', cand_text):
                return False
            return True

        # ── Figure captions: merge if continuation ───────────
        if role == ElementRole.FIGURE_CAPTION:
            if re.match(r'^(?:Fig\.?|Figure)\s*\d+', cand_text, re.IGNORECASE):
                return False
            return True

        # ── Body / Abstract: sentence-continuation heuristics ─
        #
        # Key insight for PDF-to-DOCX: paragraph-ending lines are SHORT
        # (don't fill the column width) because they're the last line of
        # a paragraph. Continuation lines are near-full width.
        #
        # So: if last line ends with period AND is significantly shorter
        # than the median line length, it's likely a paragraph end.

        # Case 1: hyphen break → always continuation
        if _HYPHEN_BREAK.search(last_text):
            return True

        # Case 2: no sentence-ending punctuation → mid-sentence continuation
        if not _SENTENCE_END.search(last_text):
            return True

        # Case 3: next starts lowercase → continuation (e.g. "and\nfurthermore")
        if _STARTS_LOWER.match(cand_text):
            return True

        # Case 4: candidate starts with a paragraph-starting pattern → new para
        if self._looks_like_new_paragraph(cand_text):
            return False

        # Case 5: SHORT-LINE PARAGRAPH BOUNDARY DETECTION
        # If the last line ends with sentence punctuation AND is
        # significantly shorter than the median line → paragraph end.
        # In PDFs, the final line of a paragraph is typically < 85% of
        # the column width, while continuation lines are near 100%.
        median = self._median_line_length
        if _SENTENCE_END.search(last_text) and len(last_text) < median * 0.82:
            # Short line ending with period → likely paragraph end
            # But only if the candidate also starts with uppercase
            if cand_text and cand_text[0].isupper():
                return False

        # Case 6: Both lines are full-width (close to median) and last
        # ends with sentence punctuation → same paragraph (just happens
        # to end at a sentence boundary mid-line)
        return True

    @staticmethod
    def _looks_like_new_paragraph(text: str) -> bool:
        """Check if text looks like the start of a new paragraph."""
        # Numbered list: "1. Something" or "(a) Something"
        if re.match(r'^[\(\[]?\d+[\.\)]\s', text):
            return True
        if re.match(r'^[\(\[]?[a-z][\.\)]\s', text):
            return True
        # Bullet points
        if text.startswith(('•', '–', '-', '▪', '◦')):
            return True
        return False

    # ── Flush a group into a merged element ──────────────────

    def _flush_group(self, group: list[DocElement], role: Optional[ElementRole]) -> DocElement:
        """Merge a group of elements into a single DocElement."""
        if len(group) == 1:
            return group[0]

        # Join text with hyphen-break reconstruction
        merged_text = self._join_texts([e.content.strip() for e in group])

        # Create merged element using the first element as base
        merged = group[0].model_copy(deep=True)
        merged.content = merged_text

        # Merge citations from all elements in the group
        all_citations = []
        for elem in group:
            all_citations.extend(elem.citations_found)
        merged.citations_found = all_citations

        # Use highest confidence in the group
        merged.role_confidence = max(e.role_confidence for e in group)

        # Mark subordinate elements for skip in transformer mapping
        # (They'll have their content cleared)
        for elem in group[1:]:
            elem.content = ""
            elem.role = ElementRole.UNKNOWN  # Will be skipped

        return merged

    _INVISIBLE = ("\u200b", "\u200f", "\ufeff", "\u00ad")   # same set _join_texts strips

    @classmethod
    def _join_runs(cls, elements: list[DocElement]) -> list:
        """Run-level twin of _join_texts: concatenating the returned runs'
        text gives exactly what _join_texts gives for the same elements
        (same invisible-character removal, stripping, spacing and hyphen
        repair), so downstream code can map formatting back onto the text."""
        from ..schemas.docir import RunFormatting

        result: list = []
        for elem in elements:
            runs = []
            for r in elem.runs:
                t = r.text
                for ch in cls._INVISIBLE:
                    t = t.replace(ch, "")
                if t:
                    c = r.model_copy()
                    c.text = t
                    runs.append(c)
            # strip() at element level, across run boundaries
            while runs and not runs[0].text.strip():
                runs.pop(0)
            while runs and not runs[-1].text.strip():
                runs.pop()
            if not runs:
                continue
            runs[0].text = runs[0].text.lstrip()
            runs[-1].text = runs[-1].text.rstrip()

            if result:
                prev = result[-1]
                if prev.text.endswith("-") and runs[0].text[:1].islower():
                    prev.text = prev.text[:-1]        # "re-" + "port" -> "report"
                    if not prev.text:
                        result.pop()
                elif not prev.text.endswith(" "):
                    result.append(RunFormatting(text=" "))
            result.extend(runs)
        return result

    @staticmethod
    def _join_texts(texts: list[str]) -> str:
        """
        Join text fragments, reconstructing hyphenated words.
        
        "re-" + "port that" → "report that"
        "normal text." + "Next sentence" → "normal text. Next sentence"
        """
        if not texts:
            return ""

        # Clean up zero-width spaces and other PDF artifacts
        cleaned: list[str] = []
        for t in texts:
            # Remove zero-width spaces, soft hyphens, BOM
            t = t.replace('\u200b', '').replace('\u200f', '')
            t = t.replace('\ufeff', '').replace('\u00ad', '')
            t = t.strip()
            if t:
                cleaned.append(t)

        if not cleaned:
            return ""

        result = cleaned[0]
        for text in cleaned[1:]:
            if not text:
                continue

            # Hyphenated word reconstruction
            if result.endswith('-'):
                # Check if it looks like a real hyphenated word or a line-break split
                # Line-break split: "re-" + "port" → lowercase continuation
                if text and text[0].islower():
                    result = result[:-1] + text  # Remove hyphen, join
                    continue

            # Normal join with space
            if result and not result.endswith(' '):
                result += ' '
            result += text

        return result


# ── Module-level convenience function ────────────────────────

def merge_paragraphs(docir: DocIR, force: bool = False) -> DocIR:
    """Convenience function: detect fragmentation and merge if needed."""
    return ParagraphMerger(force_merge=force).merge(docir)
