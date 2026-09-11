"""
run.py — Score contracts from the command line.

Usage:
    python -m src.risk.run
    python -m src.risk.run --contract <contract_id>
    python -m src.risk.run --as-of 2024-01-01
    python -m src.risk.run --limit 10

Writes:
    data/processed/scored/<contract_id>.json
    data/processed/scored/index.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime

from src.paths import SCORED_DIR
from src.risk.score import (
    load_absences_by_contract,
    load_answers_by_contract,
    load_clauses_by_contract,
    load_metadata_by_contract,
    score_contract,
)


_SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str, max_len: int = 180) -> str:
    s = _SAFE.sub("_", name).strip()
    return s[:max_len] or "unnamed"


def _parse_as_of(raw: str | None) -> date | None:
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=str, default=None,
                        help="Score a single contract by id")
    parser.add_argument("--as-of", type=str, default=None,
                        help="Reference date (YYYY-MM-DD) for expiration logic")
    parser.add_argument("--limit", type=int, default=None,
                        help="Score only the first N contracts")
    args = parser.parse_args()

    as_of = _parse_as_of(args.as_of)
    SCORED_DIR.mkdir(parents=True, exist_ok=True)

    clauses = load_clauses_by_contract()
    absences = load_absences_by_contract()
    answers = load_answers_by_contract()
    metadata = load_metadata_by_contract()

    contract_ids = sorted(set(clauses) | set(absences) | set(answers))

    if args.contract:
        if args.contract not in contract_ids:
            print(f"Contract not found: {args.contract}")
            return
        contract_ids = [args.contract]

    if args.limit:
        contract_ids = contract_ids[: args.limit]

    ref = as_of.isoformat() if as_of else "none"
    n_multi = sum(
        1 for cid in contract_ids
        if cid in metadata and metadata[cid].group_id
    )
    n_redacted = sum(
        1 for cid in contract_ids
        if cid in metadata and metadata[cid].has_redactions
    )

    print(f"Scoring {len(contract_ids)} contract(s) "
          f"(reference date: {ref})")
    print(f"  Multi-part contracts:  {n_multi}")
    print(f"  Contracts with redactions: {n_redacted}")

    index: list[dict] = []
    for cid in contract_ids:
        card = score_contract(
            contract_id=cid,
            spans=clauses.get(cid, []),
            absences=absences.get(cid, []),
            answers=answers.get(cid, {}),
            as_of=as_of,
            metadata=metadata.get(cid),
        )
        out_path = SCORED_DIR / f"{_safe_filename(cid)}.json"
        out_path.write_text(
            json.dumps(card.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        index.append({
            "contract_id": cid,
            "score": card.score,
            "n_findings": len(card.findings),
            "high": sum(1 for f in card.findings if f.severity == "high"),
            "medium": sum(1 for f in card.findings if f.severity == "medium"),
            "low": sum(1 for f in card.findings if f.severity == "low"),
            "liability_state": card.liability["state"],
            "group_id": card.group_id,
            "part_number": card.part_number,
        })

    (SCORED_DIR / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(index)} scorecard(s) to {SCORED_DIR}")


if __name__ == "__main__":
    main()