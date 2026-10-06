from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Detachment, Disposition
from app.schemas import DetachmentIn, DetachmentOut

router = APIRouter(prefix="/detachments", tags=["detachments"])


def _to_out(detachment: Detachment, disposition_ids: list[int]) -> DetachmentOut:
    return DetachmentOut(
        id=detachment.id,
        name=detachment.name,
        faction_id=detachment.faction_id,
        disposition_ids=disposition_ids,
    )


@router.get("", response_model=list[DetachmentOut])
async def list_detachments(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Detachment).options(selectinload(Detachment.dispositions)).order_by(Detachment.id)
    )
    return [
        _to_out(detachment, [d.id for d in detachment.dispositions])
        for detachment in result.scalars().all()
    ]


@router.post("", response_model=DetachmentOut, status_code=201)
async def create_detachment(payload: DetachmentIn, session: AsyncSession = Depends(get_session)):
    dispositions: list[Disposition] = []
    if payload.disposition_ids:
        result = await session.execute(
            select(Disposition).where(Disposition.id.in_(payload.disposition_ids))
        )
        dispositions = list(result.scalars().all())
        if len(dispositions) != len(set(payload.disposition_ids)):
            raise HTTPException(status_code=400, detail="one or more disposition_ids not found")

    detachment = Detachment(
        name=payload.name, faction_id=payload.faction_id, dispositions=dispositions
    )
    session.add(detachment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid faction_id") from exc
    return _to_out(detachment, [d.id for d in dispositions])


@router.delete("/{detachment_id}", status_code=204)
async def delete_detachment(detachment_id: int, session: AsyncSession = Depends(get_session)):
    detachment = (
        await session.execute(select(Detachment).where(Detachment.id == detachment_id))
    ).scalar_one_or_none()
    if detachment is None:
        raise HTTPException(status_code=404, detail="detachment not found")

    await session.delete(detachment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="cannot delete detachment: it is still referenced by one or more lists",
        ) from exc
