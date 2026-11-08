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
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("LENDING_DB", "lending.db")
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database when the application starts."""
    init_db()
    yield


app = FastAPI(
    title="Equipment Lending API",
    version="1.0.0",
    description="Manage equipment and date-based loans. Loans use inclusive dates.",
    lifespan=lifespan,
)

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
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
    return False

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
    if rows("SELECT id FROM loans WHERE equipment_id=? AND status='active'", (equipment_id,)):
        raise ValueError("Cannot remove equipment with active loans. Cancel its loans first.")
    with db() as conn:
        conn.execute("DELETE FROM equipment WHERE id=?", (equipment_id,))

def create_loan(equipment_id, start, end):
    valid_dates(start, end)
    if not equipment_exists(equipment_id):
        raise ValueError(f"Equipment {equipment_id} not found.")
    if overlap_exists(equipment_id, start, end):
        raise ValueError("Loan conflicts with an existing active loan for this equipment.")
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO loans(equipment_id,start_date,end_date)
               VALUES (?,?,?)""",
            (equipment_id, start, end),
        )
        created = conn.execute(
            "SELECT * FROM loans WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return dict(created)

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

def api_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 409 if ("conflict" in message.lower() or "active loans" in message.lower() or "cancelled" in message.lower()) else 400
        raise HTTPException(status_code=status, detail=message)

# The browser-based application is available at /.
# The JSON API remains available through the resource endpoints (/equipment, /loans).
@app.get("/api", tags=["system"])
def api_root():
    """Return API information."""
    return {"message": "Equipment Lending API", "docs": "/docs", "web_app": "/"}

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



# ---------------------------------------------------------------------------
# Browser-based web application (HTML forms)
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PROJECT_DIR / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_DIR / "static")),
    name="static",
)


def _ui_redirect(path: str, message: str, level: str = "success"):
    """Redirect after a successful or failed form submission."""
    separator = "&" if "?" in path else "?"
    query = urlencode({"message": message, "level": level})
    return RedirectResponse(url=f"{path}{separator}{query}", status_code=303)


def _render(request: Request, template: str, context: dict, status_code: int = 200):
    """Render an HTML page with the common request context."""
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=context,
        status_code=status_code,
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def web_home(
    request: Request,
    message: str | None = None,
    level: str = "success",
):
    equipment_items = rows("SELECT * FROM equipment ORDER BY id")
    loan_items = rows(
        """SELECT l.*, e.name AS equipment_name
           FROM loans l JOIN equipment e ON e.id=l.equipment_id
           ORDER BY l.id DESC"""
    )
    active_loans = [loan for loan in loan_items if loan["status"] == "active"]
    return _render(
        request,
        "index.html",
        {
            "request": request,
            "equipment_count": len(equipment_items),
            "loan_count": len(loan_items),
            "active_loan_count": len(active_loans),
            "recent_loans": loan_items[:5],
            "message": message,
            "level": level,
        },
    )


@app.get("/ui/equipment", response_class=HTMLResponse, include_in_schema=False)
def web_equipment(
    request: Request,
    message: str | None = None,
    level: str = "success",
):
    return _render(
        request,
        "equipment.html",
        {
            "request": request,
            "equipment_items": rows("SELECT * FROM equipment ORDER BY id"),
            "message": message,
            "level": level,
        },
    )


