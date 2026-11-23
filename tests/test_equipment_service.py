
import pytest
from fastapi.testclient import TestClient

from services.equipment_service import database
from services.equipment_service.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Each test uses an isolated SQLite database.
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "equipment_test.db",
    )

    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_equipment_list_initially_empty(client):
    response = client.get("/equipment")

    assert response.status_code == 200
    assert response.json() == []


def test_create_equipment(client):
    response = client.post(
        "/equipment",
        json={
            "name": "Dell Laptop",
            "description": "Latitude 5420",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Dell Laptop"


def test_get_equipment(client):
    created = client.post(
        "/equipment",
        json={"name": "Projector", "description": "Epson"},
    ).json()

    response = client.get(f"/equipment/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Projector"


def test_update_equipment(client):
    created = client.post(
        "/equipment",
        json={"name": "Old Laptop", "description": ""},
    ).json()

    response = client.patch(
        f"/equipment/{created['id']}",
        json={"name": "Updated Laptop"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Laptop"


def test_equipment_not_found(client):
    response = client.get("/equipment/9999")

    assert response.status_code == 404


def test_reject_empty_equipment_name(client):
    response = client.post(
        "/equipment",
        json={"name": "", "description": ""},
    )

    assert response.status_code == 422
@pytest.fixture(autouse=True)
def mock_rabbitmq(monkeypatch):
    from services.equipment_service import main

    monkeypatch.setattr(
        main,
        "publish_event",
        lambda event_type, equipment: None,
    )