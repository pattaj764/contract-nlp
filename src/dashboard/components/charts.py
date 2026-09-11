"""
charts.py — Plotly chart builders for the dashboard.

Colors match the LaTeX report template so a reviewer moving between the
two outputs sees a consistent visual language.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


SEVERITY_COLORS = {
    "high": "#c82828",
    "medium": "#c89600",
    "low": "#3c823c",
}

LIABILITY_COLORS = {
    "capped": "#3c823c",
    "uncapped": "#c82828",
    "contradictory": "#c82828",
    "silent": "#c89600",
}


def _layout(**overrides) -> dict:
    """
    Build a layout dict. Base keys are applied first; overrides win.
    Returned as a plain dict for passing to fig.update_layout(layout).
    """
    base = {
        "plot_bgcolor": "white",
        "paper_bgcolor": "white",
        "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
        "font": {"family": "sans-serif", "size": 12, "color": "#333"},
        "showlegend": False,
    }
    base.update(overrides)
    return base


def score_histogram(contracts: list[dict]) -> go.Figure:
    scores = [c["score"] for c in contracts]
    df = pd.DataFrame({"score": scores})
    fig = px.histogram(df, x="score", nbins=20)
    fig.update_traces(marker_color="#4a6fa5", marker_line_width=0)
    fig.update_layout(_layout(
        xaxis_title="Risk score",
        yaxis_title="Contracts",
        bargap=0.05,
    ))
    fig.update_xaxes(range=[0, 100], showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#eeeeee", zeroline=False)
    return fig


def liability_state_bar(distribution: dict[str, int]) -> go.Figure:
    order = ["capped", "silent", "contradictory", "uncapped"]
    labels = [k for k in order if k in distribution]
    values = [distribution[k] for k in labels]
    colors = [LIABILITY_COLORS[k] for k in labels]

    fig = go.Figure(go.Bar(
        x=[k.title() for k in labels],
        y=values,
        marker_color=colors,
        text=values,
        textposition="outside",
    ))
    fig.update_layout(_layout(
        xaxis_title="Liability state",
        yaxis_title="Contracts",
    ))
    fig.update_yaxes(showgrid=True, gridcolor="#eeeeee", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


def category_frequency_bar(rows: list[dict], limit: int = 15) -> go.Figure:
    """
    rows is the output of dao.category_frequency:
    [{"category": ..., "severity": ..., "n": ...}, ...]
    Aggregate by category across severities, take top N.
    """
    agg: dict[str, int] = {}
    for r in rows:
        agg[r["category"]] = agg.get(r["category"], 0) + r["n"]

    top = sorted(agg.items(), key=lambda x: -x[1])[:limit]
    top.reverse()
    cats = [k for k, _ in top]
    counts = [v for _, v in top]

    fig = go.Figure(go.Bar(
        x=counts,
        y=cats,
        orientation="h",
        marker_color="#4a6fa5",
        text=counts,
        textposition="outside",
    ))
    fig.update_layout(_layout(
        xaxis_title="Findings",
        yaxis_title="",
        height=max(320, 22 * len(cats) + 80),
    ))
    fig.update_xaxes(showgrid=True, gridcolor="#eeeeee", zeroline=False)
    fig.update_yaxes(showgrid=False)
    return fig


def severity_bar(distribution: dict[str, int]) -> go.Figure:
    order = ["high", "medium", "low"]
    labels = [k for k in order if k in distribution]
    values = [distribution[k] for k in labels]
    colors = [SEVERITY_COLORS[k] for k in labels]

    fig = go.Figure(go.Bar(
        x=[k.title() for k in labels],
        y=values,
        marker_color=colors,
        text=values,
        textposition="outside",
    ))
    fig.update_layout(_layout(
        xaxis_title="",
        yaxis_title="Findings",
        height=280,
    ))
    fig.update_yaxes(showgrid=True, gridcolor="#eeeeee", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig