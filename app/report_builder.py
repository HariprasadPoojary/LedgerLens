"""
Report Builder — generates a self-contained HTML report.

Uses Plotly for interactive charts (bundled inline, no CDN needed).
Uses Jinja2 for the HTML template.
Output: single .html file that works offline.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs
from jinja2 import Environment, select_autoescape

from app.analyzer import AnalysisResult

REPORT_VERSION = "5"

# ── Color palette ─────────────────────────────────────────────────────────────

COLORS = [
    "#6366f1",
    "#f59e0b",
    "#10b981",
    "#ef4444",
    "#3b82f6",
    "#8b5cf6",
    "#ec4899",
    "#14b8a6",
    "#f97316",
    "#84cc16",
    "#06b6d4",
    "#a855f7",
    "#e11d48",
    "#0ea5e9",
    "#d97706",
]

INCOME_COLOR = "#10b981"
EXPENSE_COLOR = "#ef4444"
NET_COLOR = "#6366f1"
BACKGROUND = "rgba(0,0,0,0)"


def _chart_config() -> dict:
    return {
        "displayModeBar": False,
        "responsive": True,
    }


def _base_layout(**kwargs) -> dict:
    base = dict(
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(family="Inter, system-ui, sans-serif", size=13, color="#e2e8f0"),
        margin=dict(l=16, r=16, t=40, b=16),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            linecolor="rgba(255,255,255,0.1)",
            tickcolor="rgba(255,255,255,0.1)",
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            linecolor="rgba(255,255,255,0.1)",
            tickcolor="rgba(255,255,255,0.1)",
        ),
    )
    base.update(kwargs)
    return base


def _fig_to_html(fig: go.Figure) -> str:
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,  # injected once in template
        config=_chart_config(),
        div_id=None,
    )


# ── Chart generators ──────────────────────────────────────────────────────────


def _chart_spending_pie(result: AnalysisResult) -> str:
    labels = [c.category for c in result.by_category]
    values = [c.total for c in result.by_category]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=COLORS[: len(labels)], line=dict(color="#1e293b", width=2)),
            textinfo="label+percent",
            textfont=dict(size=12),
            hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(
        **_base_layout(
            title=dict(text="Spending by Category", x=0.5, font=dict(size=15)),
            showlegend=False,
            height=380,
        )
    )
    return _fig_to_html(fig)


def _chart_monthly_bar(result: AnalysisResult) -> str:
    months = [m.month_label for m in result.monthly]
    incomes = [m.income for m in result.monthly]
    expenses = [m.expenses for m in result.monthly]
    nets = [m.net for m in result.monthly]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Income",
            x=months,
            y=incomes,
            marker_color=INCOME_COLOR,
            opacity=0.85,
            hovertemplate="Income: ₹%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Expenses",
            x=months,
            y=expenses,
            marker_color=EXPENSE_COLOR,
            opacity=0.85,
            hovertemplate="Expenses: ₹%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Net",
            x=months,
            y=nets,
            mode="lines+markers",
            line=dict(color=NET_COLOR, width=2.5),
            marker=dict(size=7),
            hovertemplate="Net: ₹%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_base_layout(
            title=dict(text="Monthly Income vs Expenses", x=0.5, font=dict(size=15)),
            barmode="group",
            height=360,
        )
    )
    return _fig_to_html(fig)


def _chart_daily_trend(result: AnalysisResult) -> str:
    dates = list(result.daily_expenses.keys())
    amounts = list(result.daily_expenses.values())

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=amounts,
            mode="lines",
            fill="tozeroy",
            line=dict(color=EXPENSE_COLOR, width=1.5),
            fillcolor="rgba(239,68,68,0.15)",
            hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>",
            name="Daily Spend",
        )
    )
    fig.update_layout(
        **_base_layout(
            title=dict(text="Daily Spending Trend", x=0.5, font=dict(size=15)),
            height=280,
            showlegend=False,
        )
    )
    return _fig_to_html(fig)


def _chart_category_bar(result: AnalysisResult) -> str:
    cats = [c.category for c in reversed(result.by_category)]
    totals = [c.total for c in reversed(result.by_category)]
    colors = [COLORS[i % len(COLORS)] for i in range(len(cats))]

    fig = go.Figure(
        go.Bar(
            x=totals,
            y=cats,
            orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="<b>%{y}</b><br>₹%{x:,.0f}<extra></extra>",
            text=[f"₹{t:,.0f}" for t in totals],
            textposition="outside",
            textfont=dict(size=11),
        )
    )
    fig.update_layout(
        **_base_layout(
            title=dict(text="Expenses by Category", x=0.5, font=dict(size=15)),
            height=max(300, len(cats) * 38),
            showlegend=False,
            xaxis=dict(visible=False),
            margin=dict(l=120, r=80, t=40, b=16),
        )
    )
    return _fig_to_html(fig)


# ── Main entry point ──────────────────────────────────────────────────────────


def generate_report(
    result: AnalysisResult,
    output_path: str,
    session_id: str | None = None,
) -> str:
    """Render the HTML report and write to output_path."""
    review_url = f"/review/{session_id}" if session_id else None
    uncategorized_count = sum(
        1
        for _, row in result.transactions.iterrows()
        if row["category"] in ("Other", "Other Income")
    )
    table_transactions = result.transactions.copy()
    table_transactions["date_iso"] = pd.to_datetime(table_transactions["date"]).dt.strftime(
        "%Y-%m-%d"
    )
    table_categories = sorted(table_transactions["category"].dropna().unique())

    env = Environment(autoescape=select_autoescape(["html"]))
    template = env.from_string(
        (Path(__file__).parent / "templates" / "report.html").read_text(encoding="utf-8")
    )

    html = template.render(
        result=result,
        report_version=REPORT_VERSION,
        plotly_js=get_plotlyjs(),
        table_transactions=table_transactions,
        table_categories=table_categories,
        pie_chart=_chart_spending_pie(result),
        monthly_chart=_chart_monthly_bar(result),
        daily_chart=_chart_daily_trend(result),
        cat_bar_chart=_chart_category_bar(result),
        review_url=review_url if uncategorized_count > 0 else None,
        uncategorized_count=uncategorized_count,
    )

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path
