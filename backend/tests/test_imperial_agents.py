from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import DatasheetAbility, Keyword, Model, Unit, UnitModel
from app.models.model import TransportCapacity
from app.routers.games import _load_game
from app.seeds import weapon_abilities as weapon_ability_seeds
from app.seeds.factions.imperial_agents import datasheet_abilities as agents
from app.services import combat
from app.services.in_game import casualties, deployment, psychic, shooting
from tests.test_combat import _ability, _condition, _effect, _model, _unit, _unit_model, _weapon
from tests.test_deployment import _deployment, _game, _set, _unit_named
from tests.test_movement import _battle
from tests.test_shooting import _place
from tests.test_space_marine_units import _model_of
from tests.test_space_marines import _applies

# Inquisitor Draxus's rules, and [PSYCHIC] weapons.

VEIL = "Psychic Veil (Psychic)"


def test_xenos_hunter_against_xenos_while_leading():
    rules = agents.RULES["Xenos Hunter"]
    leading = {"attacker_unit_model_keywords": [{"CHARACTER"}, {"INFANTRY"}]}
    assert _applies(rules, {**leading, "defender_keywords": {"ORKS"}})
    assert not _applies(rules, {**leading, "defender_keywords": {"IMPERIUM"}})
    assert not _applies(rules, {**leading, "defender_keywords": {"CHAOS"}})
    assert not _applies(rules, {"attacker_unit_model_keywords": [{"CHARACTER"}]})


