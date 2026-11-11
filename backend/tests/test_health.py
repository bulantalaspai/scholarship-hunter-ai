from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_returns_typed_service_status():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok", "service": "scholarship-hunter-ai"}


def test_openapi_documents_the_health_response():
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    operation = schema["paths"]["/api/health"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
    assert schema["components"]["schemas"]["HealthResponse"]["required"] == [
        "status",
        "service",
    ]


def test_interactive_api_documentation_is_available():
    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/openapi.json" in response.text
