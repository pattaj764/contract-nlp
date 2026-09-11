"""
groups.py — Groups tab: multi-part contract analysis with provenance.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.db import dao


_SEV_COLORS = {
    "high": "#c82828",
    "medium": "#c89600",
    "low": "#3c823c",
}


@st.cache_data(show_spinner=False, ttl=300)
def _load_groups() -> list[dict]:
    return dao.list_groups()


@st.cache_data(show_spinner=False, ttl=300)
def _load_group_parts(group_id: str) -> list[dict]:
    return dao.get_group(group_id)


@st.cache_data(show_spinner=False, ttl=300)
def _load_group_findings(group_id: str) -> list[dict]:
    return dao.get_group_findings_with_provenance(group_id)


def render() -> None:
    st.header("Groups")
    st.caption(
        "Contracts that were filed across multiple exhibits are grouped here. "
        "Findings are merged across parts, with severity escalated to the "
        "highest observed."
    )

    groups = _load_groups()
    if not groups:
        st.info("No multi-part groups in the database.")
        return

    st.subheader(f"{len(groups)} multi-part groups")

    summary_df = pd.DataFrame(groups)
    summary_df["contract_count"] = summary_df["n_parts"]
    summary_df = summary_df.rename(columns={
        "group_id": "Group",
        "n_parts": "Parts",
        "sum_score": "Sum",
        "max_score": "Max",
        "min_score": "Min",
    })
    summary_df["Spread"] = summary_df["Max"] - summary_df["Min"]
    summary_df = summary_df[["Group", "Parts", "Min", "Max", "Spread"]]

    st.dataframe(
        summary_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Group": st.column_config.TextColumn("Group", width="large"),
            "Parts": st.column_config.NumberColumn("Parts", width="small"),
            "Min": st.column_config.NumberColumn("Min", width="small"),
            "Max": st.column_config.NumberColumn("Max", width="small"),
            "Spread": st.column_config.NumberColumn("Spread", width="small"),
        },
    )

    st.divider()

    selected = st.selectbox(
        "Select a group",
        options=[g["group_id"] for g in groups],
        index=0,
    )

    if not selected:
        return

    parts = _load_group_parts(selected)
    findings = _load_group_findings(selected)

    st.subheader("Parts")
    parts_df = pd.DataFrame(parts)
    parts_df["Liability"] = parts_df["liability_state"].str.title()
    parts_df = parts_df.rename(columns={
        "contract_id": "Contract",
        "part_number": "Part",
        "score": "Score",
        "char_count": "Chars",
        "has_redactions": "Redacted",
    })
    parts_df = parts_df[["Part", "Contract", "Score", "Liability", "Chars", "Redacted"]]

    st.dataframe(
        parts_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d",
            ),
            "Redacted": st.column_config.CheckboxColumn("Redacted"),
            "Chars": st.column_config.NumberColumn("Chars", format="%d"),
            "Contract": st.column_config.TextColumn("Contract", width="large"),
        },
    )

    st.subheader(f"Combined findings ({len(findings)})")
    st.caption(
        "Deduplicated by category. Severity shown is the highest across "
        "parts. The Parts column lists which parts contributed the finding."
    )

    for f in findings:
        color = _SEV_COLORS.get(f["severity"], "#666")
        left, right = st.columns([5, 1])
        with left:
            st.markdown(f"**{f['category']}**")
        with right:
            st.markdown(
                f"<div style='text-align: right; color: {color};'>"
                f"<b>{f['severity'].upper()}</b></div>",
                unsafe_allow_html=True,
            )
        st.write(f["rationale"])
        parts_label = ", ".join(f"Part {p}" for p in f["parts"])
        st.caption(f"Seen in: {parts_label}")
        st.divider()