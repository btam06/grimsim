from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    datasheet_ability_links,
    model_base_sizes,
    model_faction_ability_links,
    model_keyword_links,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.base_size import BaseSize
    from app.models.datasheet_ability import DatasheetAbility
    from app.models.faction import Faction
    from app.models.faction_ability import FactionAbility
    from app.models.keyword import Keyword
    from app.models.unit_model import UnitModel
    from app.models.wargear import Wargear
    from app.models.weapon import Weapon


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    save: Mapped[int] = mapped_column(Integer)
    toughness: Mapped[int] = mapped_column(Integer)
    oc: Mapped[int] = mapped_column(Integer)
    invulnerable: Mapped[int | None] = mapped_column(Integer, nullable=True)
    movement: Mapped[int] = mapped_column(Integer)
    wounds: Mapped[int] = mapped_column(Integer)
    feel_no_pain: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leadership: Mapped[int] = mapped_column(Integer)
    is_support: Mapped[bool] = mapped_column(Boolean, default=False)
    is_leader: Mapped[bool] = mapped_column(Boolean, default=False)

    faction: Mapped["Faction"] = relationship(back_populates="models")
    weapons: Mapped[list["Weapon"]] = relationship(back_populates="model")
    wargear: Mapped[list["Wargear"]] = relationship(back_populates="model")
    abilities: Mapped[list["DatasheetAbility"]] = relationship(
        secondary=datasheet_ability_links, back_populates="models"
    )
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary=model_keyword_links, back_populates="models"
    )
    # Faction-wide rules this model has access to (e.g. Doctrina Imperatives).
    # Like a keyword in that it's a tag on the model, but it names a rule from
    # app/seeds/factions/<faction>/abilities.py rather than a datasheet keyword.
    faction_abilities: Mapped[list["FactionAbility"]] = relationship(
        secondary=model_faction_ability_links, back_populates="models"
    )
    unit_models: Mapped[list["UnitModel"]] = relationship(back_populates="model")
    mortal_fnp_link: Mapped["ModelMortalFeelNoPain | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    ranged_only_invulnerable_link: Mapped["ModelRangedOnlyInvulnerable | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def invulnerable_ranged_only(self) -> bool:
        # Its invulnerable save only applies against ranged attacks (e.g. an
        # Imperial Knight's ion shield).
        return self.ranged_only_invulnerable_link is not None

    @invulnerable_ranged_only.setter
    def invulnerable_ranged_only(self, ranged_only: bool) -> None:
        self.ranged_only_invulnerable_link = (
            ModelRangedOnlyInvulnerable() if ranged_only else None
        )

    @property
    def feel_no_pain_mortal(self) -> int | None:
        # A Feel No Pain that only applies against mortal wounds (e.g. 5+),
        # on top of any feel_no_pain. None if it has none.
        return self.mortal_fnp_link.value if self.mortal_fnp_link else None

    @feel_no_pain_mortal.setter
    def feel_no_pain_mortal(self, value: int | None) -> None:
        self.mortal_fnp_link = ModelMortalFeelNoPain(value=value) if value else None

    # The base it's on, if entered (see BaseSize).
    base_size: Mapped["BaseSize | None"] = relationship(
        secondary=model_base_sizes, uselist=False, lazy="selectin"
    )


class ModelMortalFeelNoPain(Base):
    # A model's Feel No Pain against mortal wounds. Its own table rather than a
    # column on models, so existing databases pick it up without a migration.
    __tablename__ = "model_mortal_feel_no_pain"

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)


class ModelRangedOnlyInvulnerable(Base):
    # Marks a model's invulnerable save as against ranged attacks only. Its own
    # table rather than a column on models, so existing databases pick it up
    # without a migration.
    __tablename__ = "model_ranged_only_invulnerable"

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), primary_key=True)
