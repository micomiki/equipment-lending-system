
from pydantic import BaseModel, Field


class EquipmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class EquipmentUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    description: str | None = None
