
import pytest
from fastapi.testclient import TestClient

from services.loan_service import database
from services.loan_service import main as loan_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Use a separate SQLite database for every test.
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "loans_test.db",
    )

    # Simulate the Equipment Microservice.
    # Equipment ID 1 exists; other IDs do not.
    def fake_get_equipment(equipment_id):
        if equipment_id == 1:
            return {
                "id": 1,
                "name": "Dell Laptop",
                "description": "Test equipment",
            }
        return None

    monkeypatch.setattr(
        loan_service,
        "get_equipment",
        fake_get_equipment,
    )

    with TestClient(loan_service.app) as test_client:
        yield test_client


def create_test_loan(
    client,
    start="2026-12-01",
    end="2026-12-05",
):
    return client.post(
        "/loans",
        json={
            "equipment_id": 1,
            "start_date": start,
            "end_date": end,
        },
    )


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_loans_initially_empty(client):
    response = client.get("/loans")

    assert response.status_code == 200
    assert response.json() == []


def test_create_loan(client):
    response = create_test_loan(client)

    assert response.status_code == 201

    loan = response.json()
    assert loan["equipment_id"] == 1
    assert loan["status"] == "active"
    assert loan["start_date"] == "2026-12-01"
    assert loan["end_date"] == "2026-12-05"


def test_equipment_not_found(client):
    response = client.post(
        "/loans",
        json={
            "equipment_id": 999,
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
        },
    )

    assert response.status_code == 404


def test_invalid_date_range(client):
    response = create_test_loan(
        client,
        start="2026-12-10",
        end="2026-12-01",
    )

    assert response.status_code == 400


def test_overlapping_loans_rejected(client):
    first = create_test_loan(client)
    assert first.status_code == 201

    second = create_test_loan(
        client,
        start="2026-12-03",
        end="2026-12-07",
    )

    assert second.status_code == 409

    # Only the first loan should be stored.
    loans = client.get("/loans").json()
    assert len(loans) == 1


def test_update_loan(client):
    created = create_test_loan(client).json()
    loan_id = created["id"]

    response = client.patch(
        f"/loans/{loan_id}",
        json={
            "start_date": "2026-12-02",
            "end_date": "2026-12-08",
        },
    )

    assert response.status_code == 200
    assert response.json()["start_date"] == "2026-12-02"
    assert response.json()["end_date"] == "2026-12-08"


def test_cancel_loan(client):
    created = create_test_loan(client).json()
    loan_id = created["id"]

    response = client.post(
        f"/loans/{loan_id}/cancel"
    )

    assert response.status_code == 200

    loan = client.get(f"/loans/{loan_id}").json()
    assert loan["status"] == "cancelled"


def test_cancelled_loan_cannot_be_updated(client):
    created = create_test_loan(client).json()
    loan_id = created["id"]

    client.post(f"/loans/{loan_id}/cancel")

    response = client.patch(
        f"/loans/{loan_id}",
        json={"end_date": "2026-12-10"},
    )

    assert response.status_code == 409


def test_equipment_available_after_cancellation(client):
    created = create_test_loan(client).json()

    client.post(f"/loans/{created['id']}/cancel")

    # The same dates should now be available.
    response = create_test_loan(client)

    assert response.status_code == 201


def test_active_loans_for_equipment(client):
    create_test_loan(client)

    response = client.get(
        "/loans/active/equipment/1"
    )

    assert response.status_code == 200

    data = response.json()
    assert data["equipment_id"] == 1
    assert data["has_active_loans"] is True
    assert len(data["loans"]) == 1


def test_adjacent_date_overlap_rejected(client):
    create_test_loan(client)

    # Inclusive dates: December 5 is already booked.
    response = create_test_loan(
        client,
        start="2026-12-05",
        end="2026-12-09",
    )

    assert response.status_code == 409

def test_loan_rejected_during_equipment_deletion(client):
    from services.loan_service.database import db

    # Simulate a deletion already in progress.
    with db() as conn:
        conn.execute(
            """
            INSERT INTO equipment_deletion_guards(
                equipment_id,
                status
            )
            VALUES (?, ?)
            """,
            (1, "pending"),
        )

    response = create_test_loan(client)

    assert response.status_code == 409
    assert "deletion" in response.json()["detail"].lower()

    # No loan must be created.
    loans = client.get("/loans").json()
    assert loans == []
