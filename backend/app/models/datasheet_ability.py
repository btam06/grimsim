from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    datasheet_ability_conditions,
    datasheet_ability_effects,
    datasheet_ability_links,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.condition import Condition
    from app.models.effect import Effect
    from app.models.model import Model


class DatasheetAbility(Base):
    __tablename__ = "datasheet_abilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Any amount of conditions (OR'd) and any amount of effects, reusing the same
    # Condition/Effect catalog that WeaponAbility/WargearAbility draw from.
    conditions: Mapped[list["Condition"]] = relationship(secondary=datasheet_ability_conditions)
    effects: Mapped[list["Effect"]] = relationship(secondary=datasheet_ability_effects)

    models: Mapped[list["Model"]] = relationship(
        secondary=datasheet_ability_links, back_populates="abilities"
    )
