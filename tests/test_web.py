"""Automated tests for the browser forms."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LENDING_DB", str(tmp_path / "web_test.db"))
    import lending

    lending = importlib.reload(lending)
    with TestClient(lending.app) as test_client:
        yield test_client


def test_dashboard_and_main_form_pages_load(client):
    for path in ("/", "/ui/equipment", "/ui/equipment/new", "/ui/loans",
                 "/ui/loans/new", "/ui/availability"):
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.text}"


def test_equipment_can_be_added_and_updated_through_forms(client):
    created = client.post(
        "/ui/equipment",
        data={"name": "Form laptop", "description": "Created using HTML form"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    items = client.get("/equipment").json()
    equipment = next(item for item in items if item["name"] == "Form laptop")

    updated = client.post(
        f"/ui/equipment/{equipment['id']}/update",
        data={"name": "Updated laptop", "description": "Updated from browser"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    refreshed = client.get("/equipment").json()
    assert any(item["id"] == equipment["id"] and item["name"] == "Updated laptop"
               for item in refreshed)


def test_loan_can_be_created_cancelled_and_releases_equipment(client):
    created_equipment = client.post(
        "/ui/equipment",
        data={"name": "Form projector", "description": "HDMI"},
        follow_redirects=False,
    )
    assert created_equipment.status_code == 303
    equipment = next(
        item for item in client.get("/equipment").json()
        if item["name"] == "Form projector"
    )

    created_loan = client.post(
        "/ui/loans",
        data={
            "equipment_id": str(equipment["id"]),
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
        },
        follow_redirects=False,
    )
    assert created_loan.status_code == 303
    loans = client.get("/loans").json()
    loan = next(item for item in loans if item["equipment_id"] == equipment["id"])

    cancelled = client.post(
        f"/ui/loans/{loan['id']}/cancel",
        follow_redirects=False,
    )
    assert cancelled.status_code == 303

    available = client.get(
        "/equipment/search",
        params={"start_date": "2026-11-02", "end_date": "2026-11-04"},
    )
    assert any(item["id"] == equipment["id"] for item in available.json())


def test_overlapping_loan_form_shows_validation_error(client):
    equipment = client.post(
        "/equipment",
        json={"name": "Form camera", "description": ""},
    ).json()
    first = client.post(
        "/loans",
        json={
            "equipment_id": equipment["id"],
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/ui/loans",
        data={
            "equipment_id": str(equipment["id"]),
            "start_date": "2026-11-04",
            "end_date": "2026-11-06",
        },
    )
    assert second.status_code == 400
    assert "conflict" in second.text.lower()


def test_equipment_with_active_loan_cannot_be_removed_through_form(client):
    equipment = client.post(
        "/equipment",
        json={"name": "Form microphone", "description": ""},
    ).json()
    loan = client.post(
        "/loans",
        json={
            "equipment_id": equipment["id"],
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
        },
    )
    assert loan.status_code == 201

    response = client.post(
        f"/ui/equipment/{equipment['id']}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert any(item["id"] == equipment["id"] for item in client.get("/equipment").json())


def test_availability_form_returns_equipment_for_date_range(client):
    client.post("/equipment", json={"name": "Available keyboard", "description": ""})
    response = client.get(
        "/ui/availability",
        params={"start_date": "2026-11-10", "end_date": "2026-11-12"},
    )
    assert response.status_code == 200
    assert "Available keyboard" in response.text


def test_loan_dates_can_be_changed_through_form(client):
    equipment = client.post(
        "/equipment",
        json={"name": "Form tablet", "description": ""},
    ).json()
    created = client.post(
        "/ui/loans",
        data={
            "equipment_id": str(equipment["id"]),
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    loan = next(
        item for item in client.get("/loans").json()
        if item["equipment_id"] == equipment["id"]
    )

    changed = client.post(
        f"/ui/loans/{loan['id']}/update",
        data={"start_date": "2026-11-02", "end_date": "2026-11-06"},
        follow_redirects=False,
    )
    assert changed.status_code == 303
    updated = next(item for item in client.get("/loans").json()
                   if item["id"] == loan["id"])
    assert updated["start_date"] == "2026-11-02"
    assert updated["end_date"] == "2026-11-06"


def test_equipment_without_loans_can_be_removed_through_form(client):
    created = client.post(
        "/ui/equipment",
        data={"name": "Temporary item", "description": "Remove me"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    equipment = next(
        item for item in client.get("/equipment").json()
        if item["name"] == "Temporary item"
    )

    removed = client.post(
        f"/ui/equipment/{equipment['id']}/delete",
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert all(item["id"] != equipment["id"] for item in client.get("/equipment").json())
