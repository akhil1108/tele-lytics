"""Rating-parameter and call-category management — the org's stage-2 taxonomy.

Both are read by every analysis run (`app/services/pipeline.py`) and edited
here by admins; staff can list them read-only to build filters and legends.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin, require_staff
from app.core.errors import BadRequest, Conflict, NotFound
from app.db.models import CallCategory, RatingParameter, User
from app.db.session import get_session
from app.schemas.common import Ack
from app.schemas.settings import (
    CallCategoryCreate,
    CallCategoryOut,
    CallCategoryUpdate,
    RatingParameterCreate,
    RatingParameterOut,
    RatingParameterUpdate,
)

rating_parameters_router = APIRouter(prefix="/rating-parameters", tags=["settings"])
call_categories_router = APIRouter(prefix="/call-categories", tags=["settings"])


# --------------------------------------------------------- rating parameters


@rating_parameters_router.get("", response_model=list[RatingParameterOut])
async def list_rating_parameters(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False,
) -> list[RatingParameterOut]:
    filters = [RatingParameter.org_id == user.org_id]
    if not include_inactive:
        filters.append(RatingParameter.is_active.is_(True))
    rows = (
        await session.execute(
            select(RatingParameter).where(*filters).order_by(RatingParameter.sort_order)
        )
    ).scalars().all()
    return [RatingParameterOut.model_validate(row) for row in rows]


@rating_parameters_router.post("", response_model=RatingParameterOut, status_code=201)
async def create_rating_parameter(
    payload: RatingParameterCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RatingParameterOut:
    if payload.scale_min >= payload.scale_max:
        raise BadRequest("scale_min must be less than scale_max")
    existing = (
        await session.execute(
            select(RatingParameter.id).where(
                RatingParameter.org_id == admin.org_id, RatingParameter.name == payload.name
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"A rating parameter named '{payload.name}' already exists")

    parameter = RatingParameter(
        org_id=admin.org_id, created_by_user_id=admin.id, **payload.model_dump()
    )
    session.add(parameter)
    await session.commit()
    return RatingParameterOut.model_validate(parameter)


@rating_parameters_router.patch("/{parameter_id}", response_model=RatingParameterOut)
async def update_rating_parameter(
    parameter_id: str,
    payload: RatingParameterUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RatingParameterOut:
    parameter = await session.get(RatingParameter, parameter_id)
    if parameter is None or parameter.org_id != admin.org_id:
        raise NotFound("Rating parameter")

    changes = payload.model_dump(exclude_unset=True)
    scale_min = changes.get("scale_min", parameter.scale_min)
    scale_max = changes.get("scale_max", parameter.scale_max)
    if scale_min >= scale_max:
        raise BadRequest("scale_min must be less than scale_max")
    for field, value in changes.items():
        setattr(parameter, field, value)

    await session.commit()
    return RatingParameterOut.model_validate(parameter)


@rating_parameters_router.delete("/{parameter_id}", response_model=Ack)
async def delete_rating_parameter(
    parameter_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    parameter = await session.get(RatingParameter, parameter_id)
    if parameter is None or parameter.org_id != admin.org_id:
        raise NotFound("Rating parameter")

    # Past scores are snapshotted onto Analysis.custom_ratings, so removing the
    # parameter row itself does not touch call history.
    name = parameter.name
    await session.delete(parameter)
    await session.commit()
    return Ack(message=f"Removed rating parameter '{name}'")


# --------------------------------------------------------------- categories


@call_categories_router.get("", response_model=list[CallCategoryOut])
async def list_call_categories(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False,
) -> list[CallCategoryOut]:
    filters = [CallCategory.org_id == user.org_id]
    if not include_inactive:
        filters.append(CallCategory.is_active.is_(True))
    rows = (
        await session.execute(
            select(CallCategory).where(*filters).order_by(CallCategory.sort_order)
        )
    ).scalars().all()
    return [CallCategoryOut.model_validate(row) for row in rows]


@call_categories_router.post("", response_model=CallCategoryOut, status_code=201)
async def create_call_category(
    payload: CallCategoryCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CallCategoryOut:
    existing = (
        await session.execute(
            select(CallCategory.id).where(
                CallCategory.org_id == admin.org_id, CallCategory.name == payload.name
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"A category named '{payload.name}' already exists")

    category = CallCategory(
        org_id=admin.org_id, created_by_user_id=admin.id, **payload.model_dump()
    )
    session.add(category)
    await session.commit()
    return CallCategoryOut.model_validate(category)


@call_categories_router.patch("/{category_id}", response_model=CallCategoryOut)
async def update_call_category(
    category_id: str,
    payload: CallCategoryUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CallCategoryOut:
    category = await session.get(CallCategory, category_id)
    if category is None or category.org_id != admin.org_id:
        raise NotFound("Call category")
    if category.is_default and payload.is_active is False:
        raise BadRequest("The default category cannot be deactivated")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)

    await session.commit()
    return CallCategoryOut.model_validate(category)


@call_categories_router.delete("/{category_id}", response_model=Ack)
async def delete_call_category(
    category_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    category = await session.get(CallCategory, category_id)
    if category is None or category.org_id != admin.org_id:
        raise NotFound("Call category")
    if category.is_default:
        # The pipeline resolves an unmatched model answer to this category —
        # removing it would leave nothing for that fallback to land on.
        raise BadRequest("The default category cannot be deleted")

    name = category.name
    await session.delete(category)
    await session.commit()
    return Ack(message=f"Removed category '{name}'")
