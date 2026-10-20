from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DetachmentRuleKeywordOption, Keyword, StratagemKeywordOption
from app.models.associations import (
    enhancement_excluded_keywords,
    enhancement_keywords,
    stratagem_excluded_keywords,
    stratagem_keywords,
)
from app.schemas import KeywordIn, KeywordOut

router = APIRouter(prefix="/keywords", tags=["keywords"])


@router.get("", response_model=list[KeywordOut])
async def list_keywords(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Keyword).order_by(Keyword.id))
    return result.scalars().all()


@router.post("", response_model=KeywordOut, status_code=201)
async def create_keyword(payload: KeywordIn, session: AsyncSession = Depends(get_session)):
    keyword = Keyword(**payload.model_dump())
    session.add(keyword)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="keyword name must be unique") from exc
    return keyword


@router.delete("/{keyword_id}", status_code=204)
async def delete_keyword(keyword_id: int, session: AsyncSession = Depends(get_session)):
    keyword = (
        await session.execute(select(Keyword).where(Keyword.id == keyword_id))
    ).scalar_one_or_none()
    if keyword is None:
        raise HTTPException(status_code=404, detail="keyword not found")

    # Many-to-many with models: deleting a keyword just unlinks it from any
    # models that had it, rather than being blocked - models keep existing.
    # Likewise for stratagems and enhancements that require or exclude it.
    for table in (
        stratagem_keywords,
        stratagem_excluded_keywords,
        enhancement_keywords,
        enhancement_excluded_keywords,
    ):
        await session.execute(delete(table).where(table.c.keyword_id == keyword_id))
    for option in (StratagemKeywordOption, DetachmentRuleKeywordOption):
        await session.execute(delete(option).where(option.keyword_id == keyword_id))
    await session.delete(keyword)
    await session.commit()
