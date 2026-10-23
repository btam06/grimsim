from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import ArmyList, Detachment, FactionUnit, Model, Unit, User
from app.schemas import ArmyListIn, ArmyListOut, ListEligibleOut
from app.services.list_building import allies as list_building

router = APIRouter(prefix="/lists", tags=["lists"])


def _to_out(army_list: ArmyList) -> ArmyListOut:
    return ArmyListOut(
        id=army_list.id,
        name=army_list.name,
        points_limit=army_list.points_limit,
        faction_id=army_list.faction_id,
        detachment_ids=[d.id for d in army_list.detachments],
        user_id=army_list.owner.id if army_list.owner else None,
    )


async def _build_owner(session: AsyncSession, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="invalid user_id")
    return user


async def _build_detachments(
    session: AsyncSession, detachment_ids: list[int], faction_id: int
) -> list[Detachment]:
    if not detachment_ids:
        return []
    result = await session.execute(select(Detachment).where(Detachment.id.in_(detachment_ids)))
    detachments = list(result.scalars().all())
    if len(detachments) != len(set(detachment_ids)):
        raise HTTPException(status_code=400, detail="one or more detachment_ids not found")
    if any(d.faction_id != faction_id for d in detachments):
        raise HTTPException(
            status_code=400, detail="detachment does not belong to the selected faction"
        )
    # Detachments sharing a unique tag (e.g. two DYNASTY detachments) can't be
    # taken together.
    tags = [d.unique_tag for d in detachments if d.unique_tag]
    clashing = sorted({tag for tag in tags if tags.count(tag) > 1})
    if clashing:
        raise HTTPException(
            status_code=400,
            detail=f"only one {', '.join(clashing)} detachment can be taken",
        )
    return detachments


@router.get("", response_model=list[ArmyListOut])
async def list_lists(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ArmyList)
        .options(selectinload(ArmyList.detachments), selectinload(ArmyList.owner))
        .order_by(ArmyList.id)
    )
    return [_to_out(army_list) for army_list in result.scalars().all()]


@router.get("/{list_id}/eligible", response_model=ListEligibleOut)
async def eligible_for_list(list_id: int, session: AsyncSession = Depends(get_session)):
    # The faction units and models a unit in this list can use (see
    # app/list_rules.py for ally rules, e.g. Agents of the Imperium).
    context = await list_building.load_list_context(session, list_id, None)
    if context is None:
        raise HTTPException(status_code=404, detail="list not found")
    rules = list_building.active_rules(context.faction, context.detachments)
    faction_units = (await session.execute(select(FactionUnit))).scalars().all()
    models = (
        await session.execute(select(Model).options(selectinload(Model.keywords)))
    ).scalars().all()
    return ListEligibleOut(
        faction_unit_ids=sorted(
            fu.id
            for fu in faction_units
            if list_building.faction_allowed(
                context.faction_names[fu.faction_id], context.faction, rules
            )
        ),
        model_ids=sorted(
            m.id
            for m in models
            if list_building.model_unavailable_reason(
                m, context.faction_names[m.faction_id], context.faction, rules
            )
            is None
        ),
    )


@router.post("", response_model=ArmyListOut, status_code=201)
async def create_list(payload: ArmyListIn, session: AsyncSession = Depends(get_session)):
    detachments = await _build_detachments(session, payload.detachment_ids, payload.faction_id)
    owner = await _build_owner(session, payload.user_id)

    army_list = ArmyList(
        name=payload.name,
        points_limit=payload.points_limit,
        faction_id=payload.faction_id,
        detachments=detachments,
        owner=owner,
    )
    session.add(army_list)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc
    return _to_out(army_list)


@router.put("/{list_id}", response_model=ArmyListOut)
async def update_list(
    list_id: int, payload: ArmyListIn, session: AsyncSession = Depends(get_session)
):
    army_list = (
        await session.execute(
            select(ArmyList)
            .options(selectinload(ArmyList.detachments), selectinload(ArmyList.owner))
            .where(ArmyList.id == list_id)
        )
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=404, detail="list not found")

    detachments = await _build_detachments(session, payload.detachment_ids, payload.faction_id)

    army_list.name = payload.name
    army_list.points_limit = payload.points_limit
    army_list.faction_id = payload.faction_id
    army_list.detachments = detachments
    army_list.owner = await _build_owner(session, payload.user_id)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc
    return _to_out(army_list)


@router.delete("/{list_id}", status_code=204)
async def delete_list(list_id: int, session: AsyncSession = Depends(get_session)):
    army_list = (
        await session.execute(select(ArmyList).where(ArmyList.id == list_id))
    ).scalar_one_or_none()
    if army_list is None:
        raise HTTPException(status_code=404, detail="list not found")

    await session.execute(update(Unit).where(Unit.list_id == list_id).values(list_id=None))
    await session.delete(army_list)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="cannot delete list: it has been used in a game"
        ) from exc
