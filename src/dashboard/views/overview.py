"""
overview.py — Overview tab: corpus-level analytics.
"""

from __future__ import annotations

import streamlit as st

from src.db import dao
from src.dashboard.components import charts


@st.cache_data(show_spinner=False, ttl=300)
def _load_data() -> dict:
    contracts = dao.list_contracts_dashboard()
    return {
        "contracts": contracts,
        "severity": dao.severity_distribution(),
        "liability": dao.liability_state_distribution(),
        "categories": dao.category_frequency(),
    }


def render() -> None:
    st.header("Overview")

    data = _load_data()
    contracts = data["contracts"]
    n = len(contracts)

    if n == 0:
        st.info("No contracts in the database.")
        return

    total_findings = sum(c["total_findings"] for c in contracts)
    mean_score = sum(c["score"] for c in contracts) / n
    n_high = data["severity"].get("high", 0)
    n_redacted = sum(1 for c in contracts if c["has_redactions"])
    n_multi = sum(1 for c in contracts if c["group_id"])

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Contracts", f"{n}")
    col2.metric("Mean score", f"{mean_score:.1f}")
    col3.metric("Total findings", f"{total_findings:,}")
    col4.metric("High-severity findings", f"{n_high:,}")
    col5.metric("Multi-part contracts", f"{n_multi}")

    st.divider()

    left, right = st.columns(2)
    with left:
        st.subheader("Score distribution")
        st.plotly_chart(
            charts.score_histogram(contracts),
            use_container_width=True,
        )
    with right:
        st.subheader("Liability state")
        st.plotly_chart(
            charts.liability_state_bar(data["liability"]),
            use_container_width=True,
        )

    st.divider()

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.subheader("Top categories by finding count")
        st.plotly_chart(
            charts.category_frequency_bar(data["categories"], limit=15),
            use_container_width=True,
        )
    with col_b:
        st.subheader("Findings by severity")
        st.plotly_chart(
            charts.severity_bar(data["severity"]),
            use_container_width=True,
        )

    st.divider()

    with st.expander("Corpus notes"):
        st.markdown(
            f"""
- **Contracts:** {n}
- **Contracts with redaction markers:** {n_redacted}
- **Multi-part contracts:** {n_multi} (fragments of larger agreements)
- **Multi-part groups:** {len([g for g in set(c.get('group_id') for c in contracts) if g])}
            """
        )