from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.disposition import Disposition

# Battlefield terrain. Every layout uses the same kit - the same terrain areas
# (baseplates) and terrain features (ruin walls and obstacles) - placed,
# turned and sometimes flipped differently, and not always all of it.
#
# Everything is in inches on the 60" x 44" board, seen from above: x runs 0-60
# left to right, y runs 0-44 top to bottom. (A portrait layout map, 44" across
# and 60" down, is turned a quarter anticlockwise onto it: the map's top edge
# is the board's left edge.) Rotations are in degrees, clockwise (as on
# screen, where y points down). A placement that's mirrored is flipped before
# it's turned: its shape's x is negated.

# What a terrain feature is: a ruin wall, or an obstacle.
TERRAIN_FEATURE_KINDS = ("ruin_wall", "obstacle")

# Whose a deployment zone is.
DEPLOYMENT_SIDES = ("attacker", "defender")

# What an objective is: each player's home objective, an expansion, or the
# centre (as on the layout cards).
OBJECTIVE_KINDS = ("attacker_home", "defender_home", "expansion", "centre")


class TerrainDeployment(Base):
    # A deployment (e.g. Dawn of War): the attacker's and the defender's
    # deployment zones, each a polygon on the board (concave ones too, e.g.
    # Search and Destroy's quarters with the centre cut out).
    __tablename__ = "terrain_deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    points: Mapped[list["TerrainDeploymentPoint"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TerrainDeploymentPoint.id"
    )

    def zone(self, side: str) -> list[tuple[float, float]]:
        # One side's zone: its corners, in order around it.
        return [(p.x, p.y) for p in self.points if p.side == side]


class TerrainDeploymentPoint(Base):
    # One corner of a deployment zone, in order around it.
    __tablename__ = "terrain_deployment_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    deployment_id: Mapped[int] = mapped_column(ForeignKey("terrain_deployments.id"))
    side: Mapped[str] = mapped_column(String(16))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)


