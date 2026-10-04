# Parser fixture provenance and formats

Every CSV in this directory is a hand-authored synthetic example. Names,
descriptions, dates, balances, and amounts are invented for parser tests; the
fixtures were not copied from a real person, bank, account, or statement.

- `sbi_metadata_split.csv` models a statement with metadata before its header,
  `Tran Date` / `Details` aliases, split debit and credit columns, Indian rupee
  notation and grouping, plus a bad date and a transaction with no amount.
- `axis_reversed_columns.csv` models the `CR` / `DR` / `BAL` aliases where the
  `CR` column represents incoming funds and the `DR` column represents outgoing
  funds. Balance changes make this reversed convention detectable.
- `debit_credit_aliases.csv` covers `Date` / `PARTICULARS`, day-first dates,
  quoted Indian digit grouping, and accounting-style negative amounts.

The tests assert normalized rows and parser warnings for each fixture. These
examples are intentionally small and contain no account identifiers or actual
customer data.
