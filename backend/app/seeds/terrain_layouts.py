import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    TerrainArea,
    TerrainAreaShape,
    TerrainAreaShapePoint,
    TerrainDeployment,
    TerrainDeploymentPoint,
    TerrainFeature,
    TerrainFeatureShape,
    TerrainFeatureShapePart,
    TerrainLayout,
    TerrainObjective,
    TerrainObjectiveArea,
)
from app.models.terrain import DEPLOYMENT_SIDES, OBJECTIVE_KINDS, TERRAIN_FEATURE_KINDS
from app.seeds import data_files
from app.seeds.lookup import get_dispositions_by_name
from app.services.in_game.terrain import is_convex

# The terrain kit and the layouts that place it, from
# app/data/terrain_layouts.json - a local file, not committed (see
# app/data/README.md). Positions are in inches on the 60" x 44" board (see
# app/models/terrain.py).


SECTIONS = ("deployments", "area_shapes", "feature_shapes", "layouts")


def load(path: Path | None = None) -> dict:
    # The file's deployments, kit shapes and layouts (SECTIONS), each empty if
    # there's no file.
    path = path or data_files.data_dir() / "terrain_layouts.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {key: data.get(key, []) for key in SECTIONS}


def deployment(entry: dict) -> TerrainDeployment:
    # Its zones: "attacker_zone" and "defender_zone", each corners in order.
    found = TerrainDeployment(name=entry["name"])
    found.points = [
        TerrainDeploymentPoint(side=side, x=x, y=y)
        for side in DEPLOYMENT_SIDES
        for x, y in entry[f"{side}_zone"]
    ]
    if any(len(found.zone(side)) < 3 for side in DEPLOYMENT_SIDES):
        raise ValueError(f"deployment {entry['name']!r} needs at least 3 corners per zone")
    return found


def area_shape(entry: dict) -> TerrainAreaShape:
    # A rectangle (width, height), or a convex polygon (points, in order
    # around it - its width and height are their extent).
    name = entry["name"]
    points = [tuple(p) for p in entry.get("points", [])]
    if points and not is_convex(points):
        raise ValueError(f"terrain area shape {name!r} isn't a convex polygon")
    if points:
        width = max(p[0] for p in points) - min(p[0] for p in points)
        height = max(p[1] for p in points) - min(p[1] for p in points)
    else:
        width, height = entry["width"], entry["height"]
    shape = TerrainAreaShape(name=name, count=entry["count"], width=width, height=height)
    shape.points = [TerrainAreaShapePoint(x=x, y=y) for x, y in points]
    return shape


def feature_shape(entry: dict) -> TerrainFeatureShape:
    name = entry["name"]
    if entry["kind"] not in TERRAIN_FEATURE_KINDS:
        raise ValueError(f"terrain feature shape {name!r} has unknown kind {entry['kind']!r}")
    shape = TerrainFeatureShape(name=name, kind=entry["kind"], count=entry["count"])
    shape.parts = [
        TerrainFeatureShapePart(x=p["x"], y=p["y"], width=p["width"], height=p["height"])
        for p in entry["parts"]
    ]
    return shape


def objectives(entry: dict, areas: list[TerrainArea]) -> list[TerrainObjective]:
    # The layout's objectives: each a kind, where its marker is, and its
    # terrain areas - indexes into the layout's areas, in the file's order.
    name = entry["name"]
    found = []
    for o in entry.get("objectives", []):
        if o["kind"] not in OBJECTIVE_KINDS:
            raise ValueError(
                f"terrain layout {name!r} has an objective of unknown kind {o['kind']!r}"
            )
        if not o["areas"] or any(not 0 <= i < len(areas) for i in o["areas"]):
            raise ValueError(f"terrain layout {name!r} has an objective without its terrain areas")
        objective = TerrainObjective(kind=o["kind"], x=o["x"], y=o["y"])
        objective.area_links = [TerrainObjectiveArea(area=areas[i]) for i in o["areas"]]
        found.append(objective)
    return found


async def seed(session: AsyncSession, path: Path | None = None) -> None:
    # Adds any deployments, kit shapes and layouts not already present (by
    # name); an existing layout only gains its deployment if it has none, and
    # nothing else is changed. Deployments, shapes and dispositions are looked
    # up by name, so this runs after dispositions.seed - an unknown one is an
    # error, not skipped, as is a layout using more of a shape than the kit
    # has.
    data = load(path)
    if not any(data.values()):
        return

    deployments = {d.name: d for d in (await session.execute(select(TerrainDeployment))).scalars()}
    for entry in data["deployments"]:
        if entry["name"] not in deployments:
            deployments[entry["name"]] = deployment(entry)
            session.add(deployments[entry["name"]])

    area_shapes = {s.name: s for s in (await session.execute(select(TerrainAreaShape))).scalars()}
    for entry in data["area_shapes"]:
        if entry["name"] not in area_shapes:
            area_shapes[entry["name"]] = area_shape(entry)
            session.add(area_shapes[entry["name"]])
    feature_shapes = {
        s.name: s for s in (await session.execute(select(TerrainFeatureShape))).scalars()
    }
    for entry in data["feature_shapes"]:
        if entry["name"] not in feature_shapes:
            feature_shapes[entry["name"]] = feature_shape(entry)
            session.add(feature_shapes[entry["name"]])

    dispositions = await get_dispositions_by_name(session)
    existing = {
        layout.name: layout for layout in (await session.execute(select(TerrainLayout))).scalars()
    }

    def lookup(table: dict, key: str, kind: str, layout: str):
        if key not in table:
            raise ValueError(f"terrain layout {layout!r} references unknown {kind} {key!r}")
        return table[key]

    for entry in data["layouts"]:
        name = entry["name"]
        layout_deployment = (
            lookup(deployments, entry["deployment"], "deployment", name)
            if entry.get("deployment")
            else None
        )
        if name in existing:
            # Its deployment and objectives, if added since it was seeded.
            layout = existing[name]
            if layout_deployment is not None and layout.deployment is None:
                layout.deployment = layout_deployment
            if entry.get("objectives") and not layout.objectives:
                layout.objectives = objectives(entry, list(layout.areas))
            continue
        areas = [
            TerrainArea(
                shape=lookup(area_shapes, a["shape"], "area shape", name),
                x=a["x"],
                y=a["y"],
                rotation=a.get("rotation", 0),
                mirrored=a.get("mirrored", False),
            )
            for a in entry.get("areas", [])
        ]
        features = [
            TerrainFeature(
                shape=lookup(feature_shapes, f["shape"], "feature shape", name),
                x=f["x"],
                y=f["y"],
                rotation=f.get("rotation", 0),
                mirrored=f.get("mirrored", False),
            )
            for f in entry.get("features", [])
        ]
        # Only what the kit has: each shape at most its count.
        for placed in (areas, features):
            for shape, used in Counter(p.shape for p in placed).items():
                if used > shape.count:
                    raise ValueError(
                        f"terrain layout {name!r} uses {used} of {shape.name!r}, "
                        f"but the kit has {shape.count}"
                    )
        layout = TerrainLayout(
            name=name,
            attacker_disposition=lookup(
                dispositions, entry["attacker_disposition"], "disposition", name
            ),
            defender_disposition=lookup(
                dispositions, entry["defender_disposition"], "disposition", name
            ),
        )
        layout.areas = areas
        layout.features = features
        layout.deployment = layout_deployment
        layout.objectives = objectives(entry, areas)
        session.add(layout)
        existing[name] = layout
    await session.commit()
