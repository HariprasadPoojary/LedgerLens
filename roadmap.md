# Financial Statement Analyzer Roadmap

This roadmap tracks work from fixing the current application through new spending analysis features. Items are ordered by dependency and user value. Work through them one checkbox at a time; check an item only after its completion criteria are met.

## Product direction

- **Audience:** India-first, with bank statement support designed so other regions can be added.
- **Privacy:** Local-first. Bank data stays on the user's machine; no accounts, hosted storage, paid APIs, or AI/LLM processing are planned for the initial product.
- **Input:** CSV is the initial supported format. Other formats are later work.
- **Core promise:** Turn uploaded statements into a clear, trustworthy summary of income, spending, cash flow, and transactions.

## 1. Fix current issues

### 1.1 Repair the transaction review page

- [x] **Serve the review UI from `review.html`.** The current `/review/{session_id}` route reads `settings.html` while inserting review-specific placeholders.
  - **Done when:** the route serves the review page, fills its session, transaction rows, count, and report link placeholders, and the browser can submit edits and return to the regenerated report.

### 1.2 Make upload and date errors reliable

- [x] **Validate uploaded files and date filters.** Check all files before processing, handle `.csv` extensions case-insensitively, validate date values and date order, and clean up temporary uploads on every failed request path.
  - **Done when:** invalid file types, unreadable CSVs, invalid dates, reversed date ranges, and empty filtered results return clear errors; partial uploads are removed after failure; valid multiple-file uploads still work.

### 1.3 Protect transaction data rendered into HTML

- [x] **Escape review-page values and restrict manual category changes.** Encode descriptions, current category names, and generated option values for their HTML context. Accept review overrides only for existing transaction indexes and categories from the active rules.
  - **Done when:** special HTML characters display as text in the review page, crafted values cannot create markup or script, invalid categories/indexes are rejected or ignored consistently, and valid changes still regenerate the report.

### 1.4 Cover the HTTP workflow with tests

- [x] **Add FastAPI route tests.** Use temporary upload, report, session, and rules paths so tests do not touch a user's local data.
  - **Done when:** tests cover upload validation and success, missing reports/sessions, review rendering and submission, and rules read/save/reset behavior, including error responses.

### 1.5 Fix navigation from /report to Home page
- [x] **Add a "Back to Home" link on the report page.** The report page should link back to the home page so users can upload new statements without manually changing the URL.
  - **Done when:** the report page has a working link to `/` that allows users to return to the upload page without losing their session or encountering errors.

### 1.6 List of existing sessions on the home page
- [x] **Display recent sessions on the home page.** Show a list of previously generated reports with links to view them, allowing users to easily access their past analyses without needing to remember session IDs.
  - **Done when:** the home page displays a list of recent sessions with clickable links, and the list updates appropriately as new sessions are created or old ones expire.

## 2. Improve reliability and privacy

### 2.1 Make local-only use the safe default

- [x] **Default documented startup to localhost.** Update setup instructions to bind to `127.0.0.1` by default and explain that binding to a LAN/public interface can expose transaction reports and rule editing to other reachable users.
  - **Done when:** the primary run command is local-only, network exposure is clearly documented, and the app makes no claim that network access is authenticated.

### 2.2 Bound upload resource use

- [x] **Add configurable upload limits.** Limit the number of CSV files, each file's byte size, and total request size; return useful errors before large files exhaust memory or disk.
  - **Done when:** boundary tests cover just-under and over-limit requests, limits can be changed in one documented configuration location, and normal uploads are unaffected.

### 2.3 Clean up expired local artifacts

- [x] **Add configurable retention for sessions and reports.** Remove expired session pickles and matching generated reports; keep cleanup separate from active request data and never delete source files outside the app's own storage directories.
  - **Done when:** cleanup has a documented retention setting, tests prove old artifacts are removed and recent artifacts are preserved, and cleanup handles missing or malformed files safely.

### 2.4 Make rule errors actionable

- [x] **Validate rules before saving and report pattern errors in the UI.** Detect invalid regex syntax and malformed rule structures rather than silently skipping a broken pattern during categorization.
  - **Done when:** invalid rule submissions return a useful validation message naming the affected rule/pattern, valid rules continue to load, and the settings page displays the error without discarding the user's edits.

### 2.5 Build a dependable parser regression set

- [x] **Add anonymized Indian bank CSV fixtures and parser tests.** Include representative header aliases, metadata rows, date and amount formats, debit/credit conventions, balance columns, and malformed rows without real personal or account data.
  - **Done when:** each fixture has expected normalized transactions and warnings, tests cover ambiguous or invalid inputs, and fixture provenance/format notes are documented.

## 3. Polish the existing workflow

### 3.1 Preview parsed statements before analysis

- [ ] **Add a parse-preview step.** Show detected columns, transaction count, date range, parser warnings, and a small sample before the user commits to generating a report.
  - **Done when:** users can confirm a parse or return to choose different files; preview failures show actionable messages; uploaded CSV contents are not persisted beyond the documented local workflow.

