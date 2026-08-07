"""
API-level tests. Uses a throwaway SQLite DB (isolated from the app's
real storage/app.db) and mocks the Celery `.delay()` call so these
tests don't require a running Redis/worker — they verify the HTTP
contract (upload -> status -> results), not the async processing
itself (that's covered by exercising the real stack via
scripts/test_with_samples.py against a live server).
"""
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image

from app.main import app
from app.database import Base, get_db

TEST_DB_URL = "sqlite:///./storage/test.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _fake_png_bytes():
    img = Image.new("RGB", (300, 300), color=(120, 120, 120))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("app.main.process_image.delay")
def test_upload_returns_pending_id(mock_delay, client):
    resp = client.post(
        "/api/v1/images",
        files={"file": ("test.png", _fake_png_bytes(), "image/png")},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert "id" in body
    mock_delay.assert_called_once_with(body["id"])


@patch("app.main.process_image.delay")
def test_upload_rejects_bad_content_type(mock_delay, client):
    resp = client.post(
        "/api/v1/images",
        files={"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
    )
    assert resp.status_code == 415
    mock_delay.assert_not_called()


@patch("app.main.process_image.delay")
def test_status_then_results_flow(mock_delay, client):
    upload_resp = client.post(
        "/api/v1/images",
        files={"file": ("test.png", _fake_png_bytes(), "image/png")},
    )
    image_id = upload_resp.json()["id"]

    status_resp = client.get(f"/api/v1/images/{image_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "pending"

    # Results before processing completes -> 409, not a 200 with nulls,
    # so a client can't mistake "not ready" for "ready but empty".
    results_resp = client.get(f"/api/v1/images/{image_id}/results")
    assert results_resp.status_code == 409


def test_status_404_for_unknown_id(client):
    resp = client.get("/api/v1/images/does-not-exist/status")
    assert resp.status_code == 404
