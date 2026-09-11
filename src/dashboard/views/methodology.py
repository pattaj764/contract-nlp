"""
methodology.py — Methodology and limitations tab.
"""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.header("Methodology and Limitations")

    st.markdown(
        """
### Purpose

This tool applies a diligence-oriented risk rubric to commercial contracts
sourced from the Contract Understanding Atticus Dataset (CUAD) v1. Findings
flag clauses that merit attorney review. They do not constitute legal advice
and do not opine on whether a clause is favorable or unfavorable to any
particular party.

### Scoring

Findings are assigned one of three severity tiers:

- **High** -- material legal exposure or ambiguity.
- **Medium** -- notable gap or exposure; worth a reviewer's attention.
- **Low** -- informational; may be a standard feature of the contract type.

Severity weights are 10, 5, and 2 points respectively. The final score is
the sum of all finding weights, capped at 100.

### Rule layers

1. **Absence rubric.** Twelve protective categories are checked for
   presence. If a protective clause is missing, a finding is raised at the
   severity assigned to that category.
2. **Value rules.** Categories with normalized value answers (`Governing
   Law`, `Effective Date`, `Expiration Date`, `Renewal Term`) are checked
   for content-level issues such as non-US governing law or a short
   renewal notice window.
3. **Presence scoring for restrictive clauses.** `Non-Compete`,
   `Exclusivity`, `Rofr/Rofo/Rofn`, and `Non-Transferable License` are
   scored when present, not when absent. Presence is the finding for
   restrictive clauses.
4. **Cross-category inference.** Group 1 categories are combined into a
   lifecycle narrative. Group 5 categories are combined into a four-state
   liability exposure assessment (`capped`, `uncapped`, `contradictory`,
   `silent`).

### Known limitations

- **CUAD date normalization.** Some normalized dates in CUAD contain
  transposition errors. Date-derived lifecycle values should be verified
  against the original contract text.
- **Multi-part agreements.** Thirty-five contracts in this corpus are
  fragments of larger agreements filed across multiple exhibits. Absence
  findings on those contracts carry a caveat in the report and are
  annotated in the detail view.
- **Redactions.** Two hundred forty-six contracts contain redaction
  markers. Clauses redacted at the SEC filing stage cannot be scored.
- **Reference date.** Expiration-based findings do not fire unless a
  reference date is supplied. Regenerate scorecards with
  `python -m src.risk.run --as-of YYYY-MM-DD` to evaluate the corpus
  against a specific date.

### Data source

Contract data sourced from the Contract Understanding Atticus Dataset
(CUAD) v1, created by The Atticus Project and licensed under CC BY 4.0.
The underlying contracts are public SEC EDGAR filings.

Dataset: https://www.atticusprojectai.org/cuad
        """
    )