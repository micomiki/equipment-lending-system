
import os

import httpx

EQUIPMENT_SERVICE_URL = os.getenv(
    "EQUIPMENT_SERVICE_URL",
    "http://127.0.0.1:8001",
)


def get_equipment(equipment_id: int):
    with httpx.Client(timeout=5.0) as client:
        response = client.get(
            f"{EQUIPMENT_SERVICE_URL}/equipment/{equipment_id}"
        )

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()


def list_equipment():
    with httpx.Client(timeout=5.0) as client:
        response = client.get(
            f"{EQUIPMENT_SERVICE_URL}/equipment"
        )

    response.raise_for_status()
    return response.json()


def create_equipment(name: str, description: str = ""):
    with httpx.Client(timeout=5.0) as client:
        response = client.post(
            f"{EQUIPMENT_SERVICE_URL}/equipment",
            json={
                "name": name,
                "description": description,
            },
        )

    response.raise_for_status()
    return response.json()


def update_equipment(equipment_id: int, **changes):
    with httpx.Client(timeout=5.0) as client:
        response = client.patch(
            f"{EQUIPMENT_SERVICE_URL}/equipment/{equipment_id}",
            json=changes,
        )

    response.raise_for_status()
    return response.json()
