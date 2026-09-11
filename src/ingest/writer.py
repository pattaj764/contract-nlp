"""
writer.py — Persist normalized CUAD data to disk.

Outputs (all under data/processed/):
    clauses.jsonl          one record per answer span
    absences.jsonl         one record per is_impossible QA
    contracts/{title}.json per-contract nested view
    answers.csv            long-format (contract, category, answer)
    ingestion_report.json  full validation output
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict

from src.paths import (
    PROCESSED_DIR,
    CONTRACTS_DIR,
    CLAUSES_JSONL,
    ABSENCES_JSONL,
    ANSWERS_CSV,
    REPORT_PATH,
)
from src.ingest.loader import (
    iter_clause_spans,
    iter_absences,
    load_csv_answers,
    canonicalize_title,
    detect_contract_groups,
)
from src.paths import (
    PROCESSED_DIR,
    CONTRACTS_DIR,
    CLAUSES_JSONL,
    ABSENCES_JSONL,
    ANSWERS_CSV,
    REPORT_PATH,
    CONTRACT_METADATA_JSONL,
)
from src.nlp.categories import CANONICAL_CATEGORIES


_SAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str, max_len: int = 180) -> str:
    safe = _SAFE_NAME.sub("_", name).strip()
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip()
    return safe or "unnamed"


def _ensure_dirs() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)


def write_clauses(pad: int = 800) -> int:
    """Stream clause spans into clauses.jsonl and per-contract JSON files."""
    _ensure_dirs()
    by_contract: dict[str, list[dict]] = {}
    n = 0

    with CLAUSES_JSONL.open("w", encoding="utf-8") as f:
        for span in iter_clause_spans(pad=pad):
            rec = asdict(span)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            by_contract.setdefault(span.contract_id, []).append(rec)
            n += 1

    for cid, records in by_contract.items():
        target = CONTRACTS_DIR / f"{_safe_filename(cid)}.json"
        target.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return n


def write_absences() -> int:
    _ensure_dirs()
    n = 0
    with ABSENCES_JSONL.open("w", encoding="utf-8") as f:
        for absence in iter_absences():
            f.write(json.dumps(asdict(absence), ensure_ascii=False) + "\n")
            n += 1
    return n


def write_answers_csv() -> int:
    """
    Long-format CSV: contract_id, category, answer.
    One row per (contract, category), including empty answers for absent clauses.
    """
    _ensure_dirs()
    lookup = load_csv_answers()

    titles = set()
    for span in iter_clause_spans(pad=0):
        titles.add(span.contract_id)
    for absence in iter_absences():
        titles.add(absence.contract_id)

    rows = 0
    with ANSWERS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["contract_id", "category", "answer"])
        for title in sorted(titles):
            title_canon = canonicalize_title(title)
            for cat in CANONICAL_CATEGORIES:
                answer = lookup.get((title_canon, cat), "")
                writer.writerow([title, cat, answer])
                rows += 1
    return rows


def write_report(report: dict) -> None:
    _ensure_dirs()
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def write_contract_metadata() -> dict:
    """
    Write one ContractMetadata record per contract to a JSONL artifact.
    Returns a summary dict for logging.
    """
    _ensure_dirs()
    records = detect_contract_groups()

    with CONTRACT_METADATA_JSONL.open("w", encoding="utf-8") as f:
        for m in records:
            f.write(json.dumps({
                "contract_id": m.contract_id,
                "canonical_title": m.canonical_title,
                "char_count": m.char_count,
                "group_id": m.group_id,
                "part_number": m.part_number,
                "sibling_ids": list(m.sibling_ids),
                "has_redactions": m.has_redactions,
                "redaction_count": m.redaction_count,
            }, ensure_ascii=False) + "\n")

    groups: dict[str, int] = {}
    for m in records:
        if m.group_id:
            groups[m.group_id] = groups.get(m.group_id, 0) + 1

    return {
        "total_records": len(records),
        "multi_part_groups": len(groups),
        "multi_part_contracts": sum(groups.values()),
        "largest_group_size": max(groups.values()) if groups else 0,
        "contracts_with_redactions": sum(
            1 for m in records if m.has_redactions
        ),
    }