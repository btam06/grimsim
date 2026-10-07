from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import detachment_dispositions
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.army_list import ArmyList
    from app.models.disposition import Disposition
    from app.models.faction import Faction


class Detachment(Base):
    __tablename__ = "detachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))
    dp: Mapped[int] = mapped_column(Integer)

    faction: Mapped["Faction"] = relationship(back_populates="detachments")
    dispositions: Mapped[list["Disposition"]] = relationship(
        secondary=detachment_dispositions, back_populates="detachments"
    )
    lists: Mapped[list["ArmyList"]] = relationship(back_populates="detachment")
