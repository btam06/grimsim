from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.models import Unit
from app.engine.state import Game, GameJudgement
from app.services import dice
from app.services.combat import WeaponBonus
from app.services.in_game import casualties, deployment
from app.services.in_game.deployment import TOLERANCE, gap
from app.services.list_building import enhancements as enhancement_rules

# Adepta Sororitas datasheet abilities, in a game (the combat ones that need
# nothing but their conditions - Abbess Sanctorum, Fury of the Righteous,
# Medicus Ministorum - are rules in datasheet_abilities.py; Sacred Command is
# a STRATAGEM_DISCOUNTS entry):
#
# - Righteous Repugnance (Morvenn Vahl): each time its unit is selected to
#   shoot or fight, discard 1 Miracle dice: +3 Attacks for Fidelis and the
#   Lance of Illumination until the end of the phase. An enemy unit destroyed
#   by its unit: a Miracle dice (its unit's attacks stand in for its own).
# - Rapturous Blows (Palatine): each time its unit is selected to fight,
#   discard 1 Miracle dice: each wound its melee attacks score inflicts 1
#   mortal wound as well, until the end of the phase.
# - Divine Deliverance (Canoness with jump pack): once a battle, as its unit
#   fights (for the start of the Fight phase - it only changes its own
#   attacks): +3 Attacks and [DEVASTATING WOUNDS] for its melee weapons.
# - Judged for Execution (Intranzia Fraye): at the end of its player's
#   Movement phase (declared during it), select an enemy unit within 18" of
#   and visible to it: until the start of their next Command phase, their
#   ADEPTA SORORITAS units' attacks against it have [LETHAL HITS].
# - Righteous Denunciation (Intranzia Fraye): at the start of the Fight
#   phase, each enemy unit within 6" of it takes a Battle-shock test, -1 to it
#   (see app/services/in_game/battle_shock.py start_of_fight).
# - Sacred Healing (Hospitaller): while leading a unit, once in its player's
#   Command phase, return up to 1 destroyed non-CHARACTER model to it - or,
#   discarding 1 Miracle dice, up to D3+1. They come back with their full
#   wounds, for the player to set up (see app/services/in_game/heal.py).
# - Zealot (Ministorum Priest): once a battle, as its unit fights: +3
#   Attacks and Strength for its melee weapons until the end of the phase.
# - Cherub / Cherubs (Battle Sisters, Dominion and Retributor Squads): once
#   (twice) a battle, after the unit performs an Act of Faith, a Miracle dice.
# - Simulacrum Imperialis (wargear): at the end of its player's Command
#   phase, for each objective marker they control with one or more units
#   with a model carrying one within range, a D6 - on a 4+, a Miracle dice
#   showing that.
# - Storm of Retribution (Retributor Squad): +1 to hit and wound against a
#   unit that's destroyed one of its army's ADEPTA SORORITAS units (see
#   killed_sororitas - the re-rolls of 1 are rules in datasheet_abilities.py).

RIGHTEOUS_REPUGNANCE = "Righteous Repugnance"
RAPTUROUS_BLOWS = "Rapturous Blows"
DIVINE_DELIVERANCE = "Divine Deliverance"
ZEALOT = "Zealot"
ZEALOT_BONUS = 3
CHERUBS = {"Cherub": 1, "Cherubs": 2}

# Transports that split a unit in two at the start of the Declare Battle
# Formations step, one half starting embarked in it - {transport keyword:
# the keywords of the units it can split} (see
# app/services/in_game/unit_splits.py): the Immolator.
SPLITTING_TRANSPORTS = {
    "IMMOLATOR": ("BATTLE SISTERS SQUAD", "DOMINION SQUAD", "SISTERS NOVITIATE SQUAD"),
}
SIMULACRUM = "Simulacrum Imperialis"
SIMULACRUM_ROLL = 4
JUDGED_FOR_EXECUTION = "Judged for Execution"
RIGHTEOUS_DENUNCIATION = "Righteous Denunciation"
SACRED_HEALING = "Sacred Healing"

