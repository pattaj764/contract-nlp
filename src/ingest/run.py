"""
run.py — End-to-end CUAD ingestion.

Usage:
    python -m src.ingest.run

Produces:
    data/processed/clauses.jsonl
    data/processed/absences.jsonl
    data/processed/contracts/*.json
    data/processed/answers.csv
    data/processed/ingestion_report.json
"""

from __future__ import annotations

from src.ingest.validate import validate
from src.ingest.writer import (
    write_clauses,
    write_absences,
    write_answers_csv,
    write_report,
    write_contract_metadata,
)


def _hr(label: str) -> None:
    print()
    print("=" * 72)
    print(label)
    print("=" * 72)


def main() -> None:
    _hr("1. VALIDATING")
    report = validate()

    c = report["counts"]
    print(f"  Contracts:            {c['contracts']}")
    print(f"  Paragraphs:           {c['paragraphs']}")
    print(f"  Total QAs:            {c['total_qas']}")
    print(f"  Answer spans:         {c['answer_spans']}")
    print(f"  Absences:             {c['absences']}")
    print(f"  Distinct QA ids:      {c['distinct_qa_ids']}")
    print(f"  Duplicate QA ids:     {c['duplicate_qa_ids']}")

    oi = report["offset_integrity"]
    print(f"  Offset matches OK:    {oi['ok']}")
    print(f"  Offset mismatches:    {oi['bad']}")
    print(f"  '<omitted>' tokens:   {report['omitted_tokens']}")
    print(f"  Redacted spans:       {report['redactions']['spans']}")

    ta = report.get("txt_alignment", {})
    if ta:
        print(f"  TXT files:            {ta['txt_files_total']}")
        print(f"  Matched after canon:  {ta['matched_after_canonicalization']}")
        print(f"  JSON-only titles:     {ta['json_titles_without_txt']}")
        print(f"  TXT-only files:       {ta['txt_files_without_json']}")

    if report["warnings"]:
        print()
        print("  Warnings:")
        for w in report["warnings"]:
            print(f"    - {w}")

    _hr("2. WRITING CLAUSE SPANS")
    n = write_clauses(pad=800)
    print(f"  clauses.jsonl:        {n} records")

    _hr("3. WRITING ABSENCES")
    n = write_absences()
    print(f"  absences.jsonl:       {n} records")

    _hr("4. WRITING ANSWERS CSV")
    n = write_answers_csv()
    print(f"  answers.csv:          {n} rows")

    _hr("5. WRITING CONTRACT METADATA")
    meta_summary = write_contract_metadata()
    print(f"  Records:              {meta_summary['total_records']}")
    print(f"  Multi-part groups:    {meta_summary['multi_part_groups']}")
    print(f"  Multi-part contracts: {meta_summary['multi_part_contracts']}")
    print(f"  Largest group size:   {meta_summary['largest_group_size']}")
    print(f"  Contracts with redactions: {meta_summary['contracts_with_redactions']}")

    _hr("6. WRITING REPORT")
    write_report(report)
    print(f"  ingestion_report.json written")



if __name__ == "__main__":
    main()