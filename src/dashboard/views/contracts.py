"""
contracts.py — Contracts tab: filterable table plus detail panel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from src.db import dao
from src.dashboard.components import charts, tables
from src.paths import PDF_DIR


_SEV_COLORS = {
    "high": "#c82828",
    "medium": "#c89600",
    "low": "#3c823c",
}

_SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str, max_len: int = 180) -> str:
    s = _SAFE.sub("_", name).strip()
    return s[:max_len] or "unnamed"


@st.cache_data(show_spinner=False, ttl=300)
def _load_contracts() -> list[dict]:
    return dao.list_contracts_dashboard()


@st.cache_data(show_spinner=False, ttl=300)
def _load_categories() -> list[str]:
    from src.nlp.categories import CANONICAL_CATEGORIES
    return list(CANONICAL_CATEGORIES)


def _apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    out = df.copy()

    out = out[out["Score"].between(filters["score_min"], filters["score_max"])]

    if filters["liability_states"]:
        out = out[out["Liability"].str.lower().isin(
            [s.lower() for s in filters["liability_states"]]
        )]

    if filters["severity_min"] == "High":
        out = out[out["High"] > 0]
    elif filters["severity_min"] == "Medium":
        out = out[out["High"] + out["Medium"] > 0]
    elif filters["severity_min"] == "Low":
        out = out[out["Total"] > 0]

    if filters["id_search"]:
        out = out[out["Contract"].str.contains(
            filters["id_search"], case=False, na=False,
        )]

    if filters["multi_part_only"]:
        out = out[out["Multi-part"]]

    if filters["redacted_only"]:
        out = out[out["Redacted"]]

    if filters["category"]:
        matching_ids = {
            r["contract_id"]
            for r in dao.contracts_with_category(
                filters["category"], present=filters["category_present"]
            )
        }
        out = out[out["Contract"].isin(matching_ids)]

    return out


def _find_pdf(contract_id: str) -> Path | None:
    p = PDF_DIR / f"{_safe_filename(contract_id)}.pdf"
    return p if p.exists() else None


def _render_detail(contract_id: str) -> None:
    card = dao.get_scorecard(contract_id)
    if card is None:
        st.warning("Contract not found in database.")
        return

    contract = card["contract"]
    findings = card["findings"]
    lifecycle = card["lifecycle"]
    inventory = card["inventory"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score", f"{contract['score']} / 100")
    c2.metric("Liability", contract["liability_state"].title())
    c3.metric("Governing law", contract["governing_law"] or "not specified")
    c4.metric("Findings", len(findings))

    if contract.get("group_id"):
        st.info(
            f"Part {contract['part_number']} of a multi-part agreement. "
            f"Absence findings may reflect content in a sibling part."
        )
    if contract.get("has_redactions"):
        st.warning(
            f"This contract contains approximately "
            f"{contract['redaction_count']} redaction markers."
        )

    if lifecycle:
        st.subheader("Lifecycle")
        st.markdown(f"*{lifecycle['narrative']}*")
        lc_cols = st.columns(5)
        lc_cols[0].caption("Agreement")
        lc_cols[0].write(lifecycle["agreement_date"] or "n/a")
        lc_cols[1].caption("Effective")
        lc_cols[1].write(lifecycle["effective_date"] or "n/a")
        lc_cols[2].caption("Expiration")
        lc_cols[2].write(lifecycle["expiration_date"] or "n/a")
        lc_cols[3].caption("Renewal")
        lc_cols[3].write(lifecycle["renewal_term"] or "n/a")
        lc_cols[4].caption("Notice")
        lc_cols[4].write(lifecycle["notice_period"] or "n/a")

    st.subheader("Findings")
    if not findings:
        st.write("No findings for this contract.")
    else:
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
            if f.get("evidence"):
                st.caption(f"Evidence: {f['evidence'][:400]}")
            if f.get("caveat"):
                st.caption(f["caveat"])
            st.caption(f"Source: {f['source']}")
            st.divider()

    st.subheader("Clause inventory")
    inv_left, inv_right = st.columns(2)
    with inv_left:
        st.markdown(f"**Present ({len(inventory['present'])})**")
        for c in inventory["present"]:
            st.markdown(f"- {c}")
    with inv_right:
        st.markdown(f"**Absent ({len(inventory['absent'])})**")
        for c in inventory["absent"]:
            st.markdown(f"- {c}")

    pdf_path = _find_pdf(contract_id)
    st.divider()
    if pdf_path is not None:
        with pdf_path.open("rb") as f:
            st.download_button(
                label="Download PDF report",
                data=f.read(),
                file_name=pdf_path.name,
                mime="application/pdf",
            )
    else:
        st.caption(
            "PDF report not generated for this contract. Run "
            f"`python3 -m src.report.run --contract \"{contract_id}\"` "
            "to build one."
        )


def render() -> None:
    st.header("Contracts")

    contracts = _load_contracts()
    if not contracts:
        st.info("No contracts in the database.")
        return

    df_all = tables.contracts_dataframe(contracts)

    with st.expander("Filters", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)

        with f_col1:
            score_min, score_max = st.slider(
                "Score range", min_value=0, max_value=100, value=(0, 100),
            )

        with f_col2:
            liability_states = st.multiselect(
                "Liability state",
                options=["Capped", "Silent", "Contradictory", "Uncapped"],
                default=[],
            )
            severity_min = st.selectbox(
                "Minimum severity",
                options=["Any", "Low", "Medium", "High"],
                index=0,
            )

        with f_col3:
            category = st.selectbox(
                "Category filter",
                options=["(none)"] + _load_categories(),
                index=0,
            )
            category_present = st.radio(
                "Category present?",
                options=["Present", "Absent"],
                horizontal=True,
                label_visibility="collapsed",
            ) == "Present"

        with f_col4:
            id_search = st.text_input("Contract ID contains", value="")
            multi_part_only = st.checkbox("Multi-part only", value=False)
            redacted_only = st.checkbox("Redacted only", value=False)

    filters = {
        "score_min": score_min,
        "score_max": score_max,
        "liability_states": liability_states,
        "severity_min": severity_min,
        "category": None if category == "(none)" else category,
        "category_present": category_present,
        "id_search": id_search,
        "multi_part_only": multi_part_only,
        "redacted_only": redacted_only,
    }

    df = _apply_filters(df_all, filters)

    st.caption(f"{len(df)} of {len(df_all)} contracts match the current filters.")

    st.dataframe(
        df,
        column_config=tables.contracts_column_config(),
        hide_index=True,
        use_container_width=True,
        height=420,
    )

    if df.empty:
        return

    selected = st.selectbox(
        "Select a contract to view details",
        options=df["Contract"].tolist(),
        index=0,
    )

    if selected:
        st.divider()
        _render_detail(selected)