# Abilities that discard a Miracle dice as their unit's selected to shoot or
# fight: {name: the phases}.
SELECTION_DISCARDS = {RIGHTEOUS_REPUGNANCE: ("shooting", "fight"), RAPTUROUS_BLOWS: ("fight",)}
REPUGNANCE_WEAPONS = ("Fidelis", "Lance of Illumination")
REPUGNANCE_ATTACKS = 3
DELIVERANCE_ATTACKS = 3
JUDGED_RANGE = 18.0
DENUNCIATION_RANGE = 6.0
DENUNCIATION_MODIFIER = -1


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _models_with(game: Game, unit: Unit, ability: str) -> list:
    # The unit's models on the battlefield with the ability.
    return [
        m
        for m in deployment.models_on_battlefield(game, unit)
        if any(a.name == ability for a in m.model.abilities)
    ]


def _base(game: Game, unit_model):
    p = deployment.positions(game)[unit_model.id]
    return deployment.base_at(unit_model, p.x, p.y, p.rotation)


def _army_rule(game: Game, unit: Unit) -> bool:
    from app.seeds.factions.adepta_sororitas import acts_of_faith

    return acts_of_faith.army_rule(deployment.owner(game, unit))


# --- discarding a Miracle dice as the unit's selected to shoot or fight ---


def discard_options(game: Game, unit: Unit) -> list[str]:
    # The abilities its player could discard a Miracle dice for as the unit's
    # selected to shoot or fight now.
    from app.seeds.factions.adepta_sororitas import miracle_rules

    player = deployment.owner(game, unit)
    if not _army_rule(game, unit) or not player.miracle_dice:
        return []
    return [
        name
        for name, phases in SELECTION_DISCARDS.items()
        if game.phase in phases
        and _models_with(game, unit, name)
        and not miracle_rules.used(game, player.seat, name, unit.id)
    ]


def use_discards(game: Game, unit: Unit, discards: dict[str, int]) -> None:
    # The unit's selected to shoot or fight: discards those Miracle dice (by
    # ability: the dice's value) for those abilities.
    from app.seeds.factions.adepta_sororitas import miracle_rules

    available = discard_options(game, unit)
    player = deployment.owner(game, unit)
    for name, value in discards.items():
        if name not in available:
            raise _bad_request(f"{unit.label} can't discard a Miracle dice for {name} now")
        miracle_rules._take(player, [value])
        miracle_rules._record(game, player.seat, name, unit.id, [value], [])


def weapon_bonuses(game: Game, unit: Unit, wounds: dict[int, int]) -> dict[int, list]:
    # What rules add to the unit's models' weapons now, by unit model id
    # (see app/services/combat.py WeaponBonus): Righteous Repugnance,
    # Rapturous Blows and Divine Deliverance - and Righteous Rage and Through
    # Suffering, Strength (see miracle_rules.py). `wounds`: each model's
    # wounds left.
    from app.seeds.factions.adepta_sororitas import miracle_rules

    found = miracle_rules.weapon_bonuses(game, unit, wounds)
    player = deployment.owner(game, unit)

    def add(model, bonus: WeaponBonus) -> None:
        found.setdefault(model.id, []).append(bonus)

    if miracle_rules.used(game, player.seat, RIGHTEOUS_REPUGNANCE, unit.id):
        for m in _models_with(game, unit, RIGHTEOUS_REPUGNANCE):
            add(
                m,
                WeaponBonus(
                    attacks=REPUGNANCE_ATTACKS, melee_only=False, names=REPUGNANCE_WEAPONS
                ),
            )
    if miracle_rules.used(game, player.seat, RAPTUROUS_BLOWS, unit.id):
        for m in _models_with(game, unit, RAPTUROUS_BLOWS):
            add(m, WeaponBonus(mortal_on_wound=True))
    def fight_ability_used(name: str) -> bool:
        return game.phase == "fight" and any(
            u.unit_id == unit.id
            and u.ability == name
            and u.battle_round == game.battle_round
            and u.turn_seat == game.turn_seat
            for u in game.fight_ability_uses
        )

    if fight_ability_used(DIVINE_DELIVERANCE):
        for m in _models_with(game, unit, DIVINE_DELIVERANCE):
            add(m, WeaponBonus(attacks=DELIVERANCE_ATTACKS, devastating=True))
    if fight_ability_used(ZEALOT):
        for m in _models_with(game, unit, ZEALOT):
            add(m, WeaponBonus(attacks=ZEALOT_BONUS, strength=ZEALOT_BONUS))
    return found


