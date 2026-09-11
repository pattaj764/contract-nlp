"""
absence_eda.py — Absence-rate report per category.

Answers: "which categories are present in the corpus, and which are mostly
absent?" — critical for deciding which risk findings the tool should surface.

Usage:
    python -m src.ingest.absence_eda
"""

from __future__ import annotations

from collections import Counter

from src.ingest.loader import iter_clause_spans, iter_absences
from src.nlp.categories import (
    CANONICAL_CATEGORIES,
    CATEGORY_GROUPS,
    ANSWER_TYPE,
)


def main() -> None:
    present = Counter()
    absent = Counter()

    for span in iter_clause_spans(pad=0):
        present[span.category] += 1
    for absence in iter_absences():
        absent[absence.category] += 1

    rows = []
    for cat in CANONICAL_CATEGORIES:
        p = present.get(cat, 0)
        a = absent.get(cat, 0)
        total = p + a
        rate = a / total if total else 0.0
        rows.append({
            "category": cat,
            "answer_type": ANSWER_TYPE[cat],
            "group": CATEGORY_GROUPS.get(cat),
            "present_qas": p,
            "absent_qas": a,
            "total_qas": total,
            "absence_rate": rate,
        })

    rows.sort(key=lambda r: r["absence_rate"])

    print(f"{'Category':<40} {'Type':<8} {'Grp':<4} "
          f"{'Present':>8} {'Absent':>8} {'Abs%':>7}")
    print("-" * 82)
    for r in rows:
        grp = "-" if r["group"] is None else str(r["group"])
        print(f"{r['category']:<40} {r['answer_type']:<8} {grp:<4} "
              f"{r['present_qas']:>8} {r['absent_qas']:>8} "
              f"{r['absence_rate']*100:>6.1f}%")

    print()
    print("Interpretation guide:")
    print("  Absence rate ~0%  -> near-universal clause; not a useful flag.")
    print("  Absence rate 5-50% -> meaningful variation; strong signal.")
    print("  Absence rate >80% -> rare clause; flagging presence is more useful.")
    print()
    print("Portfolio recommendation:")
    print("  Focus the risk rubric on categories with absence rate 5-60% AND")
    print("  meaningful legal consequence if present/absent.")


if __name__ == "__main__":
    main()