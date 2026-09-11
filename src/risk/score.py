"""
score.py — Scorecard orchestrator.

Reads clauses.jsonl, absences.jsonl, answers.csv, and contract_metadata.jsonl
for each contract, applies every rule layer, and emits a Scorecard.

Multi-part contracts (contracts whose titles share a base after stripping
part markers) receive a caveat on every absence finding. Group-level
aggregation is deferred; the Scorecard records group_id and part_number so
a future group view is a join away.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date

from src.paths import ABSENCES_JSONL, ANSWERS_CSV, CLAUSES_JSONL
from src.nlp.categories import CANONICAL_CATEGORIES
from src.risk import cross_category, presence_rules, value_rules
from src.risk.rubric import (
    ABSENCE_RATIONALE,
    ABSENCE_SEVERITY,
    SEVERITY_WEIGHT,
    Finding,
)


MULTI_PART_CAVEAT = (
    "Part {n} of a multi-part agreement; absence may reflect content "
    "in another part."
)


@dataclass
class Scorecard:
    contract_id: str
    score: int
    findings: list[Finding]
    lifecycle: dict
    liability: dict
    inventory_present: list[str]
    inventory_absent: list[str]
    governing_law: str | None
    reference_date: str | None
    group_id: str | None = None
    part_number: int | None = None
    sibling_ids: tuple[str, ...] = ()
    has_redactions: bool = False

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "score": self.score,
            "findings": [asdict(f) for f in self.findings],
            "lifecycle": self.lifecycle,
            "liability": self.liability,
            "inventory_present": self.inventory_present,
            "inventory_absent": self.inventory_absent,
            "governing_law": self.governing_law,
            "reference_date": self.reference_date,
            "group_id": self.group_id,
            "part_number": self.part_number,
            "sibling_ids": list(self.sibling_ids),
            "has_redactions": self.has_redactions,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_clauses_by_contract() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    if not CLAUSES_JSONL.exists():
        return result
    with CLAUSES_JSONL.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            result.setdefault(rec["contract_id"], []).append(rec)
    return result


def load_absences_by_contract() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not ABSENCES_JSONL.exists():
        return result
    with ABSENCES_JSONL.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            result.setdefault(rec["contract_id"], []).append(rec["category"])
    return result


def load_answers_by_contract() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if not ANSWERS_CSV.exists():
        return result
    with ANSWERS_CSV.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["contract_id"]
            cat = row["category"]
            ans = row.get("answer", "")
            result.setdefault(cid, {})[cat] = ans
    return result


def load_metadata_by_contract() -> dict:
    """
    Load contract metadata. Uses the ingestion artifact if present; otherwise
    computes in memory from the source JSON.
    """
    from src.ingest.loader import load_contract_metadata
    try:
        return load_contract_metadata()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _apply_multi_part_caveat(findings: list[Finding], metadata) -> None:
    """
    Annotate absence findings on multi-part contracts in place. No-op when
    metadata is None or the contract is not part of a group.
    """
    if metadata is None or not metadata.group_id:
        return
    n = metadata.part_number if metadata.part_number is not None else "?"
    caveat = MULTI_PART_CAVEAT.format(n=n)
    for f in findings:
        if f.source == "absence":
            f.caveat = caveat


def score_contract(
    contract_id: str,
    spans: list[dict],
    absences: list[str],
    answers: dict[str, str],
    as_of: date | None,
    metadata=None,
) -> Scorecard:
    present: set[str] = set()
    span_by_category: dict[str, str] = {}
    for s in spans:
        present.add(s["category"])
        span_by_category.setdefault(s["category"], s["span_text"])

    findings: list[Finding] = []

    # Layer 1: absence rubric
    for category, severity in ABSENCE_SEVERITY.items():
        if category in present:
            continue
        findings.append(Finding(
            category=category,
            severity=severity,
            rationale=ABSENCE_RATIONALE.get(category, "Absent."),
            evidence="",
            source="absence",
        ))

    # Layer 2: value rules
    gov = answers.get("Governing Law", "")
    for candidate in (
        value_rules.governing_law_finding(gov),
        value_rules.agreement_effective_gap_finding(
            answers.get("Agreement Date", ""),
            answers.get("Effective Date", ""),
        ),
        value_rules.expiration_finding(
            answers.get("Expiration Date", ""),
            answers.get("Effective Date", ""),
            answers.get("Renewal Term", ""),
            answers.get("Notice Period To Terminate Renewal", ""),
            as_of,
        ),
        value_rules.renewal_notice_finding(
            answers.get("Renewal Term", ""),
            answers.get("Notice Period To Terminate Renewal", ""),
        ),
    ):
        if candidate is not None:
            findings.append(candidate)

    # Layer 3: presence scoring for restrictive clauses
    for category, extractor in (
        ("Non-Compete", presence_rules.non_compete_finding),
        ("Exclusivity", presence_rules.exclusivity_finding),
        ("Rofr/Rofo/Rofn", presence_rules.rofr_finding),
        ("Non-Transferable License", presence_rules.non_transferable_license_finding),
    ):
        if category not in present:
            continue
        f = extractor(span_by_category.get(category, ""))
        if f is not None:
            findings.append(f)

    # Layer 4: cross-category inference
    lifecycle = cross_category.build_lifecycle(answers, present)
    liability = cross_category.assess_liability_exposure(
        cap_present="Cap On Liability" in present,
        uncapped_present="Uncapped Liability" in present,
    )
    lf = cross_category.liability_finding(liability)
    if lf is not None:
        findings.append(lf)

    # Annotation layer
    _apply_multi_part_caveat(findings, metadata)

    score = _compute_score(findings)

    return Scorecard(
        contract_id=contract_id,
        score=score,
        findings=findings,
        lifecycle=lifecycle.to_dict(),
        liability=liability.to_dict(),
        inventory_present=sorted(present),
        inventory_absent=sorted(
            cat for cat in CANONICAL_CATEGORIES if cat not in present
        ),
        governing_law=gov or None,
        reference_date=as_of.isoformat() if as_of else None,
        group_id=metadata.group_id if metadata else None,
        part_number=metadata.part_number if metadata else None,
        sibling_ids=metadata.sibling_ids if metadata else (),
        has_redactions=metadata.has_redactions if metadata else False,
    )


def _compute_score(findings: list[Finding]) -> int:
    total = sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in findings)
    return min(total, 100)