# --- Cherub, Simulacrum Imperialis, Storm of Retribution ---


def act_of_faith_performed(game: Game, unit: Unit) -> None:
    # The unit just performed an Act of Faith: a Cherub's Miracle dice, if it
    # has one (or two) left this battle.
    from app.seeds.factions.adepta_sororitas import acts_of_faith

    from app.services.in_game import unit_splits

    names = {a.name for m in unit.unit_models for a in m.model.abilities}
    uses = max((n for name, n in CHERUBS.items() if name in names), default=0)
    # (A unit split in two: only one of them can use it.)
    if not uses or not unit_splits.cherub_allowed(game, unit):
        return
    used = sum(1 for g in game.miracle_gains if g.reason == "Cherub" and g.unit_id == unit.id)
    if used < uses:
        acts_of_faith._gain(game, deployment.owner(game, unit), "Cherub", unit.id)


def simulacrum(game: Game) -> None:
    # The end of the turn player's Command phase: a D6 for each objective
    # marker they control with a unit carrying a Simulacrum Imperialis within
    # range - a Miracle dice showing it, on a 4+. (Once a turn.)
    from app.seeds.factions.adepta_sororitas import acts_of_faith, miracle_rules
    from app.services.in_game import mission_state, objectives

    player = next(p for p in game.players if p.seat == game.turn_seat)
    if not acts_of_faith.army_rule(player) or miracle_rules.used(game, player.seat, SIMULACRUM):
        return
    carriers = [
        u
        for u in deployment.deployable_units(player)
        if any(
            g.name == SIMULACRUM
            for m in deployment.models_on_battlefield(game, u)
            for g in m.wargear
        )
    ]
    held = {c.objective.id for c in objectives.controlled_by(game, player.seat)}
    covered = {
        o.id
        for u in carriers
        for o in mission_state.unit_objectives(game, u)
        if o.id in held
    }
    if not covered:
        return
    gained = []
    for _ in sorted(covered):
        roll = dice.randint(1, 6)
        if roll >= SIMULACRUM_ROLL:
            player.miracle_dice.append(roll)
            acts_of_faith._record_gain(game, player, SIMULACRUM, None, roll)
            gained.append(roll)
    # (Rolled for this turn - whatever came of it.)
    miracle_rules._record(game, player.seat, SIMULACRUM, None, [], gained)


def killed_sororitas(game: Game, unit: Unit, seat: int) -> bool:
    # Whether the unit has destroyed one or more of `seat`'s ADEPTA
    # SORORITAS units this battle.
    for record in game.models_destroyed:
        if not record.unit_destroyed or record.destroyed_by_unit_id != unit.id:
            continue
        victim = deployment.find_unit(game, record.unit_id)
        if deployment.owner(game, victim).seat == seat and any(
            "ADEPTA SORORITAS" in enhancement_rules.model_keywords(victim, m)
            for m in victim.unit_models
        ):
            return True
    return False


