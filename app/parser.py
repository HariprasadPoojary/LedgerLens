"""
CSV Parser — normalizes bank statement CSVs from different banks
into a single clean schema:

    date | description | amount | type (debit/credit)

Supported formats auto-detected:
    - Standard: Date, Description, Amount (negative = debit)
    - Split columns: Date, Description, Debit, Credit
    - OFX-style: Date, Name, Amount, Transaction Type
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.const import (
    BALANCE_ALIASES,
    CREDIT_ALIASES,
    DATE_ALIASES,
    DEBIT_ALIASES,
    DESCRIPTION_ALIASES,
)


@dataclass
class ParseResult:
    df: pd.DataFrame  # normalized dataframe
    source_file: str  # original filename
    row_count: int
    date_range: tuple  # (min_date, max_date)
    warnings: list[str]  # non-fatal issues found during parsing


def _normalize_col_name(name: str) -> str:
    return name.strip()


def _find_column(df_cols: list[str], aliases: list[str]) -> str | None:
    """Return the first df column that matches any alias."""
    normalized = {_normalize_col_name(c): c for c in df_cols}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def _detect_header_row(raw: pd.DataFrame) -> int:
    """
    Some bank CSVs have metadata rows before the actual header.
    Scan the first 10 rows to find the row that contains the most
    recognizable column names.
    """
    all_aliases = (
        DATE_ALIASES + DESCRIPTION_ALIASES + DEBIT_ALIASES + CREDIT_ALIASES + BALANCE_ALIASES
    )
    normalized_aliases = {alias.lower() for alias in all_aliases}

    best_row, best_score = 0, 0
    for i in range(min(10, len(raw))):
        row_values = [str(v).strip().lower() for v in raw.iloc[i].values]
        score = sum(1 for v in row_values if v in normalized_aliases)
        if score > best_score:
            best_score, best_row = score, i

    return best_row if best_score >= 2 else 0


def _parse_amount(value) -> float | None:
    """Clean and convert amount strings like '$1,234.56' or '(500.00)'."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s in ("-", ""):
        return None
    # Handle accounting negatives: (500.00) → -500.00
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[()$₹,\s]", "", s)
    try:
        val = float(s)
        return -abs(val) if negative else val
    except ValueError:
        return None


def _parse_date(series: pd.Series) -> pd.Series:
    """Try multiple date formats, return normalized datetime series."""
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y%m%d",
    ]
    for fmt in formats:
        try:
            parsed = pd.to_datetime(series, format=fmt, dayfirst=False)
            if parsed.notna().sum() > len(series) * 0.8:
                return parsed
        except Exception:
            continue
    # Last resort: let pandas infer
    return pd.to_datetime(series, format="mixed", dayfirst=True, errors="coerce")


# ── Core parsing logic ─────────────────────────────────────────────────────────


