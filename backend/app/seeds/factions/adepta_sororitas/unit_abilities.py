from __future__ import annotations

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


# --- Sacred Healing ---


def _healed(game: Game, unit: Unit) -> bool:
    from app.seeds.factions.adepta_sororitas import miracle_rules

    seat = deployment.owner(game, unit).seat
    return bool(miracle_rules.used(game, seat, SACRED_HEALING, unit.id))


def returnable(game: Game, unit: Unit) -> list:
    # The unit's destroyed models Sacred Healing could return (not
    # CHARACTERs).
    lost = casualties.damage(game)
    return [
        m
        for m in deployment.unit_models(unit)
        if m.id in lost
        and lost[m.id].destroyed
        and "CHARACTER" not in enhancement_rules.model_keywords(unit, m)
    ]


def healing_reason(game: Game, unit: Unit) -> str | None:
    healers = _models_with(game, unit, SACRED_HEALING)
    if not healers or not any(enhancement_rules.is_leading(unit, m) for m in healers):
        return "it has no Hospitaller leading it"
    if game.phase != "command" or game.turn_seat != deployment.owner(game, unit).seat:
        return "it's used in its player's Command phase"
    if _healed(game, unit):
        return "it has already been used this phase"
    if not returnable(game, unit):
        return "it has no destroyed models to return"
    return None


def sacred_healing(game: Game, unit: Unit, discard: int | None) -> int:
    # Returns up to 1 destroyed model - or, discarding the Miracle dice of
    # `discard`, up to D3+1 - with full wounds, to be set up. How many.
    from app.seeds.factions.adepta_sororitas import miracle_rules

    if (reason := healing_reason(game, unit)) is not None:
        raise _bad_request(f"{unit.label} can't use {SACRED_HEALING}: {reason}")
    player = deployment.owner(game, unit)
    removed = []
    count = 1
    if discard is not None:
        if not _army_rule(game, unit):
            raise _bad_request("only an Adepta Sororitas army has Miracle dice")
        miracle_rules._take(player, [discard])
        removed = [discard]
        count = dice.randint(1, 3) + 1
    lost = casualties.damage(game)
    back = returnable(game, unit)[:count]
    for m in back:
        lost[m.id].destroyed = False
        lost[m.id].wounds_lost = 0
    miracle_rules._record(game, player.seat, SACRED_HEALING, unit.id, removed, [])
    return len(back)


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
