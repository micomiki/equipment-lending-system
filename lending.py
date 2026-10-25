#!/usr/bin/env python3
"""Equipment lending CLI and REST API.

CLI examples:
  python lending.py equipment add --name "Laptop" --description "Dell laptop"
  python lending.py loan create --equipment 1 --from 2026-11-01 --to 2026-11-05
  python lending.py equipment search --from 2026-11-01 --to 2026-11-05

Run the REST API:
  uvicorn lending:app --reload
  Open http://127.0.0.1:8000/docs
"""
import argparse
import os
import sqlite3
from contextlib import contextmanager, asynccontextmanager
from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("LENDING_DB", "lending.db")
app = FastAPI(title="Equipment Lending API", version="1.0.0",
              description="Manage equipment and date-based loans. Loans use inclusive dates.")

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE RESTRICT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled')),
            CHECK(start_date <= end_date)
        );
        """)

def valid_dates(start, end):
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ValueError("Dates must use YYYY-MM-DD format.")
    if e < s:
        raise ValueError("'to' date must be on or after 'from' date.")

def rows(sql, params=()):
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def equipment_exists(equipment_id):
    return bool(rows("SELECT id FROM equipment WHERE id=?", (equipment_id,)))

def overlap_exists(equipment_id, start, end, exclude_id=None):
    sql = """SELECT id FROM loans
             WHERE equipment_id=? AND status='active'
             AND start_date <= ? AND end_date >= ?"""
    params = [equipment_id, end, start]
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    return bool(rows(sql, params))

def add_equipment(name, description):
    if not name.strip():
        raise ValueError("Equipment name cannot be empty.")
    with db() as conn:
        cur = conn.execute("INSERT INTO equipment(name,description) VALUES (?,?)",
                           (name.strip(), description.strip()))
        return dict(conn.execute("SELECT * FROM equipment WHERE id=?", (cur.lastrowid,)).fetchone())

def update_equipment(equipment_id, name=None, description=None):
    if not equipment_exists(equipment_id):
        raise ValueError(f"Equipment {equipment_id} not found.")
    fields, values = [], []
    if name is not None:
        if not name.strip():
            raise ValueError("Equipment name cannot be empty.")
        fields.append("name=?"); values.append(name.strip())
    if description is not None:
        fields.append("description=?"); values.append(description.strip())
    if fields:
        values.append(equipment_id)
        with db() as conn:
            conn.execute(f"UPDATE equipment SET {', '.join(fields)} WHERE id=?", values)
    return rows("SELECT * FROM equipment WHERE id=?", (equipment_id,))[0]

def remove_equipment(equipment_id):
    if not equipment_exists(equipment_id):
        raise ValueError(f"Equipment {equipment_id} not found.")

    # Check whether the equipment has any active loans.
    active_loans = rows(
        "SELECT id FROM loans "
        "WHERE equipment_id = ? AND status = 'active'",
        (equipment_id,)
    )

    if active_loans:
        raise ValueError(
            "Cannot remove equipment because it has active loans. "
            "Cancel all active loans first."
        )

    # Delete cancelled loan records before deleting the equipment.
    with db() as conn:
        conn.execute(
            "DELETE FROM loans "
            "WHERE equipment_id = ? AND status != 'active'",
            (equipment_id,)
        )

        conn.execute(
            "DELETE FROM equipment WHERE id = ?",
            (equipment_id,)
        )
def create_loan(equipment_id, start, end):
    valid_dates(start, end)

    if not equipment_exists(equipment_id):
        raise ValueError(f"Equipment {equipment_id} not found.")

    if overlap_exists(equipment_id, start, end):
        raise ValueError(
            "Loan conflicts with an existing active loan for this equipment."
        )

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO loans(equipment_id, start_date, end_date)
               VALUES (?, ?, ?)""",
            (equipment_id, start, end)
        )

        loan = conn.execute(
            "SELECT * FROM loans WHERE id = ?",
            (cur.lastrowid,)
        ).fetchone()

        return dict(loan)


def change_loan(loan_id, start=None, end=None):
    found = rows("SELECT * FROM loans WHERE id=?", (loan_id,))
    if not found:
        raise ValueError(f"Loan {loan_id} not found.")
    loan = found[0]
    if loan["status"] == "cancelled":
        raise ValueError("A cancelled loan cannot be changed.")
    new_start = start or loan["start_date"]
    new_end = end or loan["end_date"]
    valid_dates(new_start, new_end)
    if overlap_exists(loan["equipment_id"], new_start, new_end, exclude_id=loan_id):
        raise ValueError("Loan change conflicts with another active loan.")
    with db() as conn:
        conn.execute("UPDATE loans SET start_date=?, end_date=? WHERE id=?",
                     (new_start, new_end, loan_id))
    return rows("SELECT * FROM loans WHERE id=?", (loan_id,))[0]

def cancel_loan(loan_id):
    found = rows("SELECT id FROM loans WHERE id=?", (loan_id,))
    if not found:
        raise ValueError(f"Loan {loan_id} not found.")
    with db() as conn:
        conn.execute("UPDATE loans SET status='cancelled' WHERE id=?", (loan_id,))

def search_equipment(start, end):
    valid_dates(start, end)
    return rows("""SELECT e.* FROM equipment e
                   WHERE NOT EXISTS (
                     SELECT 1 FROM loans l
                     WHERE l.equipment_id=e.id AND l.status='active'
                       AND l.start_date <= ? AND l.end_date >= ?
                   ) ORDER BY e.id""", (end, start))

# REST API request models
class EquipmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""

