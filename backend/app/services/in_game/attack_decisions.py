from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from fastapi import HTTPException

from app.engine.state import Game, GamePendingAttack
from app.models import Unit
from app.seeds.factions.adepta_sororitas import acts_of_faith
from app.seeds.factions.adeptus_mechanicus import saves as admech_saves
from app.services.in_game import deployment

# Decisions players make as an attack is made - when only they can decide,
# mid-attack:
#
# - once rolls are made - a weapon's Hit, Wound or saving throws (together),
#   its Attacks roll, a Damage roll, a hazard roll - the rolling player's
#   offered what can re-roll or change one, a dice at a time (REROLL_DICE):
#   Command Re-roll (15.02 - any of them, for its CP, once a phase), an
#   ability that re-rolls one failed Hit or Wound roll this attack (e.g.
#   Seething Hatred), or Artisan (a failed saving throw's an unmodified 6 -
#   see app/seeds/factions/adeptus_mechanicus/saves.py). A dice is never
#   re-rolled twice: one re-rolled already (e.g. Twin-linked, re-rolling 1s)
#   isn't offered;
# - before a weapon's saving throws are rolled: an Act of Faith (Adepta
#   Sororitas) - a Miracle dice for one of them;
# - as a saving throw fails: Necromechanic (the attack's Damage is 0);
# - as a unit's targeted: Atavistic Instigation's stand firm or duck.
#
# An attack is resolved in one go (see app/services/combat.py), so when it
# comes to a decision nobody's made yet, it stops (NeedDecision): the game's
# put back as it was before the attack and the attack's kept waiting on it
# (Game.pending_attack). Once the player decides, the attack's made again
# from the start with the same dice (a game's rolls are a seeded stream -
# see app/services/dice.py) and the decisions so far, which it takes in turn
# - up to the next decision, or the end. Until then, the game waits on it.
#
# A decision's options each have an id; DECLINE (or CARRY_ON) does nothing.
# A failed save declined isn't asked about again for the same weapon in that attack (its
# other failed saves are the same).

DECLINE = "decline"
SAVE_MIRACLE = "save_miracle"
FAILED_SAVE = "failed_save"
ATAVISTIC = "atavistic"
REROLL_DICE = "reroll_dice"
CARRY_ON = "carry_on"
COMMAND_REROLL = "Command Re-roll"
ROLLS = {
    "hit": "Hit rolls", "wound": "Wound rolls", "save": "saving throws",
    "damage": "Damage roll", "hazard": "hazard roll", "attacks": "Attacks roll",
}
STAND_FIRM = "stand_firm"
DUCK = "duck"


class NeedDecision(Exception):
    def __init__(self, decision: dict) -> None:
        super().__init__(decision.get("prompt", "a decision is needed"))
        self.decision = decision


@dataclass
class SaveChoice:
    # What the defender chose as a save failed, described.
    note: str


