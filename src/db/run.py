"""
run.py — CLI entry point for the database layer.

Usage:
    python -m src.db.run build
    python -m src.db.run summary
    python -m src.db.run contract <contract_id>
    python -m src.db.run group <group_id>
    python -m src.db.run groups
"""

from __future__ import annotations

import sys

from src.db import dao
from src.db.build_db import build_db


def _hr(label: str) -> None:
    print()
    print("=" * 72)
    print(label)
    print("=" * 72)


def cmd_build() -> None:
    _hr("BUILDING DATABASE")
    summary = build_db()
    print(f"  Path:           {summary['db_path']}")
    print(f"  Size:           {summary['size_kb']} KB")
    print(f"  Contracts:      {summary['contracts']}")
    print(f"  Findings:       {summary['findings']}")
    print(f"  Lifecycle rows: {summary['lifecycle_rows']}")
    print(f"  Inventory rows: {summary['inventory_rows']}")
    print(f"  Answers:        {summary['answers']}")
    print(f"  Absences:       {summary['absences']}")


def cmd_summary() -> None:
    _hr("CORPUS SUMMARY")
    sev = dao.severity_distribution()
    print("Findings by severity:")
    for k in ("high", "medium", "low"):
        print(f"  {k:<8} {sev.get(k, 0)}")

    liab = dao.liability_state_distribution()
    print()
    print("Liability state:")
    for k, n in liab.items():
        print(f"  {k:<14} {n}")

    print()
    print("Top 10 contracts by score:")
    for row in dao.top_contracts_by_score(10):
        red = " [redacted]" if row["has_redactions"] else ""
        print(f"  {row['score']:>3}  {row['contract_id'][:70]}{red}")


def cmd_contract(contract_id: str) -> None:
    card = dao.get_scorecard(contract_id)
    if card is None:
        print(f"Not found: {contract_id}")
        return
    print(f"Score:           {card['contract']['score']}")
    print(f"Liability state: {card['contract']['liability_state']}")
    print(f"Governing law:   {card['contract']['governing_law'] or '(none)'}")
    print()
    print("Findings:")
    for f in card["findings"]:
        print(f"  [{f['severity']:<6}] {f['category']}")
        if f.get("caveat"):
            print(f"           caveat: {f['caveat']}")


def cmd_group(group_id: str) -> None:
    parts = dao.get_group(group_id)
    if not parts:
        print(f"Group not found: {group_id}")
        return
    print(f"Group:  {group_id}")
    print(f"Parts:  {len(parts)}")
    for p in parts:
        print(f"  Part {p['part_number']}: score {p['score']} "
              f"({p['liability_state']}, {p['char_count']} chars)")
    print()
    print("Combined findings (deduplicated by category, highest severity):")
    for f in dao.get_group_findings(group_id):
        print(f"  [{f['severity']:<6}] {f['category']}  (from {f['contract_id'][:50]})")


def cmd_groups() -> None:
    groups = dao.list_groups()
    print(f"Multi-part groups: {len(groups)}")
    for g in groups:
        print(f"  {g['n_parts']}x  {g['group_id'][:80]}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "build":
        cmd_build()
        return
    cmd = args[0]
    if cmd == "summary":
        cmd_summary()
    elif cmd == "contract" and len(args) >= 2:
        cmd_contract(args[1])
    elif cmd == "group" and len(args) >= 2:
        cmd_group(args[1])
    elif cmd == "groups":
        cmd_groups()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()