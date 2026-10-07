from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import list_detachments
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.detachment import Detachment
    from app.models.faction import Faction
    from app.models.unit import Unit


class ArmyList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    points_limit: Mapped[int] = mapped_column(Integer)
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    faction: Mapped["Faction"] = relationship(back_populates="lists")
    detachments: Mapped[list["Detachment"]] = relationship(secondary=list_detachments)
    units: Mapped[list["Unit"]] = relationship(back_populates="army_list")
