from __future__ import annotations

import contextvars
import itertools
import typing
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from app.services import dice

if TYPE_CHECKING:
    from app.models.army_list import ArmyList
    from app.models.disposition import Disposition
    from app.models.mission import PrimaryMission, SecondaryMission
    from app.models.stratagem import Stratagem
    from app.models.terrain import TerrainLayout
    from app.models.user import User

# A game's state, as plain Python objects: played in memory (see
# app/engine/store.py), not through the database. Each class is one kind
# of record - a player, a unit's move, a model's position - held in lists on
# the Game (or on its players, and so on), in the order they were made.
#
# What a record points to in the catalog - a list, a unit, a stratagem - is
# held by id (unit_id, unit_model_id, ...); the few it refers to as objects
# (a player's army list, a secondary's mission card, ...) are listed in each
# class's _refs with the id kept alongside, so a save need only hold the ids
# (see app/engine/saves.py).

# A turn's phases, in order.
PHASES = ("command", "movement", "shooting", "charge", "fight")
BATTLE_ROUNDS = 5
# A game is set up, then its armies are deployed (if its terrain layout has
# deployment zones - see app/services/in_game/deployment.py), then it's played.
GAME_STATUSES = ("setup", "deployment", "in_progress", "finished")
SECONDARY_MODES = ("fixed", "tactical")
SECONDARY_STATUSES = ("active", "achieved", "discarded")
SCORE_KINDS = ("primary", "secondary")
# How a unit moves in its movement phase (see app/services/in_game/movement.py). Not
# moving at all is remaining stationary.
MOVE_KINDS = ("normal", "advance", "fall_back")
# Where a unit starts the battle, if not on the battlefield: in Strategic
# Reserves, or embarked in a transport (see
# app/services/in_game/battle_formations.py).
FORMATION_PLACES = ("reserves", "embarked")
# A Strategic Reserves unit that didn't arrive by the end of the third battle
# round: destroyed.
RESERVES_DESTROYED = "destroyed"

# The catalog classes records refer to, for resolving their fields' types
# (they're only imported for type checking).
_CATALOG_TYPES = {
    name: object
    for name in (
        "ArmyList", "Disposition", "PrimaryMission", "SecondaryMission", "Stratagem",
        "TerrainLayout", "User",
    )
}

# Records' ids, in the order records are made (so sorting by id is sorting
# by when): counted by the game being played (Game.record_ids - so replaying
# it from a save makes the same ids), or - with none bound, e.g. while a new
# game's being put together - by the process.
_ids = itertools.count(1)
_playing: contextvars.ContextVar[Game | None] = contextvars.ContextVar("playing", default=None)


def next_id() -> int:
    game = _playing.get()
    if game is None:
        return next(_ids)
    game.record_ids += 1
    return game.record_ids


def playing(game: Game | None) -> contextvars.Token:
    # The game whose records are being made (see app/engine/context.py).
    return _playing.set(game)


def stop_playing(token: contextvars.Token) -> None:
    _playing.reset(token)


def ids_from(start: int) -> None:
    # Ids from `start` on (at least): past every id in a restored save.
    global _ids
    current = next(_ids)
    _ids = itertools.count(max(current, start))


# Games' own ids, one after another (and past every saved game's - see
# app/engine/store.py).
_game_ids = itertools.count(1)


def next_game_id() -> int:
    return next(_game_ids)


def game_ids_from(start: int) -> None:
    global _game_ids
    current = next(_game_ids)
    _game_ids = itertools.count(max(current, start))


class Children(list):
    # A record's list of records that point back to it (e.g. a player's
    # secondaries: each card's .player): set as they're added.
    __slots__ = ("owner", "back")

    def __init__(self, owner, back: str, items=()) -> None:
        super().__init__()
        self.owner, self.back = owner, back
        self.extend(items)

    def _adopt(self, item) -> None:
        object.__setattr__(item, self.back, self.owner)

    def append(self, item) -> None:
        self._adopt(item)
        super().append(item)

    def insert(self, index, item) -> None:
        self._adopt(item)
        super().insert(index, item)

    def extend(self, items) -> None:
        items = list(items)
        for item in items:
            self._adopt(item)
        super().extend(items)

    def __iadd__(self, items):
        self.extend(items)
        return self

    def __setitem__(self, index, value) -> None:
        for item in value if isinstance(index, slice) else [value]:
            self._adopt(item)
        super().__setitem__(index, value)

    def __reduce_ex__(self, protocol):
        return (Children, (self.owner, self.back, list(self)))


