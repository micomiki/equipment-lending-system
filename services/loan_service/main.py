
from contextlib import asynccontextmanager
from datetime import date

import httpx
from fastapi import FastAPI, HTTPException

from clients.equipment_client import get_equipment
from services.loan_service.database import db, init_db, rows
from services.loan_service.models import LoanCreate, LoanUpdate


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Loan Microservice",
    version="1.0.0",
    lifespan=lifespan,
)


def valid_dates(start, end):
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Dates must use YYYY-MM-DD format.",
        )

    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="'to' date must be on or after 'from' date.",
        )


def overlap_exists(conn, equipment_id, start, end, exclude_id=None):
    sql = """
        SELECT id FROM loans
        WHERE equipment_id=? AND status='active'
        AND start_date <= ? AND end_date >= ?
    """
    params = [equipment_id, end, start]

    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)

    return conn.execute(sql, params).fetchone() is not None


@app.get("/health")
def health():
    return {"status": "healthy", "service": "loan"}


@app.get("/loans")
def list_loans():
    return rows("SELECT * FROM loans ORDER BY id")


@app.get("/loans/{loan_id}")
def get_loan(loan_id: int):
    result = rows(
        "SELECT * FROM loans WHERE id=?",
        (loan_id,),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Loan {loan_id} not found.",
        )

    return result[0]



@app.post("/loans", status_code=201)
def create_loan(item: LoanCreate):
    valid_dates(item.start_date, item.end_date)

    with db() as conn:
        # Serialize loan creation and deletion coordination.
        conn.execute("BEGIN IMMEDIATE")

        # Block borrowing while equipment deletion is pending.
        guard = conn.execute(
            """
            SELECT status
            FROM equipment_deletion_guards
            WHERE equipment_id=?
            """,
            (item.equipment_id,),
        ).fetchone()

        if guard is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Equipment is unavailable because "
                    "deletion is pending or completed."
                ),
            )

        # Check equipment while holding the transaction lock.
        try:
            equipment = get_equipment(item.equipment_id)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail="Equipment Service unavailable.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail="Equipment Service returned an error.",
            ) from exc

        if equipment is None:
            raise HTTPException(
                status_code=404,
                detail=f"Equipment {item.equipment_id} not found.",
            )

        # Preserve the original inclusive overlap rule.
        if overlap_exists(
            conn,
            item.equipment_id,
            item.start_date,
            item.end_date,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Loan conflicts with an existing "
                    "active loan."
                ),
            )

        cursor = conn.execute(
            """
            INSERT INTO loans(
                equipment_id,
                start_date,
                end_date
            )
            VALUES (?, ?, ?)
            """,
            (
                item.equipment_id,
                item.start_date,
                item.end_date,
            ),
        )

        created = conn.execute(
            "SELECT * FROM loans WHERE id=?",
            (cursor.lastrowid,),
        ).fetchone()

        return dict(created)


@app.patch("/loans/{loan_id}")
def change_loan(loan_id: int, item: LoanUpdate):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")

        loan = conn.execute(
            "SELECT * FROM loans WHERE id=?",
            (loan_id,),
        ).fetchone()

        if loan is None:
            raise HTTPException(
                status_code=404,
                detail=f"Loan {loan_id} not found.",
            )

        if loan["status"] == "cancelled":
            raise HTTPException(
                status_code=409,
                detail="A cancelled loan cannot be changed.",
            )

        start = item.start_date or loan["start_date"]
        end = item.end_date or loan["end_date"]

        valid_dates(start, end)

        if overlap_exists(
            conn,
            loan["equipment_id"],
            start,
            end,
            exclude_id=loan_id,
        ):
            raise HTTPException(
                status_code=409,
                detail="Loan change conflicts with another active loan.",
            )

        conn.execute(
            """
            UPDATE loans
            SET start_date=?, end_date=?
            WHERE id=?
            """,
            (start, end, loan_id),
        )

        return dict(
            conn.execute(
                "SELECT * FROM loans WHERE id=?",
                (loan_id,),
            ).fetchone()
        )


@app.post("/loans/{loan_id}/cancel")
def cancel_loan(loan_id: int):
    with db() as conn:
        cursor = conn.execute(
            "UPDATE loans SET status='cancelled' WHERE id=?",
            (loan_id,),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Loan {loan_id} not found.",
            )

    return {"message": f"Loan {loan_id} cancelled"}


@app.get("/loans/active/equipment/{equipment_id}")
def active_loans_for_equipment(equipment_id: int):
    active = rows(
        """
        SELECT * FROM loans
        WHERE equipment_id=? AND status='active'
        ORDER BY id
        """,
        (equipment_id,),
    )

    return {
        "equipment_id": equipment_id,
        "has_active_loans": bool(active),
        "loans": active,
    }
