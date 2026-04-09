from pathlib import Path
import io

import pandas as pd

from app.core.config import settings
from app.services.ingest_service import SheetTable, ingest_service


def _build_xlsx_payload() -> bytes:
    frame = pd.DataFrame(
        [
            {
                "Course Code": "CSE 104",
                "Course Name": "Introduction to Computing",
                "Exam Date": "2026-05-20",
                "Exam Time": "10:00 AM",
                "Location": "Room A101",
                "Notes": "Bring student ID",
            },
            {
                "Course Code": "MAT 113",
                "Course Name": "Calculus I",
                "Exam Date": "2026-05-21",
                "Exam Time": "1:00 PM",
                "Location": "Room B202",
                "Notes": "Closed book",
            },
        ]
    )
    handle = io.BytesIO()
    with pd.ExcelWriter(handle, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Final Exams")
    return handle.getvalue()


def test_upload_url_ingests_html(client, monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = """
        <html>
          <head><title>Course</title></head>
          <body>
            <h1>CSE 104 Syllabus</h1>
            <p>Midterm Exam: 2026-05-14 at 10:00 AM Room A201.</p>
          </body>
        </html>
        """
        content = text.encode("utf-8")

    monkeypatch.setattr("app.services.ingest_service.requests.get", lambda *args, **kwargs: FakeResponse())

    response = client.post("/api/upload-url", json={"url": "https://example.com/syllabus"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["uploaded"]
    assert payload["uploaded"][0]["kind"] == "upload"
    assert payload["uploaded"][0]["ingest_mode"] == "url_public_html"


def test_upload_url_google_public_sheet_ingests(client, monkeypatch):
    xlsx_payload = _build_xlsx_payload()

    class FakeResponse:
        def __init__(self, status_code=200, headers=None, text="", content=b""):
            self.status_code = status_code
            self.headers = headers or {}
            self.text = text
            self.content = content

    def fake_get(url, *args, **kwargs):
        if "docs.google.com/spreadsheets" in url and "format=xlsx" in url:
            return FakeResponse(
                status_code=200,
                headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                content=xlsx_payload,
            )
        return FakeResponse(status_code=404, headers={"content-type": "text/plain"}, text="not found")

    monkeypatch.setattr("app.services.ingest_service.requests.get", fake_get)

    response = client.post(
        "/api/upload-url",
        json={"url": "https://docs.google.com/spreadsheets/d/abc123DEF456/edit?usp=sharing#gid=0"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["uploaded"]
    uploaded = payload["uploaded"][0]
    assert uploaded["kind"] == "upload"
    assert uploaded["ingest_mode"] == "google_public"


def test_upload_url_invalid_google_sheet_link_returns_400(client):
    response = client.post(
        "/api/upload-url",
        json={"url": "https://docs.google.com/spreadsheets/edit#gid=0"},
    )
    assert response.status_code == 400
    assert "invalid google sheets url" in response.json()["detail"].lower()


def test_upload_url_private_google_sheet_requires_credentials(client, monkeypatch):
    class FakeResponse:
        status_code = 403
        headers = {"content-type": "text/html"}
        text = "forbidden"
        content = b"forbidden"

    monkeypatch.setattr("app.services.ingest_service.requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(settings, "google_sheets_service_account_file", "")
    monkeypatch.setattr(settings, "google_sheets_service_account_json", "")

    response = client.post(
        "/api/upload-url",
        json={"url": "https://docs.google.com/spreadsheets/d/privateSheetId/edit#gid=0"},
    )
    assert response.status_code == 400
    assert "configure google_sheets_service_account" in response.json()["detail"].lower()


def test_upload_url_private_google_sheet_via_api(client, monkeypatch):
    class FakeResponse:
        status_code = 403
        headers = {"content-type": "text/html"}
        text = "forbidden"
        content = b"forbidden"

    monkeypatch.setattr("app.services.ingest_service.requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(settings, "google_sheets_service_account_json", '{"type":"service_account"}')
    monkeypatch.setattr(settings, "google_sheets_service_account_file", "")

    def fake_private_tables(_spreadsheet_id, _gid):
        return (
            [
                SheetTable(
                    sheet_name="Exam Plan",
                    headers=["Course Code", "Exam Date", "Exam Time", "Location"],
                    rows=[
                        ["CSE 104", "2026-05-22", "10:00 AM", "Room C101"],
                        ["MAT 113", "2026-05-23", "12:00 PM", "Room D204"],
                    ],
                )
            ],
            {"title": "Private Exam Schedule"},
        )

    monkeypatch.setattr(ingest_service, "_fetch_google_private_sheet_tables", fake_private_tables)

    response = client.post(
        "/api/upload-url",
        json={"url": "https://docs.google.com/spreadsheets/d/privateSheetId/edit#gid=0"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["uploaded"]
    uploaded = payload["uploaded"][0]
    assert uploaded["ingest_mode"] == "google_private_api"
    assert uploaded["name"].startswith("Google Sheet:")


def test_delete_selected_source_removes_file_and_records(client, uploaded_source, storage):
    source_id = uploaded_source["source_id"]
    source = storage.get_source(source_id)
    assert source is not None
    file_path = Path(source["file_path"])
    assert file_path.exists()

    response = client.post(
        "/api/settings/actions",
        json={"action": "delete_source", "source_id": source_id},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert storage.get_source(source_id) is None
    assert not file_path.exists()


def test_clear_uploads_requires_admin_password(client, uploaded_source):
    response = client.post("/api/settings/actions", json={"action": "clear_uploads"})
    assert response.status_code == 403


def test_clear_uploads_with_admin_password(client, uploaded_source, second_uploaded_source):
    response = client.post(
        "/api/settings/actions",
        json={"action": "clear_uploads", "admin_password": settings.admin_password},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["removed_sources"] >= 2

    state = client.get("/api/conversations").json()
    assert all(source["kind"] != "upload" for source in state["sources"])


def test_clear_all_resets_conversations_and_uploads(client, uploaded_source):
    conversation_id = uploaded_source["conversation_id"]
    response = client.post(
        "/api/settings/actions",
        json={"action": "clear_all", "admin_password": settings.admin_password},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["removed_conversations"] >= 1
    assert payload["removed_sources"] >= 1

    listing = client.get("/api/conversations").json()
    assert listing["conversations"] == []
    assert all(source["kind"] != "upload" for source in listing["sources"])

    convo_messages = client.get(f"/api/conversations?conversation_id={conversation_id}").json()
    assert convo_messages["messages"] == []
