"""
Tests for app/report_builder.py

Covers:
  - generate_report produces valid HTML file
  - Required sections present in output
  - Review banner shown only when uncategorized txns exist
  - Charts rendered (not escaped as raw text)
"""

from pathlib import Path

import pandas as pd
import pytest

from app.analyzer import analyze
from app.report_builder import generate_report

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def analysis_result():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-05",
                    "2024-01-10",
                    "2024-01-15",
                    "2024-02-01",
                    "2024-02-10",
                ]
            ),
            "description": [
                "SALARY DEPOSIT",
                "Zomato Food",
                "Netflix",
                "ATM Withdrawal",
                "SALARY DEPOSIT",
                "Other Expense",
            ],
            "amount": [85000.0, -450.0, -199.0, -2000.0, 85000.0, -300.0],
            "type": ["credit", "debit", "debit", "debit", "credit", "debit"],
            "category": [
                "Income",
                "Dining",
                "Subscriptions & Entertainment",
                "Cash & ATM",
                "Income",
                "Other",
            ],
        }
    )
    return analyze(df, warnings=["Test parser warning"])


@pytest.fixture
def report_html(analysis_result, tmp_path):

    out = str(tmp_path / "report.html")
    generate_report(analysis_result, out, session_id="testsession")
    return Path(out).read_text(encoding="utf-8")


# ── Output file ───────────────────────────────────────────────────────────────


class TestReportFile:

    def test_file_created(self, analysis_result, tmp_path):

        out = str(tmp_path / "r.html")
        generate_report(analysis_result, out)
        assert Path(out).exists()

    def test_file_is_not_empty(self, report_html):
        assert len(report_html) > 1000

    def test_returns_output_path(self, analysis_result, tmp_path):

        out = str(tmp_path / "r.html")
        returned = generate_report(analysis_result, out)
        assert returned == out


# ── HTML structure ────────────────────────────────────────────────────────────


class TestReportContent:

    def test_is_valid_html(self, report_html):
        assert report_html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in report_html

    def test_contains_kpi_values(self, report_html):
        # KPI section should show income/expense numbers
        assert "₹" in report_html
        assert "Total Income" in report_html.upper() or "TOTAL INCOME" in report_html

    def test_contains_chart_divs(self, report_html):
        # Plotly renders into div elements — not raw JSON text
        assert "plotly-graph-div" in report_html

    def test_charts_not_escaped(self, report_html):
        # Raw HTML should NOT appear as escaped entities
        assert "&lt;div" not in report_html
        assert "&lt;script" not in report_html

    def test_plotly_is_bundled_for_offline_reports(self, report_html):
        assert 'src="https://cdn.plot.ly/' not in report_html
        assert "Plotly.newPlot" in report_html

    def test_parser_warning_shown(self, report_html):
        assert "Test parser warning" in report_html

    def test_transaction_table_present(self, report_html):
        assert "txn-table" in report_html or "All Transactions" in report_html

    def test_transaction_exploration_controls_present(self, report_html):
        assert 'id="txn-date-from"' in report_html
        assert 'id="txn-date-to"' in report_html
        assert 'id="txn-direction"' in report_html
        assert 'data-sort="amount"' in report_html
        assert "clearTableFilters" in report_html
        assert "No transactions match these filters" in report_html

    def test_filter_data_uses_iso_dates_and_every_transaction_category(
        self, analysis_result, tmp_path
    ):
        analysis_result.transactions.loc[len(analysis_result.transactions)] = [
            "11 Feb 2024",
            "REFUND",
            50.0,
            "credit",
            "Other Income",
        ]
        out = str(tmp_path / "r.html")
        generate_report(analysis_result, out)
        html = Path(out).read_text(encoding="utf-8")

        assert 'data-date="2024-02-11"' in html
        assert '<option value="Other Income">Other Income</option>' in html

    def test_category_summary_present(self, report_html):
        assert "Category Summary" in report_html or "CATEGORY SUMMARY" in report_html


# ── Review banner ─────────────────────────────────────────────────────────────


class TestReviewBanner:

    def test_review_banner_shown_when_uncategorized(self, analysis_result, tmp_path):
        # analysis_result has "Other" category transactions
        out = str(tmp_path / "r.html")
        generate_report(analysis_result, out, session_id="abc123")
        html = Path(out).read_text(encoding="utf-8")
        assert "/review/abc123" in html

    def test_review_banner_hidden_when_all_categorized(self, tmp_path):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-05"]),
                "description": ["SALARY", "RENT"],
                "amount": [50000.0, -15000.0],
                "type": ["credit", "debit"],
                "category": ["Income", "Housing"],
            }
        )
        result = analyze(df)
        out = str(tmp_path / "r.html")
        generate_report(result, out, session_id="xyz")
        html = Path(out).read_text(encoding="utf-8")
        assert "/review/xyz" not in html

    def test_no_review_banner_without_session_id(self, analysis_result, tmp_path):
        out = str(tmp_path / "r.html")
        generate_report(analysis_result, out, session_id=None)
        html = Path(out).read_text(encoding="utf-8")
        assert "/review/" not in html
