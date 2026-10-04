# AI Financial Report

An intelligent financial statement analyzer that automatically categorizes bank transactions and generates comprehensive HTML reports. Built with FastAPI, this tool helps you understand your spending patterns by categorizing transactions using customizable rule-based patterns.

![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

- **CSV Parsing**: Parse bank statements from multiple CSV formats with support for various column name aliases
- **Smart Categorization**: Automatically categorize transactions using regex-based patterns and rules
- **Interactive Web Interface**: Upload statements and view categorized reports through a clean web UI
- **Transaction Review**: Review and reclassify uncategorized transactions in real-time
- **Customizable Rules**: Edit and manage transaction categorization rules through the settings interface
- **HTML Reports**: Generate beautiful, interactive HTML reports with transaction summaries and visualizations
- **Multi-Statement Support**: Process multiple bank statements in a single analysis
- **Date Filtering**: Filter transactions by date range during analysis
- **Session Management**: Persistent session storage for multi-step workflows

## 📋 Requirements

- **Python**: 3.14 or higher
- **Package Manager**: [uv](https://docs.astral.sh/uv/)

## 🚀 Installation

### Using `uv` (Recommended)

#### 1. Install `uv` (if not already installed)

**On Windows** (using PowerShell):

```powershell
powershell -ExecutionPolicy BypassPolicy -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**On macOS/Linux**:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or visit the [uv Installation Guide](https://docs.astral.sh/uv/getting-started/installation/) for more options.

#### 2. Clone or Navigate to the Project

```bash
git clone <repository-url>
cd AI-Financial-Report
```

#### 3. Create and Activate Virtual Environment

```bash
# Create a virtual environment
uv venv

# Activate it
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

#### 4. Install Dependencies

```bash
# Install all dependencies with uv
uv sync
```

## 📖 Usage

### Web Interface (Recommended)

1. **Start the FastAPI server**:

    ```bash
    uvicorn app.fast_api:app --reload --host 127.0.0.1 --port 8000
    ```

   This binds the app to this computer only. Binding to `0.0.0.0` or another LAN/public interface can let other reachable users view generated transaction reports and change categorization rules. The app does not authenticate network users, so do not expose it to a network.

2. **Open in browser**:
   Navigate to `http://localhost:8000`

3. **Upload statements**:
    - Upload one or more CSV files containing bank statements
    - Optionally filter by date range
    - Click "Analyze" to process

4. **Review results**:
    - View the generated HTML report with categorized transactions
    - Click "Review" to edit categorizations for problematic transactions
    - Access the "Settings" page to manage categorization rules

Upload limits are configured together in `app/const.py`: up to 10 CSV files per request, 10 MiB per file, and 50 MiB for the complete request including multipart form data. Change those values in that file to adjust the limits. The upload page displays the current limits. Requests above the total limit and files above the per-file limit are rejected with an error before they are saved for analysis.

### Command Line Interface

Run the provided test pipeline:

```bash
python test_pipeline.py
```

Or use `main.py` to parse and analyze statements:

```python
from app.parser import parse_csv
from app.categorizer import categorize_dataframe
from app.analyzer import analyze

# Parse a CSV statement
result = parse_csv("path/to/statement.csv")

# Categorize transactions
df = categorize_dataframe(result.dataframe)

# Generate analysis
analysis = analyze(df)
```

## 📁 Project Structure

```
AI-Financial-Report/
├── app/                              # Main application package
│   ├── analyzer.py                   # Transaction analysis logic
│   ├── categorizer.py                # Transaction categorization
│   ├── const.py                      # Category rules and configuration
│   ├── fast_api.py                   # FastAPI web server
│   ├── parser.py                     # CSV parsing utilities
│   ├── report_builder.py             # HTML report generation
│   ├── rules_store.py                # Rules management
│   └── templates/                    # HTML templates
│       ├── index.html                # Upload form
│       ├── report.html               # Report display
│       ├── review.html               # Transaction review UI
│       └── settings.html             # Rules editor
├── data/                             # Data files
│   └── rules.json                    # Stored categorization rules
├── reports/                          # Generated HTML reports
├── sessions/                         # Session state files
├── uploads/                          # Uploaded CSV files
├── main.py                           # CLI entry point
├── test_pipeline.py                  # Test/example script
├── pyproject.toml                    # Project configuration
└── README.md                         # This file
```

## 🔧 Configuration

### Categorization Rules

Transaction categorization rules are defined in [app/const.py](app/const.py) as a list of tuples:

```python
CATEGORY_RULES: list[tuple[str, list[str], str]] = [
    ("Category Name", [r"pattern1", r"pattern2"], "credit|debit|both"),
    ...
]
```

- **Category Name**: The transaction category (e.g., "Income", "Groceries")
- **Patterns**: List of patterns matched against transaction descriptions. Plain text is a case-insensitive literal; use `case:` for a case-sensitive literal, `re:` for a case-insensitive regular expression, or `re:case:` for a case-sensitive regular expression.
- **Type**: "credit", "debit", or "both"

Rules are validated before saving. Invalid regular expressions and malformed rule entries are rejected with an error that identifies the rule and pattern; the settings editor keeps the current edits visible so they can be corrected.

### Temporary Artifact Retention

Generated session pickles and HTML reports are cleaned up when the app starts. Configure `ARTIFACT_RETENTION_DAYS` in [app/const.py](app/const.py) to change the retention period (180 days by default). Cleanup only considers session and report filenames generated by this app inside the `sessions/` and `reports/` directories.

### Adding Custom CSV Formats

Column name aliases are configurable in [app/const.py](app/const.py). Add your column names to the appropriate alias list:

```python
DATE_ALIASES = ["Date", "Tran Date", "Your Bank Date Column"]
DESCRIPTION_ALIASES = ["PARTICULARS", "Details", "Your Bank Description Column"]
DEBIT_ALIASES = ["Debit", "CR", "Debit Amount"]
CREDIT_ALIASES = ["Credit", "DR", "Credit Amount"]
```

## 📊 API Endpoints

| Method | Endpoint           | Description                  |
| ------ | ------------------ | ---------------------------- |
| GET    | `/`                | Upload interface             |
| POST   | `/analyze`         | Process uploaded statements  |
| GET    | `/report/{id}`     | View generated report        |
| GET    | `/review/{id}`     | Transaction review interface |
| POST   | `/review/{id}`     | Apply reclassifications      |
| GET    | `/settings`        | Category rules editor        |
| GET    | `/api/rules`       | Fetch rules as JSON          |
| POST   | `/api/rules`       | Save modified rules          |
| POST   | `/api/rules/reset` | Reset rules to defaults      |

## 🛠️ Dependencies

- **fastapi** (0.134.0+) - Modern web framework
- **uvicorn** (0.41.0+) - ASGI server
- **pandas** (3.0.1+) - Data processing
- **jinja2** (3.1.6+) - Template engine
- **plotly** (6.5.2+) - Interactive visualizations
- **aiofiles** (25.1.0+) - Async file I/O
- **python-multipart** (0.0.22+) - Multipart form parsing

## 📝 Example Bank Statements

Sample bank statements are included to test the application:

```
uploads/
├── Axis_statement_last_3_months.csv
├── AxisBank_Dec_Month_Statement.csv
├── SBI_Dec_Month_Statement.csv
└── SBI_statement_last_3_months.csv
```

## 🐛 Troubleshooting

### Port 8000 Already in Use

```bash
# Use a different port
uvicorn app.fast_api:app --reload --host 127.0.0.1 --port 8000
```

### CSV Parsing Errors

- Ensure your CSV has one of the recognized column names (see Configuration)
- Check that date format matches the parser's expectations
- Review warnings in the UI after upload

### Memory Issues with Large Files

If a CSV exceeds the configured upload limits, split it into smaller files before uploading or adjust the limits in `app/const.py`.

## 📄 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📧 Support

For issues, questions, or suggestions, please open an issue on the repository.

---

**Happy analyzing! 📊**
