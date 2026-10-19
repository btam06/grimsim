from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    stratagem_conditions,
    stratagem_detachments,
    stratagem_effects,
    stratagem_keywords,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.condition import Condition
    from app.models.detachment import Detachment
    from app.models.effect import Effect
    from app.models.keyword import Keyword


class Stratagem(Base):
    # A core stratagem (e.g. "Command Re-roll") is usable by any army and is
    # attached to no detachment; every other stratagem belongs to one or more
    # detachments and is only usable by an army that has taken one of them.
    __tablename__ = "stratagems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    cp: Mapped[int] = mapped_column(Integer)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)

    # Same Condition/Effect catalog as the abilities - when a stratagem is used
    # in combat, its effects apply to the attacking unit like wargear abilities.
    conditions: Mapped[list["Condition"]] = relationship(secondary=stratagem_conditions)
    effects: Mapped[list["Effect"]] = relationship(secondary=stratagem_effects)

    # Keywords a model needs (all of them) for this stratagem to apply to it,
    # e.g. CHARACTER for Epic Challenge. None means it applies to any model.
    keywords: Mapped[list["Keyword"]] = relationship(secondary=stratagem_keywords)

    # When it can be used, as (phase, whose turn) pairs. None means any time.
    timings: Mapped[list["StratagemTiming"]] = relationship(
        back_populates="stratagem", cascade="all, delete-orphan", order_by="StratagemTiming.id"
    )
    game_action_link: Mapped["StratagemGameAction | None"] = relationship(
        cascade="all, delete-orphan", uselist=False
    )

    @property
    def game_action(self) -> str | None:
        # What the game tracker does when it's used, beyond spending CP (see
        # STRATAGEM_GAME_ACTIONS), if anything.
        return self.game_action_link.action if self.game_action_link else None

    @game_action.setter
    def game_action(self, action: str | None) -> None:
        self.game_action_link = StratagemGameAction(action=action) if action else None

    detachments: Mapped[list["Detachment"]] = relationship(
        secondary=stratagem_detachments, back_populates="stratagems"
    )


# Whose turn a stratagem timing is for, from the using player's point of view.
STRATAGEM_TURNS = ("your_turn", "opponent_turn", "either")


class StratagemTiming(Base):
    # One phase (and whose turn) a stratagem can be used in - e.g. Fire
    # Overwatch: the opponent's movement phase, and the opponent's charge phase.
    __tablename__ = "stratagem_timings"

    id: Mapped[int] = mapped_column(primary_key=True)
    stratagem_id: Mapped[int] = mapped_column(ForeignKey("stratagems.id"))
    phase: Mapped[str] = mapped_column(String(32))
    turn: Mapped[str] = mapped_column(String(32))

    stratagem: Mapped["Stratagem"] = relationship(back_populates="timings")


# Things a stratagem can do in a game besides cost CP, carried out by the game
# tracker when it's used:
# - "replace_secondary": discard one of the player's active tactical Secondary
#   Mission cards (the stratagem's target) and draw one new one (New Orders).
STRATAGEM_GAME_ACTIONS = ("replace_secondary",)


class StratagemGameAction(Base):
    # A stratagem's game action (one at most). Its own table rather than a
    # column on stratagems, so existing databases pick it up without a migration.
    __tablename__ = "stratagem_game_actions"

    stratagem_id: Mapped[int] = mapped_column(ForeignKey("stratagems.id"), primary_key=True)
    action: Mapped[str] = mapped_column(String(64))
