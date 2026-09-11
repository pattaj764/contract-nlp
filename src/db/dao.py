"""
dao.py — Read-only query helpers for the analysis database.

Query patterns:
    1. Per-contract lookups (get_scorecard, get_findings, get_lifecycle)
    2. Corpus-wide aggregates (severity_distribution, top_contracts_by_score)
    3. Group-level views (get_group, get_group_findings)
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from src.paths import DB_PATH


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Run src.db.build_db first."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Per-contract queries
# ---------------------------------------------------------------------------

def get_contract(contract_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        return dict(row) if row else None


def get_findings(contract_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT category, severity, source, rationale, evidence, caveat
               FROM findings
               WHERE contract_id = ?
               ORDER BY
                 CASE severity
                   WHEN 'high' THEN 1
                   WHEN 'medium' THEN 2
                   ELSE 3
                 END,
                 category""",
            (contract_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_lifecycle(contract_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM lifecycle WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        return dict(row) if row else None


def get_inventory(contract_id: str) -> dict[str, list[str]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, present FROM inventory WHERE contract_id = ?",
            (contract_id,),
        ).fetchall()
    present = [r["category"] for r in rows if r["present"]]
    absent = [r["category"] for r in rows if not r["present"]]
    return {"present": sorted(present), "absent": sorted(absent)}


def get_scorecard(contract_id: str) -> dict | None:
    contract = get_contract(contract_id)
    if contract is None:
        return None
    return {
        "contract": contract,
        "findings": get_findings(contract_id),
        "lifecycle": get_lifecycle(contract_id),
        "inventory": get_inventory(contract_id),
    }


# ---------------------------------------------------------------------------
# Corpus-wide aggregates
# ---------------------------------------------------------------------------

def category_frequency() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT category, severity, COUNT(*) AS n
               FROM findings
               GROUP BY category, severity
               ORDER BY n DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def severity_distribution() -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT severity, COUNT(*) AS n FROM findings GROUP BY severity"
        ).fetchall()
        return {r["severity"]: r["n"] for r in rows}


def liability_state_distribution() -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT liability_state, COUNT(*) AS n FROM contracts GROUP BY liability_state"
        ).fetchall()
        return {r["liability_state"]: r["n"] for r in rows}


def inventory_coverage() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT category,
                      SUM(present) AS present_count,
                      COUNT(*) AS total
               FROM inventory
               GROUP BY category
               ORDER BY present_count DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def top_contracts_by_score(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT contract_id, score, liability_state, governing_law,
                      group_id, part_number, has_redactions
               FROM contracts
               ORDER BY score DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def contracts_with_category(category: str, present: bool = True) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT c.contract_id, c.score, c.liability_state
               FROM contracts c
               JOIN inventory i ON i.contract_id = c.contract_id
               WHERE i.category = ? AND i.present = ?
               ORDER BY c.score DESC""",
            (category, 1 if present else 0),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Group-level queries (Option D foundation)
# ---------------------------------------------------------------------------

def get_group(group_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT contract_id, part_number, score, liability_state,
                      char_count, has_redactions
               FROM contracts
               WHERE group_id = ?
               ORDER BY part_number""",
            (group_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_groups() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT group_id,
                      COUNT(*)     AS n_parts,
                      SUM(score)   AS sum_score,
                      MAX(score)   AS max_score,
                      MIN(score)   AS min_score
               FROM contracts
               WHERE group_id IS NOT NULL
               GROUP BY group_id
               ORDER BY group_id""",
        ).fetchall()
        return [dict(r) for r in rows]


def get_group_findings(group_id: str) -> list[dict]:
    """
    Combined findings across all parts in a group, deduplicated by category
    keeping the highest severity. This is the Option D combined view.
    """
    with _connect() as conn:
        rows = conn.execute(
            """SELECT f.category, f.severity, f.source, f.rationale,
                      f.contract_id
               FROM findings f
               JOIN contracts c ON c.contract_id = f.contract_id
               WHERE c.group_id = ?""",
            (group_id,),
        ).fetchall()

    rank = {"high": 3, "medium": 2, "low": 1}
    by_category: dict[str, dict] = {}
    for r in rows:
        cat = r["category"]
        existing = by_category.get(cat)
        if existing is None or rank[r["severity"]] > rank[existing["severity"]]:
            by_category[cat] = dict(r)

    return sorted(
        by_category.values(),
        key=lambda r: (-rank[r["severity"]], r["category"]),
    )

def list_contracts_dashboard() -> list[dict]:
    """
    One row per contract with finding counts and metadata, for the
    Contracts table in the dashboard.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.contract_id,
                c.score,
                c.liability_state,
                c.governing_law,
                c.has_redactions,
                c.redaction_count,
                c.group_id,
                c.part_number,
                COALESCE(SUM(CASE WHEN f.severity = 'high'   THEN 1 ELSE 0 END), 0) AS high,
                COALESCE(SUM(CASE WHEN f.severity = 'medium' THEN 1 ELSE 0 END), 0) AS medium,
                COALESCE(SUM(CASE WHEN f.severity = 'low'    THEN 1 ELSE 0 END), 0) AS low,
                COUNT(f.id) AS total_findings
            FROM contracts c
            LEFT JOIN findings f ON f.contract_id = c.contract_id
            GROUP BY c.contract_id
            ORDER BY c.score DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_group_findings_with_provenance(group_id: str) -> list[dict]:
    """
    Combined findings across a group, deduplicated by category, keeping
    the highest severity. Each result lists the parts that contributed.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT f.category, f.severity, f.source, f.rationale,
                   f.contract_id, c.part_number
            FROM findings f
            JOIN contracts c ON c.contract_id = f.contract_id
            WHERE c.group_id = ?
            ORDER BY f.category, c.part_number
            """,
            (group_id,),
        ).fetchall()

    rank = {"high": 3, "medium": 2, "low": 1}
    by_category: dict[str, dict] = {}

    for r in rows:
        cat = r["category"]
        existing = by_category.get(cat)
        if existing is None:
            by_category[cat] = {
                "category": cat,
                "severity": r["severity"],
                "source": r["source"],
                "rationale": r["rationale"],
                "parts": [r["part_number"]],
            }
        else:
            if r["part_number"] not in existing["parts"]:
                existing["parts"].append(r["part_number"])
            if rank[r["severity"]] > rank[existing["severity"]]:
                existing["severity"] = r["severity"]
                existing["source"] = r["source"]
                existing["rationale"] = r["rationale"]

    return sorted(
        by_category.values(),
        key=lambda x: (-rank[x["severity"]], x["category"]),
    )