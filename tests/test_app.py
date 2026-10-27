import re
from pathlib import Path

from fastapi.testclient import TestClient

from repair_agent.app import create_app


def test_control_origin_and_csrf_boundary(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        token = re.search(r'name="csrf-token" content="([^"]+)"', response.text)[1]
        payload = {"fixture": "13-correct-form", "mode": "scripted"}
        assert client.post("/api/runs", json=payload).status_code == 403
        assert (
            client.post(
                "/api/runs",
                json=payload,
                headers={"origin": "http://127.0.0.1:9000", "x-csrf-token": token},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/runs",
                json={"fixture": "../../private"},
                headers={"origin": "http://testserver", "x-csrf-token": token},
            ).status_code
            == 422
        )
        assert client.get("/fixtures/01-newsletter/index.html").status_code == 404
        assert client.get("/runs/invalid/image/original.png").status_code == 404
        assert client.get("/", headers={"host": "attacker.example"}).status_code == 400
        assert "frame-src 'none'" in response.headers["content-security-policy"]


def test_live_missing_credentials_is_explicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/")
        token = re.search(r'name="csrf-token" content="([^"]+)"', response.text)[1]
        result = client.post(
            "/api/runs",
            json={"fixture": "01-newsletter", "mode": "live"},
            headers={"origin": "http://testserver", "x-csrf-token": token},
        )
        assert result.status_code == 400
        assert "unavailable" in result.json()["detail"]
