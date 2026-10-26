from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    unit_model_enhancements,
    unit_model_wargear,
    unit_model_weapons,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.enhancement import Enhancement
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
    wargear: Mapped[list["Wargear"]] = relationship(secondary=unit_model_wargear, lazy="selectin")
    # The enhancement this model carries, if any (a CHARACTER only).
    @property
    def wounds(self) -> int:
        # Its Wounds characteristic: its model's, plus any its wargear gives it
        # (see app/seeds/datasheet_abilities.py WARGEAR_WOUNDS - e.g. a Storm
        # Shield: +1 W). Needs its model and wargear loaded.
        from app.seeds import datasheet_abilities

        bonus = datasheet_abilities.WARGEAR_WOUNDS
        return self.model.wounds + sum(bonus.get(w.name, 0) for w in self.wargear)

    enhancement: Mapped["Enhancement | None"] = relationship(
        secondary=unit_model_enhancements, uselist=False, lazy="selectin"
    )
