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
    # Who goes first: rolled off once everything is set up (see
    # app/services/in_game/first_turn.py) - None until then.
    first_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    # Units embarking and disembarking during the battle.
    unit_transits: Mapped[list["GameUnitTransit"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameUnitTransit.id"
    )
    # Transports destroyed with units inside, and those units' emergency
    # disembarking.
    transport_wrecks: Mapped[list["GameTransportWreck"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameTransportWreck.id"
    )
    emergency_disembarks: Mapped[list["GameEmergencyDisembark"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameEmergencyDisembark.id"
    )
    emergency_rolls: Mapped[list["GameEmergencyRoll"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameEmergencyRoll.id"
    )
    # Teleport Homer tokens, and who's finished setting theirs up.
    teleport_homers: Mapped[list["GameTeleportHomer"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameTeleportHomer.id"
    )
    teleport_homers_done: Mapped[list["GameTeleportHomersDone"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameTeleportHomersDone.id"
    )
    # Models repaired in Command phases (see app/services/in_game/repair.py).
    repairs: Mapped[list["GameRepair"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameRepair.id"
    )
    # Reactive moves units can make, or made (see
    # app/services/in_game/reactive_move.py).
    reactive_moves: Mapped[list["GameReactiveMove"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameReactiveMove.id"
    )
    # Units disembarking from transports, and from which (see
    # app/services/in_game/embarked.py).
    disembarkations: Mapped[list["GameDisembarkation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameDisembarkation.id"
    )
    # Enemy units transports picked out for the units that disembarked from
    # them (Fire Support - see app/seeds/factions/adeptus_mechanicus/fire_support.py).
    fire_support_targets: Mapped[list["GameFireSupport"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameFireSupport.id"
    )
    # The roll-off for who goes first, every roll (ties are re-rolled).
    first_turn_rolls: Mapped[list["GameFirstTurnRoll"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameFirstTurnRoll.id"
    )
    # The players done making Scouts moves, before the battle.
    scouts_done: Mapped[list["GameScoutsDone"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameScoutsDone.id"
    )
    # Transports' Firing Deck uses: the units in them then (see
    # app/services/in_game/shooting.py).
    firing_deck_uses: Mapped[list["GameFiringDeckUse"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameFiringDeckUse.id"
    )
    # Destroyed models not yet removed from the battlefield (e.g. Duty in
    # Death - see app/services/in_game/duty_in_death.py).
    lingering_models: Mapped[list["GameLingeringModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameLingeringModel.id"
    )
    # Psychic abilities used.
    psychic_uses: Mapped[list["GamePsychicUse"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GamePsychicUse.id",
        foreign_keys="GamePsychicUse.game_id",
    )
    # Objectives secured (sticky) by a player.
    secured_objectives: Mapped[list["GameSecuredObjective"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameSecuredObjective.id"
    )
    # Objectives players have selected for their rules (e.g. Acquisition At
    # Any Cost - see app/services/in_game/selected_objectives.py).
    selected_objectives: Mapped[list["GameSelectedObjective"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameSelectedObjective.id"
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
    # What happened each turn, for missions (see
    # app/services/in_game/turn_record.py): models destroyed, and how things
    # stood at the start of each turn.
    models_destroyed: Mapped[list["GameModelDestroyed"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameModelDestroyed.id"
    )
    turn_start_control: Mapped[list["GameTurnStartControl"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameTurnStartControl.id"
    )
    turn_start_objectives: Mapped[list["GameTurnStartOnObjective"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameTurnStartOnObjective.id"
    )
    turn_start_areas: Mapped[list["GameTurnStartInArea"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameTurnStartInArea.id"
    )
    # Choices made for secondary cards when drawn (see
    # app/services/in_game/mission_state.py).
    card_choices: Mapped[list["GameCardChoice"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameCardChoice.id"
    )
    # Missions' operation markers, the choices they prompt players for, the
    # units they mark (see app/services/in_game/mission_state.py).
    operation_markers: Mapped[list["GameOperationMarker"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameOperationMarker.id"
    )
    mission_prompts: Mapped[list["GameMissionPrompt"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameMissionPrompt.id"
    )
    marked_units: Mapped[list["GameMarkedUnit"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameMarkedUnit.id"
    )
    # Actions units have done (see app/services/in_game/actions.py).
    actions: Mapped[list["GameAction"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameAction.id"
    )
    # Automatic scoring (see app/services/in_game/scoring.py): the scoring
    # moments evaluated, and tactical secondaries offered to be claimed.
    scoring_steps: Mapped[list["GameScoringStep"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameScoringStep.id"
    )
    claim_offers: Mapped[list["GameClaimOffer"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameClaimOffer.id"
    )
    # Battle-shock tests taken (or to take) - see app/services/in_game/battle_shock.py.
    battle_shock_tests: Mapped[list["GameBattleShockTest"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameBattleShockTest.id"
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
    # Why it was scored, for VP scored automatically: each mission line met.
    reasons: Mapped[list["GameScoreReason"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="GameScoreReason.id"
    )


class GameScoreReason(Base):
    # A line of a mission card that scored, and its VP.
    __tablename__ = "game_score_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_score_id: Mapped[int] = mapped_column(ForeignKey("game_scores.id"))
    text: Mapped[str] = mapped_column(String)
    points: Mapped[int] = mapped_column(Integer)


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
    target_link: Mapped["GameStratagemTarget | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def target_unit_id(self) -> int | None:
        # The unit it was used on, for a stratagem whose game action targets
        # one (e.g. Gunship Extraction).
        return self.target_link.unit_id if self.target_link else None


class GameStratagemTarget(Base):
    # The unit a stratagem use targeted (one at most). Its own table rather
    # than a column on game_stratagem_uses, so existing databases pick it up
    # without a migration.
    __tablename__ = "game_stratagem_targets"

    stratagem_use_id: Mapped[int] = mapped_column(
        ForeignKey("game_stratagem_uses.id"), primary_key=True
    )
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))


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


class GameSecuredObjective(Base):
    # An objective a player has secured (e.g. with Raise the Banner): it stays
    # theirs while their opponent has no OC on it - and is no longer secured
    # once they do (see app/services/in_game/objectives.py).
    __tablename__ = "game_secured_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("terrain_objectives.id", ondelete="CASCADE")
    )
    seat: Mapped[int] = mapped_column(Integer)


class GameSelectedObjective(Base):
    # An objective a player selected for a rule (`name` - e.g. "Acquisition")
    # in their Command phase (battle round), until the start of their next
    # one; `extra`: one added to it by a stratagem (e.g. Infoslave Skull)
    # rather than the rule's own selection (see
    # app/services/in_game/selected_objectives.py).
    __tablename__ = "game_selected_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("terrain_objectives.id", ondelete="CASCADE")
    )
    battle_round: Mapped[int] = mapped_column(Integer)
    extra: Mapped[bool] = mapped_column(Boolean, default=False)


class GameTransportWreck(Base):
    # Where a destroyed transport's model was, while units were embarked in
    # it - they emergency disembark round it (see
    # app/services/in_game/emergency.py).
    __tablename__ = "game_transport_wrecks"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    transport_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    rotation: Mapped[float] = mapped_column(Float, default=0)


class GameEmergencyDisembark(Base):
    # A unit that was embarked in a transport when it was destroyed, which
    # must emergency disembark (`placed` once it has).
    __tablename__ = "game_emergency_disembarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    transport_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    placed: Mapped[bool] = mapped_column(Boolean, default=False)


class GameEmergencyRoll(Base):
    # A roll after an emergency disembark: a set-up model's hazard roll
    # ("hazard", and the wounds it took), the destroyed transport's Deadly
    # Demise ("deadly_demise"), and on a 6 the mortal wounds rolled for each
    # unit within 6" ("deadly_demise_wounds", by one of its models).
    __tablename__ = "game_emergency_rolls"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    transport_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    unit_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("unit_models.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    roll: Mapped[int] = mapped_column(Integer)
    wounds: Mapped[int] = mapped_column(Integer, default=0)


class GameTeleportHomer(Base):
    # A unit's Teleport Homer token, set up at the start of the battle (see
    # app/seeds/factions/space_marines/teleport_homer.py): `status` "placed" while it's on
    # the battlefield, then "used" or "removed".
    __tablename__ = "game_teleport_homers"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="placed")


class GameTeleportHomersDone(Base):
    # A player has finished setting up their Teleport Homer tokens.
    __tablename__ = "game_teleport_homers_done"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)


class GameRepair(Base):
    # A model repaired by a unit's ability in one Command phase (battle round
    # and whose turn) - and the Feel No Pain it has until its player's next
    # Command phase, if any (a VEHICLE's).
    __tablename__ = "game_repairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    source_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    feel_no_pain: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GameReactiveMove(Base):
    # A unit that can make a reactive move (e.g. Tactica Obliqua) in one phase
    # (battle round and whose turn), because `trigger_unit_id` ended a move
    # near it: its roll for how far, once rolled, and whether it's made it.
    __tablename__ = "game_reactive_moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    trigger_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    made: Mapped[bool] = mapped_column(Boolean, default=False)


class GameDisembarkation(Base):
    # A unit disembarking from a transport, in one turn (battle round and
    # whose turn).
    __tablename__ = "game_disembarkations"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    transport_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)


class GameFireSupport(Base):
    # An enemy unit a transport scored hits against, picked out for the units
    # that disembarked from it, for the rest of one Shooting phase (battle
    # round and whose turn).
    __tablename__ = "game_fire_support"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    transport_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    target_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)


class GameFirstTurnRoll(Base):
    # One player's D6 in the roll-off for who goes first (`attempt`: 1, then
    # 2... after each tie).
    __tablename__ = "game_first_turn_rolls"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    attempt: Mapped[int] = mapped_column(Integer)
    seat: Mapped[int] = mapped_column(Integer)
    roll: Mapped[int] = mapped_column(Integer)


class GameScoutsDone(Base):
    # A player has finished making Scouts moves, before the battle.
    __tablename__ = "game_scouts_done"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)


class GameFiringDeckUse(Base):
    # A unit embarked in a transport that used its Firing Deck, in one turn
    # (battle round and whose turn) - it isn't eligible to shoot until the end
    # of that turn.
    __tablename__ = "game_firing_deck_uses"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    transport_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)


class GameLingeringModel(Base):
    # A destroyed model left on the battlefield for now (see
    # app/services/in_game/duty_in_death.py), in one phase (battle round and
    # whose turn) - removed when its unit has fought, or at the end of the
    # phase.
    __tablename__ = "game_lingering_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    # The unit whose attacks destroyed it, if any.
    destroyed_by_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )


class GamePsychicUse(Base):
    # A PSYKER unit using a psychic ability (see
    # app/services/in_game/psychic.py): when (battle round, whose turn,
    # phase), its psychic roll, and the enemy unit it picked (Soul Sight).
    __tablename__ = "game_psychic_uses"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    ability: Mapped[str] = mapped_column(String(255))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32))
    roll: Mapped[int] = mapped_column(Integer)
    target_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )


class GameUnitTransit(Base):
    # A unit embarking in or disembarking from a transport during the battle
    # (`kind`: "embarked" or "disembarked" - and "shock_disembarked" too, for
    # a shock disembark move), in one movement phase (battle round and whose
    # turn) - it can't do the other in the same phase.
    __tablename__ = "game_unit_transits"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))


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
    # returned (see app/seeds/factions/necrons/reanimation.py).
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


class GameBattleShockTest(Base):
    # A Battle-shock test a unit takes (battle round, whose turn, phase): why
    # ("battle_shock_step", or a rule or stratagem's name), any modifier to
    # the roll - and once taken, its 2D6 (none if Insane Bravery passed it)
    # and whether it passed. A unit is Battle-shocked while its latest test
    # taken failed (see app/services/in_game/battle_shock.py).
    __tablename__ = "game_battle_shock_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(255))
    modifier: Mapped[int] = mapped_column(Integer, default=0)
    first_die: Mapped[int | None] = mapped_column(Integer, nullable=True)
    second_die: Mapped[int | None] = mapped_column(Integer, nullable=True)
    insane_bravery: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Mortal wounds it suffered for failing (e.g. Delirium), if any (its own
    # table: see GameBattleShockWounds).
    wounds: Mapped["GameBattleShockWounds | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )


class GameBattleShockWounds(Base):
    # Mortal wounds a unit suffered for failing a Battle-shock test (e.g.
    # Delirium's D3): the roll - its own table, so existing databases pick it
    # up without a migration.
    __tablename__ = "game_battle_shock_wounds"

    test_id: Mapped[int] = mapped_column(
        ForeignKey("game_battle_shock_tests.id"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(64))
    roll: Mapped[int] = mapped_column(Integer)


class GameModelDestroyed(Base):
    # A model destroyed (battle round, whose turn, phase): its unit, the unit
    # whose attacks destroyed it (None: none - e.g. its own Hazardous weapon,
    # or not arriving from Reserves), and whether that destroyed its unit
    # (it was the last of it on the battlefield).
    __tablename__ = "game_models_destroyed"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    unit_model_id: Mapped[int] = mapped_column(ForeignKey("unit_models.id", ondelete="CASCADE"))
    destroyed_by_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )
    unit_destroyed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Its unit was destroyed by a unit within range of an objective then (its
    # own table: see GameKillOnObjective).
    on_objective: Mapped["GameKillOnObjective | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )
    # Its unit was destroyed within range of objectives its player controlled
    # (e.g. for Cached Acquisition) - their own table, likewise.
    controlled_objectives: Mapped[list["GameDestroyedOnObjective"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class GameKillOnObjective(Base):
    # A unit destroyed by a unit that was within range of one or more
    # objectives at the time (e.g. for Purge and Secure) - its own table, so
    # existing databases pick it up without a migration.
    __tablename__ = "game_kills_on_objective"

    model_destroyed_id: Mapped[int] = mapped_column(
        ForeignKey("game_models_destroyed.id"), primary_key=True
    )


class GameDestroyedOnObjective(Base):
    # An objective a destroyed unit was within range of, that its player
    # controlled, when its last model was destroyed.
    __tablename__ = "game_destroyed_on_objectives"

    model_destroyed_id: Mapped[int] = mapped_column(
        ForeignKey("game_models_destroyed.id"), primary_key=True
    )
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("terrain_objectives.id", ondelete="CASCADE"), primary_key=True
    )


class GameTurnStartControl(Base):
    # Who controlled an objective at the start of a turn (None: no one).
    __tablename__ = "game_turn_start_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    objective_id: Mapped[int] = mapped_column(ForeignKey("terrain_objectives.id"))
    controller: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GameTurnStartOnObjective(Base):
    # A unit within range of an objective (a model on one of its terrain
    # areas) at the start of a turn.
    __tablename__ = "game_turn_start_on_objective"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    objective_id: Mapped[int] = mapped_column(ForeignKey("terrain_objectives.id"))


class GameTurnStartInArea(Base):
    # A unit within a terrain area (a model over it) at the start of a turn.
    __tablename__ = "game_turn_start_in_area"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    area_id: Mapped[int] = mapped_column(ForeignKey("terrain_areas.id"))


class GameScoringStep(Base):
    # A scoring moment that's been evaluated (battle round, whose turn, and
    # which: "command_end", "turn_end" or "battle_end").
    __tablename__ = "game_scoring_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    timing: Mapped[str] = mapped_column(String(32))


class GameClaimOffer(Base):
    # A tactical secondary that was completed at a scoring moment: its VP
    # then, and why - for its holder to claim (scored, and the card done) or
    # hold (it stays in their hand, to be checked again at later moments).
    __tablename__ = "game_claim_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    game_secondary_id: Mapped[int] = mapped_column(ForeignKey("game_secondaries.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    timing: Mapped[str] = mapped_column(String(32))
    points: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[str] = mapped_column(String)
    # "pending", "claimed" or "held".
    status: Mapped[str] = mapped_column(String(16), default="pending")


class GameAction(Base):
    # An action a unit started (battle round, whose turn, phase): which, on
    # which objective or terrain area, and how it went - "started" (it
    # completes later), "completed" or "failed".
    __tablename__ = "game_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(64))
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("terrain_objectives.id"), nullable=True
    )
    area_id: Mapped[int | None] = mapped_column(ForeignKey("terrain_areas.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="started")
    # The enemy unit it's done on, for one done on a unit (its own table: see
    # GameActionUnitTarget).
    unit_target: Mapped["GameActionUnitTarget | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )

    @property
    def target_unit_id(self) -> int | None:
        return self.unit_target.unit_id if self.unit_target else None


class GameActionUnitTarget(Base):
    # The unit an action is done on (e.g. Surveil the Foe's enemy unit) - its
    # own table, so existing databases pick it up without a migration.
    __tablename__ = "game_action_unit_targets"

    action_id: Mapped[int] = mapped_column(ForeignKey("game_actions.id"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))


class GameOperationMarker(Base):
    # One of a player's operation markers: within range of an objective, or
    # within a terrain area - placed by a mission (`source`: an action's name,
    # "Locate and Deny" or "Consecrate"), when, and when it was removed from
    # the battlefield (none: it's still there).
    __tablename__ = "game_operation_markers"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64))
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("terrain_objectives.id"), nullable=True
    )
    area_id: Mapped[int | None] = mapped_column(ForeignKey("terrain_areas.id"), nullable=True)
    placed_round: Mapped[int] = mapped_column(Integer)
    placed_turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    removed_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    removed_turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GameMissionPrompt(Base):
    # A choice a mission needs a player to make (battle round, whose turn):
    # `kind` - "place_markers" (Locate and Deny, at the start of the battle),
    # "consecrate" (end of their turn), "condemn" (Punishment, start of their
    # turn) or "remove_marker" (a sensor sweep: `action_id` is its action) -
    # and whether it's answered.
    __tablename__ = "game_mission_prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_actions.id", ondelete="CASCADE"), nullable=True
    )
    answered: Mapped[bool] = mapped_column(Boolean, default=False)


class GameMarkedUnit(Base):
    # A unit a mission marks (by `seat`'s mission): "condemned" (Punishment,
    # until the start of that player's next turn), "surveilled" (Surveil the
    # Foe, until the end of the turn) or "consecration" (Consecrate, until it
    # consecrates an objective) - from when (battle round, whose turn).
    __tablename__ = "game_marked_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    seat: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended: Mapped[bool] = mapped_column(Boolean, default=False)


class GameCardChoice(Base):
    # A choice made for a secondary card (battle round, whose turn): its
    # beacon unit (Beacon), a unit guarding an objective (Burden of Trust,
    # until the start of its holder's next turn), or its tempting target (A
    # Tempting Target, chosen by its holder's opponent).
    __tablename__ = "game_card_choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    game_secondary_id: Mapped[int] = mapped_column(
        ForeignKey("game_secondaries.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("terrain_objectives.id"), nullable=True
    )
    battle_round: Mapped[int] = mapped_column(Integer)
    turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