class State:
    # Catalog objects a record refers to: {attribute: (the attribute holding
    # its id, its catalog class)}. Setting the object sets the id too.
    _refs: ClassVar[dict[str, tuple[str, str]]] = {}
    # Lists of records that point back to this one: {attribute: the
    # attribute on each pointing back}.
    _children: ClassVar[dict[str, str]] = {}

    def __setattr__(self, name: str, value: Any) -> None:
        back = self._children.get(name)
        if back is not None:
            value = Children(self, back, value or ())
        object.__setattr__(self, name, value)
        ref = self._refs.get(name)
        if ref is not None and value is not None:
            object.__setattr__(self, ref[0], value.id)

    @classmethod
    def _field_types(cls) -> dict[str, Any]:
        # Each field's type, resolved (cached per class).
        cached = cls.__dict__.get("_types")
        if cached is None:
            cached = typing.get_type_hints(cls, globals(), _CATALOG_TYPES)
            type.__setattr__(cls, "_types", cached)
        return cached

    def to_dict(self) -> dict[str, Any]:
        # Its fields, as JSON-able values: records nested, catalog objects
        # left out (their ids are kept).
        out: dict[str, Any] = {}
        for f in fields(self):
            if f.name in self._refs:
                continue
            value = getattr(self, f.name)
            if isinstance(value, State):
                value = value.to_dict()
            elif isinstance(value, list):
                value = [v.to_dict() if isinstance(v, State) else v for v in value]
            elif isinstance(value, datetime):
                value = value.isoformat()
            out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        # As to_dict made it (catalog objects are left None: see
        # app/engine/saves.py).
        types = cls._field_types()
        kwargs: dict[str, Any] = {}
        for name, value in data.items():
            kind = _record_class(types[name])
            if kind is not None and value is not None:
                value = (
                    [kind.from_dict(v) for v in value]
                    if isinstance(value, list)
                    else kind.from_dict(value)
                )
            elif value is not None and _is_datetime(types[name]):
                value = datetime.fromisoformat(value)
            kwargs[name] = value
        return cls(**kwargs)

    def records(self):
        # It and every record nested in it, depth first.
        yield self
        for f in fields(self):
            if f.name in self._refs:
                continue
            value = getattr(self, f.name)
            if isinstance(value, State):
                yield from value.records()
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, State):
                        yield from v.records()


def _record_class(kind) -> type[State] | None:
    # The State class a field holds (alone, optionally, or in a list), if any.
    if isinstance(kind, type):
        return kind if issubclass(kind, State) else None
    for arg in typing.get_args(kind):
        found = _record_class(arg)
        if found is not None:
            return found
    return None


def _is_datetime(kind) -> bool:
    return kind is datetime or datetime in typing.get_args(kind)


