from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Faction, FactionAbility
from app.schemas import FactionAbilityIn, FactionAbilityOut
from app.seeds import factions as faction_seeds

router = APIRouter(prefix="/faction-abilities", tags=["faction-abilities"])


def _to_out(faction_ability: FactionAbility, faction_name: str) -> FactionAbilityOut:
    return FactionAbilityOut(
        id=faction_ability.id,
        name=faction_ability.name,
        description=faction_ability.description,
        faction_id=faction_ability.faction_id,
        rule_options=list(faction_seeds.rule_options(faction_name, faction_ability.name)),
    )


@router.get("", response_model=list[FactionAbilityOut])
async def list_faction_abilities(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(FactionAbility)
        .options(selectinload(FactionAbility.faction))
        .order_by(FactionAbility.id)
    )
    return [_to_out(fa, fa.faction.name) for fa in result.scalars().all()]


@router.post("", response_model=FactionAbilityOut, status_code=201)
async def create_faction_ability(
    payload: FactionAbilityIn, session: AsyncSession = Depends(get_session)
):
    faction = (
        await session.execute(select(Faction).where(Faction.id == payload.faction_id))
    ).scalar_one_or_none()
    if faction is None:
        raise HTTPException(status_code=400, detail="invalid faction_id")

    faction_ability = FactionAbility(**payload.model_dump())
    session.add(faction_ability)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="faction ability name must be unique within its faction"
        ) from exc
    return _to_out(faction_ability, faction.name)


@router.delete("/{faction_ability_id}", status_code=204)
async def delete_faction_ability(
    faction_ability_id: int, session: AsyncSession = Depends(get_session)
):
    faction_ability = (
        await session.execute(
            select(FactionAbility).where(FactionAbility.id == faction_ability_id)
        )
    ).scalar_one_or_none()
    if faction_ability is None:
        raise HTTPException(status_code=404, detail="faction ability not found")

    await session.delete(faction_ability)
    await session.commit()
