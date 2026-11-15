from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# A datasheet's points, from the Munitorum Field Manual (see
# app/services/import/, and app/services/unit_points.py for how a unit
# in a list is priced from them). A datasheet with none is priced by hand.


class UnitPointCost(Base):
    # The datasheet's cost at `models` starting strength, for its
    # `from_copy`th copy in a list on (requisition thresholds: e.g. "Your
    # 3rd+ Units Cost" - 3). `composition`: [[count, model name], ...] when
    # the manual names the models (e.g. 3 Wolf Guard Headtakers and 3
    # Hunting Wolves), else null.
    __tablename__ = "unit_point_costs"
    __table_args__ = (UniqueConstraint("faction_unit_id", "from_copy", "models", "points"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    faction_unit_id: Mapped[int] = mapped_column(
        ForeignKey("faction_units.id", ondelete="CASCADE"), index=True
    )
    from_copy: Mapped[int] = mapped_column(Integer, default=1)
    models: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    composition: Mapped[list | None] = mapped_column(JSON, nullable=True)


class UnitWargearCost(Base):
    # Points per item taken, on top of the unit's cost: a weapon, a piece of
    # wargear or a model (e.g. "+ 1 Tidewall Defence Platform"), by name.
    __tablename__ = "unit_wargear_costs"
    __table_args__ = (UniqueConstraint("faction_unit_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    faction_unit_id: Mapped[int] = mapped_column(
        ForeignKey("faction_units.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    points: Mapped[int] = mapped_column(Integer)


class PointsSource(Base):
    # Where a datasheet's points last came from: the manual's page and its
    # version (e.g. "chaos-knights", "v1.6"), and when.
    __tablename__ = "points_sources"

    faction_unit_id: Mapped[int] = mapped_column(
        ForeignKey("faction_units.id", ondelete="CASCADE"), primary_key=True
    )
    page: Mapped[str] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # The manual's name for it, when it isn't ours exactly (e.g. our
    # "Sicarial Ruststalkers", its "SICARIAN RUSTSTALKERS").
    matched_name: Mapped[str] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
