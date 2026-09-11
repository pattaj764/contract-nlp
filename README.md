# Contract Risk Analyzer

A diligence-oriented tool that ingests commercial contracts from the Contract Understanding Atticus Dataset (CUAD) v1, applies a legal risk rubric across 41 clause categories, and produces three outputs:

- A SQLite analysis database for ad-hoc querying
- Per-contract PDF reports built with LaTeX
- An interactive Streamlit dashboard with corpus, contract, and group views

> **Not legal advice.** This tool flags clauses for attorney review. It does not opine on whether a clause is favorable or unfavorable to any party and is not a substitute for qualified legal analysis.

---

## Contents

- [Why This Exists](#why-this-exists)
- [Architecture](#architecture)
- [Dataset](#dataset)
- [Risk Rubric](#risk-rubric)
- [Setup](#setup)
- [Running the Pipeline](#running-the-pipeline)
- [Project Layout](#project-layout)
- [Example Queries](#example-queries)
- [Design Decisions](#design-decisions)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License and Attribution](#license-and-attribution)

---

## Why This Exists

Contract review is one of the most time-consuming tasks in legal practice. A paralegal or associate reviewing a stack of commercial agreements is typically looking for the same set of clauses over and over: is there a cap on liability, does the contract have a change-of-control provision, who owns the intellectual property created under the agreement, etc.

This project automates the first pass, reading every contract in the CUAD corpus, scoring each one against a diligence rubric, and producing outputs that let a reviewer see the "shape" of the deal quicker. While this tool does not replace legal judgment, it can tell a reviewer where to look.

The project was built as a portfolio piece demonstrating the intersection of programming and legal reasoning: the risk rubric is drawn from the same categories that experienced attorneys identified as important in contract review, and the scoring engine translates those categories into explicit, auditable rules.

---

## Architecture

```
CUAD_v1.json ─────┐
master_clauses.csv┼──► Ingestion ──► clauses.jsonl
full_contract_txt/┘                  absences.jsonl
                                     answers.csv
                                     contract_metadata.jsonl
                                            │
                                            ▼
                                     Risk Scoring
                                            │
                              ┌─────────────┼─────────────┐
                              ▼             ▼             ▼
                          SQLite        LaTeX PDF     Streamlit
                        (analysis.db)    (reports/)   (dashboard)
```

Each layer is independent. The ingestion layer can be re-run without re-scoring. The scoring layer can be re-run without rebuilding the database. The presentation layers read only from the database, so they stay consistent with each other by construction.

---

## Dataset

Contract data is sourced from the **Contract Understanding Atticus Dataset (CUAD) v1**, created by The Atticus Project and licensed under CC BY 4.0.

- **510 commercial contracts** from SEC EDGAR filings
- **13,000+ expert annotations** across **41 clause categories**
- **~173 MB** total including PDFs, TXT files, and the labeled JSON
- **License:** CC BY 4.0 (free for commercial and non-commercial use)

The dataset is available on Kaggle:
https://www.kaggle.com/datasets/konradb/atticus-open-contract-dataset-aok-beta

Original source:
https://www.atticusprojectai.org/cuad

### Files used

| File | Purpose |
|---|---|
| `CUAD_v1.json` | SQuAD-format clause spans with character offsets (primary label source) |
| `master_clauses.csv` | Normalized value answers (dates, jurisdictions, entity names) |
| `full_contract_txt/` | Full contract text for cross-checking |

The JSON is derived from the CSV, per the CUAD documentation. Both are used. The JSON provides span offsets and absence flags; the CSV provides normalized answers for value-typed categories such as `Governing Law` and `Expiration Date`.

---

## Risk Rubric

The rubric is diligence-oriented. Every finding answers one question: *should a reviewer look at this?* Findings are ranked in three severity tiers.

### Scoring

| Severity | Weight |
|---|---|
| High | 10 |
| Medium | 5 |
| Low | 2 |

The final score is the sum of all finding weights, capped at 100.

### Rule layers

**Layer 1 — Absence rubric.** Nine protective categories are checked for presence. If a protective clause is missing, a finding is raised at the severity assigned to that category.

| Category | Severity if absent |
|---|---|
| Cap On Liability | High |
| Change Of Control | High |
| IP Ownership Assignment | High |
| Insurance | Medium |
| Post-Termination Services | Medium |
| Effective Date | Medium |
| Renewal Term | Medium |
| License Grant | Low |
| Audit Rights | Low |

**Layer 2 — Value rules.** Four categories carry normalized value answers that are checked for content-level issues.

| Category | Rule |
|---|---|
| Governing Law | Flag non-US jurisdictions as medium |
| Effective Date | Flag gap over 30 days from Agreement Date as low |
| Expiration Date | Flag perpetual or expired-against-reference-date |
| Renewal Term | Flag auto-renewal with notice window under 30 days |

**Layer 3 — Presence scoring for restrictive clauses.** Four categories are scored when present, not absent. For restrictive clauses, presence is the finding.

| Category | Trigger |
|---|---|
| Non-Compete | Duration over 24 months or worldwide scope escalates to high |
| Exclusivity | Presence flagged as medium |
| Rofr/Rofo/Rofn | Presence flagged as medium |
| Non-Transferable License | Presence flagged as low |

**Layer 4 — Cross-category inference.**

*Group 1* combines `Agreement Date`, `Effective Date`, `Expiration Date`, `Renewal Term`, and `Notice Period To Terminate Renewal` into a lifecycle narrative.

*Group 5* combines `Cap On Liability` and `Uncapped Liability` into a four-state liability exposure assessment:

| State | Meaning | Severity |
|---|---|---|
| Capped | Cap present, no uncapped language | Low (informational) |
| Silent | Neither present | Medium |
| Uncapped | Explicit uncapped language | High |
| Contradictory | Both present | High |

---

## Setup

### Prerequisites

- Python 3.10 or later
- A LaTeX distribution with `xelatex` (MacTeX, TeX Live, or MiKTeX)
- A Kaggle account for dataset download

### Installation

```bash
git clone <repository-url>
cd contract-nlp

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
```

### Dataset

Download CUAD v1 with the Kaggle CLI:

```bash
kaggle datasets download -d konradb/atticus-open-contract-dataset-aok-beta
unzip atticus-open-contract-dataset-aok-beta.zip -d data/raw/
```

The final layout must be:

```
data/raw/CUAD_v1/
├── CUAD_v1.json
├── master_clauses.csv
└── full_contract_txt/
```

If you prefer to download manually, the same directory layout works.

---

## Running the Pipeline

The pipeline runs in four stages. Each stage reads from the previous stage's output, so you can re-run any stage independently.

### 1. Ingestion

```bash
python3 -m src.ingest.run
```

Validates the dataset, writes clause spans and absences, and produces `data/processed/contract_metadata.jsonl` with multi-part grouping information.

### 2. Absence-rate report

```bash
python3 -m src.ingest.absence_eda
```

Prints a per-category table showing which clauses are near-universal, which have meaningful variation, and which are rare. Useful for understanding the corpus before scoring.

### 3. Scoring

```bash
# Score the full corpus
python3 -m src.risk.run

# Score a single contract
python3 -m src.risk.run --contract "LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT"

# Evaluate expiration logic against a specific date
python3 -m src.risk.run --as-of 2024-01-01
```

Writes one scorecard per contract to `data/processed/scored/`.

### 4. Database

```bash
python3 -m src.db.run build
python3 -m src.db.run summary
```

Builds `reports/analysis.db` from the scorecards and processed artifacts.

### 5. LaTeX reports

```bash
# One contract
python3 -m src.report.run --contract "LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT"

# Top 5 by score
python3 -m src.report.run --top 5

# Full corpus (slow; each PDF takes a few seconds)
python3 -m src.report.run --all

# Emit .tex without compiling (useful without xelatex)
python3 -m src.report.run --top 5 --no-compile
```

PDFs land in `reports/pdf/`.

### 6. Dashboard

```bash
python3 -m streamlit run src/dashboard/app.py
```

Opens a browser to `http://localhost:8501`. Four tabs: Overview, Contracts, Groups, Methodology.

---

## Project Layout

```
contract-nlp/
├── data/
│   ├── raw/CUAD_v1/                Downloaded dataset (not committed)
│   └── processed/                  Derived artifacts (not committed)
├── src/
│   ├── paths.py                    Central path definitions
│   ├── nlp/
│   │   └── categories.py           Canonical 41-category vocabulary
│   ├── ingest/
│   │   ├── loader.py               JSON/CSV loaders, group detection
│   │   ├── validate.py             Ingestion integrity checks
│   │   ├── writer.py               Writes JSONL and CSV artifacts
│   │   ├── absence_eda.py          Absence-rate report
│   │   ├── inspect.py              Structural inspection of the raw dataset
│   │   └── run.py                  Ingestion CLI
│   ├── risk/
│   │   ├── rubric.py               Finding record, severity tables
│   │   ├── value_rules.py          Value-category content rules
│   │   ├── presence_rules.py       Restrictive-clause presence rules
│   │   ├── cross_category.py       Group 1 and Group 5 inference
│   │   ├── score.py                Scorecard orchestrator
│   │   └── run.py                  Scoring CLI
│   ├── db/
│   │   ├── schema.sql              DDL
│   │   ├── build_db.py             Drops, recreates, populates
│   │   ├── dao.py                  Read-only query helpers
│   │   └── run.py                  Database CLI
│   ├── report/
│   │   ├── template.tex.j2         Jinja2 LaTeX template
│   │   ├── build_report.py         Renders and compiles
│   │   └── run.py                  Report CLI
│   └── dashboard/
│       ├── app.py                  Streamlit entry point
│       ├── views/                  Tab renderers
│       └── components/             Chart and table builders
├── reports/
│   ├── analysis.db                 SQLite database
│   ├── latex/                      Generated .tex files
│   ├── pdf/                        Compiled PDFs
│   └── build/                      xelatex intermediate files
├── requirements.txt
└── README.md
```

---

## Example Queries

The database is designed to support ad-hoc SQL. A few examples.

**Contracts with a score above 60 that have at least one high-severity finding:**

```sql
SELECT c.contract_id, c.score, COUNT(f.id) AS high_findings
FROM contracts c
JOIN findings f ON f.contract_id = c.contract_id
WHERE c.score > 60 AND f.severity = 'high'
GROUP BY c.contract_id
ORDER BY c.score DESC;
```

**How often each category is flagged across the corpus:**

```sql
SELECT category, severity, COUNT(*) AS n
FROM findings
GROUP BY category, severity
ORDER BY n DESC;
```

**Contracts with contradictory liability language:**

```sql
SELECT contract_id, score
FROM contracts
WHERE liability_state = 'contradictory'
ORDER BY score DESC;
```

**Contracts governed by non-US law:**

```sql
SELECT contract_id, governing_law, score
FROM contracts
WHERE governing_law IS NOT NULL
  AND governing_law NOT LIKE '%New York%'
  AND governing_law NOT LIKE '%Delaware%'
  AND governing_law NOT LIKE '%California%'
ORDER BY score DESC;
```

**Multi-part groups and their part counts:**

```sql
SELECT group_id, COUNT(*) AS parts, MAX(score) AS max_score
FROM contracts
WHERE group_id IS NOT NULL
GROUP BY group_id
ORDER BY parts DESC;
```

---

## Design Decisions

A few choices worth documenting for anyone reading the code.

**Diligence-oriented, not party-oriented.** The rubric flags items for review. It does not attempt to determine whether a clause is favorable to one party. Party orientation would require knowing which side we represent, which the corpus does not encode.

**Absence rubric excludes restrictive clauses.** Categories such as `Non-Compete` and `Exclusivity` are scored only when present. Their absence is the legal default and produces no finding.

**Presence scoring limited to one extraction per category.** For `Non-Compete`, duration is extracted and worldwide scope is flagged. Other restrictive categories record presence and defer detailed analysis to the reviewer. The reasoning is that structured extraction from legal prose is prone to confident error, and "present, see clause" is more honest.

**Multi-part contracts are annotated, not merged.** Thirty-five contracts in the corpus are fragments of larger agreements. Their absence findings carry a caveat: absence may reflect content in a sibling part. Merging parts would require re-offsetting spans and deciding how to deduplicate overlapping labels, which is a larger change deferred to the roadmap.

**Value answers prefer the CSV, spans prefer the JSON.** The JSON has character offsets and is the only source of span text. The CSV has normalized answers for date and entity categories. Both are loaded and joined on `(contract_id, category)`.

**The database is a derived artifact.** `python -m src.db.run build` drops and recreates all tables on each run. The source of truth is the processed artifacts under `data/processed/`.

---

## Known Limitations

**CUAD date normalization errors.** Some normalized dates in CUAD contain day/month transposition errors. The LIMEENERGYCO distributor agreement is one example: the contract is dated "7th day of September, 1999" in the source but CUAD's normalized `Agreement Date-Answer` reads `7/7/99`. Date-derived lifecycle values should be verified against the original contract text.

**CUAD duration normalization artifacts.** CUAD occasionally produces malformed durations. `"ten (10) years"` in a source contract becomes `"10 1 years"` after normalization. The lifecycle narrative quotes unparsed durations verbatim so a reviewer sees the artifact rather than a misleading paraphrase.

**Multi-part agreements.** Thirty-five contracts are fragments of larger agreements. Their absence findings are annotated with a caveat, and the Groups dashboard tab provides a merged view.

**Redactions.** Two hundred forty-six contracts contain redaction markers. Clauses redacted at the SEC filing stage cannot be scored. Contracts with redactions carry a flag in the metadata, and their reports include a redaction notice.

**Reference date.** Expiration-based findings do not fire unless a reference date is supplied. Regenerate scorecards with `--as-of YYYY-MM-DD` to evaluate the corpus against a specific date. Without a reference date, an expiration finding only fires if the expiration value is literally `Perpetual`.

**Corpus bias.** EDGAR contracts are more heavily negotiated and more complex than the general population of commercial contracts. The tool's outputs reflect that bias. Findings on this corpus may not generalize to simpler agreements.

**Rule-based only.** The current rubric uses regex and structural features. No machine-learning classifier is trained. This is deliberate: rule-based findings are auditable, and every threshold or pattern is documented in the rule modules.

---

## Roadmap

Items deliberately deferred from v1.

**Group-level LaTeX reports.** The `render_group()` stub in `src/report/build_report.py` documents the entry point. The template and the DAO are already designed for it.

**ML clause classifier.** A second rule layer using TF-IDF and logistic regression, trained on CUAD's expert labels, could catch clauses the rules miss. Would run in parallel with the rule layers, not replace them.

**Redaction-aware findings.** Currently a redaction anywhere in a contract sets a flag. A finer-grained version would detect redactions near a specific clause and annotate only the findings that touch that region.

**Contract type awareness.** The rubric uses a single severity per category. Type-aware overrides (for example, `Insurance` absence in a service agreement escalating to high) would refine the scores. Deferred because the corpus mixes original agreements with amendments and exhibits.

**Export to Word.** Some reviewers prefer `.docx` to PDF. A parallel renderer with `python-docx` would be straightforward.

**Streamlit caching improvements.** The current cache resets after five minutes. A manual "clear cache" button in the sidebar would help during development. 

---

## License and Attribution

### Source code

This project's source code is released under the MIT License. See [License](license.txt) for the full text.

Copyright (c) 2026 Jack Pattarini
**Dataset attribution (required by CC BY 4.0):**

> Contract data sourced from the Contract Understanding Atticus Dataset (CUAD) v1, created by The Atticus Project. Licensed under CC BY 4.0. Original dataset: https://www.atticusprojectai.org/cuad 

**Underlying contracts:** Public SEC EDGAR filings. The Atticus Project makes no representations or warranties regarding the license status of the underlying contracts.

**Intended use:** Tools to aid legal professionals. Not a substitute for legal advice. Findings should be reviewed by qualified counsel before any action is taken.

**Not permitted:** Use of this tool as the sole input for contract drafting, contract management, dispute resolution, or the provision of legal advice.