def unit_destroyed(game: Game, unit: Unit, destroyed_by: Unit | None) -> None:
    # Righteous Repugnance: an enemy unit destroyed by its unit - a Miracle
    # dice.
    from app.seeds.factions.adepta_sororitas import acts_of_faith

    # (Recount the Deeds of the Saints: a Miracle dice too.)
    acts_of_faith.enemy_unit_destroyed(game, unit, destroyed_by)
    if destroyed_by is None or not _army_rule(game, destroyed_by):
        return
    player = deployment.owner(game, destroyed_by)
    if player.seat == deployment.owner(game, unit).seat:
        return
    if any(
        a.name == RIGHTEOUS_REPUGNANCE for m in destroyed_by.unit_models for a in m.model.abilities
    ):
        acts_of_faith._gain(game, player, RIGHTEOUS_REPUGNANCE, destroyed_by.id)


# --- Judged for Execution ---


def visible_enemies(game: Game, unit: Unit, reach: float, models=None) -> list[Unit]:
    # The enemy units within `reach` of and visible to one of the unit's
    # models (`models`, if given - hidden models only within their detection
    # range).
    from app.services.in_game import shooting

    sight = shooting.Sight(game)
    own = [_base(game, m) for m in (models or deployment.models_on_battlefield(game, unit))]
    found = []
    for enemy in shooting.enemy_units(game, unit):
        hidden = shooting.hidden_models(game, enemy, sight)
        detection = shooting.detection_range(game, enemy)
        for model_id, base in shooting._bases(game, enemy).items():
            if any(
                gap(b, base) <= reach + TOLERANCE
                and sight.sees(b, base)
                and (model_id not in hidden or gap(b, base) <= detection + TOLERANCE)
                for b in own
            ):
                found.append(enemy)
                break
    return found


def _turn_index(game: Game, battle_round: int, turn_seat: int) -> int:
    return battle_round * 2 + (0 if turn_seat == game.first_seat else 1)


def judgements(game: Game, seat: int | None = None) -> list[GameJudgement]:
    # Those in play now: until the start of their player's next Command
    # phase (their next turn).
    now = _turn_index(game, game.battle_round, game.turn_seat)
    return [
        j
        for j in game.judgements
        if now < _turn_index(game, j.battle_round, j.turn_seat) + 2
        and (seat is None or j.seat == seat)
    ]


def judge_reason(game: Game, unit: Unit) -> str | None:
    if not _models_with(game, unit, JUDGED_FOR_EXECUTION):
        return f"it doesn't have {JUDGED_FOR_EXECUTION}"
    if game.phase != "movement" or game.turn_seat != deployment.owner(game, unit).seat:
        return "it's used at the end of its player's Movement phase"
    if any(
        j.unit_id == unit.id
        and j.battle_round == game.battle_round
        and j.turn_seat == game.turn_seat
        for j in game.judgements
    ):
        return "it has already been used this phase"
    return None


def judge_targets(game: Game, unit: Unit) -> list[Unit]:
    if judge_reason(game, unit) is not None:
        return []
    return visible_enemies(
        game, unit, JUDGED_RANGE, _models_with(game, unit, JUDGED_FOR_EXECUTION)
    )


