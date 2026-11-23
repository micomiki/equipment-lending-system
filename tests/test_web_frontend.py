
import pytest
from fastapi.testclient import TestClient

from web import main as web


@pytest.fixture
def client(monkeypatch):
    equipment = [
        {
            "id": 1,
            "name": "Dell Laptop",
            "description": "Latitude 5420",
        }
    ]

    loans = [
        {
            "id": 1,
            "equipment_id": 1,
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
            "status": "active",
        }
    ]

    monkeypatch.setattr(
        web, "service_list_equipment", lambda: equipment
    )
    monkeypatch.setattr(
        web, "service_list_loans", lambda: loans
    )
    monkeypatch.setattr(
        web, "get_equipment",
        lambda equipment_id: next(
            (e for e in equipment if e["id"] == equipment_id),
            None,
        ),
    )

    return TestClient(web.app)


def test_dashboard(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_equipment_list(client):
    response = client.get("/ui/equipment")

    assert response.status_code == 200
    assert "Dell Laptop" in response.text


def test_loan_list(client):
    response = client.get("/ui/loans")

    assert response.status_code == 200
    assert "Dell Laptop" in response.text


def test_equipment_creation(client, monkeypatch):
    created = []

    def fake_create(name, description):
        created.append((name, description))
        return {
            "id": 2,
            "name": name,
            "description": description,
        }

    monkeypatch.setattr(
        web, "service_create_equipment", fake_create
    )

    response = client.post(
        "/ui/equipment",
        data={
            "name": "Projector",
            "description": "Epson",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert created == [("Projector", "Epson")]


def test_loan_creation(client, monkeypatch):
    created = []

    def fake_create(equipment_id, start, end):
        created.append((equipment_id, start, end))
        return {
            "id": 2,
            "equipment_id": equipment_id,
            "start_date": start,
            "end_date": end,
            "status": "active",
        }

    monkeypatch.setattr(
        web, "service_create_loan", fake_create
    )

    response = client.post(
        "/ui/loans",
        data={
            "equipment_id": "1",
            "start_date": "2026-12-10",
            "end_date": "2026-12-15",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert created == [(1, "2026-12-10", "2026-12-15")]


def test_equipment_availability(client):
    response = client.get(
        "/ui/availability",
        params={
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
        },
    )

    assert response.status_code == 200
    assert "Dell Laptop" not in response.text
