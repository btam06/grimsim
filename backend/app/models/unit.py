from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.army_list import ArmyList
    from app.models.faction_unit import FactionUnit
    from app.models.unit_model import UnitModel


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    faction_unit_id: Mapped[int] = mapped_column(ForeignKey("faction_units.id"))
    points: Mapped[int] = mapped_column(Integer)
    list_id: Mapped[int | None] = mapped_column(ForeignKey("lists.id"), nullable=True)

    faction_unit: Mapped["FactionUnit"] = relationship(back_populates="units")
    army_list: Mapped["ArmyList | None"] = relationship(back_populates="units")
    unit_models: Mapped[list["UnitModel"]] = relationship(
        back_populates="unit", cascade="all, delete-orphan"
    )
