"""
loader.py — Load and normalize the CUAD dataset.

Responsibilities:
    - Read CUAD_v1.json once, cache in memory.
    - Yield ClauseSpan records for every labeled answer.
    - Yield Absence records for every is_impossible QA.
    - Load master_clauses.csv and expose normalized answers keyed by
      (canonical_title, canonical_category).
    - Detect multi-part contracts and expose per-contract metadata.
"""

from __future__ import annotations

import ast
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path

from src.paths import JSON_PATH, CSV_PATH, TXT_DIR, CONTRACT_METADATA_JSONL
from src.nlp.categories import (
    CANONICAL_CATEGORIES,
    canonicalize_column_name,
    extract_category_from_qa_id,
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClauseSpan:
    contract_id: str
    category: str
    qa_id: str
    span_text: str
    answer_start: int
    answer_end: int
    context_window: str
    span_index: int
    total_spans_in_qa: int
    has_redaction: bool


@dataclass(frozen=True)
class Absence:
    contract_id: str
    category: str
    qa_id: str


@dataclass(frozen=True)
class ContractMetadata:
    contract_id: str
    canonical_title: str
    char_count: int
    group_id: str | None
    part_number: int | None
    sibling_ids: tuple[str, ...]
    has_redactions: bool
    redaction_count: int


# ---------------------------------------------------------------------------
# Canonicalization helpers
# ---------------------------------------------------------------------------

def canonicalize_title(title: str) -> str:
    """Normalize whitespace and case for cross-source matching."""
    return " ".join(title.split()).strip().lower()


REDACTION_MARKERS = ("***", "___", "[*", "*]", "[ ]")


def _has_redaction(text: str) -> bool:
    return any(m in text for m in REDACTION_MARKERS)


def _build_context_window(context: str, start: int, end: int, pad: int) -> str:
    lo = max(0, start - pad)
    hi = min(len(context), end + pad)
    return context[lo:hi]


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_json() -> dict:
    with JSON_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def iter_contracts():
    """Yield (contract_id, context, qas) tuples."""
    for contract in load_json()["data"]:
        title = contract["title"]
        for para in contract["paragraphs"]:
            yield title, para.get("context", ""), para.get("qas", [])


# ---------------------------------------------------------------------------
# Span + absence iteration
# ---------------------------------------------------------------------------

def iter_clause_spans(pad: int = 800):
    """
    Yield ClauseSpan for every labeled answer across all contracts.
    Contract scope is one paragraph per contract (verified by inspect.py).
    """
    for contract_id, context, qas in iter_contracts():
        for qa in qas:
            if qa.get("is_impossible"):
                continue
            category = extract_category_from_qa_id(qa["id"])
            answers = qa.get("answers", [])
            total = len(answers)
            for i, ans in enumerate(answers):
                text = ans["text"]
                start = ans["answer_start"]
                end = start + len(text)
                yield ClauseSpan(
                    contract_id=contract_id,
                    category=category,
                    qa_id=qa["id"],
                    span_text=text,
                    answer_start=start,
                    answer_end=end,
                    context_window=_build_context_window(context, start, end, pad),
                    span_index=i,
                    total_spans_in_qa=total,
                    has_redaction=_has_redaction(text),
                )


def iter_absences():
    """Yield Absence for every is_impossible QA."""
    for contract_id, _context, qas in iter_contracts():
        for qa in qas:
            if qa.get("is_impossible"):
                yield Absence(
                    contract_id=contract_id,
                    category=extract_category_from_qa_id(qa["id"]),
                    qa_id=qa["id"],
                )


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _parse_cell(raw: str) -> str:
    """
    CSV non-answer cells look like Python list reprs:
        "['MARKETING AFFILIATE AGREEMENT']"
    Answer cells are plain strings.
    Return a display string either way.
    """
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return "; ".join(str(x) for x in parsed if x)
        except (ValueError, SyntaxError):
            pass
    return s


def load_csv_answers() -> dict[tuple[str, str], str]:
    """
    Return {(canonical_title, category): normalized_answer}.
    Only includes rows whose columns map to canonical categories.
    """
    if not CSV_PATH.exists():
        return {}

    result: dict[tuple[str, str], str] = {}

    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        col_map: list[tuple[int, str, bool]] = []
        for idx, raw_col in enumerate(header):
            stripped = raw_col.strip()
            is_answer = bool(stripped) and "answer" in stripped.lower().rsplit("-", 1)[-1]
            canonical = canonicalize_column_name(raw_col)
            if canonical in CANONICAL_CATEGORIES or stripped.lower() == "filename":
                col_map.append((idx, canonical, is_answer))

        for row in reader:
            if not row:
                continue
            title_canon = None
            answers: dict[str, str] = {}
            for idx, col, is_answer in col_map:
                if idx >= len(row):
                    continue
                cell = _parse_cell(row[idx])
                if col == "Filename":
                    stem = cell.rsplit(".", 1)[0] if cell.lower().endswith(".pdf") else cell
                    title_canon = canonicalize_title(stem)
                elif is_answer:
                    answers[col] = cell
            if title_canon is None:
                continue
            for cat, val in answers.items():
                result[(title_canon, cat)] = val

    return result


# ---------------------------------------------------------------------------
# Contract metadata and multi-part group detection
# ---------------------------------------------------------------------------

_PART_SUFFIX_RE = re.compile(r"[_\s]*Part\s*\d+\s*$", re.IGNORECASE)
_TRAILING_DIGIT_RE = re.compile(r"(?<=[a-zA-Z ])\d+\s*$")


def _base_title(title: str) -> str:
    """Return the grouping key for a contract title."""
    s = title.strip()
    s = _PART_SUFFIX_RE.sub("", s).strip()
    s = _TRAILING_DIGIT_RE.sub("", s).strip()
    return s


def _part_number(title: str) -> int:
    """Extract the trailing part number, or return 0 if none is present."""
    m = _PART_SUFFIX_RE.search(title)
    if m:
        m2 = re.search(r"(\d+)\s*$", m.group(0))
        if m2:
            return int(m2.group(1))
    m = _TRAILING_DIGIT_RE.search(title)
    if m:
        m2 = re.search(r"(\d+)", m.group(0))
        if m2:
            return int(m2.group(1))
    return 0


def _count_redactions(text: str) -> int:
    return sum(text.count(m) for m in REDACTION_MARKERS)


def detect_contract_groups() -> list[ContractMetadata]:
    """
    Group contracts by base title. A group exists only when two or more
    contracts share a base title after stripping part markers. Contracts
    with no siblings are emitted with group_id=None.
    """
    payload = load_json()
    contracts = payload["data"]

    base_to_members: dict[str, list[dict]] = defaultdict(list)

    for c in contracts:
        title = c["title"]
        context = "".join(p.get("context", "") for p in c.get("paragraphs", []))
        rcount = _count_redactions(context)
        base_to_members[_base_title(title)].append({
            "title": title,
            "char_count": len(context),
            "redaction_count": rcount,
            "has_redactions": rcount > 0,
            "part_number": _part_number(title),
        })

    metadata: list[ContractMetadata] = []

    for base, members in base_to_members.items():
        is_group = len(members) > 1
        members_sorted = sorted(members, key=lambda m: (m["part_number"], m["title"]))

        for m in members_sorted:
            if is_group:
                group_id = base
                part_number = m["part_number"] or None
                sibling_ids = tuple(
                    x["title"] for x in members_sorted if x["title"] != m["title"]
                )
            else:
                group_id = None
                part_number = None
                sibling_ids = ()

            metadata.append(ContractMetadata(
                contract_id=m["title"],
                canonical_title=canonicalize_title(m["title"]),
                char_count=m["char_count"],
                group_id=group_id,
                part_number=part_number,
                sibling_ids=sibling_ids,
                has_redactions=m["has_redactions"],
                redaction_count=m["redaction_count"],
            ))

    return metadata


@lru_cache(maxsize=1)
def load_contract_metadata() -> dict[str, ContractMetadata]:
    """
    Load the metadata map. Reads from the written JSONL artifact if present,
    otherwise recomputes from the source JSON. Returns {contract_id: metadata}.
    """
    if CONTRACT_METADATA_JSONL.exists():
        result: dict[str, ContractMetadata] = {}
        with CONTRACT_METADATA_JSONL.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                result[rec["contract_id"]] = ContractMetadata(
                    contract_id=rec["contract_id"],
                    canonical_title=rec["canonical_title"],
                    char_count=rec["char_count"],
                    group_id=rec.get("group_id"),
                    part_number=rec.get("part_number"),
                    sibling_ids=tuple(rec.get("sibling_ids", [])),
                    has_redactions=rec.get("has_redactions", False),
                    redaction_count=rec.get("redaction_count", 0),
                )
        return result

    return {m.contract_id: m for m in detect_contract_groups()}


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def to_dict(record) -> dict:
    """Convert a frozen dataclass instance to a plain dict."""
    return asdict(record)