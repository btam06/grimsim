from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.army_list import ArmyList
    from app.models.disposition import Disposition
    from app.models.mission import PrimaryMission, SecondaryMission
    from app.models.stratagem import Stratagem
    from app.models.terrain import GameTerrainLayout, TerrainLayout
    from app.models.user import User

# A turn's phases, in order.
PHASES = ("command", "movement", "shooting", "charge", "fight")
BATTLE_ROUNDS = 5
# A game is set up, then its armies are deployed (if its terrain layout has
# deployment zones - see app/services/in_game/deployment.py), then it's played.
GAME_STATUSES = ("setup", "deployment", "in_progress", "finished")
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
    layout_link: Mapped["GameTerrainLayout | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    # Units set aside when battle formations are declared (in Strategic
    # Reserves, or embarked in a transport), and the players who've declared.
    battle_formations: Mapped[list["GameBattleFormation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameBattleFormation.id"
    )
    formations_done: Mapped[list["GameFormationsDone"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameFormationsDone.id"
    )
    # Movement phases the player whose turn it was has finished (for Rapid
    # Ingress at the end of them).
    movements_ended: Mapped[list["GameMovementEnded"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameMovementEnded.id"
    )
    # Options selected for abilities in command phases, and wounds healed at
    # their start.
    command_choices: Mapped[list["GameCommandChoice"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameCommandChoice.id"
    )
    command_heals: Mapped[list["GameCommandHeal"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameCommandHeal.id"
    )
    # Reanimation Protocols activated at the end of command phases.
    reanimations: Mapped[list["GameReanimation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameReanimation.id"
    )
    # Where each deployed model is on the battlefield.
    model_positions: Mapped[list["GameModelPosition"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameModelPosition.id"
    )
    # How units have moved in movement phases.
    unit_moves: Mapped[list["GameUnitMove"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitMove.id"
    )
    # Wounds models have lost in this game, and which are destroyed.
    model_damage: Mapped[list["GameModelDamage"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameModelDamage.id"
    )
    # Charges units have rolled for and made in charge phases.
    unit_charges: Mapped[list["GameUnitCharge"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitCharge.id"
    )
    # Units' pile-ins at the start of fight phases, and which players have
    # finished piling in.
    unit_pile_ins: Mapped[list["GameUnitPileIn"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitPileIn.id"
    )
    pile_ins_done: Mapped[list["GamePileInDone"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GamePileInDone.id"
    )
    # Which units have fought in fight phases, at what, and in what order.
    unit_fights: Mapped[list["GameUnitFight"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitFight.id"
    )
    # Options chosen for army rules each battle round (e.g. which Doctrina
    # Imperative is active).
    rule_choices: Mapped[list["GameRuleChoice"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameRuleChoice.id"
    )
    # Which units have shot in shooting phases, and at what.
    unit_shots: Mapped[list["GameUnitShot"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitShot.id"
    )

    @property
    def layout(self) -> "TerrainLayout | None":
        # The terrain layout it's played on, if one fits the players'
        # dispositions (see app/services/in_game/terrain.py).
        return self.layout_link.layout if self.layout_link else None


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


class GameModelPosition(Base):
    # A model on the battlefield: its base centred on (x, y) inches on the
    # board (see app/models/terrain.py), turned `rotation` degrees clockwise.
    __tablename__ = "game_model_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    # Gone with the model if it's taken out of its list.
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    rotation: Mapped[float] = mapped_column(Float, default=0)


# How a unit moves in its movement phase (see app/services/in_game/movement.py). Not
# moving at all is remaining stationary.
MOVE_KINDS = ("normal", "advance", "fall_back")


class GameUnitMove(Base):
    # A unit's move in one movement phase (battle round and whose turn). An
    # Advance's D6 is rolled before the unit moves, so the row can exist with
    # `completed` False (and the roll) until it has; `kind` is then the move it
    # made, which needn't be the Advance.
    __tablename__ = "game_unit_moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    # Gone with the unit if it's taken out of its list.
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    advance_roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    distance_link: Mapped["GameUnitMoveDistance | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    # Where its models were at the start of the phase, once it's moved - its
    # moves are measured from there, and resetting it puts them back.
    starts: Mapped[list["GameUnitMoveStart"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitMoveStart.id"
    )

    @property
    def distance(self) -> float | None:
        # How far its furthest-moved model went, once it's moved (None for a
        # move recorded before distances were).
        return self.distance_link.distance if self.distance_link else None

    @distance.setter
    def distance(self, distance: float | None) -> None:
        self.distance_link = None if distance is None else GameUnitMoveDistance(distance=distance)


class GameUnitMoveStart(Base):
    # Where one of a moved unit's models was at the start of the movement
    # phase.
    __tablename__ = "game_unit_move_starts"

    id: Mapped[int] = mapped_column(primary_key=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("game_unit_moves.id", ondelete="CASCADE"))
    unit_model_id: Mapped[int] = mapped_column(
        ForeignKey("unit_models.id", ondelete="CASCADE")
    )
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    rotation: Mapped[float] = mapped_column(Float, default=0)


class GameUnitMoveDistance(Base):
    # How far a unit's move took its furthest-moved model (e.g. for whether
    # it moved less than 3" when it shoots). Its own table rather than a column,
    # so existing databases pick it up without a migration.
    __tablename__ = "game_unit_move_distances"

    move_id: Mapped[int] = mapped_column(
        ForeignKey("game_unit_moves.id", ondelete="CASCADE"), primary_key=True
    )
    distance: Mapped[float] = mapped_column(Float)


class GameUnitShot(Base):
    # A unit shooting in a shooting phase (battle round and whose turn): its
    # target, and what it did (see app/services/in_game/shooting.py).
    __tablename__ = "game_unit_shots"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    # Gone with either unit if it's taken out of its list.
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    target_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    total_damage: Mapped[int] = mapped_column(Integer)
    models_destroyed: Mapped[int] = mapped_column(Integer)


class GameModelDamage(Base):
    # Wounds a model has lost in a game - and whether it's destroyed: then
    # it's taken off the battlefield (its position removed). Only this game:
    # the model stays in its list.
    __tablename__ = "game_model_damage"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    wounds_lost: Mapped[int] = mapped_column(Integer, default=0)
    destroyed: Mapped[bool] = mapped_column(Boolean, default=False)


class GameUnitCharge(Base):
    # A unit's charge in one charge phase (battle round and whose turn): its
    # 2D6 charge roll (rolled first, kept for the phase), and once it's made
    # the charge, its target (see app/services/in_game/charging.py).
    __tablename__ = "game_unit_charges"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    first_die: Mapped[int] = mapped_column(Integer)
    second_die: Mapped[int] = mapped_column(Integer)
    target_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def roll(self) -> int:
        return self.first_die + self.second_die


class GameUnitPileIn(Base):
    # A unit piling in at the start of one fight phase (battle round and
    # whose turn) - see app/services/in_game/fighting.py.
    __tablename__ = "game_unit_pile_ins"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)


class GamePileInDone(Base):
    # A player has finished piling in at the start of one fight phase.
    __tablename__ = "game_pile_ins_done"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    seat: Mapped[int] = mapped_column(Integer)


class GameUnitFight(Base):
    # A unit fighting in one fight phase (battle round and whose turn): whose
    # unit it is (activations alternate - see app/services/in_game/fighting.py),
    # its target, and what it did. In the order they fought.
    __tablename__ = "game_unit_fights"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    target_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    seat: Mapped[int] = mapped_column(Integer)
    fights_first: Mapped[bool] = mapped_column(Boolean, default=False)
    total_damage: Mapped[int] = mapped_column(Integer)
    models_destroyed: Mapped[int] = mapped_column(Integer)

    consolidation: Mapped["GameUnitConsolidation | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class GameUnitConsolidation(Base):
    # After a unit fights, its consolidation: made (`moved`) or skipped. Until
    # there's one, the next unit can't be picked to fight. Its own table
    # rather than a column, so existing databases pick it up.
    __tablename__ = "game_unit_consolidations"

    fight_id: Mapped[int] = mapped_column(
        ForeignKey("game_unit_fights.id", ondelete="CASCADE"), primary_key=True
    )
    moved: Mapped[bool] = mapped_column(Boolean, default=False)


class GameRuleChoice(Base):
    # A player's choice for an army rule with options, for one battle round
    # (e.g. Doctrina Imperatives: the Protector Imperative) - made at the start
    # of the round (see app/services/in_game/battle_round.py), and active for
    # their units with that rule when they attack or are attacked.
    __tablename__ = "game_rule_choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    seat: Mapped[int] = mapped_column(Integer)
    faction_ability_id: Mapped[int] = mapped_column(
        ForeignKey("faction_abilities.id", ondelete="CASCADE")
    )
    option: Mapped[str] = mapped_column(String(255))


# Where a unit starts the battle, if not on the battlefield: in Strategic
# Reserves, or embarked in a transport (see
# app/services/in_game/battle_formations.py).
FORMATION_PLACES = ("reserves", "embarked")
# A Strategic Reserves unit that didn't arrive by the end of the third battle
# round: destroyed.
RESERVES_DESTROYED = "destroyed"


class GameBattleFormation(Base):
    # A unit that isn't deployed: in Strategic Reserves, or embarked in a
    # friendly transport (`transport_unit_id`). Units without one are deployed.
    __tablename__ = "game_battle_formations"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    place: Mapped[str] = mapped_column(String(32))
    transport_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )


class GameFormationsDone(Base):
    # A player has declared their battle formations.
    __tablename__ = "game_formations_done"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)


class GameMovementEnded(Base):
    # The player whose turn it is has finished moving in this movement phase:
    # its end, when their opponent can use Rapid Ingress (see
    # app/services/in_game/reinforcements.py).
    __tablename__ = "game_movements_ended"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)


class GameReanimation(Base):
    # A unit's Reanimation Protocols activating at the end of its owner's
    # command phase (battle round and whose turn): its D3 roll, and how many
    # wounds that restored to wounded models and how many destroyed models it
    # returned (see app/services/in_game/reanimation.py).
    __tablename__ = "game_reanimations"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    roll: Mapped[int] = mapped_column(Integer)
    healed: Mapped[int] = mapped_column(Integer, default=0)
    returned: Mapped[int] = mapped_column(Integer, default=0)


class GameCommandChoice(Base):
    # An option a player selected for one of their units' abilities in their
    # Command phase (battle round, seat): the unit with the ability, which
    # ability and option - and, for one that applies to another unit (e.g.
    # Rod of the War Forge), that unit (see app/services/in_game/command_phase.py).
    __tablename__ = "game_command_choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    seat: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    ability: Mapped[str] = mapped_column(String(255))
    option: Mapped[str] = mapped_column(String(255))
    target_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )


class GameCommandHeal(Base):
    # A model regaining lost wounds at the start of its owner's Command phase
    # (e.g. Self-repair Mechanisms): its roll, and how many it regained.
    __tablename__ = "game_command_heals"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    seat: Mapped[int] = mapped_column(Integer)
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    ability: Mapped[str] = mapped_column(String(255))
    roll: Mapped[int] = mapped_column(Integer)
    healed: Mapped[int] = mapped_column(Integer, default=0)