@app.get(
    "/ui/equipment/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def web_equipment_new(request: Request):
    return _render(
        request,
        "equipment_form.html",
        {
            "request": request,
            "equipment": None,
            "error": None,
            "values": {"name": "", "description": ""},
        },
    )


@app.post("/ui/equipment", include_in_schema=False)
async def web_equipment_create(request: Request):
    form = await request.form()
    name = str(form.get("name", ""))
    description = str(form.get("description", ""))
    try:
        add_equipment(name, description)
        return _ui_redirect("/ui/equipment", "Equipment added successfully.")
    except ValueError as exc:
        return _render(
            request,
            "equipment_form.html",
            {
                "request": request,
                "equipment": None,
                "error": str(exc),
                "values": {"name": name, "description": description},
            },
            status_code=400,
        )


@app.get(
    "/ui/equipment/{equipment_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def web_equipment_edit(request: Request, equipment_id: int):
    found = rows("SELECT * FROM equipment WHERE id=?", (equipment_id,))
    if not found:
        return _ui_redirect("/ui/equipment", f"Equipment {equipment_id} not found.", "error")
    return _render(
        request,
        "equipment_form.html",
        {
            "request": request,
            "equipment": found[0],
            "error": None,
            "values": found[0],
        },
    )


@app.post("/ui/equipment/{equipment_id}/update", include_in_schema=False)
async def web_equipment_update(request: Request, equipment_id: int):
    form = await request.form()
    name = str(form.get("name", ""))
    description = str(form.get("description", ""))
    try:
        update_equipment(equipment_id, name=name, description=description)
        return _ui_redirect("/ui/equipment", "Equipment updated successfully.")
    except ValueError as exc:
        found = rows("SELECT * FROM equipment WHERE id=?", (equipment_id,))
        return _render(
            request,
            "equipment_form.html",
            {
                "request": request,
                "equipment": found[0] if found else {"id": equipment_id},
                "error": str(exc),
                "values": {"name": name, "description": description},
            },
            status_code=400,
        )


@app.post("/ui/equipment/{equipment_id}/delete", include_in_schema=False)
def web_equipment_delete(equipment_id: int):
    try:
        remove_equipment(equipment_id)
        return _ui_redirect("/ui/equipment", "Equipment removed successfully.")
    except ValueError as exc:
        return _ui_redirect("/ui/equipment", str(exc), "error")


@app.get("/ui/loans", response_class=HTMLResponse, include_in_schema=False)
def web_loans(
    request: Request,
    message: str | None = None,
    level: str = "success",
):
    loan_items = rows(
        """SELECT l.*, e.name AS equipment_name
           FROM loans l JOIN equipment e ON e.id=l.equipment_id
           ORDER BY l.id DESC"""
    )
    return _render(
        request,
        "loans.html",
        {
            "request": request,
            "loan_items": loan_items,
            "message": message,
            "level": level,
        },
    )


@app.get("/ui/loans/new", response_class=HTMLResponse, include_in_schema=False)
def web_loan_new(request: Request):
    return _render(
        request,
        "loan_form.html",
        {
            "request": request,
            "loan": None,
            "equipment_items": rows("SELECT * FROM equipment ORDER BY name"),
            "error": None,
            "values": {"equipment_id": "", "start_date": "", "end_date": ""},
        },
    )


@app.post("/ui/loans", include_in_schema=False)
async def web_loan_create(request: Request):
    form = await request.form()
    equipment_value = str(form.get("equipment_id", ""))
    start = str(form.get("start_date", ""))
    end = str(form.get("end_date", ""))
    values = {
        "equipment_id": equipment_value,
        "start_date": start,
        "end_date": end,
    }
    try:
        equipment_id = int(equipment_value)
        create_loan(equipment_id, start, end)
        return _ui_redirect("/ui/loans", "Loan created successfully.")
    except (ValueError, TypeError) as exc:
        message = str(exc) or "Select a valid equipment item."
        return _render(
            request,
            "loan_form.html",
            {
                "request": request,
                "loan": None,
                "equipment_items": rows("SELECT * FROM equipment ORDER BY name"),
                "error": message,
                "values": values,
            },
            status_code=400,
        )


@app.get(
    "/ui/loans/{loan_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def web_loan_edit(request: Request, loan_id: int):
    found = rows(
        """SELECT l.*, e.name AS equipment_name
           FROM loans l JOIN equipment e ON e.id=l.equipment_id
           WHERE l.id=?""",
        (loan_id,),
    )
    if not found:
        return _ui_redirect("/ui/loans", f"Loan {loan_id} not found.", "error")
    loan = found[0]
    return _render(
        request,
        "loan_form.html",
        {
            "request": request,
            "loan": loan,
            "equipment_items": rows("SELECT * FROM equipment ORDER BY name"),
            "error": None,
            "values": {
                "equipment_id": str(loan["equipment_id"]),
                "start_date": loan["start_date"],
                "end_date": loan["end_date"],
            },
        },
    )


@app.post("/ui/loans/{loan_id}/update", include_in_schema=False)
async def web_loan_update(request: Request, loan_id: int):
    form = await request.form()
    start = str(form.get("start_date", ""))
    end = str(form.get("end_date", ""))
    try:
        change_loan(loan_id, start=start, end=end)
        return _ui_redirect("/ui/loans", "Loan dates updated successfully.")
    except ValueError as exc:
        found = rows(
            """SELECT l.*, e.name AS equipment_name
               FROM loans l JOIN equipment e ON e.id=l.equipment_id
               WHERE l.id=?""",
            (loan_id,),
        )
        return _render(
            request,
            "loan_form.html",
            {
                "request": request,
                "loan": found[0] if found else {"id": loan_id},
                "equipment_items": rows("SELECT * FROM equipment ORDER BY name"),
                "error": str(exc),
                "values": {
                    "equipment_id": str(found[0]["equipment_id"]) if found else "",
                    "start_date": start,
                    "end_date": end,
                },
            },
            status_code=400,
        )


@app.post("/ui/loans/{loan_id}/cancel", include_in_schema=False)
def web_loan_cancel(loan_id: int):
    try:
        cancel_loan(loan_id)
        return _ui_redirect("/ui/loans", "Loan cancelled successfully.")
    except ValueError as exc:
        return _ui_redirect("/ui/loans", str(exc), "error")


@app.get("/ui/availability", response_class=HTMLResponse, include_in_schema=False)
def web_availability(
    request: Request,
    start_date: str | None = None,
    end_date: str | None = None,
):
    available_items = None
    error = None
    if start_date or end_date:
        try:
            if not start_date or not end_date:
                raise ValueError("Enter both a start date and an end date.")
            available_items = search_equipment(start_date, end_date)
        except ValueError as exc:
            error = str(exc)
    return _render(
        request,
        "availability.html",
        {
            "request": request,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "available_items": available_items,
            "error": error,
        },
    )


def print_items(items):
    if not items:
        print("No records found.")
        return
    for item in items:
        print(" | ".join(f"{key}: {value}" for key, value in item.items()))

def build_parser():
    parser = argparse.ArgumentParser(description="Equipment lending management")
    sub = parser.add_subparsers(dest="entity", required=True)
    equipment = sub.add_parser("equipment", help="Manage equipment")
    es = equipment.add_subparsers(dest="action", required=True)
    es.add_parser("list")
    p = es.add_parser("add"); p.add_argument("--name", required=True); p.add_argument("--description", required=True)
    p = es.add_parser("update"); p.add_argument("id", type=int); p.add_argument("--name"); p.add_argument("--description")
    p = es.add_parser("remove"); p.add_argument("id", type=int)
    p = es.add_parser("search"); p.add_argument("--from", dest="start", required=True); p.add_argument("--to", dest="end", required=True)
    loan = sub.add_parser("loan", help="Manage loans")
    ls = loan.add_subparsers(dest="action", required=True)
    ls.add_parser("list")
    p = ls.add_parser("create"); p.add_argument("--equipment", type=int, required=True); p.add_argument("--from", dest="start", required=True); p.add_argument("--to", dest="end", required=True)
    p = ls.add_parser("change"); p.add_argument("id", type=int); p.add_argument("--from", dest="start"); p.add_argument("--to", dest="end")
    p = ls.add_parser("cancel"); p.add_argument("id", type=int)
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
