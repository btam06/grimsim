from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Condition, DatasheetAbility, Effect
from app.schemas import DatasheetAbilityIn, DatasheetAbilityOut

router = APIRouter(prefix="/datasheet-abilities", tags=["datasheet-abilities"])


def _to_out(ability: DatasheetAbility) -> DatasheetAbilityOut:
    return DatasheetAbilityOut(
        id=ability.id,
        name=ability.name,
        description=ability.description,
        condition_ids=[c.id for c in ability.conditions],
        effect_ids=[e.id for e in ability.effects],
    )


@router.get("", response_model=list[DatasheetAbilityOut])
async def list_datasheet_abilities(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(DatasheetAbility)
        .options(
            selectinload(DatasheetAbility.conditions), selectinload(DatasheetAbility.effects)
        )
        .order_by(DatasheetAbility.id)
    )
    return [_to_out(ability) for ability in result.scalars().all()]


@router.post("", response_model=DatasheetAbilityOut, status_code=201)
async def create_datasheet_ability(
    payload: DatasheetAbilityIn, session: AsyncSession = Depends(get_session)
):
    conditions: list[Condition] = []
    if payload.condition_ids:
        result = await session.execute(
            select(Condition).where(Condition.id.in_(payload.condition_ids))
        )
        conditions = list(result.scalars().all())
        if len(conditions) != len(set(payload.condition_ids)):
            raise HTTPException(status_code=400, detail="one or more condition_ids not found")

    effects: list[Effect] = []
    if payload.effect_ids:
        result = await session.execute(select(Effect).where(Effect.id.in_(payload.effect_ids)))
        effects = list(result.scalars().all())
        if len(effects) != len(set(payload.effect_ids)):
            raise HTTPException(status_code=400, detail="one or more effect_ids not found")

    ability = DatasheetAbility(
        name=payload.name,
        description=payload.description,
        conditions=conditions,
        effects=effects,
    )
    session.add(ability)
    await session.commit()
    return _to_out(ability)
