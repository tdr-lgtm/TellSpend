from fastapi.testclient import TestClient
from tellspend.main import app

client = TestClient(app)

def test_health_reports_ok_when_database_answers():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}