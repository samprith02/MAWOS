"""The FastAPI process is API-only; React is served by Vite separately."""
from fastapi.testclient import TestClient
from starlette.routing import Mount

from backend.app.main import app


def test_backend_root_and_documentation_remain_available():
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert root.headers["content-type"].startswith("application/json")
    assert root.json() == {
        "service": "MAWOS API", "status": "running", "docs": "/docs"}
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_backend_does_not_mount_or_serve_any_frontend():
    client = TestClient(app)

    mounted_paths = {route.path for route in app.routes if isinstance(route, Mount)}
    assert "/static" not in mounted_paths
    assert "/assets" not in mounted_paths
    for path in ("/static/index.html", "/assets/missing.js", "/student", "/admin",
                 "/api/not-a-real-route"):
        response = client.get(path)
        assert response.status_code == 404
        assert "text/html" not in response.headers.get("content-type", "")
