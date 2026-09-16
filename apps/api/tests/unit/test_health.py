def test_health_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_readiness_reports_database_status(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.get_json()["dependencies"]["database"] is True
