from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.faction import Faction
    from app.models.unit import Unit


class FactionUnit(Base):
    __tablename__ = "faction_units"
    __table_args__ = (UniqueConstraint("faction_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    faction: Mapped["Faction"] = relationship(back_populates="faction_units")
    units: Mapped[list["Unit"]] = relationship(back_populates="faction_unit")
