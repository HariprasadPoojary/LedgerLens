"""HTTP route coverage with all writable app data redirected to pytest temp dirs."""

import pickle
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.fast_api as fast_api
import app.rules_store as rules_store
from app import const
from app.const import CATEGORY_RULES


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Keep every route's filesystem writes inside this test's temporary tree."""
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"
    session_dir = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    for path in (upload_dir, report_dir, session_dir, data_dir):
        path.mkdir()

    monkeypatch.setattr(fast_api, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(fast_api, "REPORT_DIR", report_dir)
    monkeypatch.setattr(fast_api, "SESSION_DIR", session_dir)
    monkeypatch.setattr(rules_store, "DATA_DIR", data_dir)
    monkeypatch.setattr(rules_store, "RULES_FILE", data_dir / "rules.json")

    # Route tests exercise the response and workflow; keep generated artifacts tiny.
    def write_report(analysis, output_path, session_id=None):
        from pathlib import Path

        Path(output_path).write_text(f"report:{session_id}", encoding="utf-8")

    monkeypatch.setattr(fast_api, "generate_report", write_report)
    with TestClient(fast_api.app) as test_client:
        yield test_client


VALID_CSV = """Date,PARTICULARS,Debit,Credit,Balance
01/01/2024,ACH-CR SALARY,,50000,50000
05/01/2024,UPI/Zomato Food,500,,49500
"""


def test_analyze_rejects_non_csv_upload(client, tmp_path):
    response = client.post(
        "/analyze", files={"files": ("statement.txt", b"not a csv", "text/plain")}
    )

    assert response.status_code == 400
    assert "Only CSV files" in response.json()["error"]
    assert list((tmp_path / "uploads").iterdir()) == []


def test_analyze_rejects_bad_date_range(client, tmp_path):
    response = client.post(
        "/analyze",
        files={"files": ("statement.csv", VALID_CSV, "text/csv")},
        data={"date_from": "2024-02-01", "date_to": "2024-01-01"},
    )

    assert response.status_code == 400
    assert "on or before" in response.json()["error"]
    assert list((tmp_path / "uploads").iterdir()) == []


def test_analyze_returns_error_and_cleans_upload_after_parse_failure(client, tmp_path):
    response = client.post(
        "/analyze",
        files={"files": ("statement.csv", b"not,a,valid,bank,statement\n", "text/csv")},
    )

    assert response.status_code == 422
    assert "Could not read statement.csv" in response.json()["error"]
    assert list((tmp_path / "uploads").iterdir()) == []


def test_analyze_success_saves_session_and_report_then_cleans_upload(client, tmp_path):
    response = client.post(
        "/analyze", files={"files": ("statement.CSV", VALID_CSV, "text/csv")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report_url"].startswith("/report/")
    assert body["other_count"] >= 0
    session_id = body["report_url"].rsplit("/", 1)[-1]
    assert (tmp_path / "sessions" / f"{session_id}.pkl").is_file()
    assert (tmp_path / "reports" / f"report_{session_id}.html").read_text() == (
        f"report:{session_id}"
    )
    assert list((tmp_path / "uploads").iterdir()) == []


def test_analyze_accepts_file_just_under_configured_size_limit(
    client, monkeypatch
):
    content = VALID_CSV.encode()
    monkeypatch.setattr(const, "MAX_FILE_SIZE_BYTES", len(content) + 1)

    response = client.post(
        "/analyze", files={"files": ("statement.csv", content, "text/csv")}
    )

    assert response.status_code == 200


def test_analyze_rejects_file_over_configured_size_limit(client, monkeypatch):
    content = VALID_CSV.encode() + b"\n\n"
    monkeypatch.setattr(
        const, "MAX_FILE_SIZE_BYTES", len(VALID_CSV.encode()) + 1
    )

    response = client.post(
        "/analyze", files={"files": ("statement.csv", content, "text/csv")}
    )

    assert response.status_code == 413
    assert "Each CSV must be at most" in response.json()["error"]


def test_analyze_accepts_file_count_at_configured_limit(client, monkeypatch):
    monkeypatch.setattr(const, "MAX_UPLOAD_FILES", 2)

    response = client.post(
        "/analyze",
        files=[
            ("files", ("one.csv", VALID_CSV, "text/csv")),
            ("files", ("two.csv", VALID_CSV, "text/csv")),
        ],
    )

    assert response.status_code == 200


def test_analyze_rejects_file_count_over_configured_limit(client, monkeypatch):
    monkeypatch.setattr(const, "MAX_UPLOAD_FILES", 2)

    response = client.post(
        "/analyze",
        files=[
            ("files", ("one.csv", VALID_CSV, "text/csv")),
            ("files", ("two.csv", VALID_CSV, "text/csv")),
            ("files", ("three.csv", VALID_CSV, "text/csv")),
        ],
    )

    assert response.status_code == 413
    assert "maximum is 2 files" in response.json()["error"]


def test_analyze_accepts_request_just_under_total_size_limit(
    client, monkeypatch
):
    boundary = "upload-boundary"
    content = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="statement.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode() + VALID_CSV.encode() + f"\r\n--{boundary}--\r\n".encode()
    monkeypatch.setattr(
        const, "MAX_REQUEST_SIZE_BYTES", len(content) + 1
    )

    response = client.post(
        "/analyze",
        content=content,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 200


def test_analyze_rejects_request_over_total_size_limit(client, monkeypatch):
    boundary = "upload-boundary"
    content = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="statement.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode() + VALID_CSV.encode() + f"\r\n--{boundary}--\r\n".encode()
    monkeypatch.setattr(
        const, "MAX_REQUEST_SIZE_BYTES", len(content) + 1
    )

    response = client.post(
        "/analyze",
        content=content + b"  ",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 413
    assert "maximum total request size" in response.json()["error"]


def test_home_page_displays_configured_upload_limits(client, monkeypatch):
    monkeypatch.setattr(const, "MAX_UPLOAD_FILES", 3)
    monkeypatch.setattr(const, "MAX_FILE_SIZE_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(const, "MAX_REQUEST_SIZE_BYTES", 7 * 1024 * 1024)

    response = client.get("/")

    assert response.status_code == 200
    assert "up to 3 CSV files" in response.text
    assert "2 MiB per file" in response.text
    assert "7 MiB total per upload" in response.text


def test_report_and_review_return_404_for_missing_artifacts(client):
    missing_id = "0123456789"

    report = client.get(f"/report/{missing_id}")
    review = client.get(f"/review/{missing_id}")
    submission = client.post(
        f"/review/{missing_id}", json={"overrides": {"0": "Dining"}}
    )

    assert report.status_code == 404
    assert "Report not found" in report.text
    assert review.status_code == 404
    assert "Session not found" in review.text
    assert submission.status_code == 404
    assert submission.json() == {"error": "Session not found."}


def test_review_renders_session_and_accepts_override(client, tmp_path):
    session_id = "0123456789"
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-05")],
            "description": ["UPI unknown shop"],
            "amount": [-250.0],
            "type": ["debit"],
            "category": ["Other"],
        }
    )
    with (tmp_path / "sessions" / f"{session_id}.pkl").open("wb") as session_file:
        pickle.dump({"df": frame, "warnings": []}, session_file)

    page = client.get(f"/review/{session_id}")
    assert page.status_code == 200
    assert "UPI unknown shop" in page.text
    assert 'data-idx="0"' in page.text
    assert f"/report/{session_id}" in page.text

    submitted = client.post(
        f"/review/{session_id}", json={"overrides": {"0": "Dining"}}
    )
    assert submitted.status_code == 200
    assert submitted.json() == {"report_url": f"/report/{session_id}"}
    with (tmp_path / "sessions" / f"{session_id}.pkl").open("rb") as session_file:
        saved = pickle.load(session_file)
    assert saved["df"].at[0, "category"] == "Dining"
    assert (tmp_path / "reports" / f"report_{session_id}.html").is_file()


def test_review_rejects_bad_submission_without_changing_session(client, tmp_path):
    session_id = "0123456789"
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-05")],
            "description": ["UPI unknown shop"],
            "amount": [-250.0],
            "type": ["debit"],
            "category": ["Other"],
        }
    )
    with (tmp_path / "sessions" / f"{session_id}.pkl").open("wb") as session_file:
        pickle.dump({"df": frame, "warnings": []}, session_file)

    response = client.post(
        f"/review/{session_id}", json={"overrides": {"9": "Dining"}}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid transaction index."}
    with (tmp_path / "sessions" / f"{session_id}.pkl").open("rb") as session_file:
        saved = pickle.load(session_file)
    assert saved["df"].at[0, "category"] == "Other"
    assert list((tmp_path / "reports").iterdir()) == []


def test_rules_api_reads_saves_and_resets_rules(client):
    initial = client.get("/api/rules")
    assert initial.status_code == 200
    assert initial.json() == [
        {"category": category, "patterns": patterns, "txn_type": txn_type}
        for category, patterns, txn_type in CATEGORY_RULES
    ]

    custom_rules = [
        {"category": "Dining", "patterns": ["Cafe"], "txn_type": "debit"}
    ]
    saved = client.post("/api/rules", json=custom_rules)
    assert saved.status_code == 200
    assert saved.json() == {"ok": True, "count": 1}
    assert client.get("/api/rules").json() == custom_rules

    reset = client.post("/api/rules/reset")
    assert reset.status_code == 200
    assert reset.json() == {"ok": True}
    assert client.get("/api/rules").json() == initial.json()


@pytest.mark.parametrize("body", [{"bad": "shape"}, {"category": "Dining"}, "not a list"])
def test_rules_api_reports_invalid_save_payload(client, body):
    response = client.post("/api/rules", json=body)

    assert response.status_code == 400
    assert "error" in response.json()


def test_rules_api_names_invalid_pattern_and_preserves_saved_rules(client):
    existing = [{"category": "Dining", "patterns": ["Cafe"], "txn_type": "debit"}]
    assert client.post("/api/rules", json=existing).status_code == 200

    response = client.post(
        "/api/rules",
        json=[{"category": "Dining", "patterns": ["re:[invalid"], "txn_type": "debit"}],
    )

    assert response.status_code == 400
    assert "Dining" in response.json()["error"]
    assert "re:[invalid" in response.json()["error"]
    assert client.get("/api/rules").json() == existing


def test_cleanup_expired_artifacts_removes_only_old_app_artifacts(client, tmp_path, monkeypatch):
    import app.fast_api as fast_api

    retention = const.ARTIFACT_RETENTION_DAYS * 24 * 60 * 60
    now = 2_000_000_000
    artifact_root = tmp_path / "cleanup"
    sessions = artifact_root / "sessions"
    reports = artifact_root / "reports"
    sessions.mkdir(parents=True)
    reports.mkdir()
    monkeypatch.setattr(fast_api, "SESSION_DIR", sessions)
    monkeypatch.setattr(fast_api, "REPORT_DIR", reports)

    old_id = "a" * 10
    recent_id = "b" * 10
    old_session = sessions / f"{old_id}.pkl"
    recent_session = sessions / f"{recent_id}.pkl"
    old_report = reports / f"report_{old_id}.html"
    recent_report = reports / f"report_{recent_id}.html"
    malformed_old_session = sessions / f"{'c' * 10}.pkl"
    unrelated_old_file = sessions / "user-notes.pkl"
    for path in (old_session, recent_session, old_report, recent_report, malformed_old_session, unrelated_old_file):
        path.write_text("artifact", encoding="utf-8")
    os.utime(old_session, (now - retention - 1, now - retention - 1))
    os.utime(old_report, (now - retention - 1, now - retention - 1))
    os.utime(malformed_old_session, (now - retention - 1, now - retention - 1))
    os.utime(unrelated_old_file, (now - retention - 1, now - retention - 1))
    os.utime(recent_session, (now - retention + 1, now - retention + 1))
    os.utime(recent_report, (now - retention + 1, now - retention + 1))

    fast_api.cleanup_expired_artifacts(now=now)

    assert not old_session.exists()
    assert not old_report.exists()
    assert not malformed_old_session.exists()
    assert recent_session.exists()
    assert recent_report.exists()
    assert unrelated_old_file.exists()
