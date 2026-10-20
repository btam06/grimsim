from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Condition, DatasheetAbility, Effect
from app.schemas import DatasheetAbilityIn, DatasheetAbilityOut
from app.seeds import datasheet_abilities as datasheet_ability_seeds

router = APIRouter(prefix="/datasheet-abilities", tags=["datasheet-abilities"])


def _to_out(ability: DatasheetAbility) -> DatasheetAbilityOut:
    return DatasheetAbilityOut(
        id=ability.id,
        name=ability.name,
        description=ability.description,
        condition_ids=[c.id for c in ability.conditions],
        effect_ids=[e.id for e in ability.effects],
        rule_options=list(datasheet_ability_seeds.OPTIONS.get(ability.name, {})),
        rule_option_descriptions={
            name: option.description
            for name, option in datasheet_ability_seeds.OPTIONS.get(ability.name, {}).items()
            if option.description
        },
        calculator_notes=datasheet_ability_seeds.calculator_notes(ability.name),
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


async def _conditions_and_effects(
    session: AsyncSession, payload: DatasheetAbilityIn
) -> tuple[list[Condition], list[Effect]]:
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

    return conditions, effects


@router.post("", response_model=DatasheetAbilityOut, status_code=201)
async def create_datasheet_ability(
    payload: DatasheetAbilityIn, session: AsyncSession = Depends(get_session)
):
    conditions, effects = await _conditions_and_effects(session, payload)
    ability = DatasheetAbility(
        name=payload.name,
        description=payload.description,
        conditions=conditions,
        effects=effects,
    )
    session.add(ability)
    await session.commit()
    return _to_out(ability)


@router.put("/{ability_id}", response_model=DatasheetAbilityOut)
async def update_datasheet_ability(
    ability_id: int, payload: DatasheetAbilityIn, session: AsyncSession = Depends(get_session)
):
    # The ability is shared, so this changes it for every model that has it.
    ability = (
        await session.execute(
            select(DatasheetAbility)
            .options(
                selectinload(DatasheetAbility.conditions), selectinload(DatasheetAbility.effects)
            )
            .where(DatasheetAbility.id == ability_id)
        )
    ).scalar_one_or_none()
    if ability is None:
        raise HTTPException(status_code=404, detail="datasheet ability not found")

    conditions, effects = await _conditions_and_effects(session, payload)
    ability.name = payload.name
    ability.description = payload.description
    ability.conditions = conditions
    ability.effects = effects
    await session.commit()
    return _to_out(ability)
