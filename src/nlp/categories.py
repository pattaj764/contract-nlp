"""
categories.py — Canonical vocabulary for the 41 CUAD clause categories.

Sources of truth:
    - CUAD_v1.json QA IDs use the "canonical" spelling (verified by inspect.py).
    - master_clauses.csv column names are near-canonical but have whitespace
      and dash-spacing inconsistencies (e.g. "Notice Period To Terminate
      Renewal- Answer").

Everything downstream (loader, validator, risk engine, dashboard) imports
its vocabulary from here.
"""

from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# Canonical 41 categories — exactly as they appear in CUAD_v1.json QA IDs
# ---------------------------------------------------------------------------

CANONICAL_CATEGORIES: tuple[str, ...] = (
    "Document Name",
    "Parties",
    "Agreement Date",
    "Effective Date",
    "Expiration Date",
    "Renewal Term",
    "Notice Period To Terminate Renewal",
    "Governing Law",
    "Most Favored Nation",
    "Non-Compete",
    "Exclusivity",
    "No-Solicit Of Customers",
    "Competitive Restriction Exception",
    "No-Solicit Of Employees",
    "Non-Disparagement",
    "Termination For Convenience",
    "Rofr/Rofo/Rofn",
    "Change Of Control",
    "Anti-Assignment",
    "Revenue/Profit Sharing",
    "Price Restrictions",
    "Minimum Commitment",
    "Volume Restriction",
    "Ip Ownership Assignment",
    "Joint Ip Ownership",
    "License Grant",
    "Non-Transferable License",
    "Affiliate License-Licensor",
    "Affiliate License-Licensee",
    "Unlimited/All-You-Can-Eat-License",
    "Irrevocable Or Perpetual License",
    "Source Code Escrow",
    "Post-Termination Services",
    "Audit Rights",
    "Uncapped Liability",
    "Cap On Liability",
    "Liquidated Damages",
    "Warranty Duration",
    "Insurance",
    "Covenant Not To Sue",
    "Third Party Beneficiary",
)

assert len(CANONICAL_CATEGORIES) == 41, "Expected exactly 41 categories"


# ---------------------------------------------------------------------------
# Groups — from CUAD README "Category List"
# Clauses in the same group may overlap or share text context.
# ---------------------------------------------------------------------------

CATEGORY_GROUPS: dict[str, int | None] = {
    "Agreement Date": 1,
    "Effective Date": 1,
    "Expiration Date": 1,
    "Renewal Term": 1,
    "Notice Period To Terminate Renewal": 1,
    "Non-Compete": 2,
    "Exclusivity": 2,
    "No-Solicit Of Customers": 2,
    "Competitive Restriction Exception": 2,
    "Change Of Control": 3,
    "Anti-Assignment": 3,
    "License Grant": 4,
    "Non-Transferable License": 4,
    "Affiliate License-Licensor": 4,
    "Affiliate License-Licensee": 4,
    "Irrevocable Or Perpetual License": 4,
    "Uncapped Liability": 5,
    "Cap On Liability": 5,
    # All others are ungrouped
}
for cat in CANONICAL_CATEGORIES:
    CATEGORY_GROUPS.setdefault(cat, None)


# ---------------------------------------------------------------------------
# Answer type — per CUAD README:
#   33 categories have derived answer Yes/No (the "answer" is whether the
#   clause exists; the span text carries the substance).
#   8 (here 9, including Document Name) have a normalized value answer.
# ---------------------------------------------------------------------------

VALUE_CATEGORIES: frozenset[str] = frozenset({
    "Document Name",
    "Parties",
    "Agreement Date",
    "Effective Date",
    "Expiration Date",
    "Renewal Term",
    "Notice Period To Terminate Renewal",
    "Governing Law",
    "Warranty Duration",
})

ANSWER_TYPE: dict[str, str] = {
    cat: ("value" if cat in VALUE_CATEGORIES else "yes_no")
    for cat in CANONICAL_CATEGORIES
}


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------

# Recognized "-Answer" suffixes in the CSV column names
_ANSWER_SUFFIX_PATTERNS = (
    re.compile(r"-\s*[Aa]nswer\s*$"),
)

_CANONICAL_LOOKUP = {c.lower(): c for c in CANONICAL_CATEGORIES}


def canonicalize_column_name(col: str) -> str:
    """
    Normalize a CSV column name to a canonical category name, or return
    the cleaned string if no match. Examples:

        "Notice Period To Terminate Renewal- Answer" -> "Notice Period To Terminate Renewal"
        "Rofr/Rofo/Rofn-Answer"                      -> "Rofr/Rofo/Rofn"
        "Ip Ownership Assignment"                    -> "Ip Ownership Assignment"
    """
    s = col.strip()
    for pat in _ANSWER_SUFFIX_PATTERNS:
        s = pat.sub("", s).rstrip()
    s = " ".join(s.split())
    return _CANONICAL_LOOKUP.get(s.lower(), s)


def extract_category_from_qa_id(qa_id: str) -> str:
    """QA IDs follow '{contract_title}__{Category}'."""
    if "__" not in qa_id:
        raise ValueError(f"Malformed QA id (no '__' separator): {qa_id!r}")
    return qa_id.split("__", 1)[1]


def category_group(category: str) -> int | None:
    return CATEGORY_GROUPS.get(category)


def answer_type(category: str) -> str:
    return ANSWER_TYPE.get(category, "yes_no")