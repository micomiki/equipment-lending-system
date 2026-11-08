"""Automated API tests for the FastAPI Equipment Lending project."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Use a separate temporary SQLite database for every test."""
    monkeypatch.setenv("LENDING_DB", str(tmp_path / "test_lending.db"))

    # Import/reload only after setting LENDING_DB because lending.py reads it
    # when the module is imported.
    import lending

    lending = importlib.reload(lending)
    with TestClient(lending.app) as test_client:
        yield test_client


def add_equipment(client, name="Test laptop", description="For automated tests"):
    response = client.post(
        "/equipment", json={"name": name, "description": description}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_loan(client, equipment_id, start="2026-11-01", end="2026-11-05"):
    return client.post(
        "/loans",
        json={
            "equipment_id": equipment_id,
            "start_date": start,
            "end_date": end,
        },
    )


def test_add_and_list_equipment(client):
    added = add_equipment(client, "Laptop", "Dell laptop")
    assert added["name"] == "Laptop"

    response = client.get("/equipment")
    assert response.status_code == 200
    assert any(item["id"] == added["id"] for item in response.json())


def test_overlapping_loan_is_rejected_and_cancel_frees_equipment(client):
    equipment = add_equipment(client, "Projector", "HDMI")

    first = create_loan(client, equipment["id"])
    assert first.status_code == 201, first.text
    loan_id = first.json()["id"]

    overlap = create_loan(
        client, equipment["id"], start="2026-11-03", end="2026-11-07"
    )
    assert overlap.status_code == 409, overlap.text

    cancelled = client.post(f"/loans/{loan_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text

    after_cancel = create_loan(
        client, equipment["id"], start="2026-11-03", end="2026-11-07"
    )
    assert after_cancel.status_code == 201, after_cancel.text


def test_invalid_date_range_returns_error(client):
    equipment = add_equipment(client, "Tablet")
    response = create_loan(
        client, equipment["id"], start="2026-11-06", end="2026-11-01"
    )
    assert response.status_code == 400, response.text


def test_equipment_cannot_be_deleted_with_active_loan(client):
    equipment = add_equipment(client, "Camera")
    loan = create_loan(
        client, equipment["id"], start="2026-11-01", end="2026-11-02"
    )
    assert loan.status_code == 201, loan.text

    response = client.delete(f"/equipment/{equipment['id']}")
    assert response.status_code == 409, response.text


def test_equipment_search_excludes_items_with_overlapping_active_loan(client):
    equipment = add_equipment(client, "Microphone")
    loan = create_loan(
        client, equipment["id"], start="2026-11-01", end="2026-11-05"
    )
    assert loan.status_code == 201, loan.text

    response = client.get(
        "/equipment/search",
        params={"start_date": "2026-11-03", "end_date": "2026-11-04"},
    )
    assert response.status_code == 200, response.text
    assert all(item["id"] != equipment["id"] for item in response.json())
