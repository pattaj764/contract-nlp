"""
rubric.py — Severity tables and the Finding record.

Diligence-oriented framing: findings tell a reviewer where to look, not
whether a clause is good or bad for a particular party.

This module has no project-internal dependencies so every rule layer can
import from it without creating cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    category: str
    severity: str            # "high" | "medium" | "low"
    rationale: str
    evidence: str = ""
    source: str = ""         # "absence" | "value" | "presence" | "cross_category"
    caveat: str = ""         # optional annotation, e.g. multi-part contracts


# Severity when a protective clause is absent.
ABSENCE_SEVERITY: dict[str, str] = {
    "Cap On Liability": "high",
    "Change Of Control": "high",
    "Ip Ownership Assignment": "high",
    "Insurance": "medium",
    "Post-Termination Services": "medium",
    "Effective Date": "medium",
    "Renewal Term": "medium",
    "License Grant": "low",
    "Audit Rights": "low",
}

# Restrictive clauses (Non-Compete, Exclusivity, Rofr/Rofo/Rofn,
# Non-Transferable License) are intentionally excluded. For restrictive
# clauses, presence is the finding, not absence. They are scored in
# presence_rules.py.
ABSENCE_RATIONALE: dict[str, str] = {
    "Cap On Liability":
        "No contractual cap on liability. Exposure is potentially unlimited "
        "for one or both parties.",
    "Change Of Control":
        "No change-of-control provision. Survival of the contract upon "
        "acquisition or reorganization is ambiguous.",
    "Ip Ownership Assignment":
        "No IP ownership assignment. Ownership of work product created "
        "under the contract is unclear.",
    "Insurance":
        "No insurance requirement. No contractual obligation to maintain "
        "coverage for the benefit of the counterparty.",
    "Post-Termination Services":
        "No post-termination services clause. Transition obligations at "
        "termination are unaddressed.",
    "Effective Date":
        "No effective date specified. Contract start date is unclear from "
        "the face of the document.",
    "Renewal Term":
        "No renewal term specified. Contract is fixed-term with no renewal "
        "provision.",
    "License Grant":
        "No license grant. Contract contains no license from one party to "
        "the other.",
    "Audit Rights":
        "No audit rights. No contractual mechanism to audit books, records, "
        "or locations.",
}


# Categories tracked only in the inventory layer, not scored.
INVENTORY_ONLY: frozenset[str] = frozenset({
    "Minimum Commitment",
    "Revenue/Profit Sharing",
    "Termination For Convenience",
})


# Categories where presence (not absence) is the diligence finding.
PRESENCE_SCORED: frozenset[str] = frozenset({
    "Non-Compete",
    "Exclusivity",
    "Rofr/Rofo/Rofn",
    "Non-Transferable License",
    "Uncapped Liability",
})


SEVERITY_WEIGHT: dict[str, int] = {
    "high": 10,
    "medium": 5,
    "low": 2,
}