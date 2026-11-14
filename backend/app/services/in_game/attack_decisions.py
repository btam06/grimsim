from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from fastapi import HTTPException

from app.engine.state import Game, GamePendingAttack
from app.models import Unit
from app.seeds.factions.adepta_sororitas import acts_of_faith
from app.seeds.factions.adeptus_mechanicus import saves as admech_saves
from app.services.in_game import deployment

# Decisions the defending player makes as an attack is made against their
# unit - when only they can decide, mid-attack:
#
# - before a weapon's saving throws are rolled: an Act of Faith (Adepta
#   Sororitas) - a Miracle dice for one of them;
# - as a saving throw fails: Artisan (the roll's an unmodified 6 instead) or
#   Necromechanic (the attack's Damage is 0) - see
#   app/seeds/factions/adeptus_mechanicus/saves.py.
#
# An attack is resolved in one go (see app/services/combat.py), so when it
# comes to a decision nobody's made yet, it stops (NeedDecision): the game's
# put back as it was before the attack and the attack's kept waiting on it
# (Game.pending_attack). Once the player decides, the attack's made again
# from the start with the same dice (a game's rolls are a seeded stream -
# see app/services/dice.py) and the decisions so far, which it takes in turn
# - up to the next decision, or the end. Until then, the game waits on it.
#
# A decision's options each have an id; DECLINE does nothing. A failed save
# declined isn't asked about again for the same weapon in that attack (its
# other failed saves are the same).

DECLINE = "decline"
SAVE_MIRACLE = "save_miracle"
FAILED_SAVE = "failed_save"


class NeedDecision(Exception):
    def __init__(self, decision: dict) -> None:
        super().__init__(decision.get("prompt", "a decision is needed"))
        self.decision = decision


@dataclass
class SaveChoice:
    # What the defender chose as a save failed: described, and the roll it's
    # now (Artisan's 6), if it changed.
    note: str
    save_roll: int | None = None


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

    # --- as a save fails ---

    def failed_save(
        self, unit_model_id: int, weapon, roll: int, passes_on_six: bool
    ) -> SaveChoice | None:
        unit = self.defender
        if unit is None or weapon.id in self.declined:
            return None
        options = []
        if passes_on_six and admech_saves.artisan_reason(self.game, unit) is None:
            options.append(
                {"id": "artisan", "label": f"Artisan: the {roll} is an unmodified 6 (saved)"}
            )
        necromechanic = admech_saves.necromechanic_bearer(self.game, unit, unit_model_id)
        if necromechanic is not None:
            options.append(
                {
                    "id": "necromechanic",
                    "label": f"Necromechanic: the attack's Damage ({weapon.damage}) is 0",
                }
            )
        if not options:
            return None
        model_name = next(
            (m.model.name for m in unit.unit_models if m.id == unit_model_id), unit.label
        )
        options.append(
            {"id": DECLINE, "label": f"Neither (nor for {weapon.name}'s other failed saves)"}
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
        if answer == "artisan":
            admech_saves.use_artisan(self.game, unit)
            return SaveChoice(
                f"Artisan: a saving throw of {roll} ({weapon.name}) became a 6", save_roll=6
            )
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
    return any(acts_of_faith.army_rule(p) for p in game.players) or any(
        admech_saves.has_bearer(game, e) for e in (admech_saves.ARTISAN, admech_saves.NECROMECHANIC)
    )


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
