"""
build_db.py — Build the SQLite analysis database from processed artifacts.

Drops and recreates all tables on each run. The database is a derived
artifact; the processed JSONL/CSV files remain the source of truth.

Usage:
    python -m src.db.build_db
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from src.paths import (
    ABSENCES_JSONL,
    ANSWERS_CSV,
    CONTRACT_METADATA_JSONL,
    DB_PATH,
    REPORTS_DIR,
    SCORED_DIR,
)
from src.nlp.categories import CANONICAL_CATEGORIES


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connect() -> sqlite3.Connection:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_schema(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


def _load_metadata() -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not CONTRACT_METADATA_JSONL.exists():
        return result
    with CONTRACT_METADATA_JSONL.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            result[rec["contract_id"]] = rec
    return result


def _load_scorecards() -> list[dict]:
    cards: list[dict] = []
    if not SCORED_DIR.exists():
        return cards
    for p in sorted(SCORED_DIR.glob("*.json")):
        if p.name == "index.json":
            continue
        cards.append(json.loads(p.read_text(encoding="utf-8")))
    return cards


def _insert_contracts(conn: sqlite3.Connection, cards: list[dict],
                      metadata: dict[str, dict]) -> int:
    rows = []
    for card in cards:
        cid = card["contract_id"]
        meta = metadata.get(cid, {})
        rows.append((
            cid,
            meta.get("canonical_title", cid.lower()),
            card["score"],
            card["liability"]["state"],
            card.get("governing_law"),
            card.get("reference_date"),
            meta.get("char_count", 0),
            1 if meta.get("has_redactions") else 0,
            meta.get("redaction_count", 0),
            card.get("group_id"),
            card.get("part_number"),
            json.dumps(card.get("sibling_ids", [])),
        ))
    conn.executemany(
        """INSERT INTO contracts
           (contract_id, canonical_title, score, liability_state,
            governing_law, reference_date, char_count, has_redactions,
            redaction_count, group_id, part_number, sibling_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def _insert_findings(conn: sqlite3.Connection, cards: list[dict]) -> int:
    rows = []
    for card in cards:
        cid = card["contract_id"]
        for f in card["findings"]:
            rows.append((
                cid,
                f["category"],
                f["severity"],
                f["source"],
                f.get("rationale", ""),
                f.get("evidence", ""),
                f.get("caveat", ""),
            ))
    conn.executemany(
        """INSERT INTO findings
           (contract_id, category, severity, source, rationale, evidence, caveat)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def _insert_lifecycle(conn: sqlite3.Connection, cards: list[dict]) -> int:
    rows = []
    for card in cards:
        lc = card["lifecycle"]
        rows.append((
            card["contract_id"],
            lc.get("agreement_date"),
            lc.get("effective_date"),
            lc.get("expiration_date"),
            lc.get("renewal_term"),
            lc.get("notice_period"),
            json.dumps(lc.get("missing", [])),
            json.dumps(lc.get("missing_but_span_present", [])),
            lc.get("narrative", ""),
        ))
    conn.executemany(
        """INSERT INTO lifecycle
           (contract_id, agreement_date, effective_date, expiration_date,
            renewal_term, notice_period, missing_categories,
            missing_but_span_present, narrative)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def _insert_inventory(conn: sqlite3.Connection, cards: list[dict]) -> int:
    rows = []
    for card in cards:
        cid = card["contract_id"]
        present_set = set(card["inventory_present"])
        for cat in CANONICAL_CATEGORIES:
            rows.append((cid, cat, 1 if cat in present_set else 0))
    conn.executemany(
        "INSERT INTO inventory (contract_id, category, present) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def _insert_answers(conn: sqlite3.Connection) -> int:
    rows = []
    if not ANSWERS_CSV.exists():
        return 0
    with ANSWERS_CSV.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((row["contract_id"], row["category"], row.get("answer", "")))
    conn.executemany(
        "INSERT OR IGNORE INTO answers (contract_id, category, answer) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def _insert_absences(conn: sqlite3.Connection) -> int:
    rows = []
    if not ABSENCES_JSONL.exists():
        return 0
    with ABSENCES_JSONL.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            rows.append((rec["contract_id"], rec["category"]))
    conn.executemany(
        "INSERT OR IGNORE INTO absences (contract_id, category) VALUES (?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def build_db() -> dict:
    cards = _load_scorecards()
    metadata = _load_metadata()

    if not cards:
        raise RuntimeError(
            f"No scorecards found in {SCORED_DIR}. Run src.risk.run first."
        )

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = _connect()
    try:
        _apply_schema(conn)
        n_contracts = _insert_contracts(conn, cards, metadata)
        n_findings = _insert_findings(conn, cards)
        n_lifecycle = _insert_lifecycle(conn, cards)
        n_inventory = _insert_inventory(conn, cards)
        n_answers = _insert_answers(conn)
        n_absences = _insert_absences(conn)
        size_kb = DB_PATH.stat().st_size / 1024
    finally:
        conn.close()

    return {
        "db_path": str(DB_PATH),
        "size_kb": round(size_kb, 1),
        "contracts": n_contracts,
        "findings": n_findings,
        "lifecycle_rows": n_lifecycle,
        "inventory_rows": n_inventory,
        "answers": n_answers,
        "absences": n_absences,
    }