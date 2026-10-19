from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.army_list import ArmyList
    from app.models.disposition import Disposition
    from app.models.mission import PrimaryMission, SecondaryMission
    from app.models.stratagem import Stratagem
    from app.models.user import User

# A turn's phases, in order.
PHASES = ("command", "movement", "shooting", "charge", "fight")
BATTLE_ROUNDS = 5
GAME_STATUSES = ("setup", "in_progress", "finished")
SECONDARY_MODES = ("fixed", "tactical")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), default="setup")
    # Seats are 1 and 2 (see GamePlayer.seat).
    attacker_seat: Mapped[int] = mapped_column(Integer)
    first_seat: Mapped[int] = mapped_column(Integer)
    # 0 until the game starts.
    battle_round: Mapped[int] = mapped_column(Integer, default=0)
    turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)

    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="GamePlayer.seat"
    )


class GamePlayer(Base):
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    secondary_mode: Mapped[str] = mapped_column(String(32))
    disposition_id: Mapped[int | None] = mapped_column(
        ForeignKey("dispositions.id"), nullable=True
    )
    primary_mission_id: Mapped[int | None] = mapped_column(
        ForeignKey("primary_missions.id"), nullable=True
    )
    cp: Mapped[int] = mapped_column(Integer, default=0)

    game: Mapped["Game"] = relationship(back_populates="players")
    user: Mapped["User"] = relationship()
    army_list: Mapped["ArmyList"] = relationship()
    disposition: Mapped["Disposition | None"] = relationship()
    primary_mission: Mapped["PrimaryMission | None"] = relationship()
    secondaries: Mapped[list["GameSecondary"]] = relationship(
        back_populates="player", cascade="all, delete-orphan", order_by="GameSecondary.id"
    )
    scores: Mapped[list["GameScore"]] = relationship(
        back_populates="player", cascade="all, delete-orphan", order_by="GameScore.id"
    )
    stratagem_uses: Mapped[list["GameStratagemUse"]] = relationship(
        back_populates="player", cascade="all, delete-orphan", order_by="GameStratagemUse.id"
    )


SECONDARY_STATUSES = ("active", "achieved", "discarded")


class GameSecondary(Base):
    # A secondary mission a player holds: picked at setup (fixed) or drawn in
    # a command phase (tactical).
    __tablename__ = "game_secondaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_player_id: Mapped[int] = mapped_column(ForeignKey("game_players.id"))
    secondary_mission_id: Mapped[int] = mapped_column(ForeignKey("secondary_missions.id"))
    status: Mapped[str] = mapped_column(String(32), default="active")
    # Fixed secondaries stay active after being achieved - they can be scored
    # again in later turns.
    fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    drawn_round: Mapped[int] = mapped_column(Integer, default=0)

    player: Mapped["GamePlayer"] = relationship(back_populates="secondaries")
    mission: Mapped["SecondaryMission"] = relationship()


SCORE_KINDS = ("primary", "secondary")


class GameScore(Base):
    # VP scored by a player.
    __tablename__ = "game_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_player_id: Mapped[int] = mapped_column(ForeignKey("game_players.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    points: Mapped[int] = mapped_column(Integer)
    game_secondary_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_secondaries.id"), nullable=True
    )

    player: Mapped["GamePlayer"] = relationship(back_populates="scores")


class GameStratagemUse(Base):
    # A stratagem a player used, and the CP it cost.
    __tablename__ = "game_stratagem_uses"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_player_id: Mapped[int] = mapped_column(ForeignKey("game_players.id"))
    stratagem_id: Mapped[int] = mapped_column(ForeignKey("stratagems.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32))
    cp: Mapped[int] = mapped_column(Integer)

    player: Mapped["GamePlayer"] = relationship(back_populates="stratagem_uses")
    stratagem: Mapped["Stratagem"] = relationship()
