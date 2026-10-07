from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    weapon_ability_conditions,
    weapon_ability_effects,
    weapon_ability_links,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.condition import Condition
    from app.models.effect import Effect
    from app.models.weapon import Weapon


class WeaponAbility(Base):
    __tablename__ = "weapon_abilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Any amount of conditions (OR'd - any one matching triggers the ability)
    # and any amount of effects (all applied once triggered).
    conditions: Mapped[list["Condition"]] = relationship(secondary=weapon_ability_conditions)
    effects: Mapped[list["Effect"]] = relationship(secondary=weapon_ability_effects)

    # Many-to-many: the same ability can be attached to any number of weapons.
    weapons: Mapped[list["Weapon"]] = relationship(
        secondary=weapon_ability_links, back_populates="abilities"
    )
