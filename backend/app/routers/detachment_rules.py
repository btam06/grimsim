from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    DatasheetAbility,
    Detachment,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleWeaponAbility,
    Keyword,
    WeaponAbility,
)
from app.schemas import DetachmentRuleIn, DetachmentRuleOut, DetachmentRuleWeaponAbilitySchema
from app.services.detachment_rules import delete_rules

router = APIRouter(prefix="/detachment-rules", tags=["detachment-rules"])


def _to_out(rule: DetachmentRule) -> DetachmentRuleOut:
    return DetachmentRuleOut(
        id=rule.id,
        detachment_id=rule.detachment_id,
        name=rule.name,
        description=rule.description,
        keyword_option_ids=[[k.id for k in option] for option in rule.keyword_options],
        weapon_abilities=[
            DetachmentRuleWeaponAbilitySchema(
                weapon_ability_id=g.weapon_ability_id, weapon_type=g.weapon_type
            )
            for g in rule.weapon_ability_grants
        ],
        datasheet_ability_ids=[g.datasheet_ability_id for g in rule.datasheet_ability_grants],
    )


async def _check_ids(session: AsyncSession, model, ids: list[int], field: str) -> dict:
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail=f"duplicate {field}")
    rows = {
        row.id: row
        for row in (await session.execute(select(model).where(model.id.in_(ids)))).scalars()
    }
    if set(ids) - set(rows):
        raise HTTPException(status_code=400, detail=f"one or more {field} not found")
    return rows


@router.get("", response_model=list[DetachmentRuleOut])
async def list_detachment_rules(session: AsyncSession = Depends(get_session)):
    rules = (await session.execute(select(DetachmentRule).order_by(DetachmentRule.id))).scalars()
    return [_to_out(rule) for rule in rules]


@router.post("", response_model=DetachmentRuleOut, status_code=201)
async def create_detachment_rule(
    payload: DetachmentRuleIn, session: AsyncSession = Depends(get_session)
):
    if await session.get(Detachment, payload.detachment_id) is None:
        raise HTTPException(status_code=400, detail="invalid detachment_id")
    if any(not option for option in payload.keyword_option_ids):
        raise HTTPException(status_code=400, detail="a keyword option can't be empty")
    keywords = await _check_ids(
        session,
        Keyword,
        list({i for option in payload.keyword_option_ids for i in option}),
        "keyword_option_ids",
    )
    await _check_ids(
        session,
        WeaponAbility,
        [g.weapon_ability_id for g in payload.weapon_abilities],
        "weapon_ability_ids",
    )
    await _check_ids(
        session, DatasheetAbility, payload.datasheet_ability_ids, "datasheet_ability_ids"
    )
    rule = DetachmentRule(
        detachment_id=payload.detachment_id,
        name=payload.name,
        description=payload.description,
        keyword_options=[
            [keywords[i] for i in dict.fromkeys(option)] for option in payload.keyword_option_ids
        ],
        weapon_ability_grants=[
            DetachmentRuleWeaponAbility(
                weapon_ability_id=g.weapon_ability_id, weapon_type=g.weapon_type
            )
            for g in payload.weapon_abilities
        ],
        datasheet_ability_grants=[
            DetachmentRuleDatasheetAbility(datasheet_ability_id=i)
            for i in payload.datasheet_ability_ids
        ],
    )
    session.add(rule)
    await session.commit()
    return _to_out(rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_detachment_rule(rule_id: int, session: AsyncSession = Depends(get_session)):
    if await session.get(DetachmentRule, rule_id) is None:
        raise HTTPException(status_code=404, detail="detachment rule not found")
    await delete_rules(session, [rule_id])
    await session.commit()