@dataclass
class Decisions:
    game: Game
    answers: list = field(default_factory=list)
    # The unit being attacked (set before each target's attacks).
    defender: Unit | None = None
    asked: int = 0
    # Acts of Faith chosen: spent once the attack's done (see spend).
    miracles: list = field(default_factory=list)
    declined: set = field(default_factory=set)

    def _ask(self, decision: dict) -> str:
        if self.asked < len(self.answers):
            answer = self.answers[self.asked]
            self.asked += 1
            if answer not in {o["id"] for o in decision["options"]}:
                raise HTTPException(
                    status_code=409,
                    detail="the attack didn't play out the same again - that choice isn't "
                    "one of the options now",
                )
            return answer
        raise NeedDecision(decision)

    def _seat(self) -> int:
        return deployment.owner(self.game, self.defender).seat

    # --- before a weapon's saves are rolled ---

    def save_miracle(self, weapon, saves: int):
        # An Act of Faith for one of the weapon's `saves` saving throws: the
        # AttackMiracle (see acts_of_faith), or None.
        unit = self.defender
        if unit is None or any(m.unit is unit for m in self.miracles):
            return None
        if acts_of_faith.cant_reason(self.game, unit) is not None:
            return None
        pool = sorted(set(deployment.owner(self.game, unit).miracle_dice), reverse=True)
        damage = f", D{weapon.damage}" if weapon.damage else ""
        answer = self._ask(
            {
                "type": SAVE_MIRACLE,
                "seat": self._seat(),
                "unit_id": unit.id,
                "prompt": (
                    f"{unit.label} makes {saves} saving throw{'s' if saves != 1 else ''} "
                    f"against {weapon.name} (AP {weapon.ap}{damage}): perform an Act of "
                    "Faith - a Miracle dice for one of them?"
                ),
                "options": [
                    {"id": f"miracle:{v}", "label": f"Miracle dice {v}"} for v in pool
                ]
                + [{"id": DECLINE, "label": "No Act of Faith"}],
            }
        )
        if answer == DECLINE:
            return None
        value = int(answer.split(":", 1)[1])
        miracle = acts_of_faith.attack_miracle(
            self.game,
            unit,
            SimpleNamespace(roll=acts_of_faith.SAVE, value=value, weapon_id=weapon.id),
            acts_of_faith.DEFENCE_ROLLS,
        )
        self.miracles.append(miracle)
        return miracle

    # --- as it's targeted ---

    def atavistic(self, unit: Unit, weapon_name: str) -> str:
        # Atavistic Instigation: the target's player declares whether it
        # stands firm or ducks for cover (STAND_FIRM / DUCK).
        return self._ask(
            {
                "type": ATAVISTIC,
                "seat": deployment.owner(self.game, unit).seat,
                "unit_id": unit.id,
                "prompt": (
                    f"{unit.label} is targeted by a {weapon_name}: stand firm (ranged attacks "
                    "against it this phase score Critical Hits on 5+), or duck for cover (-1 to "
                    "hit for its attacks until the attacker's next turn)?"
                ),
                "options": [
                    {"id": STAND_FIRM, "label": "Stand firm"},
                    {"id": DUCK, "label": "Duck for cover"},
                ],
            }
        )

    # --- once rolls are made ---

    def dice(self, kind: str, unit: Unit, rolled: list, one: bool):
        # The rolls made together for `unit` (combat.RolledDie - `kind`: see
        # combat.ROLL_NAMES): its player's offered what can re-roll or change
        # one - Command Re-roll (any of them), an ability re-rolling one
        # failed Hit or Wound roll this attack (`one` - e.g. Seething Hatred),
        # or Artisan (a failed saving throw's an unmodified 6). A dice
        # re-rolled already (by anything) isn't. The choice - (source, the
        # dice, what it was) - once it's paid for, or None to carry on.
        from app.services.combat import ROLL_NAMES

        player = deployment.owner(self.game, unit)
        sources = []
        if one:
            sources.append(("one", self._one_reroll_name(unit)))
        command = self._command_reroll(player, unit)
        if command is not None:
            sources.append(("command_reroll", f"Command Re-roll ({command[1]}CP)"))
        if kind == "save" and admech_saves.artisan_reason(self.game, unit) is None:
            sources.append(("six", "Artisan"))

        def can(source: str, die) -> bool:
            if not die.rerollable or die.rerolled:
                return False
            if source == "command_reroll":
                return True
            return not die.passed and (source != "six" or die.check(6))

        options = [
            {
                "id": f"{source}:{i}",
                "label": (
                    f"{name}: dice {i + 1} (a {die.value}) becomes a 6"
                    if source == "six"
                    else f"{name}: re-roll dice {i + 1} (a {die.value})"
                ),
            }
            for source, name in sources
            for i, die in enumerate(rolled)
            if can(source, die)
        ]
        if not options:
            return None
        options.append({"id": CARRY_ON, "label": "Carry on"})
        weapon = rolled[0].weapon_name
        failed = sum(1 for d in rolled if not d.passed)
        if kind in ("damage", "attacks"):
            outcome = f"rolled {', '.join(str(d.value) for d in rolled)}"
        elif len(rolled) == 1:
            outcome = f"a {rolled[0].value} - {'passed' if rolled[0].passed else 'failed'}"
        else:
            outcome = f"{failed} of {len(rolled)} failed"
        prompt = f"{unit.label}'s {ROLLS[kind]} for {weapon}: {outcome} - re-roll or change one?"
        answer = self._ask(
            {
                "type": REROLL_DICE,
                "seat": player.seat,
                "unit_id": unit.id,
                "roll": kind,
                "prompt": prompt,
                "options": options,
                "dice": [
                    {
                        "value": d.value,
                        "passed": d.passed,
                        "rerolled": d.rerolled,
                        "rerollable": d.rerollable,
                    }
                    for d in rolled
                ],
            }
        )
        if answer == CARRY_ON:
            return None
        source, index = answer.split(":")
        die = rolled[int(index)]
        name = next(n for s_, n in sources if s_ == source)
        if source == "command_reroll":
            from app.services.in_game import game as game_service

            use = game_service.spend_stratagem(self.game, player, command[0], unit)
            from app.engine.state import GameStratagemOutcome

            use.outcome_link = GameStratagemOutcome(
                text=f"{ROLL_NAMES[kind]} of {die.value} ({die.weapon_name}) re-rolled",
                choice_id=None,
            )
            name = "Command Re-roll"
        elif source == "six":
            admech_saves.use_artisan(self.game, unit)
        return source, die, name

    def _command_reroll(self, player, unit: Unit):
        # Command Re-roll and what it'd cost, if the player can use it on a
        # roll for the unit now.
        from app.services.in_game import game as game_service

        stratagem = game_service._core_stratagem(COMMAND_REROLL)
        if stratagem is None:
            return None
        if game_service.attack_stratagem_reason(self.game, player, stratagem, unit) is not None:
            return None
        cost, _ = game_service.stratagem_cost(stratagem, unit)
        discount, _ = game_service.ability_discount(self.game, player, unit)
        if game_service.free_rule(self.game, player, stratagem) is not None:
            return stratagem, 0
        return stratagem, max(0, cost - discount)

    def _one_reroll_name(self, unit: Unit) -> str:
        names = _one_reroll_abilities() & {
            a.name for m in unit.unit_models for a in m.model.abilities
        }
        return min(names) if names else "Re-roll one"

    # --- as a save fails ---

    def failed_save(self, unit_model_id: int, weapon, roll: int) -> SaveChoice | None:
        unit = self.defender
        if unit is None or weapon.id in self.declined:
            return None
        necromechanic = admech_saves.necromechanic_bearer(self.game, unit, unit_model_id)
        if necromechanic is None:
            return None
        options = [
            {
                "id": "necromechanic",
                "label": f"Necromechanic: the attack's Damage ({weapon.damage}) is 0",
            }
        ]
        model_name = next(
            (m.model.name for m in unit.unit_models if m.id == unit_model_id), unit.label
        )
        options.append(
            {"id": DECLINE, "label": f"No (nor for {weapon.name}'s other failed saves)"}
        )
        answer = self._ask(
            {
                "type": FAILED_SAVE,
                "seat": self._seat(),
                "unit_id": unit.id,
                "prompt": (
                    f"{unit.label}: a saving throw of {roll} against {weapon.name} "
                    f"(D{weapon.damage}) fails for {model_name}."
                ),
                "options": options,
            }
        )
        if answer == DECLINE:
            self.declined.add(weapon.id)
            return None
        bearer_unit, _ = necromechanic
        admech_saves.use_necromechanic(self.game, bearer_unit)
        return SaveChoice(f"Necromechanic: a {weapon.name} attack's Damage became 0")

    def spend(self) -> None:
        # Once the attack's done: the Miracle dice used are spent.
        for miracle in self.miracles:
            acts_of_faith.spend(self.game, miracle)