def _load_raw_csv(filepath: str) -> pd.DataFrame:
    """Load CSV with encoding detection, comma-delimited."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, encoding=encoding, newline="") as source:
                rows = list(csv.reader(source))
            width = max((len(row) for row in rows), default=0)
            df = pd.DataFrame([row + [None] * (width - len(row)) for row in rows])
            if len(df.columns) > 2:
                df.columns = [str(c).strip() for c in df.columns]
                return df
        except Exception:
            pass

    raise ValueError(f"Cannot decode file: {filepath}")


def _build_normalized_df(
    df: pd.DataFrame,
    date_col: str,
    desc_col: str,
    debit_col: str | None,
    credit_col: str | None,
    balance_col: str | None,
    warnings: list[str],
) -> pd.DataFrame:
    """Build the normalized dataframe from detected columns."""

    result = pd.DataFrame()

    # Date
    result["date"] = _parse_date(df[date_col])
    bad_dates = result["date"].isna().sum()
    if bad_dates:
        warnings.append(f"{bad_dates} rows had unparseable dates and were dropped.")

    # Description — normalize and remove embedded newlines/extra whitespace
    result["description"] = (
        df[desc_col]
        .fillna("")
        .astype(str)
        .str.replace(r"[\r\n]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    # Amount — determine which column(s) contain transaction amounts
    try:
        if balance_col:
            result["balance"] = df[balance_col].apply(_parse_amount)

        if debit_col and credit_col:
            # Both columns present. Different banks use different semantics:
            # - "standard": Credit column contains incoming funds, Debit contains outgoing.
            # - "reversed": Debit column contains incoming funds (Axis style DR=credit).
            debits = df[debit_col].apply(_parse_amount).map(
                lambda value: abs(value) if pd.notna(value) else 0
            )
            credits = df[credit_col].apply(_parse_amount).map(
                lambda value: abs(value) if pd.notna(value) else 0
            )
            has_amount = (
                df[debit_col].apply(_parse_amount).notna()
                | df[credit_col].apply(_parse_amount).notna()
            )

            # Default to standard orientation (credits positive). If a balance
            # column exists, use balance deltas to detect orientation automatically.
            orientation_standard = True
            if balance_col:
                try:
                    balance = df[balance_col].apply(_parse_amount)
                    # Compute per-row balance change: current - previous
                    bal_diff = balance.diff()
                    # Consider rows where exactly one of debit/credit is non-zero
                    mask = ((debits > 0) ^ (credits > 0)) & bal_diff.notna()
                    # If no informative rows, keep default
                    if mask.sum() >= 3:
                        # Count how many rows match standard (bal_diff ≈ credits - debits)
                        std_matches = (
                            (bal_diff[mask] - (credits[mask] - debits[mask])).abs() < 0.01
                        ).sum()
                        rev_matches = (
                            (bal_diff[mask] - (debits[mask] - credits[mask])).abs() < 0.01
                        ).sum()
                        orientation_standard = std_matches >= rev_matches
                except Exception:
                    # If detection fails, fall back to default
                    orientation_standard = True

            if orientation_standard:
                # Standard: amount = credits - debits (incoming positive)
                result["amount"] = credits - debits
            else:
                # Reversed (Axis-like): amount = debits - credits
                result["amount"] = debits - credits
            result.loc[~has_amount, "amount"] = None

            # Determine type purely from computed amount
            def sign_type(x):
                if x > 0:
                    return "credit"
                if x < 0:
                    return "debit"
                return "neutral"

            result["type"] = [sign_type(x) for x in result["amount"]]
        elif debit_col:
            result["amount"] = (
                df[debit_col]
                .apply(_parse_amount)
                .apply(lambda x: -abs(x) if x is not None else None)
            )
            result["type"] = "debit"
        elif credit_col:
            result["amount"] = df[credit_col].apply(_parse_amount)
            result["type"] = "credit"
    except Exception as e:
        raise ValueError(f"Error processing amount columns: {e}")

    # Drop rows with null dates or null amounts
    before = len(result)
    result = result.dropna(subset=["date", "amount"])
    dropped = before - len(result)
    if dropped:
        warnings.append(f"{dropped} rows dropped due to missing date or amount.")

    result["amount"] = result["amount"].astype(float)
    result["date"] = pd.to_datetime(result["date"])
    result = result.sort_values("date").reset_index(drop=True)

    return result


def parse_csv(filepath: str) -> ParseResult:
    """
    Main entry point. Parse a bank statement CSV and return a ParseResult
    with a normalized dataframe.
    """
    warnings = []
    source_file = Path(filepath).name

    # Load raw CSV
    raw = _load_raw_csv(filepath)

    if raw.empty:
        raise ValueError(f"File is empty: {filepath}")

    # Find the actual header row (in case there are metadata rows)
    header_row = _detect_header_row(raw)
    if header_row > 0:
        warnings.append(f"Skipped {header_row} metadata row(s) before header.")

    # Re-read with correct header
    df = pd.read_csv(
        filepath,
        skiprows=header_row,
        dtype=str,
        encoding="utf-8",
        delimiter=",",
        on_bad_lines="skip",
    )
    df.columns = [str(c).strip() for c in df.columns]

    # Detect columns
    date_col = _find_column(list(df.columns), DATE_ALIASES)
    desc_col = _find_column(list(df.columns), DESCRIPTION_ALIASES)
    debit_col = _find_column(list(df.columns), DEBIT_ALIASES)
    credit_col = _find_column(list(df.columns), CREDIT_ALIASES)
    balance_col = _find_column(list(df.columns), BALANCE_ALIASES)

    if not date_col:
        raise ValueError(f"Could not find a date column. Found columns: {list(df.columns)}")
    if not desc_col:
        raise ValueError(f"Could not find a description column. Found columns: {list(df.columns)}")
    if not (balance_col or debit_col or credit_col):
        raise ValueError(f"Could not find any amount column. Found columns: {list(df.columns)}")

    normalized = _build_normalized_df(
        df, date_col, desc_col, debit_col, credit_col, balance_col, warnings
    )

    date_range = (
        normalized["date"].min().date(),
        normalized["date"].max().date(),
    )

    return ParseResult(
        df=normalized,
        source_file=source_file,
        row_count=len(normalized),
        date_range=date_range,
        warnings=warnings,
    )


def merge_statements(results: list[ParseResult]) -> pd.DataFrame:
    """Merge multiple parsed statements, deduplicate by (date, description, amount)."""
    if not results:
        raise ValueError("No parse results to merge.")
    combined = pd.concat([r.df for r in results], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["date", "description", "amount"])
    after = len(combined)
    if before != after:
        print(f"[parser] Removed {before - after} duplicate transactions.")
    return combined.sort_values("date").reset_index(drop=True)
