"""
validate.py — Full integrity validation for the CUAD ingestion.

Produces an ingestion_report dict with:
    - file presence
    - contract/QA/span counts
    - offset integrity (should be 0 mismatches)
    - <omitted> token count (expected 0 in JSON)
    - redaction counts
    - TXT <-> JSON alignment after title canonicalization
    - per-category span + absence counts
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.paths import JSON_PATH, CSV_PATH, TXT_DIR
from src.ingest.loader import (
    load_json,
    iter_clause_spans,
    iter_absences,
    canonicalize_title,
)
from src.nlp.categories import CANONICAL_CATEGORIES


OMITTED_TOKEN = "<omitted>"


def validate() -> dict:
    report: dict = {
        "files": {},
        "counts": {},
        "offset_integrity": {},
        "omitted_tokens": 0,
        "redactions": {},
        "txt_alignment": {},
        "categories": {},
        "warnings": [],
    }

    # --- Files ---
    report["files"] = {
        "json": JSON_PATH.exists(),
        "csv": CSV_PATH.exists(),
        "txt_dir": TXT_DIR.exists(),
    }

    # --- Counts ---
    payload = load_json()
    contracts = payload["data"]
    total_contracts = len(contracts)
    total_paragraphs = sum(len(c.get("paragraphs", [])) for c in contracts)
    total_qas = 0
    total_spans = 0
    total_absences = 0
    qa_ids = Counter()

    for c in contracts:
        for para in c.get("paragraphs", []):
            for qa in para.get("qas", []):
                total_qas += 1
                qa_ids[qa["id"]] += 1
                if qa.get("is_impossible"):
                    total_absences += 1
                else:
                    total_spans += len(qa.get("answers", []))

    report["counts"] = {
        "contracts": total_contracts,
        "paragraphs": total_paragraphs,
        "total_qas": total_qas,
        "answer_spans": total_spans,
        "absences": total_absences,
        "distinct_qa_ids": len(qa_ids),
        "duplicate_qa_ids": sum(1 for n in qa_ids.values() if n > 1),
    }

    # --- Offset integrity + omitted + redaction (single pass) ---
    offset_ok = 0
    offset_bad = 0
    omitted_count = 0
    redacted_spans = 0
    bad_examples: list[dict] = []

    for c in contracts:
        title = c["title"]
        for para in c.get("paragraphs", []):
            context = para.get("context", "")
            for qa in para.get("qas", []):
                if qa.get("is_impossible"):
                    continue
                for ans in qa.get("answers", []):
                    text = ans["text"]
                    start = ans["answer_start"]
                    if OMITTED_TOKEN in text:
                        omitted_count += 1
                        continue
                    actual = context[start:start + len(text)]
                    if actual == text:
                        offset_ok += 1
                    else:
                        offset_bad += 1
                        if len(bad_examples) < 5:
                            bad_examples.append({
                                "contract_id": title,
                                "qa_id": qa["id"],
                                "expected": text[:100],
                                "actual": actual[:100],
                            })
                    if any(m in text for m in ("***", "___", "[*", "*]", "[ ]")):
                        redacted_spans += 1

    report["offset_integrity"] = {
        "ok": offset_ok,
        "bad": offset_bad,
        "bad_examples": bad_examples,
    }
    report["omitted_tokens"] = omitted_count
    report["redactions"] = {"spans": redacted_spans}

    # --- TXT alignment (canonicalized) ---
    if TXT_DIR.exists():
        txt_files = list(TXT_DIR.glob("*.txt"))
        txt_by_canon = {canonicalize_title(p.stem): p for p in txt_files}
        json_titles_canon = {canonicalize_title(c["title"]) for c in contracts}

        matched = json_titles_canon & set(txt_by_canon.keys())
        json_only = json_titles_canon - set(txt_by_canon.keys())
        txt_only = set(txt_by_canon.keys()) - json_titles_canon

        report["txt_alignment"] = {
            "txt_files_total": len(txt_files),
            "matched_after_canonicalization": len(matched),
            "json_titles_without_txt": len(json_only),
            "txt_files_without_json": len(txt_only),
            "json_only_examples": sorted(json_only)[:5],
            "txt_only_examples": sorted(txt_only)[:5],
        }

    # --- Category counts ---
    spans_per_cat = Counter()
    absences_per_cat = Counter()

    for span in iter_clause_spans(pad=0):
        spans_per_cat[span.category] += 1
    for absence in iter_absences():
        absences_per_cat[absence.category] += 1

    categories_report = {}
    for cat in CANONICAL_CATEGORIES:
        present = spans_per_cat.get(cat, 0)
        absent = absences_per_cat.get(cat, 0)
        total = present + absent
        rate = absent / total if total else 0.0
        categories_report[cat] = {
            "present": present,
            "absent": absent,
            "total_qas": total,
            "absence_rate": round(rate, 4),
        }
    report["categories"] = categories_report

    # --- Warnings ---
    if offset_bad > 0:
        report["warnings"].append(f"{offset_bad} offset mismatches detected")
    if omitted_count > 0:
        report["warnings"].append(
            f"{omitted_count} spans contain '<omitted>' — handle before offset use"
        )
    if report["counts"]["duplicate_qa_ids"] > 0:
        report["warnings"].append(
            f"{report['counts']['duplicate_qa_ids']} duplicate QA ids"
        )
    if report.get("txt_alignment", {}).get("json_titles_without_txt", 0) > 0:
        report["warnings"].append(
            f"{report['txt_alignment']['json_titles_without_txt']} contracts "
            f"have no matching TXT file after canonicalization"
        )

    return report