class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None

class LoanCreate(BaseModel):
    equipment_id: int = Field(gt=0)
    start_date: str
    end_date: str

class LoanUpdate(BaseModel):
    start_date: str | None = None
    end_date: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Equipment Lending API",
    version="1.0.0",
    description="Manage equipment and date-based loans. Loans use inclusive dates.",
    lifespan=lifespan
)

def api_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 409 if ("conflict" in message.lower() or "active loans" in message.lower() or "cancelled" in message.lower()) else 400
        raise HTTPException(status_code=status, detail=message)

@app.get("/")
def root():
    return {"message": "Equipment Lending API", "docs": "/docs"}

@app.get("/equipment")
def api_list_equipment():
    return rows("SELECT * FROM equipment ORDER BY id")

@app.post("/equipment", status_code=201)
def api_add_equipment(item: EquipmentCreate):
    return api_call(add_equipment, item.name, item.description)

@app.patch("/equipment/{equipment_id}")
def api_update_equipment(equipment_id: int, item: EquipmentUpdate):
    return api_call(update_equipment, equipment_id, item.name, item.description)

@app.delete("/equipment/{equipment_id}", status_code=204)
def api_remove_equipment(equipment_id: int):
    api_call(remove_equipment, equipment_id)
    return None

@app.get("/loans")
def api_list_loans():
    return rows("""SELECT l.*, e.name AS equipment_name FROM loans l
                   JOIN equipment e ON e.id=l.equipment_id ORDER BY l.id""")

@app.post("/loans", status_code=201)
def api_create_loan(item: LoanCreate):
    return api_call(create_loan, item.equipment_id, item.start_date, item.end_date)

@app.patch("/loans/{loan_id}")
def api_change_loan(loan_id: int, item: LoanUpdate):
    return api_call(change_loan, loan_id, item.start_date, item.end_date)

@app.post("/loans/{loan_id}/cancel")
def api_cancel_loan(loan_id: int):
    api_call(cancel_loan, loan_id)
    return {"message": f"Loan {loan_id} cancelled"}

@app.get("/equipment/search")
def api_search_equipment(start_date: str, end_date: str):
    return api_call(search_equipment, start_date, end_date)

def print_items(items):
    if not items:
        print("No records found.")
        return
    for item in items:
        print(" | ".join(f"{key}: {value}" for key, value in item.items()))

def build_parser():
    help_text = """Usage: lending.py COMMAND [OPTIONS]

Commands:
  equipment list
  equipment add --name NAME --description TEXT
  equipment update ID [--name NAME] [--description TEXT]
  equipment remove ID
  equipment search --from DATE --to DATE

  loan list
  loan create --equipment ID --from DATE --to DATE
  loan change ID [--from DATE] [--to DATE]
  loan cancel ID

Options:
  -h, --help    Show this help message

Examples:
  python lending.py equipment add --name "Laptop" --description "Dell Laptop"
  python lending.py equipment list
  python lending.py loan create --equipment 1 --from 2026-11-01 --to 2026-11-05
  python lending.py loan list
  python lending.py equipment search --from 2026-11-01 --to 2026-11-05
"""

    parser = argparse.ArgumentParser(
        description="Equipment lending management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_text
    )

    sub = parser.add_subparsers(dest="entity", required=True)

    equipment = sub.add_parser("equipment", help="Manage equipment")
    es = equipment.add_subparsers(dest="action", required=True)

    es.add_parser("list", help="List all equipment")

    p = es.add_parser("add", help="Add equipment")
    p.add_argument("--name", required=True)
    p.add_argument("--description", required=True)

    p = es.add_parser("update", help="Update equipment")
    p.add_argument("id", type=int)
    p.add_argument("--name")
    p.add_argument("--description")

    p = es.add_parser("remove", help="Remove equipment")
    p.add_argument("id", type=int)

    p = es.add_parser("search", help="Search available equipment")
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)

    loan = sub.add_parser("loan", help="Manage loans")
    ls = loan.add_subparsers(dest="action", required=True)

    ls.add_parser("list", help="List all loans")

    p = ls.add_parser("create", help="Create a loan")
    p.add_argument("--equipment", type=int, required=True)
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)

    p = ls.add_parser("change", help="Change loan dates")
    p.add_argument("id", type=int)
    p.add_argument("--from", dest="start")
    p.add_argument("--to", dest="end")

    p = ls.add_parser("cancel", help="Cancel a loan")
    p.add_argument("id", type=int)

    return parser

def main():
    init_db()
    args = build_parser().parse_args()
    try:
        if args.entity == "equipment":
            if args.action == "list": print_items(rows("SELECT * FROM equipment ORDER BY id"))
            elif args.action == "add": print_items([add_equipment(args.name, args.description)])
            elif args.action == "update": print_items([update_equipment(args.id, args.name, args.description)])
            elif args.action == "remove": remove_equipment(args.id); print(f"Equipment {args.id} removed.")
            elif args.action == "search": print_items(search_equipment(args.start, args.end))
        else:
            if args.action == "list":
                print_items(rows("""SELECT l.*, e.name AS equipment_name FROM loans l
                                    JOIN equipment e ON e.id=l.equipment_id ORDER BY l.id"""))
            elif args.action == "create": print_items([create_loan(args.equipment, args.start, args.end)])
            elif args.action == "change": print_items([change_loan(args.id, args.start, args.end)])
            elif args.action == "cancel": cancel_loan(args.id); print(f"Loan {args.id} cancelled.")
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}")

if __name__ == "__main__":
    main()
