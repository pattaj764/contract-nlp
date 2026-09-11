"""
value_rules.py — Content rules for value-typed categories.

These categories always carry a value when present. Findings come from the
value, not from presence or absence.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from src.risk.rubric import Finding


# Non-US governing-law indicators. Presence of any of these strings in the
# Governing Law answer triggers a medium-severity finding.
NON_US_INDICATORS: tuple[str, ...] = (
    "england", "wales", "uk", "united kingdom",
    "canada", "ontario", "quebec", "british columbia",
    "cayman", "bvi", "british virgin islands", "bermuda",
    "ireland", "france", "germany", "netherlands",
    "switzerland", "singapore", "hong kong", "japan",
    "australia", "israel", "china", "india",
    "province of", "country of",
)


# Removed: the prior draft flagged US jurisdictions outside NY / DE / CA as
# low-severity findings. In practice most US commercial contracts are
# governed by other states (IL, TX, MA, WA), and flagging them produces
# noise. Only non-US jurisdictions are scored. The jurisdiction is still
# surfaced verbatim via Scorecard.governing_law.


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def parse_date(raw: str) -> date | None:
    """
    Parse CUAD's normalized date formats. Returns None if unparseable.
    Handles: M/D/YYYY, M/D/YY, YYYY-MM-DD, M-D-YYYY, M-D-YY.
    """
    if not raw:
        return None
    s = raw.strip()
    if s.lower() in {"perpetual", "n/a", "none", ""}:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_duration_days(raw: str) -> int | None:
    """Parse '30 days', '2 months', '1 year' into a number of days."""
    if not raw:
        return None
    s = raw.strip().lower()
    m = re.search(r"(\d+)\s*(day|days|month|months|year|years)", s)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit.startswith("day"):
        return n
    if unit.startswith("month"):
        return n * 30
    if unit.startswith("year"):
        return n * 365
    return None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def governing_law_finding(answer: str) -> Finding | None:
    """
    Report the jurisdiction as a note; flag only non-US as a finding.

    US states outside NY / DE / CA are common commercial venues and are
    not scored. The jurisdiction is still surfaced verbatim in the
    scorecard via Scorecard.governing_law.
    """
    if not answer:
        return None
    value = answer.strip()
    lower = value.lower()

    for prefix in ("the laws of the state of ", "the state of ", "laws of "):
        if lower.startswith(prefix):
            lower = lower[len(prefix):]
            value = value[len(prefix):]
            break

    if any(k in lower for k in NON_US_INDICATORS):
        return Finding(
            category="Governing Law",
            severity="medium",
            rationale=(
                f"Non-US governing law: {value}. Verify forum selection and "
                f"enforcement implications."
            ),
            evidence=answer,
            source="value",
        )
    return None


def agreement_effective_gap_finding(
    agreement: str, effective: str
) -> Finding | None:
    """Flag if the gap between Agreement Date and Effective Date exceeds 30 days."""
    a = parse_date(agreement)
    e = parse_date(effective)
    if a is None or e is None:
        return None
    gap = abs((e - a).days)
    if gap > 30:
        return Finding(
            category="Effective Date",
            severity="low",
            rationale=(
                f"Agreement Date and Effective Date differ by {gap} days. "
                f"Confirm a commercial reason exists."
            ),
            evidence=f"Agreement Date: {agreement}; Effective Date: {effective}",
            source="value",
        )
    return None


def expiration_finding(
    expiration: str,
    effective: str,
    renewal_term: str,
    notice_period: str,
    as_of: date | None,
) -> Finding | None:
    """Flag perpetual terms or an expiration date preceding the reference date."""
    if not expiration:
        return None
    if expiration.strip().lower() == "perpetual":
        return Finding(
            category="Expiration Date",
            severity="medium",
            rationale=(
                "Expiration date is 'Perpetual'. Confirm this is intended for "
                "a commercial agreement."
            ),
            evidence=expiration,
            source="value",
        )

    exp_date = parse_date(expiration)
    if exp_date is None or as_of is None:
        return None

    if exp_date < as_of:
        return Finding(
            category="Expiration Date",
            severity="low",
            rationale=(
                f"Stated expiration date ({expiration}) precedes the "
                f"reference date ({as_of.isoformat()})."
            ),
            evidence=expiration,
            source="value",
        )
    return None


def renewal_notice_finding(
    renewal_term: str, notice_period: str
) -> Finding | None:
    """Flag auto-renewal with a notice window shorter than 30 days."""
    if not renewal_term or not notice_period:
        return None
    if renewal_term.strip().lower() in {"", "none", "n/a"}:
        return None

    days = _parse_duration_days(notice_period)
    if days is None:
        return Finding(
            category="Renewal Term",
            severity="low",
            rationale=(
                f"Auto-renewal present with notice period '{notice_period}' "
                f"that could not be parsed as a duration."
            ),
            evidence=f"Renewal Term: {renewal_term}; Notice Period: {notice_period}",
            source="value",
        )

    if days < 30:
        return Finding(
            category="Renewal Term",
            severity="medium",
            rationale=(
                f"Auto-renewal with a {days}-day notice window. Short window; "
                f"calendar reminder advisable."
            ),
            evidence=f"Renewal Term: {renewal_term}; Notice Period: {notice_period}",
            source="value",
        )
    return None