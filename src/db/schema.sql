-- schema.sql — Analysis database schema.
--
-- The database is a derived artifact. Rebuilding from the processed
-- JSONL/CSV files is the intended workflow. Source of truth remains the
-- processed artifacts under data/processed/.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS lifecycle;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS absences;
DROP TABLE IF EXISTS answers;
DROP TABLE IF EXISTS contracts;

-- One row per contract.
CREATE TABLE contracts (
    contract_id       TEXT PRIMARY KEY,
    canonical_title   TEXT NOT NULL,
    score             INTEGER NOT NULL,
    liability_state   TEXT NOT NULL,
    governing_law     TEXT,
    reference_date    TEXT,
    char_count        INTEGER,
    has_redactions    INTEGER NOT NULL DEFAULT 0,
    redaction_count   INTEGER NOT NULL DEFAULT 0,
    group_id          TEXT,
    part_number       INTEGER,
    sibling_ids       TEXT,
    analyzed_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_contracts_score      ON contracts(score);
CREATE INDEX idx_contracts_liability  ON contracts(liability_state);
CREATE INDEX idx_contracts_group      ON contracts(group_id);
CREATE INDEX idx_contracts_gov_law    ON contracts(governing_law);

-- One row per finding.
CREATE TABLE findings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id  TEXT NOT NULL REFERENCES contracts(contract_id) ON DELETE CASCADE,
    category     TEXT NOT NULL,
    severity     TEXT NOT NULL,
    source       TEXT NOT NULL,
    rationale    TEXT,
    evidence     TEXT,
    caveat       TEXT
);

CREATE INDEX idx_findings_contract  ON findings(contract_id);
CREATE INDEX idx_findings_category  ON findings(category);
CREATE INDEX idx_findings_severity  ON findings(severity);
CREATE INDEX idx_findings_source    ON findings(source);

-- One row per contract.
CREATE TABLE lifecycle (
    contract_id              TEXT PRIMARY KEY REFERENCES contracts(contract_id) ON DELETE CASCADE,
    agreement_date           TEXT,
    effective_date           TEXT,
    expiration_date          TEXT,
    renewal_term             TEXT,
    notice_period            TEXT,
    missing_categories       TEXT,
    missing_but_span_present TEXT,
    narrative                TEXT
);

-- Long-format clause inventory. One row per (contract, category).
-- present = 1 if the category appears in clause spans, 0 if absent.
CREATE TABLE inventory (
    contract_id TEXT NOT NULL REFERENCES contracts(contract_id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    present     INTEGER NOT NULL CHECK (present IN (0, 1)),
    PRIMARY KEY (contract_id, category)
);

CREATE INDEX idx_inventory_category_present ON inventory(category, present);

-- Normalized value answers from master_clauses.csv.
CREATE TABLE answers (
    contract_id TEXT NOT NULL REFERENCES contracts(contract_id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    answer      TEXT,
    PRIMARY KEY (contract_id, category)
);

CREATE INDEX idx_answers_category ON answers(category);

-- Absences from the JSON is_impossible QAs.
CREATE TABLE absences (
    contract_id TEXT NOT NULL REFERENCES contracts(contract_id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    PRIMARY KEY (contract_id, category)
);

CREATE INDEX idx_absences_category ON absences(category);