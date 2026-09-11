"""
app.py — Streamlit entry point for the Contract Risk Analyzer dashboard.

Usage:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from src.db import dao
from src.dashboard.views import contracts, groups, methodology, overview


st.set_page_config(
    page_title="Contract Risk Analyzer",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _database_ready() -> bool:
    try:
        _ = dao.severity_distribution()
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return False


def main() -> None:
    st.title("Contract Risk Analyzer")
    st.caption(
        "Diligence-oriented review of commercial contracts. "
        "Findings flag items for attorney review. Not legal advice."
    )

    if not _database_ready():
        st.error(
            "Database not found. Run "
            "`python -m src.db.run build` to build it, then refresh."
        )
        st.stop()

    tab_overview, tab_contracts, tab_groups, tab_methodology = st.tabs(
        ["Overview", "Contracts", "Groups", "Methodology"]
    )

    with tab_overview:
        overview.render()
    with tab_contracts:
        contracts.render()
    with tab_groups:
        groups.render()
    with tab_methodology:
        methodology.render()


if __name__ == "__main__":
    main()