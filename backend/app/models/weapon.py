from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import weapon_ability_links
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model
    from app.models.weapon_ability import WeaponAbility


class Weapon(Base):
    __tablename__ = "weapons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    damage: Mapped[str] = mapped_column(String(10))
    range: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strength: Mapped[int] = mapped_column(Integer)
    ap: Mapped[int] = mapped_column(Integer)
    attacks: Mapped[str] = mapped_column(String(10))
    skill: Mapped[int] = mapped_column(Integer)
    weapon_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))

    model: Mapped["Model"] = relationship(back_populates="weapons")
    abilities: Mapped[list["WeaponAbility"]] = relationship(
        secondary=weapon_ability_links, back_populates="weapons"
    )
    default_link: Mapped["WeaponDefault | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def is_default(self) -> bool:
        # Whether the model is equipped with it by default (its datasheet's
        # "This model is equipped with: ..."), so it's pre-selected when the
        # model is added to a unit.
        return self.default_link is not None

    @is_default.setter
    def is_default(self, is_default: bool) -> None:
        self.default_link = WeaponDefault() if is_default else None


class WeaponDefault(Base):
    # Marks a weapon as equipped by default (see Weapon.is_default). Its own
    # table rather than a column, so existing databases pick it up without a
    # migration.
    __tablename__ = "weapon_defaults"

    weapon_id: Mapped[int] = mapped_column(ForeignKey("weapons.id"), primary_key=True)