def judge(game: Game, unit: Unit, target: Unit) -> None:
    if (reason := judge_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't use {JUDGED_FOR_EXECUTION}: {reason}")
    if target.id not in {t.id for t in judge_targets(game, unit)}:
        raise _bad_request(f'{target.label} isn\'t within 18" of and visible to it')
    game.judgements.append(
        GameJudgement(
            seat=deployment.owner(game, unit).seat,
            unit_id=unit.id,
            target_unit_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
        )
    )


def attack_rules(game: Game, attacker: Unit, target: Unit) -> list:
    # The attacker's attacks against the target: [LETHAL HITS] if it's an
    # ADEPTA SORORITAS unit and its player judged the target for execution.
    from app.combat_rules import Rule
    from app.combat_rules.conditions import CRITICAL_HIT
    from app.combat_rules.effects import AUTO_PASS_WOUND

    seat = deployment.owner(game, attacker).seat
    if not any(j.target_unit_id == target.id for j in judgements(game, seat)):
        return []
    if not any(
        "ADEPTA SORORITAS" in enhancement_rules.model_keywords(attacker, m)
        for m in attacker.unit_models
    ):
        return []
    return [Rule(conditions=(CRITICAL_HIT,), effects=(AUTO_PASS_WOUND,))]


# --- Righteous Denunciation ---


def denunciation_tests(game: Game) -> list[tuple[Unit, int]]:
    # The start of the Fight phase: the enemy units within 6" of a model with
    # Righteous Denunciation - each to take a Battle-shock test, at -1.
    found = []
    placed = deployment.positions(game)
    for player in game.players:
        for unit in deployment.deployable_units(player):
            sources = [_base(game, m) for m in _models_with(game, unit, RIGHTEOUS_DENUNCIATION)]
            if not sources:
                continue
            for other in game.players:
                if other.seat == player.seat:
                    continue
                for enemy in deployment.deployable_units(other):
                    if not deployment.is_deployed(enemy, placed):
                        continue
                    bases = [_base(game, m) for m in deployment.models_on_battlefield(game, enemy)]
                    if any(
                        gap(s, b) <= DENUNCIATION_RANGE + TOLERANCE
                        for s in sources
                        for b in bases
                    ):
                        found.append((enemy, DENUNCIATION_MODIFIER))
    return found


# --- Sacred Healing, Salvationist Medikit, Healing Tears: returning models ---

SALVATIONIST_MEDIKIT = "Salvationist Medikit"
HEALING_TEARS = "Healing Tears"


@dataclass(frozen=True)
class Returns:
    # An ability that returns destroyed models to its unit in its player's
    # Command phase (once a phase), with their full wounds, to be set up:
    # `count` of them (a dice expression) - or, discarding a Miracle dice,
    # `discard_count` (if it can). The models it can return: not CHARACTERs
    # (`no_characters`), or only those named `models`. Who has it: a model
    # with it leading the unit (`leading`), a model on the battlefield with
    # it, or one with the wargear `wargear` (its bearer).
    count: str = "1"
    discard_count: str | None = None
    no_characters: bool = True
    models: tuple[str, ...] = ()
    leading: bool = False
    wargear: str | None = None
    # Only while the unit has a model on the battlefield named this (e.g.
    # Healing Tears: Celestine).
    needs_model: str | None = None


RETURNS = {
    # (Hospitaller) While leading a unit: 1 - or, discarding a Miracle dice,
    # up to D3+1.
    SACRED_HEALING: Returns(count="1", discard_count="D3+1", leading=True),
    # (Sanctifiers' Salvationist) If the bearer's on the battlefield: up to D3.
    SALVATIONIST_MEDIKIT: Returns(count="D3", wargear="Salvationist medikit"),
    # (Saint Celestine) While the unit has Celestine: 1 Geminae Superia.
    HEALING_TEARS: Returns(
        count="1", no_characters=False, models=("Geminae Superia",), needs_model="Celestine"
    ),
}


def _healed(game: Game, unit: Unit, ability: str = SACRED_HEALING) -> bool:
    from app.seeds.factions.adepta_sororitas import miracle_rules

    seat = deployment.owner(game, unit).seat
    return bool(miracle_rules.used(game, seat, ability, unit.id))


def returnable(game: Game, unit: Unit, ability: str = SACRED_HEALING) -> list:
    # The unit's destroyed models the ability could return.
    config = RETURNS[ability]
    lost = casualties.damage(game)
    return [
        m
        for m in deployment.unit_models(unit)
        if m.id in lost
        and lost[m.id].destroyed
        and not (config.no_characters and "CHARACTER" in enhancement_rules.model_keywords(unit, m))
        and (not config.models or m.model.name in config.models)
    ]


def _has_return(game: Game, unit: Unit, ability: str) -> bool:
    config = RETURNS[ability]
    if config.wargear is not None:
        return any(
            g.name == config.wargear
            for m in deployment.models_on_battlefield(game, unit)
            for g in m.wargear
        )
    holders = _models_with(game, unit, ability)
    if config.leading:
        return any(enhancement_rules.is_leading(unit, m) for m in holders)
    return bool(holders)


def return_abilities(game: Game, unit: Unit) -> list[str]:
    # The returning abilities the unit could use now.
    return [a for a in RETURNS if healing_reason(game, unit, a) is None]


def healing_reason(game: Game, unit: Unit, ability: str = SACRED_HEALING) -> str | None:
    config = RETURNS[ability]
    if not _has_return(game, unit, ability):
        if ability == SACRED_HEALING:
            return "it has no Hospitaller leading it"
        return f"it doesn't have {ability}"
    if config.needs_model is not None and not any(
        m.model.name == config.needs_model for m in deployment.models_on_battlefield(game, unit)
    ):
        return f"it has no {config.needs_model} model on the battlefield"
    if game.phase != "command" or game.turn_seat != deployment.owner(game, unit).seat:
        return "it's used in its player's Command phase"
    if _healed(game, unit, ability):
        return "it has already been used this phase"
    if not returnable(game, unit, ability):
        return "it has no destroyed models to return"
    return None


def _roll(expression: str) -> int:
    # "1", "D3", "D3+1".
    count, _, plus = expression.partition("+")
    total = dice.randint(1, int(count[1:])) if count.startswith("D") else int(count)
    return total + (int(plus) if plus else 0)


def sacred_healing(
    game: Game, unit: Unit, discard: int | None, ability: str = SACRED_HEALING
) -> int:
    # Returns the ability's destroyed models - discarding the Miracle dice of
    # `discard` for more, if it can - with full wounds, to be set up. How many.
    from app.seeds.factions.adepta_sororitas import miracle_rules

    if ability not in RETURNS:
        raise _bad_request(f"{ability} doesn't return models")
    config = RETURNS[ability]
    if (reason := healing_reason(game, unit, ability)) is not None:
        raise _bad_request(f"{unit.label} can't use {ability}: {reason}")
    player = deployment.owner(game, unit)
    removed = []
    count = config.count
    if discard is not None:
        if config.discard_count is None:
            raise _bad_request(f"{ability} doesn't discard a Miracle dice")
        if not _army_rule(game, unit):
            raise _bad_request("only an Adepta Sororitas army has Miracle dice")
        miracle_rules._take(player, [discard])
        removed = [discard]
        count = config.discard_count
    lost = casualties.damage(game)
    back = returnable(game, unit, ability)[: _roll(count)]
    for m in back:
        lost[m.id].destroyed = False
        lost[m.id].wounds_lost = 0
    miracle_rules._record(game, player.seat, ability, unit.id, removed, [])
    return len(back)


# --- Fiery Conviction ---

FIERY_CONVICTION = "Fiery Conviction"


def conviction_reason(game: Game, unit: Unit) -> str | None:
    # Why the unit can't use Fiery Conviction now, if it can't: its model's
    # on the battlefield, in its player's Command phase, once a phase.
    if not _models_with(game, unit, FIERY_CONVICTION):
        return f"it has no model with {FIERY_CONVICTION} on the battlefield"
    if game.phase != "command" or game.turn_seat != deployment.owner(game, unit).seat:
        return "it's used in its player's Command phase"
    if _healed(game, unit, FIERY_CONVICTION):
        return "it has already been used this phase"
    return None


def fiery_conviction(game: Game, unit: Unit, discard: int | None) -> bool:
    # Discarding the Miracle dice of `discard`, 1CP - or, without, a
    # Leadership test for the model: passed, 1CP. Whether it gained the CP.
    from app.seeds.factions.adepta_sororitas import miracle_rules

    if (reason := conviction_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't use {FIERY_CONVICTION}: {reason}")
    player = deployment.owner(game, unit)
    removed = []
    if discard is not None:
        miracle_rules._take(player, [discard])
        removed = [discard]
        gained = True
    else:
        model = _models_with(game, unit, FIERY_CONVICTION)[0]
        gained = dice.randint(1, 6) + dice.randint(1, 6) >= model.model.leadership
    if gained:
        player.cp += 1
    miracle_rules._record(game, player.seat, FIERY_CONVICTION, unit.id, removed, [])
    return gained


# --- Relics of the Matriarchs ---

RELICS = "Relics of the Matriarchs"
# A relic chosen this battle round: a marked unit, of kind "relic:<option>".
RELIC = "relic:"
RELICS_CHOSEN = 2
RELICS_DAMAGED = 1
FIERY_HEART = "The Fiery Heart (Aura)"
FIERY_HEART_MOVE = 2
FIERY_HEART_ROLLS = 1
CENSER = "Censer of the Sacred Rose (Aura)"
EBON_CHALICE = "Simulacrum of the Ebon Chalice (Aura)"


def relic_options() -> list[str]:
    from app.seeds import datasheet_abilities

    return list(datasheet_abilities.OPTIONS.get(RELICS, {}))


def relic_models(game: Game, unit: Unit) -> list:
    return _models_with(game, unit, RELICS)


def relics_allowed(game: Game, unit: Unit) -> int:
    # How many it can select: two - one while it's Damaged.
    damaged = any(casualties.damaged_profile(game, m) is not None for m in relic_models(game, unit))
    return RELICS_DAMAGED if damaged else RELICS_CHOSEN


def chosen_relics(game: Game, unit: Unit) -> list[str]:
    # The relics the unit chose this battle round.
    return [
        m.kind[len(RELIC):]
        for m in game.marked_units
        if m.kind.startswith(RELIC)
        and m.unit_id == unit.id
        and m.battle_round == game.battle_round
        and not m.ended
    ]


def relics_reason(game: Game, unit: Unit) -> str | None:
    from app.services.in_game import battle_round

    if not relic_models(game, unit):
        return f"it has no model with {RELICS} on the battlefield"
    if game.status != "in_progress" or game.phase != battle_round.START_OF_ROUND:
        return "they're selected at the start of the battle round"
    return None


def choose_relics(game: Game, unit: Unit, options: list[str]) -> None:
    # The start of the battle round: up to two relics (one while Damaged),
    # until the start of the next.
    from app.services.in_game import mission_state

    if (reason := relics_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't select relics now: {reason}")
    options = list(dict.fromkeys(options))
    if len(options) > relics_allowed(game, unit):
        raise _bad_request(f"it can select up to {relics_allowed(game, unit)} of them now")
    unknown = [o for o in options if o not in relic_options()]
    if unknown:
        raise _bad_request(f"{RELICS} has no {unknown[0]!r}")
    for m in game.marked_units:
        if m.kind.startswith(RELIC) and m.unit_id == unit.id and m.battle_round == game.battle_round:
            m.ended = True
    seat = deployment.owner(game, unit).seat
    for option in options:
        mission_state.mark(game, seat, f"{RELIC}{option}", unit.id)


def relic_on(game: Game, unit: Unit, option: str) -> bool:
    # Whether a relic aura reaches the unit now (an ADEPTA SORORITAS unit
    # within 6" of a model whose unit chose it this round).
    from app.services.in_game import auras

    # (Cheaply, first: no relic chosen this round at all.)
    if not any(
        m.kind.startswith(RELIC) and m.battle_round == game.battle_round and not m.ended
        for m in game.marked_units
    ):
        return False
    if not _sororitas_unit(unit):
        return False
    seat = deployment.owner(game, unit).seat
    return any(
        a.ability == RELICS and a.option == option and auras.in_range(game, a, unit)
        for a in auras.auras(game, seat)
    )


def _sororitas_unit(unit: Unit) -> bool:
    return any(
        "ADEPTA SORORITAS" in enhancement_rules.model_keywords(unit, m) for m in unit.unit_models
    )


# --- Miraculous Intervention ---

MIRACULOUS_INTERVENTION = "Miraculous Intervention"
MIRACULOUS_MODEL = "Celestine"
MIRACULOUS_ROLL = 2
# Its use, the first time Celestine's destroyed (a marked unit, never ended -
# see app/services/in_game/mission_state.py).
MIRACULOUS_USED = "miraculous_intervention"


def miraculous_end_of_phase(game: Game) -> list[tuple[int, int, bool]]:
    # The end of a phase: each Celestine (with Miraculous Intervention)
    # destroyed this phase for the first time rolls a D6 - on a 2+ she's set
    # up again, as close as possible to where she was destroyed and
    # unengaged, with her full wounds. (unit model id, roll, set up) for each.
    from app.engine.state import GameModelPosition
    from app.seeds.factions.adepta_sororitas import miracle_rules
    from app.services.in_game import mission_state

    used = {m.unit_id for m in mission_state.marked(game, MIRACULOUS_USED)}
    lost = casualties.damage(game)
    results = []
    for player in game.players:
        for unit in deployment.deployable_units(player):
            if unit.id in used:
                continue
            for model in unit.unit_models:
                if model.model.name != MIRACULOUS_MODEL or not any(
                    a.name == MIRACULOUS_INTERVENTION for a in model.model.abilities
                ):
                    continue
                if model.id not in lost or not lost[model.id].destroyed:
                    continue
                where = next(
                    (
                        r
                        for r in reversed(game.models_destroyed)
                        if r.unit_model_id == model.id
                        and miracle_rules._now(game, r)
                        and r.x is not None
                    ),
                    None,
                )
                if where is None:
                    continue
                mission_state.mark(game, player.seat, MIRACULOUS_USED, unit.id)
                roll = dice.randint(1, 6)
                spot = None
                if roll >= MIRACULOUS_ROLL:
                    lost[model.id].destroyed = False
                    lost[model.id].wounds_lost = 0
                    spot = miracle_rules._set_up_spot(game, unit, model, (where.x, where.y))
                    if spot is None:
                        # Nowhere to set her up: she stays destroyed.
                        lost[model.id].destroyed = True
                        lost[model.id].wounds_lost = model.wounds
                    else:
                        game.model_positions.append(
                            GameModelPosition(
                                unit_model_id=model.id, x=spot[0], y=spot[1], rotation=0.0
                            )
                        )
                results.append((model.id, roll, spot is not None))
    return results


# --- Holy Mission, Holy Vanguard: abilities from what a unit's made of ---

HOLY_MISSION = "Holy Mission"
HOLY_VANGUARD = "Holy Vanguard"
SCOUTS_6 = 'Scouts 6"'
INFILTRATORS = "Infiltrators"


def granted_abilities(unit: Unit, unit_model, game: Game | None = None) -> set[str]:
    # Core abilities the model has from its unit (a leader attached to it is
    # part of it):
    # - Holy Mission (Ministorum Priest): Scouts 6" in a DOMINION SQUAD,
    #   Infiltrators in a SISTERS NOVITIATE SQUAD.
    # - Holy Vanguard (Dominion Squad): its leader (a CHARACTER) has Scouts 6"
    #   if the unit starts the battle embarked in a TRANSPORT (`game` needed).
    names = {a.name for a in unit_model.model.abilities}
    others = [m for m in unit.unit_models if m is not unit_model]
    found: set[str] = set()
    if HOLY_MISSION in names:
        keywords = {k for m in others for k in enhancement_rules.model_keywords(unit, m)}
        if "DOMINION SQUAD" in keywords:
            found.add(SCOUTS_6)
        if "SISTERS NOVITIATE SQUAD" in keywords:
            found.add(INFILTRATORS)
    if (
        game is not None
        and "CHARACTER" in enhancement_rules.model_keywords(unit, unit_model)
        and any(a.name == HOLY_VANGUARD for m in others for a in m.model.abilities)
    ):
        formation = deployment.battle_formation(game, unit)
        if formation is not None and formation.place == "embarked":
            found.add(SCOUTS_6)
    return found
