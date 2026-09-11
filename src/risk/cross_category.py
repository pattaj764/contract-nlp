"""
cross_category.py — Cross-category inference.

Group 1: Contract lifecycle narrative, assembled from value answers.
Group 5: Liability exposure state, assembled from Cap On Liability and
Uncapped Liability presence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.risk.rubric import Finding


# ---------------------------------------------------------------------------
# Group 1: lifecycle
# ---------------------------------------------------------------------------

_GROUP_1_FIELDS: tuple[tuple[str, str], ...] = (
    ("agreement_date", "Agreement Date"),
    ("effective_date", "Effective Date"),
    ("expiration_date", "Expiration Date"),
    ("renewal_term", "Renewal Term"),
    ("notice_period", "Notice Period To Terminate Renewal"),
)


@dataclass
class LifecycleSummary:
    agreement_date: str | None = None
    effective_date: str | None = None
    expiration_date: str | None = None
    renewal_term: str | None = None
    notice_period: str | None = None
    missing: list[str] = field(default_factory=list)
    missing_but_span_present: list[str] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> dict:
        return {
            "agreement_date": self.agreement_date,
            "effective_date": self.effective_date,
            "expiration_date": self.expiration_date,
            "renewal_term": self.renewal_term,
            "notice_period": self.notice_period,
            "missing": list(self.missing),
            "missing_but_span_present": list(self.missing_but_span_present),
            "narrative": self.narrative,
        }


def build_lifecycle(
    values: dict[str, str],
    spans_present: set[str],
) -> LifecycleSummary:
    """
    Assemble a lifecycle summary from Group 1 value answers.

    `spans_present` is the set of categories for which a JSON clause span
    exists (from clauses.jsonl). It distinguishes between "category truly
    absent" and "category present in JSON but with no normalized value
    answer in the CSV".
    """
    lc = LifecycleSummary()
    for field_name, category in _GROUP_1_FIELDS:
        val = (values.get(category) or "").strip()
        if val:
            setattr(lc, field_name, val)
        elif category in spans_present:
            lc.missing_but_span_present.append(category)
        else:
            lc.missing.append(category)
    lc.narrative = _narrate(lc)
    return lc


_DURATION_PATTERN = re.compile(
    r"^\s*\d+\s*(day|days|week|weeks|month|months|year|years)\s*$",
    re.IGNORECASE,
)


def _is_clean_duration(s: str) -> bool:
    return bool(_DURATION_PATTERN.match(s or ""))


def _narrate(lc: LifecycleSummary) -> str:
    parts: list[str] = []

    if lc.agreement_date:
        parts.append(f"dated {lc.agreement_date}")
    if lc.effective_date:
        parts.append(f"effective {lc.effective_date}")
    if lc.expiration_date:
        parts.append(f"expiring {lc.expiration_date}")
    elif ("Expiration Date" in lc.missing
          or "Expiration Date" in lc.missing_but_span_present):
        parts.append("with no stated expiration date")

    if lc.renewal_term:
        if _is_clean_duration(lc.renewal_term):
            parts.append(f"renewing for {lc.renewal_term}")
        else:
            parts.append(
                f'renewing for "{lc.renewal_term}" '
                f"(unparsed; see clause)"
            )
        if lc.notice_period:
            parts.append(f"unless notice is given {lc.notice_period} prior")
        else:
            parts.append("(notice period not specified)")

    if not parts:
        return "No lifecycle components extractable from the contract."
    return "This agreement is " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Group 5: liability exposure
# ---------------------------------------------------------------------------

@dataclass
class LiabilityExposure:
    state: str = "silent"       # capped | uncapped | contradictory | silent
    severity: str = "medium"
    note: str = ""

    def to_dict(self) -> dict:
        return {"state": self.state, "severity": self.severity, "note": self.note}


def assess_liability_exposure(
    cap_present: bool,
    uncapped_present: bool,
) -> LiabilityExposure:
    """Group 5 four-state assessment."""
    if cap_present and uncapped_present:
        return LiabilityExposure(
            state="contradictory",
            severity="high",
            note=(
                "Both a liability cap and uncapped liability language present. "
                "Attorney must reconcile scope."
            ),
        )
    if cap_present:
        return LiabilityExposure(
            state="capped",
            severity="low",
            note=(
                "Liability cap present; no uncapped language detected. "
                "Standard posture."
            ),
        )
    if uncapped_present:
        return LiabilityExposure(
            state="uncapped",
            severity="high",
            note=(
                "Explicit uncapped liability language present; no cap on "
                "liability."
            ),
        )
    return LiabilityExposure(
        state="silent",
        severity="medium",
        note=(
            "Neither liability cap nor uncapped language present. Default "
            "rules apply; exposure unclear."
        ),
    )


def liability_finding(exposure: LiabilityExposure) -> Finding | None:
    """Turn a LiabilityExposure into a Finding. The capped state is not a finding."""
    if exposure.state == "capped":
        return None
    return Finding(
        category="Liability Exposure",
        severity=exposure.severity,
        rationale=exposure.note,
        evidence="",
        source="cross_category",
    )