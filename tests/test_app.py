"""
Tests for the Flask app (routes). Run with: pytest tests/test_app.py -v
No Redis required for these tests; they use in-memory SQLite (conftest).
"""
import pytest

# Import app after conftest has set DATABASE_URL
from app import app as flask_app


@pytest.fixture
def client():
    """Flask test client."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_returns_200(client):
    """GET / returns the form page."""
    r = client.get("/")
    assert r.status_code == 200
    assert b"Place" in r.data or b"Analyze" in r.data


def test_status_404_for_unknown_job(client):
    """GET /status/<id> returns 404 when job does not exist."""
    r = client.get("/status/999999")
    assert r.status_code == 404


def test_api_status_404_for_unknown_job(client):
    """GET /api/status/<id> returns 404 JSON when job does not exist."""
    r = client.get("/api/status/999999")
    assert r.status_code == 404
    data = r.get_json()
    assert data is not None
    assert "error" in data
