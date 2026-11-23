
import os

import httpx

LOAN_SERVICE_URL = os.getenv(
    "LOAN_SERVICE_URL",
    "http://127.0.0.1:8002",
)


def list_loans():
    with httpx.Client(timeout=5.0) as client:
        response = client.get(f"{LOAN_SERVICE_URL}/loans")
        response.raise_for_status()
        return response.json()


def get_loan(loan_id: int):
    with httpx.Client(timeout=5.0) as client:
        response = client.get(f"{LOAN_SERVICE_URL}/loans/{loan_id}")

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()


def create_loan(equipment_id: int, start_date: str, end_date: str):
    with httpx.Client(timeout=5.0) as client:
        response = client.post(
            f"{LOAN_SERVICE_URL}/loans",
            json={
                "equipment_id": equipment_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        response.raise_for_status()
        return response.json()


def update_loan(loan_id: int, **changes):
    with httpx.Client(timeout=5.0) as client:
        response = client.patch(
            f"{LOAN_SERVICE_URL}/loans/{loan_id}",
            json=changes,
        )
        response.raise_for_status()
        return response.json()


def cancel_loan(loan_id: int):
    with httpx.Client(timeout=5.0) as client:
        response = client.post(
            f"{LOAN_SERVICE_URL}/loans/{loan_id}/cancel"
        )
        response.raise_for_status()
        return response.json()
