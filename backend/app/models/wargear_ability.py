from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    wargear_ability_conditions,
    wargear_ability_effects,
    wargear_ability_links,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.condition import Condition
    from app.models.effect import Effect
    from app.models.wargear import Wargear


class WargearAbility(Base):
    __tablename__ = "wargear_abilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Any amount of conditions (OR'd) and any amount of effects, reusing the same
    # Condition/Effect catalog that WeaponAbility draws from.
    conditions: Mapped[list["Condition"]] = relationship(secondary=wargear_ability_conditions)
    effects: Mapped[list["Effect"]] = relationship(secondary=wargear_ability_effects)

    # Many-to-many: the same ability can be attached to any number of wargear.
    wargear: Mapped[list["Wargear"]] = relationship(
        secondary=wargear_ability_links, back_populates="abilities"
    )
