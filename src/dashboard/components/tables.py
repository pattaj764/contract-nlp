"""
tables.py — DataFrame formatters and column configurations.

Column configs are returned as dicts ready for st.dataframe(column_config=...).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


def contracts_dataframe(contracts: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(contracts)
    if df.empty:
        return df

    df = df[[
        "contract_id", "score", "liability_state",
        "high", "medium", "low", "total_findings",
        "governing_law", "has_redactions", "group_id", "part_number",
    ]].copy()

    df["liability_state"] = df["liability_state"].str.title()
    df["multi_part"] = df["group_id"].notna()
    df = df.drop(columns=["group_id", "part_number"])

    df = df.rename(columns={
        "contract_id": "Contract",
        "score": "Score",
        "liability_state": "Liability",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "total_findings": "Total",
        "governing_law": "Governing law",
        "has_redactions": "Redacted",
        "multi_part": "Multi-part",
    })
    return df


def contracts_column_config() -> dict:
    return {
        "Score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d",
        ),
        "Liability": st.column_config.TextColumn("Liability", width="small"),
        "High": st.column_config.NumberColumn("High", width="small"),
        "Medium": st.column_config.NumberColumn("Med", width="small"),
        "Low": st.column_config.NumberColumn("Low", width="small"),
        "Total": st.column_config.NumberColumn("Total", width="small"),
        "Redacted": st.column_config.CheckboxColumn("Redacted", width="small"),
        "Multi-part": st.column_config.CheckboxColumn("Multi", width="small"),
        "Governing law": st.column_config.TextColumn("Governing law", width="medium"),
        "Contract": st.column_config.TextColumn("Contract", width="large"),
    }


def group_summary_dataframe(groups: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(groups)
    if df.empty:
        return df
    df = df.rename(columns={
        "group_id": "Group",
        "n_parts": "Parts",
        "sum_score": "Sum",
        "max_score": "Max",
        "min_score": "Min",
    })
    df["Spread"] = df["Max"] - df["Min"]
    return df[["Group", "Parts", "Min", "Max", "Spread"]]