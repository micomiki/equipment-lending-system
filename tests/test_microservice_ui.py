"""Exercise service-mode UI routing without depending on running containers."""

import importlib

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


@pytest.fixture
def service_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("LENDING_DB", str(tmp_path / "legacy.db"))
    import lending

    lending = importlib.reload(lending)
    monkeypatch.setattr(lending, "WEB_USE_MICROSERVICES", True)
    equipment = [{"id": 1, "name": "Laptop", "description": "Test"}]
    loans = []

    def fake_create_equipment(name, description):
        equipment.append({"id": len(equipment) + 1, "name": name, "description": description})

    def fake_update_equipment(equipment_id, **changes):
        next(item for item in equipment if item["id"] == equipment_id).update(changes)

    def fake_create_loan(equipment_id, start_date, end_date):
        loans.append({"id": len(loans) + 1, "equipment_id": equipment_id,
                      "start_date": start_date, "end_date": end_date, "status": "active"})

    def fake_update_loan(loan_id, **changes):
        next(item for item in loans if item["id"] == loan_id).update(changes)

    def fake_cancel_loan(loan_id):
        next(item for item in loans if item["id"] == loan_id)["status"] = "cancelled"

    monkeypatch.setattr(lending, "service_list_equipment", lambda: list(equipment))
    monkeypatch.setattr(lending, "get_equipment", lambda eid: next((e for e in equipment if e["id"] == eid), None))
    monkeypatch.setattr(lending, "service_create_equipment", fake_create_equipment)
    monkeypatch.setattr(lending, "service_update_equipment", fake_update_equipment)
    monkeypatch.setattr(lending, "service_list_loans", lambda: list(loans))
    monkeypatch.setattr(lending, "service_get_loan", lambda lid: next((l for l in loans if l["id"] == lid), None))
    monkeypatch.setattr(lending, "service_create_loan", fake_create_loan)
    monkeypatch.setattr(lending, "service_update_loan", fake_update_loan)
    monkeypatch.setattr(lending, "service_cancel_loan", fake_cancel_loan)

    def fake_render(request, template, context, status_code=200):
        context = {key: value for key, value in context.items() if key != "request"}
        return JSONResponse({"template": template, **context}, status_code=status_code)

    monkeypatch.setattr(lending, "_render", fake_render)
    with TestClient(lending.app) as client:
        yield client, equipment, loans


def test_equipment_forms_use_remote_service(service_ui):
    client, equipment, _ = service_ui
    assert client.get("/ui/equipment").json()["equipment_items"][0]["name"] == "Laptop"
    assert client.post("/ui/equipment", data={"name": "Camera", "description": "HD"}, follow_redirects=False).status_code == 303
    assert equipment[-1]["name"] == "Camera"
    assert client.post("/ui/equipment/2/update", data={"name": "New camera", "description": "HD"}, follow_redirects=False).status_code == 303
    assert equipment[-1]["name"] == "New camera"
    # Until atomic cross-service deletion is implemented, no deletion is permitted.
    response = client.post("/ui/equipment/2/delete", follow_redirects=False)
    assert response.status_code == 303
    assert len(equipment) == 2
    assert "disabled" in response.headers["location"]


def test_loan_forms_and_availability_use_remote_service(service_ui):
    client, _, loans = service_ui
    assert client.post("/ui/loans", data={"equipment_id": "1", "start_date": "2026-12-01", "end_date": "2026-12-05"}, follow_redirects=False).status_code == 303
    assert len(loans) == 1
    assert client.get("/ui/loans").json()["loan_items"][0]["equipment_name"] == "Laptop"
    response = client.get("/ui/availability", params={"start_date": "2026-12-03", "end_date": "2026-12-04"})
    assert response.json()["available_items"] == []
    assert client.post("/ui/loans/1/update", data={"start_date": "2026-12-10", "end_date": "2026-12-12"}, follow_redirects=False).status_code == 303
    assert loans[0]["start_date"] == "2026-12-10"
    assert client.post("/ui/loans/1/cancel", follow_redirects=False).status_code == 303
    assert loans[0]["status"] == "cancelled"
    response = client.get("/ui/availability", params={"start_date": "2026-12-03", "end_date": "2026-12-04"})
    assert response.json()["available_items"][0]["name"] == "Laptop"


def test_dashboard_uses_remote_counts(service_ui):
    client, equipment, loans = service_ui
    loans.append({"id": 1, "equipment_id": 1, "start_date": "2026-12-01", "end_date": "2026-12-05", "status": "active"})
    result = client.get("/").json()
    assert result["equipment_count"] == len(equipment)
    assert result["loan_count"] == 1
    assert result["active_loan_count"] == 1
