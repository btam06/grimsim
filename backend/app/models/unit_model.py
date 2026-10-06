from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import unit_model_wargear, unit_model_weapons
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model
    from app.models.unit import Unit
    from app.models.wargear import Wargear
    from app.models.weapon import Weapon


class UnitModel(Base):
    # One model slot in a unit, so the same Model can appear multiple times with distinct loadouts.
    __tablename__ = "unit_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))

    unit: Mapped["Unit"] = relationship(back_populates="unit_models")
    model: Mapped["Model"] = relationship(back_populates="unit_models")
    weapons: Mapped[list["Weapon"]] = relationship(secondary=unit_model_weapons)
    wargear: Mapped[list["Wargear"]] = relationship(secondary=unit_model_wargear)