def test_psychic_weapons_ignore_hit_penalties(monkeypatch):
    entry = {e[0]: e for e in weapon_ability_seeds.ENTRIES}["Psychic"]
    assert entry[3] == ["ignore_hit_penalties"]

    def shoot(psychic_weapon: bool) -> int:
        # A 3+ shot rolling 3s at a target in cover (-1 to hit).
        monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
        abilities = (
            [_ability([_condition("always")], [_effect("ignore_hit_penalties")])]
            if psychic_weapon
            else []
        )
        weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
        weapon.abilities = abilities
        weapon.id = 1
        result = combat.resolve_combat(
            _unit([_unit_model(_model(), [weapon])]), _unit([_unit_model(_model(), [])]),
            {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=True,
            half_range=False, moved_less_than_3=False, advanced=False,
        )
        return len(result.wound_rolls)

    assert shoot(False) == 0
    assert shoot(True) == 1


async def _veil_game(client, session, tmp_path):
    units = {1: [("A", 1, {"weapon_range": 24})], 2: [("P", 1, {"keywords": ("PSYKER",)})]}
    game, deployment_ = await _battle(
        client, session, tmp_path, units=units, spots={"A": (20, 38), "P": (20, 4)}
    )
    p = _unit_named(deployment_, "P")
    model = await _model_of(session, p)
    model.abilities.append(DatasheetAbility(name=VEIL, description=VEIL))
    await session.commit()
    game_ = await _load_game(session, game["id"])
    game_.phase = "command"
    await session.commit()
    return game["id"], _unit_named(deployment_, "A"), p


async def test_psychic_veil(client: AsyncClient, session, tmp_path, monkeypatch):
    game_id, a, p = await _veil_game(client, session, tmp_path)
    [unit] = (await client.get(f"/games/{game_id}/psychic")).json()["units"]
    assert unit["unit_id"] == p["unit_id"]
    monkeypatch.setattr(psychic.random, "randint", lambda lo, hi: 4)
    response = await client.post(
        f"/games/{game_id}/psychic", json={"unit_id": p["unit_id"], "ability": VEIL}
    )
    assert response.status_code == 200, response.text
    # Once a phase.
    response = await client.post(
        f"/games/{game_id}/psychic", json={"unit_id": p["unit_id"], "ability": VEIL}
    )
    assert response.status_code == 400
    session.expire_all()
    game_ = await _load_game(session, game_id)
    a_unit, p_unit = (deployment.find_unit(game_, u["unit_id"]) for u in (a, p))
    assert psychic.targeted_within(game_, p_unit) == 18
    # A 24" gun 20" away can't target it; 15" away it can.
    await _place(session, a, [(20, 25.3)])
    session.expire_all()
    game_ = await _load_game(session, game_id)
    a_unit, p_unit = (deployment.find_unit(game_, u["unit_id"]) for u in (a, p))
    assert not any(w.in_range for w in shooting.reach(game_, a_unit, p_unit).weapons)
    await _place(session, a, [(20, 20)])
    session.expire_all()
    game_ = await _load_game(session, game_id)
    a_unit, p_unit = (deployment.find_unit(game_, u["unit_id"]) for u in (a, p))
    assert any(w.in_range for w in shooting.reach(game_, a_unit, p_unit).weapons)


async def test_psychic_veil_failing_hurts_its_unit(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    game_id, a, p = await _veil_game(client, session, tmp_path)
    monkeypatch.setattr(psychic.random, "randint", lambda lo, hi: 1)
    monkeypatch.setattr(combat.random, "randint", lambda lo, hi: 1)
    response = await client.post(
        f"/games/{game_id}/psychic", json={"unit_id": p["unit_id"], "ability": VEIL}
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    game_ = await _load_game(session, game_id)
    p_unit = deployment.find_unit(game_, p["unit_id"])
    # A 1: D3 (a 1) mortal wounds, and no veil.
    assert casualties.damage(game_)[p_unit.unit_models[0].id].wounds_lost == 1
    assert psychic.targeted_within(game_, p_unit) is None


async def test_authority_of_the_inquisition(client: AsyncClient, session, tmp_path):
    # Seat 1's A: an ADEPTUS ASTARTES INFANTRY model led by a CHARACTER with
    # Authority of the Inquisition (and no ADEPTUS ASTARTES of her own); T can
    # only carry ADEPTUS ASTARTES INFANTRY.
    infantry = ("ADEPTUS ASTARTES", "INFANTRY")
    units = {1: [("T", 1, {"keywords": ("TRANSPORT",)}), ("A", 1, {"keywords": infantry})], 2: [("D", 1, {})]}
    game = await _game(client, session, tmp_path, units=units, declare=False)
    game_id = game["id"]
    deployment_ = await _deployment(client, game_id)
    t, a = (_unit_named(deployment_, n) for n in "TA")
    (await _model_of(session, t)).transport = TransportCapacity(capacity=7, keywords=infantry)
    a_model = await _model_of(session, a)
    character = (
        await session.execute(select(Keyword).where(Keyword.name == "CHARACTER"))
    ).scalar_one_or_none() or Keyword(name="CHARACTER")
    inquisitor = Model(
        name="Inquisitor", faction_id=a_model.faction_id, save=3, toughness=3, oc=1,
        movement=6, wounds=4, leadership=6, base_size=a_model.base_size,
    )
    inquisitor.keywords = [character]
    inquisitor.abilities = []
    session.add(inquisitor)
    unit = (
        await session.execute(
            select(Unit).options(selectinload(Unit.unit_models)).where(Unit.id == a["unit_id"])
        )
    ).scalar_one()
    unit.unit_models.append(UnitModel(model=inquisitor))
    await session.commit()

    response = await _set(client, game_id, 1, a, "embarked", t)
    assert "can only carry ADEPTUS ASTARTES INFANTRY" in response.json()["detail"]
    inquisitor = (
        await session.execute(
            select(Model).options(selectinload(Model.abilities)).where(Model.id == inquisitor.id)
        )
    ).scalar_one()
    inquisitor.abilities.append(
        DatasheetAbility(name="Authority of the Inquisition", description="Authority")
    )
    await session.commit()
    response = await _set(client, game_id, 1, a, "embarked", t)
    assert response.status_code == 200, response.text
