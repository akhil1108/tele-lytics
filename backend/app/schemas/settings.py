"""Rating-parameter and call-category schemas — the org's stage-2 taxonomy."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RatingParameterCreate(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None
    scale_min: int = 1
    scale_max: int = 5
    sort_order: int = 0


class RatingParameterUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    scale_min: int | None = None
    scale_max: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class RatingParameterOut(ORMModel):
    id: str
    org_id: str
    name: str
    description: str | None = None
    scale_min: int
    scale_max: int
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class CallCategoryCreate(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None
    sort_order: int = 0


class CallCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class CallCategoryOut(ORMModel):
    id: str
    org_id: str
    name: str
    description: str | None = None
    is_active: bool
    is_default: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
