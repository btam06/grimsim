from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Condition, Detachment, Effect, Keyword, Stratagem, StratagemTiming
from app.schemas import StratagemIn, StratagemOut, StratagemTimingSchema

router = APIRouter(prefix="/stratagems", tags=["stratagems"])


def _to_out(stratagem: Stratagem) -> StratagemOut:
    return StratagemOut(
        id=stratagem.id,
        name=stratagem.name,
        description=stratagem.description,
        cp=stratagem.cp,
        is_core=stratagem.is_core,
        detachment_ids=[d.id for d in stratagem.detachments],
        condition_ids=[c.id for c in stratagem.conditions],
        effect_ids=[e.id for e in stratagem.effects],
        keyword_ids=[k.id for k in stratagem.keywords],
        excluded_keyword_ids=[k.id for k in stratagem.excluded_keywords],
        keyword_option_ids=[[k.id for k in option] for option in stratagem.keyword_options],
        timings=[StratagemTimingSchema(phase=t.phase, turn=t.turn) for t in stratagem.timings],
        game_action=stratagem.game_action,
        combat_side=stratagem.combat_side,
        duration=stratagem.duration,
    )


async def _load_keywords(session: AsyncSession, ids: list[int], field: str) -> list[Keyword]:
    if not ids:
        return []
    keywords = list((await session.execute(select(Keyword).where(Keyword.id.in_(ids)))).scalars())
    if len(keywords) != len(set(ids)):
        raise HTTPException(status_code=400, detail=f"one or more {field} not found")
    return keywords


@router.get("", response_model=list[StratagemOut])
async def list_stratagems(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Stratagem)
        .options(
            selectinload(Stratagem.detachments),
            selectinload(Stratagem.conditions),
            selectinload(Stratagem.effects),
            selectinload(Stratagem.keywords),
            selectinload(Stratagem.timings),
            selectinload(Stratagem.game_action_link),
        )
        .order_by(Stratagem.id)
    )
    return [_to_out(stratagem) for stratagem in result.scalars().all()]


@router.post("", response_model=StratagemOut, status_code=201)
async def create_stratagem(payload: StratagemIn, session: AsyncSession = Depends(get_session)):
    detachments: list[Detachment] = []
    if payload.detachment_ids:
        result = await session.execute(
            select(Detachment).where(Detachment.id.in_(payload.detachment_ids))
        )
        detachments = list(result.scalars().all())
        if len(detachments) != len(set(payload.detachment_ids)):
            raise HTTPException(status_code=400, detail="one or more detachment_ids not found")

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

    keywords = await _load_keywords(session, payload.keyword_ids, "keyword_ids")
    excluded_keywords = await _load_keywords(
        session, payload.excluded_keyword_ids, "excluded_keyword_ids"
    )
    if set(payload.keyword_ids) & set(payload.excluded_keyword_ids):
        raise HTTPException(
            status_code=400, detail="a keyword can't be both required and excluded"
        )
    if any(not option for option in payload.keyword_option_ids):
        raise HTTPException(status_code=400, detail="a keyword option can't be empty")
    option_keywords = {
        k.id: k
        for k in await _load_keywords(
            session,
            list({i for option in payload.keyword_option_ids for i in option}),
            "keyword_option_ids",
        )
    }

    stratagem = Stratagem(
        name=payload.name,
        description=payload.description,
        cp=payload.cp,
        is_core=payload.is_core,
        detachments=detachments,
        conditions=conditions,
        effects=effects,
        keywords=keywords,
        excluded_keywords=excluded_keywords,
        keyword_options=[
            [option_keywords[i] for i in dict.fromkeys(option)]
            for option in payload.keyword_option_ids
        ],
        timings=[StratagemTiming(phase=t.phase, turn=t.turn) for t in payload.timings],
    )
    stratagem.game_action = payload.game_action
    stratagem.combat_side = payload.combat_side
    stratagem.duration = payload.duration
    session.add(stratagem)
    await session.commit()
    return _to_out(stratagem)


@router.delete("/{stratagem_id}", status_code=204)
async def delete_stratagem(stratagem_id: int, session: AsyncSession = Depends(get_session)):
    stratagem = (
        await session.execute(select(Stratagem).where(Stratagem.id == stratagem_id))
    ).scalar_one_or_none()
    if stratagem is None:
        raise HTTPException(status_code=404, detail="stratagem not found")

    await session.delete(stratagem)
    await session.commit()
