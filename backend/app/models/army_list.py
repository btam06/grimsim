from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import list_detachments, list_owners
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.detachment import Detachment
    from app.models.faction import Faction
    from app.models.unit import Unit
    from app.models.user import User


class ListWarlord(Base):
    # The unit in a list containing its WARLORD (a CHARACTER unit), if one's
    # been chosen.
    __tablename__ = "list_warlords"

    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))


class ListSubfaction(Base):
    # What a list has selected for its faction's selection, if it has one
    # (e.g. a Space Marines list's Chapter - see app/seeds/factions SUBFACTIONS).
    __tablename__ = "list_subfactions"

    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))


class ArmyList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    points_limit: Mapped[int] = mapped_column(Integer)
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    faction: Mapped["Faction"] = relationship(back_populates="lists")
    detachments: Mapped[list["Detachment"]] = relationship(secondary=list_detachments)
    units: Mapped[list["Unit"]] = relationship(back_populates="army_list")
    owner: Mapped["User | None"] = relationship(
        secondary=list_owners, back_populates="lists", uselist=False
    )
    warlord_link: Mapped["ListWarlord | None"] = relationship(
        uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    subfaction_link: Mapped["ListSubfaction | None"] = relationship(
        uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def subfaction(self) -> str | None:
        return self.subfaction_link.name if self.subfaction_link else None

    @property
    def warlord_unit_id(self) -> int | None:
        return self.warlord_link.unit_id if self.warlord_link else None

    @property
    def warlord(self) -> "Unit | None":
        # Its Warlord's unit, if it's (still) in the list.
        return next((u for u in self.units if u.id == self.warlord_unit_id), None)