### 3.2 Improve transaction exploration

- [ ] **Add report table filters and sorting.** Support filtering by category, date range, amount direction, and text; allow sorting useful columns.
  - **Done when:** filters can be combined, clearing filters restores all rows, empty results are explained, and the table remains usable on narrow screens.

### 3.3 Export analyzed transactions

- [ ] **Add a categorized CSV download.** Export the normalized date, description, amount, type, and category fields for the current report.
  - **Done when:** exported rows match the analyzed report and any selected date/category filters are applied consistently; CSV values are safely encoded for spreadsheet use.

### 3.4 Reuse manual categorization decisions

- [ ] **Offer reusable rules after transaction review.** Let users choose between changing only the current session and saving a reusable description-based rule for future imports.
  - **Done when:** current-session edits remain available, saving a rule requires a clear category and matching pattern, and later imports apply the saved rule according to the documented first-match precedence.

### 3.5 Align project documentation with current behavior

- [ ] **Refresh setup and user documentation.** Document the actual FastAPI command, Python/dependency setup, supported CSV fields, pattern syntax, limitations, privacy behavior, and troubleshooting steps.
  - **Done when:** a new local user can install, start, upload a supported CSV, interpret the report, and find known format limitations without relying on outdated README examples.

## 4. Add spending analysis features

### 4.1 Compare spending over time

- [ ] **Add month-over-month and category trend comparisons.** Show changes in total income, expenses, net savings, and category spending across comparable months or selected periods.
  - **Done when:** incomplete months and missing categories are handled consistently, percentage changes avoid division-by-zero errors, and totals can be traced to included transactions.

### 4.2 Find likely recurring payments

- [ ] **Detect recurring transactions and subscriptions.** Identify likely repeated merchants/amounts and estimate cadence and next expected date, with an explicit indication that matches are estimates.
  - **Done when:** monthly, weekly, and irregular patterns are represented; one-off lookalikes are not presented as certain subscriptions; users can inspect the transactions behind each match.

### 4.3 Track category budgets

- [ ] **Add monthly category budgets.** Let users set local budgets per category and see actual spend, remaining amount, and overspend in the report.
  - **Done when:** budgets persist locally across restarts, are editable/resettable, handle categories with no transactions, and are never included in income or spending totals themselves.

### 4.4 Separate transfers, refunds, and reversals

- [ ] **Improve cash-flow classification for non-spending movements.** Make internal transfers and returned/reversed transactions distinguishable from income and ordinary expenses, while allowing users to review uncertain classifications.
  - **Done when:** transfer/refund treatment is documented, examples have correct net-spend results, uncertain rows remain visible, and totals reconcile with the included transactions.

### 4.5 Group merchant name variations

- [ ] **Add editable merchant normalization.** Allow common description variations to roll up under a user-selected merchant while preserving the original transaction description.
  - **Done when:** reports can show grouped totals and drill into original rows, mappings are stored locally, and removing a mapping restores the original grouping.

## 5. Prepare for broader open-source use

### 5.1 Back up and share rule sets

- [ ] **Add rule import/export.** Let users download and restore their categorization rules in a documented, versioned JSON format.
  - **Done when:** exported rules can be imported on another local installation, invalid files do not replace working rules, and defaults can still be restored.

### 5.2 Document how to add bank formats

- [ ] **Create a bank-format contribution guide.** Explain how to add column aliases and anonymized fixtures, and how to verify parsing without submitting real financial data.
  - **Done when:** a contributor can follow the guide to add a fixture and parser test, and privacy requirements for samples are explicit.

### 5.3 Complete open-source project basics

- [ ] **Add contribution and security reporting guidance.** Document development setup, test commands, pull request expectations, and a private channel or process for reporting vulnerabilities; ensure the declared MIT license has its repository license file.
  - **Done when:** the repository's contribution and security instructions are discoverable and license metadata matches the checked-in license text.

### 5.4 Evaluate additional import formats

- [ ] **Assess XLSX and OFX import support after CSV hardening.** Compare format libraries, local-only behavior, maintenance cost, and realistic bank samples before selecting an implementation.
  - **Done when:** a short decision record documents supported use cases, dependency/security implications, and whether to implement each format; no format is advertised until it has fixtures and regression tests.

## Definition of done for roadmap work

- Each item has focused automated coverage appropriate to its layer; route and browser-facing changes include request or workflow tests.
- Parser changes cover valid, malformed, and ambiguous inputs, warning behavior, and the normalized transaction contract.
- Analysis changes test boundary cases such as refunds, transfers, missing months, and recurring payments with inconsistent dates or amounts.
- Relevant tests pass, user-facing documentation is updated, and transaction data is not sent to external services.
- Check a box only when its item-specific completion criteria are satisfied.