@dataclass(eq=False, kw_only=True)
class Game(State):
    id: int = field(default_factory=next_game_id)
    created_at: datetime | None = None
    status: str = 'setup'
    # Seats are 1 and 2 (see GamePlayer.seat).
    attacker_seat: int = None  # type: ignore[assignment]
    # Who goes first: rolled off once everything is set up (see
    # app/services/in_game/first_turn.py) - None until then.
    first_seat: int | None = None
    # 0 until the game starts.
    battle_round: int = 0
    turn_seat: int | None = None
    phase: str | None = None
    # Its dice: every roll comes from a stream seeded with this, and how many
    # rolls it's made so far (see app/services/dice.py).
    rng_seed: int = field(default_factory=dice.new_seed)
    rng_rolls: int = 0
    # The last id given to one of its records (see next_id).
    record_ids: int = 0

    players: list['GamePlayer'] = field(default_factory=list)
    layout_link: GameTerrainLayout | None = None
    # Units set aside when battle formations are declared (in Strategic
    # Reserves, or embarked in a transport), and the players who've declared.
    battle_formations: list['GameBattleFormation'] = field(default_factory=list)
    # Units embarking and disembarking during the battle.
    unit_transits: list['GameUnitTransit'] = field(default_factory=list)
    # Transports destroyed with units inside, and those units' emergency
    # disembarking.
    transport_wrecks: list['GameTransportWreck'] = field(default_factory=list)
    emergency_disembarks: list['GameEmergencyDisembark'] = field(default_factory=list)
    emergency_rolls: list['GameEmergencyRoll'] = field(default_factory=list)
    # Teleport Homer tokens, and who's finished setting theirs up.
    teleport_homers: list['GameTeleportHomer'] = field(default_factory=list)
    teleport_homers_done: list['GameTeleportHomersDone'] = field(default_factory=list)
    # Models repaired in Command phases (see app/services/in_game/repair.py).
    repairs: list['GameRepair'] = field(default_factory=list)
    # Reactive moves units can make, or made (see
    # app/services/in_game/reactive_move.py).
    reactive_moves: list['GameReactiveMove'] = field(default_factory=list)
    # Surge moves a rule let units make (see app/services/in_game/surge.py).
    surge_moves: list['GameSurgeMove'] = field(default_factory=list)
    # Units disembarking from transports, and from which (see
    # app/services/in_game/embarked.py).
    disembarkations: list['GameDisembarkation'] = field(default_factory=list)
    # Enemy units transports picked out for the units that disembarked from
    # them (Fire Support - see app/seeds/factions/adeptus_mechanicus/fire_support.py).
    fire_support_targets: list['GameFireSupport'] = field(default_factory=list)
    # The roll-off for who goes first, every roll (ties are re-rolled).
    first_turn_rolls: list['GameFirstTurnRoll'] = field(default_factory=list)
    # The players done making Scouts moves, before the battle.
    scouts_done: list['GameScoutsDone'] = field(default_factory=list)
    # Transports' Firing Deck uses: the units in them then (see
    # app/services/in_game/shooting.py).
    firing_deck_uses: list['GameFiringDeckUse'] = field(default_factory=list)
    # Destroyed models not yet removed from the battlefield (e.g. Duty in
    # Death - see app/services/in_game/duty_in_death.py).
    lingering_models: list['GameLingeringModel'] = field(default_factory=list)
    # Psychic abilities used.
    psychic_uses: list['GamePsychicUse'] = field(default_factory=list)
    # Objectives secured (sticky) by a player.
    secured_objectives: list['GameSecuredObjective'] = field(default_factory=list)
    # Who controls each objective, as determined at the end of the last phase
    # or turn (see app/services/in_game/objectives.py).
    objective_controls: list['GameObjectiveControl'] = field(default_factory=list)
    # Objectives players have selected for their rules (e.g. Acquisition At
    # Any Cost - see app/services/in_game/selected_objectives.py).
    selected_objectives: list['GameSelectedObjective'] = field(default_factory=list)
    formations_done: list['GameFormationsDone'] = field(default_factory=list)
    # Movement phases the player whose turn it was has finished (for Rapid
    # Ingress at the end of them).
    movements_ended: list['GameMovementEnded'] = field(default_factory=list)
    # Charge phases the player whose turn it was has finished charging in
    # (for Heroic Intervention at the end of them).
    charges_ended: list['GameChargeEnded'] = field(default_factory=list)
    # Options selected for abilities in command phases, and wounds healed at
    # their start.
    command_choices: list['GameCommandChoice'] = field(default_factory=list)
    command_heals: list['GameCommandHeal'] = field(default_factory=list)
    # What happened each turn, for missions (see
    # app/services/in_game/turn_record.py): models destroyed, and how things
    # stood at the start of each turn.
    models_destroyed: list['GameModelDestroyed'] = field(default_factory=list)
    turn_start_control: list['GameTurnStartControl'] = field(default_factory=list)
    turn_start_objectives: list['GameTurnStartOnObjective'] = field(default_factory=list)
    turn_start_areas: list['GameTurnStartInArea'] = field(default_factory=list)
    # Choices made for secondary cards when drawn (see
    # app/services/in_game/mission_state.py).
    card_choices: list['GameCardChoice'] = field(default_factory=list)
    # Missions' operation markers, the choices they prompt players for, the
    # units they mark (see app/services/in_game/mission_state.py).
    operation_markers: list['GameOperationMarker'] = field(default_factory=list)
    mission_prompts: list['GameMissionPrompt'] = field(default_factory=list)
    marked_units: list['GameMarkedUnit'] = field(default_factory=list)
    # Actions units have done (see app/services/in_game/actions.py).
    actions: list['GameAction'] = field(default_factory=list)
    # Automatic scoring (see app/services/in_game/scoring.py): the scoring
    # moments evaluated, and tactical secondaries offered to be claimed.
    scoring_steps: list['GameScoringStep'] = field(default_factory=list)
    claim_offers: list['GameClaimOffer'] = field(default_factory=list)
    # Battle-shock tests taken (or to take) - see app/services/in_game/battle_shock.py.
    battle_shock_tests: list['GameBattleShockTest'] = field(default_factory=list)
    # Reanimation Protocols activated at the end of command phases.
    reanimations: list['GameReanimation'] = field(default_factory=list)
    # Where each deployed model is on the battlefield.
    model_positions: list['GameModelPosition'] = field(default_factory=list)
    # How units have moved in movement phases.
    unit_moves: list['GameUnitMove'] = field(default_factory=list)
    # Wounds models have lost in this game, and which are destroyed.
    model_damage: list['GameModelDamage'] = field(default_factory=list)
    # Charges units have rolled for and made in charge phases.
    unit_charges: list['GameUnitCharge'] = field(default_factory=list)
    # Units' pile-ins at the start of fight phases, and which players have
    # finished piling in.
    unit_pile_ins: list['GameUnitPileIn'] = field(default_factory=list)
    pile_ins_done: list['GamePileInDone'] = field(default_factory=list)
    # Which units have fought in fight phases, at what, and in what order -
    # and players passing in the Fight step.
    unit_fights: list['GameUnitFight'] = field(default_factory=list)
    fight_passes: list['GameFightPass'] = field(default_factory=list)
    # Options chosen for army rules each battle round (e.g. which Doctrina
    # Imperative is active).
    rule_choices: list['GameRuleChoice'] = field(default_factory=list)
    # Which units have shot in shooting phases, and at what.
    unit_shots: list['GameUnitShot'] = field(default_factory=list)

    @property
    def layout(self) -> "TerrainLayout | None":
        # The terrain layout it's played on, if one fits the players'
        # dispositions (see app/services/in_game/terrain.py).
        return self.layout_link.layout if self.layout_link else None


