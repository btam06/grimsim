from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.army_list import ArmyList
    from app.models.detachment import Detachment
    from app.models.faction_ability import FactionAbility
    from app.models.faction_unit import FactionUnit
    from app.models.model import Model


class Faction(Base):
    __tablename__ = "factions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    models: Mapped[list["Model"]] = relationship(back_populates="faction")
    detachments: Mapped[list["Detachment"]] = relationship(back_populates="faction")
    lists: Mapped[list["ArmyList"]] = relationship(back_populates="faction")
    faction_units: Mapped[list["FactionUnit"]] = relationship(back_populates="faction")
    faction_abilities: Mapped[list["FactionAbility"]] = relationship(back_populates="faction")