def possible(game: Game) -> bool:
    # Whether an attack in this game could come to a decision (so it's worth
    # keeping the game as it was before it).
    from app.services.in_game import game as game_service

    return (
        game_service._core_stratagem(COMMAND_REROLL) is not None
        or any(acts_of_faith.army_rule(p) for p in game.players)
        or any(admech_saves.has_bearer(game, e) for e in (admech_saves.ARTISAN, admech_saves.NECROMECHANIC))
        # (Atavistic Instigation's stand firm or duck for cover; an ability
        # that re-rolls one Hit or Wound roll - e.g. Seething Hatred.)
        or any(
            a.name == "Atavistic Instigation" or a.name in _one_reroll_abilities()
            for p in game.players
            for u in p.army_list.units
            for m in u.unit_models
            for a in m.model.abilities
        )
    )


def _one_reroll_abilities() -> set[str]:
    from app.combat_rules.effects import REROLL_ONE_FAILED_HIT, REROLL_ONE_HIT_OR_WOUND
    from app.seeds import datasheet_abilities

    return {
        name
        for name, rules in datasheet_abilities.RULES.items()
        if any(
            e in (REROLL_ONE_FAILED_HIT, REROLL_ONE_HIT_OR_WOUND)
            for r in rules
            for e in getattr(r, "effects", ())
        )
    }


def pend(game: Game, kind: str, payload: dict, answers: list, need: NeedDecision) -> None:
    game.pending_attack = GamePendingAttack(
        kind=kind,
        payload=payload,
        rng_rolls=game.rng_rolls,
        answers=list(answers),
        decision=need.decision,
    )


def waiting_reason(game: Game) -> str | None:
    pending = game.pending_attack
    if pending is None:
        return None
    return (
        f"the attack is waiting on player {pending.decision.get('seat')}'s decision: "
        f"{pending.decision.get('prompt')}"
    )
