from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import datasheet_ability_links, unit_models
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.datasheet_ability import DatasheetAbility
    from app.models.faction import Faction
    from app.models.unit import Unit
    from app.models.weapon import Weapon


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    points: Mapped[int] = mapped_column(Integer)
    save: Mapped[int] = mapped_column(Integer)
    toughness: Mapped[int] = mapped_column(Integer)
    oc: Mapped[int] = mapped_column(Integer)
    invulnerable: Mapped[int | None] = mapped_column(Integer, nullable=True)
    movement: Mapped[int] = mapped_column(Integer)
    wounds: Mapped[int] = mapped_column(Integer)
    feel_no_pain: Mapped[int | None] = mapped_column(Integer, nullable=True)

    faction: Mapped["Faction"] = relationship(back_populates="models")
    weapons: Mapped[list["Weapon"]] = relationship(back_populates="model")
    abilities: Mapped[list["DatasheetAbility"]] = relationship(
        secondary=datasheet_ability_links, back_populates="models"
    )
    units: Mapped[list["Unit"]] = relationship(
        secondary=unit_models, back_populates="models"
    )
