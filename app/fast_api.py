"""
FastAPI app — financial analyzer web interface.

Routes:
  GET  /                      → upload UI (with date range filter)
  POST /analyze               → process CSV(s), return report URL
  GET  /report/{id}           → serve generated HTML report
  GET  /review/{id}           → uncategorized transaction review UI
  POST /review/{id}           → apply reclassifications, regenerate report
  GET  /settings              → category editor UI
  GET  /api/rules             → return rules as JSON
  POST /api/rules             → save rules
  POST /api/rules/reset       → reset rules to defaults
"""

import json
import pickle
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import AsyncIterator, cast

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.analyzer import analyze
from app.categorizer import categorize_dataframe
from app.parser import merge_statements, parse_csv
from app.report_builder import generate_report
from app.rules_store import (
    get_category_names,
    get_rules_as_dicts,
    reset_to_defaults,
    save_rules,
)
from app import const

# ── Directories ───────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
REPORT_DIR = BASE_DIR / "reports"
SESSION_DIR = BASE_DIR / "sessions"
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

for d in (UPLOAD_DIR, REPORT_DIR, SESSION_DIR, DATA_DIR):
    d.mkdir(exist_ok=True)

def cleanup_expired_artifacts(now: float | None = None) -> None:
    """Remove expired app-generated sessions and reports from their own folders."""
    cutoff = (time.time() if now is None else now) - const.ARTIFACT_RETENTION_DAYS * 86400
    session_pattern = re.compile(r"(?:[0-9a-f]{10}|[0-9a-f]{32})\.pkl")
    report_pattern = re.compile(r"report_(?:[0-9a-f]{10}|[0-9a-f]{32})\.html")

    if SESSION_DIR.is_dir():
        for session_path in SESSION_DIR.iterdir():
            if not session_pattern.fullmatch(session_path.name) or not session_path.is_file():
                continue
            try:
                expired = session_path.stat().st_mtime < cutoff
            except OSError:
                continue
            if expired:
                session_id = session_path.stem
                try:
                    session_path.unlink(missing_ok=True)
                except OSError:
                    continue
                matching_report = REPORT_DIR / f"report_{session_id}.html"
                try:
                    matching_report.unlink(missing_ok=True)
                except OSError:
                    pass

    if REPORT_DIR.is_dir():
        for report_path in REPORT_DIR.iterdir():
            if not report_pattern.fullmatch(report_path.name) or not report_path.is_file():
                continue
            try:
                if report_path.stat().st_mtime < cutoff:
                    report_path.unlink(missing_ok=True)
            except OSError:
                continue


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run retention cleanup at startup, outside active request handling."""
    cleanup_expired_artifacts()
    yield


app = FastAPI(title="Financial Analyzer", lifespan=lifespan)


class RequestSizeLimitMiddleware:
    """Reject oversized analyze requests before multipart parsing or disk writes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["path"] not in {"/analyze", "/preview"}
            or scope["method"] != "POST"
        ):
            await self.app(scope, receive, send)
            return

        max_bytes = const.MAX_REQUEST_SIZE_BYTES
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    await self._reject(scope, receive, send, max_bytes)
                    return
            except ValueError:
                pass

        messages: list[Message] = []
        total_bytes = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > max_bytes:
                    await self._reject(scope, receive, send, max_bytes)
                    return
                if not message.get("more_body", False):
                    break

        async def replay_body() -> Message:
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay_body, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, max_bytes: int) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": (
                    "Upload request is too large. The maximum total request size is "
                    f"{max_bytes} bytes."
                )
            },
        )
        await response(scope, receive, send)


app.add_middleware(RequestSizeLimitMiddleware)


# ── Session helpers ───────────────────────────────────────────────────────────


