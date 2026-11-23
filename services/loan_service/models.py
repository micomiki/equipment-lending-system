
from pydantic import BaseModel, Field


class LoanCreate(BaseModel):
    equipment_id: int = Field(gt=0)
    start_date: str
    end_date: str


class LoanUpdate(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
