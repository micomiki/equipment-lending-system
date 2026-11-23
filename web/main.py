"""FastAPI web frontend backed exclusively by the equipment and loan microservices."""

from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from clients.equipment_client import (
    create_equipment as service_create_equipment,
)
from clients.equipment_client import (
    get_equipment,
)
from clients.equipment_client import (
    list_equipment as service_list_equipment,
)
from clients.equipment_client import (
    update_equipment as service_update_equipment,
)
from clients.loan_client import (
    cancel_loan as service_cancel_loan,
)
from clients.loan_client import (
    create_loan as service_create_loan,
)
from clients.loan_client import (
    get_loan as service_get_loan,
)
from clients.loan_client import (
    list_loans as service_list_loans,
)
from clients.loan_client import (
    update_loan as service_update_loan,
)

app = FastAPI(title="Equipment Lending Web Frontend", version="1.0.0")
PROJECT_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(PROJECT_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")


def valid_dates(start, end):
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    if end_date < start_date:
        raise ValueError("'to' date must be on or after 'from' date.")


class ServiceFormError(ValueError):
    """An error reported by a remote service, safe to show in a form."""


def _remote(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Microservice unavailable") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (400, 404, 409, 422):
            try:
                detail = exc.response.json().get("detail", "Request rejected")
            except ValueError:
                detail = "Request rejected"
            if isinstance(detail, list):
                detail = "Invalid form data"
            raise ServiceFormError(str(detail)) from exc
        raise HTTPException(status_code=502, detail="Microservice error") from exc


def _equipment_items():
    return _remote(service_list_equipment)


def _loan_items():
    equipment = {item["id"]: item["name"] for item in _equipment_items()}
    loans = _remote(service_list_loans)
    return [
        {**loan, "equipment_name": equipment.get(loan["equipment_id"], "Unknown equipment")}
        for loan in sorted(loans, key=lambda item: item["id"], reverse=True)
    ]


def _equipment_by_id(equipment_id):
    return _remote(get_equipment, equipment_id)


def _loan_by_id(loan_id):
    loan = _remote(service_get_loan, loan_id)
    if loan is None:
        return None
    equipment = _equipment_by_id(loan["equipment_id"])
    return {**loan, "equipment_name": equipment["name"] if equipment else "Unknown equipment"}


def _available_equipment(start, end):
    valid_dates(start, end)
    equipment = _equipment_items()
    loans = _remote(service_list_loans)
    blocked = {
        loan["equipment_id"]
        for loan in loans
        if loan["status"] == "active"
        and loan["start_date"] <= end
        and loan["end_date"] >= start
    }
    return [item for item in equipment if item["id"] not in blocked]


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
    equipment_items = _equipment_items()
    loan_items = _loan_items()
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
            "equipment_items": _equipment_items(),
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
        _remote(service_create_equipment, name, description)
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
    equipment = _equipment_by_id(equipment_id)
    if equipment is None:
        return _ui_redirect("/ui/equipment", f"Equipment {equipment_id} not found.", "error")
    return _render(
        request,
        "equipment_form.html",
        {
            "request": request,
            "equipment": equipment,
            "error": None,
            "values": equipment,
        },
    )

@app.get("/microservices/loans")
def microservice_loans():
    try:
        return service_list_loans()

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Loan Microservice unavailable",
        )

    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="Loan Microservice returned an error",
        )
    
@app.post("/ui/equipment/{equipment_id}/update", include_in_schema=False)
async def web_equipment_update(request: Request, equipment_id: int):
    form = await request.form()
    name = str(form.get("name", ""))
    description = str(form.get("description", ""))
    try:
        _remote(service_update_equipment, equipment_id, name=name, description=description)
        return _ui_redirect("/ui/equipment", "Equipment updated successfully.")
    except ValueError as exc:
        equipment = _equipment_by_id(equipment_id)
        return _render(
            request,
            "equipment_form.html",
            {
                "request": request,
                "equipment": equipment if equipment else {"id": equipment_id},
                "error": str(exc),
                "values": {"name": name, "description": description},
            },
            status_code=400,
        )


@app.post("/ui/equipment/{equipment_id}/delete", include_in_schema=False)
def web_equipment_delete(equipment_id: int):
    # Deletion requires an atomic cross-service protocol; not safe yet.
    return _ui_redirect(
        "/ui/equipment",
        "Deletion is disabled until atomic loan protection is implemented.",
        "error",
    )


@app.get("/ui/loans", response_class=HTMLResponse, include_in_schema=False)
def web_loans(
    request: Request,
    message: str | None = None,
    level: str = "success",
):
    loan_items = _loan_items()
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
            "equipment_items": sorted(_equipment_items(), key=lambda e: e["name"]),
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
        _remote(service_create_loan, equipment_id, start, end)
        return _ui_redirect("/ui/loans", "Loan created successfully.")
    except (ValueError, TypeError) as exc:
        message = str(exc) or "Select a valid equipment item."
        return _render(
            request,
            "loan_form.html",
            {
                "request": request,
                "loan": None,
                "equipment_items": sorted(_equipment_items(), key=lambda e: e["name"]),
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
    loan = _loan_by_id(loan_id)
    if loan is None:
        return _ui_redirect("/ui/loans", f"Loan {loan_id} not found.", "error")
    return _render(
        request,
        "loan_form.html",
        {
            "request": request,
            "loan": loan,
            "equipment_items": sorted(_equipment_items(), key=lambda e: e["name"]),
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
        _remote(service_update_loan, loan_id, start_date=start, end_date=end)
        return _ui_redirect("/ui/loans", "Loan dates updated successfully.")
    except ValueError as exc:
        loan = _loan_by_id(loan_id)
        return _render(
            request,
            "loan_form.html",
            {
                "request": request,
                "loan": loan if loan else {"id": loan_id},
                "equipment_items": sorted(_equipment_items(), key=lambda e: e["name"]),
                "error": str(exc),
                "values": {
                    "equipment_id": str(loan["equipment_id"]) if loan else "",
                    "start_date": start,
                    "end_date": end,
                },
            },
            status_code=400,
        )


@app.post("/ui/loans/{loan_id}/cancel", include_in_schema=False)
def web_loan_cancel(loan_id: int):
    try:
        _remote(service_cancel_loan, loan_id)
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
            available_items = _available_equipment(start_date, end_date)
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

@app.get("/microservices/equipment/{equipment_id}")
def microservice_equipment(equipment_id: int):
    try:
        equipment = get_equipment(equipment_id)
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Equipment Service unavailable",
        )
    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="Equipment Service returned an error",
        )

    if equipment is None:
        raise HTTPException(
            status_code=404,
            detail="Equipment not found",
        )

    return equipment

