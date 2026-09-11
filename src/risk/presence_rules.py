"""
presence_rules.py — Presence scoring for restrictive clauses.

For restrictive clauses, presence (not absence) is the diligence finding.
"""

from __future__ import annotations

import re

from src.risk.rubric import Finding


_SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


def non_compete_finding(span_text: str) -> Finding | None:
    """
    Presence of a non-compete. Flag duration over 24 months as high, and
    worldwide or anywhere scope as high. Otherwise medium.
    """
    if not span_text:
        return None

    candidates: list[Finding] = []

    m = re.search(
        r"(\d+)\s*\(?\w*\)?\s*(year|years|month|months)",
        span_text, re.IGNORECASE,
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        months = n * 12 if unit.startswith("year") else n
        severity = "high" if months > 24 else "medium"
        candidates.append(Finding(
            category="Non-Compete",
            severity=severity,
            rationale=f"Non-compete duration of {n} {unit}.",
            evidence=span_text[:200],
            source="presence",
        ))
    else:
        candidates.append(Finding(
            category="Non-Compete",
            severity="medium",
            rationale=(
                "Non-compete present. Duration not extractable from span; "
                "review clause."
            ),
            evidence=span_text[:200],
            source="presence",
        ))

    if re.search(
        r"\b(worldwide|throughout the world|anywhere)\b",
        span_text, re.IGNORECASE,
    ):
        candidates.append(Finding(
            category="Non-Compete",
            severity="high",
            rationale="Non-compete scope includes worldwide or anywhere language.",
            evidence=span_text[:200],
            source="presence",
        ))

    return max(candidates, key=lambda f: _SEVERITY_ORDER[f.severity])


def exclusivity_finding(span_text: str) -> Finding | None:
    if not span_text:
        return None
    return Finding(
        category="Exclusivity",
        severity="medium",
        rationale="Exclusivity clause present. Review scope and parties bound.",
        evidence=span_text[:200],
        source="presence",
    )


def rofr_finding(span_text: str) -> Finding | None:
    if not span_text:
        return None
    return Finding(
        category="Rofr/Rofo/Rofn",
        severity="medium",
        rationale=(
            "Right of first refusal, offer, or negotiation present. Review "
            "trigger and scope."
        ),
        evidence=span_text[:200],
        source="presence",
    )


def non_transferable_license_finding(span_text: str) -> Finding | None:
    if not span_text:
        return None
    return Finding(
        category="Non-Transferable License",
        severity="low",
        rationale="Non-transferable license restriction present.",
        evidence=span_text[:200],
        source="presence",
    )


def uncapped_liability_finding(span_text: str) -> Finding | None:
    if not span_text:
        return None
    return Finding(
        category="Uncapped Liability",
        severity="high",
        rationale="Explicit uncapped liability language present.",
        evidence=span_text[:200],
        source="presence",
    )