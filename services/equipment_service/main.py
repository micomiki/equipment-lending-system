
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from services.equipment_service.database import db, init_db, rows
from services.equipment_service.models import EquipmentCreate, EquipmentUpdate


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Equipment Microservice",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "equipment"}


@app.get("/equipment")
def list_equipment():
    return rows("SELECT * FROM equipment ORDER BY id")


@app.get("/equipment/{equipment_id}")
def get_equipment(equipment_id: int):
    result = rows(
        "SELECT * FROM equipment WHERE id=?",
        (equipment_id,),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Equipment not found",
        )

    return result[0]


@app.post("/equipment", status_code=201)
def add_equipment(item: EquipmentCreate):
    if not item.name.strip():
        raise HTTPException(
            status_code=400,
            detail="Equipment name cannot be empty",
        )

    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO equipment(name, description) VALUES (?, ?)",
            (item.name.strip(), item.description.strip()),
        )

        result = conn.execute(
            "SELECT * FROM equipment WHERE id=?",
            (cursor.lastrowid,),
        ).fetchone()

        return dict(result)


@app.patch("/equipment/{equipment_id}")
def update_equipment(equipment_id: int, item: EquipmentUpdate):
    existing = get_equipment(equipment_id)

    name = item.name if item.name is not None else existing["name"]
    description = (
        item.description
        if item.description is not None
        else existing["description"]
    )

    if not name.strip():
        raise HTTPException(
            status_code=400,
            detail="Equipment name cannot be empty",
        )

    with db() as conn:
        conn.execute(
            """
            UPDATE equipment
            SET name=?, description=?
            WHERE id=?
            """,
            (name.strip(), description.strip(), equipment_id),
        )

    return get_equipment(equipment_id)
