from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import BaseSize, TerrainLayout
from app.schemas import (
    BasePositionIn,
    BasePositionOut,
    TerrainAreaOut,
    TerrainDeploymentOut,
    TerrainFeatureOut,
    TerrainFeaturePartOut,
    TerrainLayoutOut,
    TerrainObjectiveOut,
    TerrainPointOut,
    TerrainPositionOut,
)
from app.services.in_game import terrain as terrain_service

router = APIRouter(prefix="/terrain-layouts", tags=["terrain"])


def to_out(layout: TerrainLayout) -> TerrainLayoutOut:
    return TerrainLayoutOut(
        id=layout.id,
        name=layout.name,
        objectives=[
            TerrainObjectiveOut(
                id=o.id, kind=o.kind, x=o.x, y=o.y, area_ids=[a.id for a in o.areas]
            )
            for o in layout.objectives
        ],
        attacker_disposition_id=layout.attacker_disposition_id,
        defender_disposition_id=layout.defender_disposition_id,
        deployment=(
            TerrainDeploymentOut(
                name=layout.deployment.name,
                attacker_zone=[
                    TerrainPointOut(x=x, y=y) for x, y in layout.deployment.zone("attacker")
                ],
                defender_zone=[
                    TerrainPointOut(x=x, y=y) for x, y in layout.deployment.zone("defender")
                ],
            )
            if layout.deployment
            else None
        ),
        areas=[
            TerrainAreaOut(
                id=a.id,
                shape_id=a.shape_id,
                shape_name=a.shape.name,
                x=a.x,
                y=a.y,
                width=a.shape.width,
                height=a.shape.height,
                rotation=a.rotation,
                mirrored=a.mirrored,
                points=(
                    [
                        TerrainPointOut(x=x, y=y)
                        for x, y in terrain_service.area_shape_points(a)
                    ]
                    if a.shape.points
                    else []
                ),
            )
            for a in layout.areas
        ],
        features=[
            TerrainFeatureOut(
                id=f.id,
                shape_id=f.shape_id,
                shape_name=f.shape.name,
                kind=f.shape.kind,
                x=f.x,
                y=f.y,
                rotation=f.rotation,
                mirrored=f.mirrored,
                parts=[
                    TerrainFeaturePartOut(x=x, y=y, width=w, height=h)
                    for x, y, w, h in terrain_service.feature_shape_parts(f)
                ],
            )
            for f in layout.features
        ],
    )


async def _layout(session: AsyncSession, layout_id: int) -> TerrainLayout:
    layout = await session.get(TerrainLayout, layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="terrain layout not found")
    return layout


@router.get("", response_model=list[TerrainLayoutOut])
async def list_layouts(session: AsyncSession = Depends(get_session)):
    layouts = (await session.execute(select(TerrainLayout).order_by(TerrainLayout.id))).scalars()
    return [to_out(layout) for layout in layouts]


@router.get("/{layout_id}", response_model=TerrainLayoutOut)
async def get_layout(layout_id: int, session: AsyncSession = Depends(get_session)):
    return to_out(await _layout(session, layout_id))


@router.post("/{layout_id}/base-position", response_model=BasePositionOut)
async def base_position(
    layout_id: int, payload: BasePositionIn, session: AsyncSession = Depends(get_session)
):
    # Whether a base at this position is within, or wholly within, each of the
    # layout's terrain areas and terrain features.
    layout = await _layout(session, layout_id)
    if payload.base_size_id is not None:
        base_size = await session.get(BaseSize, payload.base_size_id)
        if base_size is None:
            raise HTTPException(status_code=400, detail="invalid base_size_id")
        dimensions = terrain_service.base_dimensions(base_size.name)
        if dimensions is None:
            raise HTTPException(
                status_code=400, detail=f"base size '{base_size.name}' has no measurements"
            )
    else:
        dimensions = (payload.width_mm, payload.height_mm or payload.width_mm)
    base = terrain_service.Base(
        x=payload.x,
        y=payload.y,
        width_mm=dimensions[0],
        height_mm=dimensions[1],
        rotation=payload.rotation,
    )
    areas, features = terrain_service.base_terrain(layout, base)
    return BasePositionOut(
        areas=[TerrainPositionOut(**vars(a)) for a in areas],
        features=[TerrainPositionOut(**vars(f)) for f in features],
    )