class TerrainAreaShape(Base):
    # One of the kit's baseplates: a width x height rectangle centred on where
    # it's placed, or - if it has points - the convex polygon they make,
    # relative to where it's placed (width and height are then their extent).
    # `count` is how many the kit has.
    __tablename__ = "terrain_area_shapes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    count: Mapped[int] = mapped_column(Integer)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)

    points: Mapped[list["TerrainAreaShapePoint"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TerrainAreaShapePoint.id"
    )


class TerrainAreaShapePoint(Base):
    # One corner of a polygonal baseplate, in order around it.
    __tablename__ = "terrain_area_shape_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    shape_id: Mapped[int] = mapped_column(ForeignKey("terrain_area_shapes.id"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)


class TerrainFeatureShape(Base):
    # One of the kit's ruin walls or obstacles: one or more rectangles (its
    # parts - e.g. the two legs of an L), relative to where it's placed.
    # `count` is how many the kit has.
    __tablename__ = "terrain_feature_shapes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer)

    parts: Mapped[list["TerrainFeatureShapePart"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TerrainFeatureShapePart.id"
    )


class TerrainFeatureShapePart(Base):
    # One rectangle of a terrain feature shape: its top-left corner (x, y)
    # relative to where the feature's placed, before it's turned, and its size.
    __tablename__ = "terrain_feature_shape_parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    shape_id: Mapped[int] = mapped_column(ForeignKey("terrain_feature_shapes.id"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)


class TerrainLayout(Base):
    # A battlefield's terrain for one pairing of dispositions - the attacker's
    # and the defender's (e.g. Take and Hold vs Take and Hold): where each
    # piece of the kit it uses goes. A pairing can have several; a game is
    # given one of them.
    __tablename__ = "terrain_layouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    attacker_disposition_id: Mapped[int] = mapped_column(ForeignKey("dispositions.id"))
    defender_disposition_id: Mapped[int] = mapped_column(ForeignKey("dispositions.id"))

    attacker_disposition: Mapped["Disposition"] = relationship(
        foreign_keys=[attacker_disposition_id], lazy="selectin"
    )
    defender_disposition: Mapped["Disposition"] = relationship(
        foreign_keys=[defender_disposition_id], lazy="selectin"
    )
    areas: Mapped[list["TerrainArea"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TerrainArea.id"
    )
    features: Mapped[list["TerrainFeature"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TerrainFeature.id"
    )
    deployment_link: Mapped["TerrainLayoutDeployment | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    objectives: Mapped[list["TerrainObjective"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TerrainObjective.id"
    )

    @property
    def deployment(self) -> "TerrainDeployment | None":
        # Its deployment zones, if known.
        return self.deployment_link.deployment if self.deployment_link else None

    @deployment.setter
    def deployment(self, deployment: "TerrainDeployment | None") -> None:
        self.deployment_link = (
            TerrainLayoutDeployment(deployment=deployment) if deployment else None
        )


class TerrainLayoutDeployment(Base):
    # A layout's deployment. Its own table rather than a column, so existing
    # databases pick it up without a migration.
    __tablename__ = "terrain_layout_deployments"

    layout_id: Mapped[int] = mapped_column(ForeignKey("terrain_layouts.id"), primary_key=True)
    deployment_id: Mapped[int] = mapped_column(ForeignKey("terrain_deployments.id"))

    deployment: Mapped["TerrainDeployment"] = relationship(lazy="selectin")


class TerrainArea(Base):
    # A terrain area on a layout: a kit baseplate placed at (x, y), flipped if
    # mirrored, and turned about (x, y).
    __tablename__ = "terrain_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    layout_id: Mapped[int] = mapped_column(ForeignKey("terrain_layouts.id"))
    shape_id: Mapped[int] = mapped_column(ForeignKey("terrain_area_shapes.id"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    rotation: Mapped[float] = mapped_column(Float, default=0)
    mirrored: Mapped[bool] = mapped_column(Boolean, default=False)

    shape: Mapped["TerrainAreaShape"] = relationship(lazy="selectin")


class TerrainFeature(Base):
    # A terrain feature on a layout: a kit ruin wall or obstacle placed at
    # (x, y), flipped if mirrored, and turned about (x, y).
    __tablename__ = "terrain_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    layout_id: Mapped[int] = mapped_column(ForeignKey("terrain_layouts.id"))
    shape_id: Mapped[int] = mapped_column(ForeignKey("terrain_feature_shapes.id"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    rotation: Mapped[float] = mapped_column(Float, default=0)
    mirrored: Mapped[bool] = mapped_column(Boolean, default=False)

    shape: Mapped["TerrainFeatureShape"] = relationship(lazy="selectin")


class TerrainObjective(Base):
    # An objective on a layout. Objectives are terrain areas: this one is
    # `areas` (usually one; the centre of a Take and Hold layout is both of
    # its halves). (x, y) is where its marker is drawn on the layout card.
    __tablename__ = "terrain_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    layout_id: Mapped[int] = mapped_column(ForeignKey("terrain_layouts.id"))
    kind: Mapped[str] = mapped_column(String(32))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)

    area_links: Mapped[list["TerrainObjectiveArea"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def areas(self) -> list["TerrainArea"]:
        return [link.area for link in self.area_links]


class TerrainObjectiveArea(Base):
    # A terrain area that is (part of) an objective.
    __tablename__ = "terrain_objective_areas"

    objective_id: Mapped[int] = mapped_column(
        ForeignKey("terrain_objectives.id"), primary_key=True
    )
    area_id: Mapped[int] = mapped_column(ForeignKey("terrain_areas.id"), primary_key=True)

    area: Mapped["TerrainArea"] = relationship(lazy="selectin")


class GameTerrainLayout(Base):
    # The terrain layout a game is played on. Its own table rather than a
    # column, so existing databases pick it up without a migration.
    __tablename__ = "game_terrain_layouts"

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), primary_key=True)
    layout_id: Mapped[int] = mapped_column(ForeignKey("terrain_layouts.id"))

    layout: Mapped["TerrainLayout"] = relationship(lazy="selectin")