def _load_session(session_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{10}|[0-9a-f]{32}", session_id):
        return None
    pkl = SESSION_DIR / f"{session_id}.pkl"
    if not pkl.exists():
        return None
    with open(pkl, "rb") as f:
        return pickle.load(f)


def _save_session(session_id: str, data: dict) -> None:
    with open(SESSION_DIR / f"{session_id}.pkl", "wb") as f:
        pickle.dump(data, f)


def _recent_sessions_html(limit: int = 10) -> str:
    """Render links for reports whose session data is still available."""
    reports: list[tuple[float, str]] = []
    for report_path in REPORT_DIR.glob("report_*.html"):
        session_id = report_path.stem.removeprefix("report_")
        if not re.fullmatch(r"[0-9a-f]{10}|[0-9a-f]{32}", session_id):
            continue
        try:
            if not (SESSION_DIR / f"{session_id}.pkl").is_file():
                continue
            modified = report_path.stat().st_mtime
        except OSError:
            continue
        reports.append((modified, session_id))

    reports.sort(reverse=True)
    if not reports:
        return (
            '<p class="recent-empty">'
            "No reports yet. Upload a statement to create one."
            "</p>"
        )

    items = []
    for modified, session_id in reports[:limit]:
        updated = datetime.fromtimestamp(modified).strftime("%b %d, %Y · %I:%M %p")
        try:
            session = _load_session(session_id)
        except (
            OSError,
            EOFError,
            pickle.UnpicklingError,
            AttributeError,
            ValueError,
        ):
            continue
        source_files = session.get("source_files", []) if isinstance(session, dict) else []
        if not isinstance(source_files, list):
            source_files = []
        filenames = [escape(name) for name in source_files if isinstance(name, str)]
        label = ", ".join(filenames) if filenames else "Filename unavailable"
        items.append(
            f'<div class="session-entry" data-session-id="{escape(session_id)}">'
            f'<a class="session-item" href="/report/{escape(session_id)}">'
            f'<span class="session-info"><strong>{label}</strong>'
            f'<small>Session {escape(session_id)}</small></span>'
            f'<time>{escape(updated)}</time></a>'
            f'<button class="session-delete" type="button" '
            f'aria-label="Delete report {escape(session_id)}" '
            f'onclick="deleteSession(\'{escape(session_id)}\')">Delete</button>'
            "</div>"
        )
    return "".join(items) or (
        '<p class="recent-empty">'
        "No reports yet. Upload a statement to create one."
        "</p>"
    )


# ── Analyze ───────────────────────────────────────────────────────────────────


@app.post("/preview")
async def preview_statements(request: Request):
    """Parse uploads for a preview, removing every temporary CSV before returning."""
    try:
        form = await request.form(max_files=const.MAX_UPLOAD_FILES)
    except MultiPartException:
        return JSONResponse(
            status_code=413,
            content={"error": f"Too many files uploaded. The maximum is {const.MAX_UPLOAD_FILES} files per request."},
        )
    except HTTPException as exc:
        if exc.status_code == 400 and "too many files" in str(exc.detail).lower():
            return JSONResponse(
                status_code=413,
                content={"error": f"Too many files uploaded. The maximum is {const.MAX_UPLOAD_FILES} files per request."},
            )
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    files = [value for value in form.getlist("files") if isinstance(value, UploadFile)]
    if not files or all(not file.filename for file in files):
        await form.close()
        return JSONResponse(status_code=400, content={"error": "Choose at least one CSV file to preview."})

    invalid_files = [
        file.filename or "(unnamed file)"
        for file in files
        if not file.filename or Path(file.filename).suffix.lower() != ".csv"
    ]
    if invalid_files:
        await form.close()
        return JSONResponse(
            status_code=400,
            content={"error": "Only CSV files are accepted. Invalid file(s): " + ", ".join(invalid_files)},
        )

    oversized = [
        file.filename or "(unnamed file)"
        for file in files
        if (file.size or 0) > const.MAX_FILE_SIZE_BYTES
    ]
    if oversized:
        await form.close()
        return JSONResponse(
            status_code=413,
            content={
                "error": (
                    f"File size limit exceeded. Each CSV must be at most {const.MAX_FILE_SIZE_BYTES} bytes. "
                    "Oversized file(s): " + ", ".join(oversized)
                )
            },
        )

    date_from_value = form.get("date_from")
    date_to_value = form.get("date_to")
    date_from = date_from_value if isinstance(date_from_value, str) else None
    date_to = date_to_value if isinstance(date_to_value, str) else None

    def parse_date_filter(value: str | None, label: str) -> date | None:
        if value is None or not value.strip():
            return None
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            raise ValueError(f"{label} must be a valid date in YYYY-MM-DD format.") from None
        if parsed.isoformat() != value.strip():
            raise ValueError(f"{label} must be a valid date in YYYY-MM-DD format.")
        return parsed

    try:
        start_date = parse_date_filter(date_from, "Start date")
        end_date = parse_date_filter(date_to, "End date")
    except ValueError as exc:
        await form.close()
        return JSONResponse(status_code=400, content={"error": str(exc)})
    if start_date and end_date and start_date > end_date:
        await form.close()
        return JSONResponse(status_code=400, content={"error": "Start date must be on or before end date."})

    preview_id = uuid.uuid4().hex[:10]
    temp_paths: list[Path] = []
    try:
        results = []
        for index, file in enumerate(files):
            path = UPLOAD_DIR / f"preview_{preview_id}_{index}.csv"
            temp_paths.append(path)
            path.write_bytes(await file.read())
            try:
                results.append(parse_csv(str(path)))
            except Exception as exc:
                filename = file.filename or "uploaded file"
                return JSONResponse(
                    status_code=422,
                    content={"error": f"Could not preview {filename}: {exc} Check that it is a supported bank statement CSV."},
                )

        df = results[0].df if len(results) == 1 else merge_statements(results)
        if start_date:
            df = df[df["date"] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df["date"] <= pd.Timestamp(end_date)]
        if df.empty:
            return JSONResponse(
                status_code=422,
                content={"error": "No transactions remain after parsing and applying the selected date range. Change the dates or choose different files."},
            )

        sample = []
        for _, row in df.head(5).iterrows():
            transaction_date = cast(pd.Timestamp, row["date"])
            transaction_amount = cast(float, row["amount"])
            sample.append(
                {
                    "date": transaction_date.date().isoformat(),
                    "description": str(row["description"]),
                    "amount": float(transaction_amount),
                    "type": str(row["type"]),
                }
            )
        files_preview = [
            {
                "name": Path(files[index].filename or result.source_file).name,
                "detected_columns": result.detected_columns,
                "transaction_count": result.row_count,
                "warnings": result.warnings,
            }
            for index, result in enumerate(results)
        ]
        warnings = [warning for result in results for warning in result.warnings]
        return JSONResponse(
            content={
                "files": files_preview,
                "transaction_count": len(df),
                "date_range": [df["date"].min().date().isoformat(), df["date"].max().date().isoformat()],
                "warnings": warnings,
                "sample": sample,
            }
        )
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
        await form.close()


@app.post("/analyze")
async def analyze_statements(request: Request):
    try:
        form = await request.form(max_files=const.MAX_UPLOAD_FILES)
    except MultiPartException:
        return JSONResponse(
            status_code=413,
            content={
                "error": (
                    "Too many files uploaded. The maximum is "
                    f"{const.MAX_UPLOAD_FILES} files per request."
                )
            },
        )
    except HTTPException as exc:
        if exc.status_code == 400 and "too many files" in str(exc.detail).lower():
            return JSONResponse(
                status_code=413,
                content={
                    "error": (
                        "Too many files uploaded. The maximum is "
                    f"{const.MAX_UPLOAD_FILES} files per request."
                    )
                },
            )
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    files = [value for value in form.getlist("files") if isinstance(value, UploadFile)]
    date_from_value = form.get("date_from")
    date_to_value = form.get("date_to")
    date_from = date_from_value if isinstance(date_from_value, str) else None
    date_to = date_to_value if isinstance(date_to_value, str) else None

    if not files or all(not f.filename for f in files):
        await form.close()
        return JSONResponse(status_code=400, content={"error": "No files uploaded."})

    oversized = [
        f.filename or "(unnamed file)"
        for f in files
        if (f.size or 0) > const.MAX_FILE_SIZE_BYTES
    ]
    if oversized:
        await form.close()
        return JSONResponse(
            status_code=413,
            content={
                "error": (
                    "File size limit exceeded. Each CSV must be at most "
                    f"{const.MAX_FILE_SIZE_BYTES} bytes. Oversized file(s): "
                    + ", ".join(oversized)
                )
            },
        )

    invalid_files = [
        f.filename or "(unnamed file)"
        for f in files
        if not f.filename or Path(f.filename).suffix.lower() != ".csv"
    ]
    if invalid_files:
        await form.close()
        return JSONResponse(
            status_code=400,
            content={
                "error": "Only CSV files are accepted. Invalid file(s): "
                + ", ".join(invalid_files)
            },
        )

    def parse_date_filter(value: str | None, label: str) -> date | None:
        if value is None or not value.strip():
            return None
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            raise ValueError(f"{label} must be a valid date in YYYY-MM-DD format.") from None
        if parsed.isoformat() != value.strip():
            raise ValueError(f"{label} must be a valid date in YYYY-MM-DD format.")
        return parsed

    try:
        start_date = parse_date_filter(date_from, "Start date")
        end_date = parse_date_filter(date_to, "End date")
    except ValueError as e:
        await form.close()
        return JSONResponse(status_code=400, content={"error": str(e)})

    if start_date and end_date and start_date > end_date:
        await form.close()
        return JSONResponse(
            status_code=400,
            content={"error": "Start date must be on or before end date."},
        )

    session_id = uuid.uuid4().hex[:10]
    saved_paths: list[Path] = []
    parse_results = []
    all_warnings: list[str] = []

    try:
        for index, file in enumerate(files):
            dest = UPLOAD_DIR / f"{session_id}_{index}.csv"
            saved_paths.append(dest)
            dest.write_bytes(await file.read())
            try:
                result = parse_csv(str(dest))
            except Exception as e:
                filename = file.filename or "uploaded file"
                return JSONResponse(
                    status_code=422,
                    content={"error": f"Could not read {filename} as a valid CSV: {e}"},
                )
            parse_results.append(result)
            all_warnings.extend(result.warnings)

        df = parse_results[0].df if len(parse_results) == 1 else merge_statements(parse_results)

    # ── Date range filter ─────────────────────────────────────────────────────
        if start_date:
            df = df[df["date"] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df["date"] <= pd.Timestamp(end_date)]

        if df.empty:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "No transactions remain after parsing and applying the selected date range."
                },
            )

        df = categorize_dataframe(df)
        source_files = [
            (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            for file in files
        ]
        _save_session(
            session_id,
            {"df": df, "warnings": all_warnings, "source_files": source_files},
        )

        analysis = analyze(df, all_warnings)
        report_path = REPORT_DIR / f"report_{session_id}.html"
        generate_report(analysis, str(report_path), session_id=session_id)

        other_count = int((df["category"].isin(["Other", "Other Income"])).sum())
        return JSONResponse(
            content={"report_url": f"/report/{session_id}", "other_count": other_count}
        )
    finally:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        await form.close()



# ── Report ────────────────────────────────────────────────────────────────────


@app.get("/report/{session_id}")
def get_report(session_id: str):
    path = REPORT_DIR / f"report_{session_id}.html"
    if not path.exists():
        return HTMLResponse(
            "<h2 style='font-family:sans-serif;padding:40px'>Report not found.</h2>",
            status_code=404,
        )
    return FileResponse(path, media_type="text/html")


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    if not re.fullmatch(r"[0-9a-f]{10}|[0-9a-f]{32}", session_id):
        return JSONResponse(status_code=400, content={"error": "Invalid session ID."})

    session_path = SESSION_DIR / f"{session_id}.pkl"
    report_path = REPORT_DIR / f"report_{session_id}.html"
    if not session_path.is_file() and not report_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Session not found."})

    try:
        session_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
    except OSError:
        return JSONResponse(
            status_code=500,
            content={"error": "Could not delete the session and report."},
        )
    return JSONResponse(content={"ok": True})


# ── Uncategorized Review ──────────────────────────────────────────────────────


@app.get("/review/{session_id}", response_class=HTMLResponse)
def review_page(session_id: str):
    data = _load_session(session_id)
    if data is None:
        return HTMLResponse(
            "<h2 style='font-family:sans-serif;padding:40px'>Session not found.</h2>",
            status_code=404,
        )

    df = data["df"]
    other_df = df[df["category"].isin(["Other", "Other Income"])].copy()

    if other_df.empty:
        return HTMLResponse(
            f"""<html><body style='font-family:sans-serif;padding:40px;background:#0f172a;color:#e2e8f0'>
        <h2>✅ No uncategorized transactions!</h2><br>
        <a href='/report/{session_id}' style='color:#63cab7'>← Back to report</a></body></html>"""
        )

    categories = get_category_names()
    cat_options = "".join(
        f'<option value="{escape(c, quote=True)}">{escape(c)}</option>'
        for c in categories
    )

    rows_html = ""
    for idx, row in other_df.iterrows():
        amt_class = "pos" if row["amount"] > 0 else "neg"
        amt_sign = "+" if row["amount"] > 0 else ""
        date_str = escape(str(row["date"])[:10])
        desc = escape(str(row["description"]), quote=True)
        current_category = escape(str(row["category"]))
        row_index = escape(str(idx), quote=True)
        rows_html += f"""
        <tr>
          <td class="mono muted">{date_str}</td>
          <td class="desc" title="{desc}">{desc}</td>
          <td class="{escape(amt_class, quote=True)} mono">{escape(amt_sign)}₹{abs(row['amount']):,.0f}</td>
          <td><span class="cur-cat">{current_category}</span></td>
          <td><select class="cat-select" data-idx="{row_index}">
            <option value="">— keep as {current_category} —</option>
            {cat_options}
          </select></td>
        </tr>"""

    return HTMLResponse(
        (TEMPLATES_DIR / "review.html")
        .read_text(encoding="utf-8")
        .replace("__SESSION_ID__", json.dumps(session_id))
        .replace("__OTHER_COUNT__", str(len(other_df)))
        .replace("__ROWS__", rows_html)
        .replace("__REPORT_URL__", f"/report/{session_id}")
    )


@app.post("/review/{session_id}")
async def apply_review(session_id: str, request: Request):
    data = _load_session(session_id)
    if data is None:
        return JSONResponse(status_code=404, content={"error": "Session not found."})

    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(status_code=400, content={"error": "Invalid review submission."})
    if not isinstance(body, dict) or not isinstance(body.get("overrides"), dict):
        return JSONResponse(status_code=400, content={"error": "Invalid review submission."})

    submitted = body["overrides"]
    overrides: dict[int, str] = {}
    valid_categories = set(get_category_names())
    for raw_idx, category in submitted.items():
        if not isinstance(raw_idx, str) or not re.fullmatch(r"-?\d+", raw_idx):
            return JSONResponse(status_code=400, content={"error": "Invalid transaction index."})
        idx = int(raw_idx)
        if not isinstance(category, str) or category not in valid_categories:
            return JSONResponse(status_code=400, content={"error": "Invalid category."})
        overrides[idx] = category
    if not overrides:
        return JSONResponse(status_code=400, content={"error": "No changes submitted."})

    df = data["df"].copy()
    if any(idx not in df.index for idx in overrides):
        return JSONResponse(status_code=400, content={"error": "Invalid transaction index."})
    for idx, cat in overrides.items():
        df.at[idx, "category"] = cat

    _save_session(session_id, {**data, "df": df})
    analysis = analyze(df, data["warnings"])
    generate_report(analysis, str(REPORT_DIR / f"report_{session_id}.html"), session_id=session_id)

    return JSONResponse(content={"report_url": f"/report/{session_id}"})


# ── Settings / Category Editor ────────────────────────────────────────────────


@app.get("/settings", response_class=HTMLResponse)
def settings_page():
    return (TEMPLATES_DIR / "settings.html").read_text(encoding="utf-8")


@app.get("/api/rules")
def get_rules_api():
    return JSONResponse(content=get_rules_as_dicts())


@app.post("/api/rules")
async def save_rules_api(request: Request):
    try:
        rules = await request.json()
        save_rules(rules)
        return JSONResponse(content={"ok": True, "count": len(rules)})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/rules/reset")
def reset_rules_api():
    reset_to_defaults()
    return JSONResponse(content={"ok": True})


# ── Upload UI ─────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the main HTML page with the file upload form."""
    template = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    mib = 1024 * 1024
    return (
        template.replace("__RECENT_SESSIONS__", _recent_sessions_html())
        .replace("__MAX_UPLOAD_FILES__", str(const.MAX_UPLOAD_FILES))
        .replace("__MAX_FILE_SIZE__", f"{const.MAX_FILE_SIZE_BYTES / mib:g} MiB")
        .replace("__MAX_REQUEST_SIZE__", f"{const.MAX_REQUEST_SIZE_BYTES / mib:g} MiB")
    )