@dataclass(eq=False, kw_only=True)
class GamePlayer(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    user_id: int = None  # type: ignore[assignment]
    list_id: int = None  # type: ignore[assignment]
    secondary_mode: str = None  # type: ignore[assignment]
    disposition_id: int | None = None
    primary_mission_id: int | None = None
    cp: int = 0

    user: User | None = None
    army_list: ArmyList | None = None
    disposition: Disposition | None = None
    primary_mission: PrimaryMission | None = None
    secondaries: list['GameSecondary'] = field(default_factory=list)
    scores: list['GameScore'] = field(default_factory=list)
    stratagem_uses: list['GameStratagemUse'] = field(default_factory=list)


@dataclass(eq=False, kw_only=True)
class GameSecondary(State):
    id: int = field(default_factory=next_id)
    game_player_id: int = None  # type: ignore[assignment]
    secondary_mission_id: int = None  # type: ignore[assignment]
    status: str = 'active'
    # Fixed secondaries stay active after being achieved - they can be scored
    # again in later turns.
    fixed: bool = False
    drawn_round: int = 0

    mission: SecondaryMission | None = None


@dataclass(eq=False, kw_only=True)
class GameScore(State):
    id: int = field(default_factory=next_id)
    game_player_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    kind: str = None  # type: ignore[assignment]
    points: int = None  # type: ignore[assignment]
    game_secondary_id: int | None = None

    # Why it was scored, for VP scored automatically: each mission line met.
    reasons: list['GameScoreReason'] = field(default_factory=list)


@dataclass(eq=False, kw_only=True)
class GameScoreReason(State):
    id: int = field(default_factory=next_id)
    game_score_id: int = None  # type: ignore[assignment]
    text: str = None  # type: ignore[assignment]
    points: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameStratagemUse(State):
    id: int = field(default_factory=next_id)
    game_player_id: int = None  # type: ignore[assignment]
    stratagem_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    phase: str = None  # type: ignore[assignment]
    cp: int = None  # type: ignore[assignment]

    stratagem: Stratagem | None = None
    target_link: GameStratagemTarget | None = None
    outcome_link: GameStratagemOutcome | None = None

    @property
    def outcome(self) -> str | None:
        # What it did, for one whose game action rolls dice or picks
        # something (e.g. Explosives: its six D6 and the mortal wounds).
        return self.outcome_link.text if self.outcome_link else None

    @property
    def choice_id(self) -> int | None:
        # What else its use targeted (see GameStratagemOutcome).
        return self.outcome_link.choice_id if self.outcome_link else None

    @property
    def target_unit_id(self) -> int | None:
        # The unit it was used on, for a stratagem whose game action targets
        # one (e.g. Gunship Extraction).
        return self.target_link.unit_id if self.target_link else None


@dataclass(eq=False, kw_only=True)
class GameStratagemTarget(State):
    stratagem_use_id: int | None = None
    unit_id: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameStratagemOutcome(State):
    stratagem_use_id: int | None = None
    text: str | None = None
    choice_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameModelPosition(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    # Gone with the model if it's taken out of its list.
    unit_model_id: int = None  # type: ignore[assignment]
    x: float = None  # type: ignore[assignment]
    y: float = None  # type: ignore[assignment]
    rotation: float = 0


@dataclass(eq=False, kw_only=True)
class GameUnitMove(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    # Gone with the unit if it's taken out of its list.
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    kind: str = None  # type: ignore[assignment]
    advance_roll: int | None = None
    completed: bool = False

    distance_link: GameUnitMoveDistance | None = None
    # Where its models were at the start of the phase, once it's moved - its
    # moves are measured from there, and resetting it puts them back.
    starts: list['GameUnitMoveStart'] = field(default_factory=list)

    @property
    def distance(self) -> float | None:
        # How far its furthest-moved model went, once it's moved (None for a
        # move recorded before distances were).
        return self.distance_link.distance if self.distance_link else None

    @distance.setter
    def distance(self, distance: float | None) -> None:
        self.distance_link = None if distance is None else GameUnitMoveDistance(distance=distance)


@dataclass(eq=False, kw_only=True)
class GameUnitMoveStart(State):
    id: int = field(default_factory=next_id)
    move_id: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    x: float = None  # type: ignore[assignment]
    y: float = None  # type: ignore[assignment]
    rotation: float = 0


@dataclass(eq=False, kw_only=True)
class GameUnitMoveDistance(State):
    move_id: int | None = None
    distance: float = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameUnitShot(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    # Gone with either unit if it's taken out of its list.
    unit_id: int = None  # type: ignore[assignment]
    target_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    total_damage: int = None  # type: ignore[assignment]
    models_destroyed: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameModelDamage(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    wounds_lost: int = 0
    destroyed: bool = False


@dataclass(eq=False, kw_only=True)
class GameUnitCharge(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    first_die: int = None  # type: ignore[assignment]
    second_die: int = None  # type: ignore[assignment]
    target_unit_id: int | None = None
    completed: bool = False
    # Its other charge targets, beyond `target_unit_id` (11.04: one or more).
    extra_targets: list['GameChargeTarget'] = field(default_factory=list)

    @property
    def roll(self) -> int:
        return self.first_die + self.second_die

    @property
    def target_unit_ids(self) -> list[int]:
        # Every charge target, once it's charged.
        first = [self.target_unit_id] if self.target_unit_id is not None else []
        return first + [t.unit_id for t in self.extra_targets]


@dataclass(eq=False, kw_only=True)
class GameChargeTarget(State):
    charge_id: int | None = None
    unit_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameUnitPileIn(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GamePileInDone(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameUnitFight(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    target_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    fights_first: bool = False
    total_damage: int = None  # type: ignore[assignment]
    models_destroyed: int = None  # type: ignore[assignment]

    consolidation: GameUnitConsolidation | None = None


@dataclass(eq=False, kw_only=True)
class GameFightPass(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    fights: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameUnitConsolidation(State):
    fight_id: int | None = None
    moved: bool = False


@dataclass(eq=False, kw_only=True)
class GameRuleChoice(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    faction_ability_id: int = None  # type: ignore[assignment]
    option: str = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameBattleFormation(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    place: str = None  # type: ignore[assignment]
    transport_unit_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameSecuredObjective(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    objective_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameObjectiveControl(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    objective_id: int = None  # type: ignore[assignment]
    seat: int | None = None


@dataclass(eq=False, kw_only=True)
class GameSelectedObjective(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    name: str = None  # type: ignore[assignment]
    objective_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    extra: bool = False


@dataclass(eq=False, kw_only=True)
class GameTransportWreck(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    transport_unit_id: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    x: float = None  # type: ignore[assignment]
    y: float = None  # type: ignore[assignment]
    rotation: float = 0


@dataclass(eq=False, kw_only=True)
class GameEmergencyDisembark(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    transport_unit_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    placed: bool = False


@dataclass(eq=False, kw_only=True)
class GameEmergencyRoll(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    transport_unit_id: int = None  # type: ignore[assignment]
    unit_model_id: int | None = None
    kind: str = None  # type: ignore[assignment]
    roll: int = None  # type: ignore[assignment]
    wounds: int = 0


@dataclass(eq=False, kw_only=True)
class GameTeleportHomer(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    x: float = None  # type: ignore[assignment]
    y: float = None  # type: ignore[assignment]
    status: str = 'placed'


@dataclass(eq=False, kw_only=True)
class GameTeleportHomersDone(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameRepair(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    source_unit_id: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    feel_no_pain: int | None = None


@dataclass(eq=False, kw_only=True)
class GameReactiveMove(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    trigger_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    roll: int | None = None
    made: bool = False


@dataclass(eq=False, kw_only=True)
class GameSurgeMove(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    target_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    phase: str = None  # type: ignore[assignment]
    distance: int = None  # type: ignore[assignment]
    made: bool = False


@dataclass(eq=False, kw_only=True)
class GameDisembarkation(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    transport_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameFireSupport(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    transport_unit_id: int = None  # type: ignore[assignment]
    target_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameFirstTurnRoll(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    attempt: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    roll: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameScoutsDone(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameFiringDeckUse(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    transport_unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameLingeringModel(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    # The unit whose attacks destroyed it, if any.
    destroyed_by_unit_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GamePsychicUse(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    ability: str = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    phase: str = None  # type: ignore[assignment]
    roll: int = None  # type: ignore[assignment]
    target_unit_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameUnitTransit(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    kind: str = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameFormationsDone(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameMovementEnded(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameChargeEnded(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameReanimation(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    roll: int = None  # type: ignore[assignment]
    healed: int = 0
    returned: int = 0


@dataclass(eq=False, kw_only=True)
class GameCommandChoice(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    ability: str = None  # type: ignore[assignment]
    option: str = None  # type: ignore[assignment]
    target_unit_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameCommandHeal(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    ability: str = None  # type: ignore[assignment]
    roll: int = None  # type: ignore[assignment]
    healed: int = 0


@dataclass(eq=False, kw_only=True)
class GameBattleShockTest(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    phase: str = None  # type: ignore[assignment]
    reason: str = None  # type: ignore[assignment]
    modifier: int = 0
    first_die: int | None = None
    second_die: int | None = None
    insane_bravery: bool = False
    passed: bool | None = None
    # Mortal wounds it suffered for failing (e.g. Delirium), if any (its own
    # table: see GameBattleShockWounds).
    wounds: GameBattleShockWounds | None = None


@dataclass(eq=False, kw_only=True)
class GameBattleShockWounds(State):
    test_id: int | None = None
    source: str = None  # type: ignore[assignment]
    roll: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameModelDestroyed(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    phase: str | None = None
    unit_id: int = None  # type: ignore[assignment]
    unit_model_id: int = None  # type: ignore[assignment]
    destroyed_by_unit_id: int | None = None
    unit_destroyed: bool = False
    # Its unit was destroyed by a unit within range of an objective then (its
    # own table: see GameKillOnObjective).
    on_objective: GameKillOnObjective | None = None
    # Its unit was destroyed within range of objectives its player controlled
    # (e.g. for Cached Acquisition) - their own table, likewise.
    controlled_objectives: list['GameDestroyedOnObjective'] = field(default_factory=list)


@dataclass(eq=False, kw_only=True)
class GameKillOnObjective(State):
    model_destroyed_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameDestroyedOnObjective(State):
    model_destroyed_id: int | None = None
    objective_id: int | None = None


@dataclass(eq=False, kw_only=True)
class GameTurnStartControl(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    objective_id: int = None  # type: ignore[assignment]
    controller: int | None = None


@dataclass(eq=False, kw_only=True)
class GameTurnStartOnObjective(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    objective_id: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameTurnStartInArea(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    area_id: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameScoringStep(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    timing: str = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameClaimOffer(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    game_secondary_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    timing: str = None  # type: ignore[assignment]
    points: int = None  # type: ignore[assignment]
    reasons: str = None  # type: ignore[assignment]
    # "pending", "claimed" or "held".
    status: str = 'pending'


@dataclass(eq=False, kw_only=True)
class GameAction(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int = None  # type: ignore[assignment]
    phase: str = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    action: str = None  # type: ignore[assignment]
    objective_id: int | None = None
    area_id: int | None = None
    status: str = 'started'
    # The enemy unit it's done on, for one done on a unit (its own table: see
    # GameActionUnitTarget).
    unit_target: GameActionUnitTarget | None = None

    @property
    def target_unit_id(self) -> int | None:
        return self.unit_target.unit_id if self.unit_target else None


@dataclass(eq=False, kw_only=True)
class GameActionUnitTarget(State):
    action_id: int | None = None
    unit_id: int = None  # type: ignore[assignment]


@dataclass(eq=False, kw_only=True)
class GameOperationMarker(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    source: str = None  # type: ignore[assignment]
    objective_id: int | None = None
    area_id: int | None = None
    placed_round: int = None  # type: ignore[assignment]
    placed_turn_seat: int | None = None
    removed_round: int | None = None
    removed_turn_seat: int | None = None


@dataclass(eq=False, kw_only=True)
class GameMissionPrompt(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    kind: str = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int | None = None
    action_id: int | None = None
    answered: bool = False


@dataclass(eq=False, kw_only=True)
class GameMarkedUnit(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    seat: int = None  # type: ignore[assignment]
    kind: str = None  # type: ignore[assignment]
    unit_id: int = None  # type: ignore[assignment]
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int | None = None
    ended: bool = False


@dataclass(eq=False, kw_only=True)
class GameCardChoice(State):
    id: int = field(default_factory=next_id)
    game_id: int = None  # type: ignore[assignment]
    game_secondary_id: int = None  # type: ignore[assignment]
    kind: str = None  # type: ignore[assignment]
    unit_id: int | None = None
    objective_id: int | None = None
    battle_round: int = None  # type: ignore[assignment]
    turn_seat: int | None = None


@dataclass(eq=False, kw_only=True)
class GameTerrainLayout(State):
    game_id: int | None = None
    layout_id: int = None  # type: ignore[assignment]

    layout: TerrainLayout | None = None


GamePlayer._refs = {
    "user": ("user_id", "User"),
    "army_list": ("list_id", "ArmyList"),
    "disposition": ("disposition_id", "Disposition"),
    "primary_mission": ("primary_mission_id", "PrimaryMission"),
}
GameSecondary._refs = {"mission": ("secondary_mission_id", "SecondaryMission")}
GameStratagemUse._refs = {"stratagem": ("stratagem_id", "Stratagem")}
GameTerrainLayout._refs = {"layout": ("layout_id", "TerrainLayout")}
Game._children = {"players": "game"}
GamePlayer._children = {"secondaries": "player", "scores": "player", "stratagem_uses": "player"}
