from httpx import AsyncClient

from app.models import DatasheetAbility, Faction, Keyword, Model, Unit, UnitModel
from app.routers import combat as combat_router
from app.routers.games import _load_game, _rule_options
from app.seeds.factions.space_marines import conditions as sm_conditions
from app.services.in_game import command_phase, deployment
from app.services.list_building import enhancements as enhancement_rules
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named

# Seat 1's faction is the Space Marines (renamed from the test faction): A is
# an ADEPTUS ASTARTES unit; G has the ULTRAMARINES keyword of its own (like
# Roboute Guilliman); X has neither. Seat 2 has D.


async def _space_marines_game(client, session, tmp_path):
    units = {
        1: [
            ("A", 1, {"weapon_range": 24, "keywords": ("ADEPTUS ASTARTES",)}),
            ("X", 1, {"weapon_range": 24}),
        ],
        2: [("D", 1, {"weapon_range": 24})],
    }
    game = await _game(client, session, tmp_path, units=units)
    deployment_ = await _deployment(client, game["id"])
    named = {name: _unit_named(deployment_, name) for name in "AXD"}
    unit_model = await session.get(UnitModel, named["A"]["models"][0]["unit_model_id"])
    model = await session.get(Model, unit_model.model_id)
    faction = await session.get(Faction, model.faction_id)
    faction.name = "Space Marines"
    await session.commit()
    game_ = await _load_game(session, game["id"])
    army_list = next(p for p in game_.players if p.seat == 1).army_list
    return game["id"], army_list.id, named


async def _list_payload(client, list_id, **changes):
    current = next(item for item in (await client.get("/lists")).json() if item["id"] == list_id)
    keys = ("name", "points_limit", "faction_id", "detachment_ids", "user_id", "subfaction")
    return {**{k: current[k] for k in keys}, **changes}


async def _put_list(client, list_id, **changes):
    return await client.put(f"/lists/{list_id}", json=await _list_payload(client, list_id, **changes))


async def _keywords(session, unit_id):
    # (Fresh: the list may have changed since this session last loaded it.)
    session.expire_all()
    unit = await combat_router._load_unit(session, unit_id)
    return enhancement_rules.model_keywords(unit, unit.unit_models[0])


async def test_a_chapter_gives_its_keyword_to_adeptus_astartes_models(
    client: AsyncClient, session, tmp_path
):
    _, list_id, named = await _space_marines_game(client, session, tmp_path)
    factions = (await client.get("/factions")).json()
    space_marines = next(f for f in factions if f["name"] == "Space Marines")
    assert space_marines["subfaction_label"] == "Chapter"
    assert "Ultramarines" in space_marines["subfactions"]

    response = await _put_list(client, list_id, subfaction="Iron Hands")
    assert response.status_code == 400 and "no Chapter" in response.json()["detail"]
    response = await _put_list(client, list_id, subfaction="Ultramarines")
    assert response.status_code == 200, response.text
    assert response.json()["subfaction"] == "Ultramarines"
    assert "ULTRAMARINES" in await _keywords(session, named["A"]["unit_id"])
    # Only ADEPTUS ASTARTES models.
    assert "ULTRAMARINES" not in await _keywords(session, named["X"]["unit_id"])
    await _put_list(client, list_id, subfaction=None)
    assert "ULTRAMARINES" not in await _keywords(session, named["A"]["unit_id"])


async def test_a_chapter_keyword_model_only_in_that_chapters_list(
    client: AsyncClient, session, tmp_path
):
    _, list_id, named = await _space_marines_game(client, session, tmp_path)
    # A model with ULTRAMARINES of its own (like Roboute Guilliman).
    a = await session.get(Unit, named["A"]["unit_id"])
    unit_model = await session.get(UnitModel, named["A"]["models"][0]["unit_model_id"])
    await session.refresh(unit_model, ["model"])
    await session.refresh(unit_model.model, ["keywords"])
    unit_model.model.keywords.append(Keyword(name="ULTRAMARINES"))
    await session.commit()
    payload = {
        "faction_unit_id": a.faction_unit_id,
        "points": 100,
        "list_id": list_id,
        "unit_models": [{"model_id": unit_model.model_id, "weapon_ids": [], "wargear_ids": []}],
    }
    response = await client.post("/units", json=payload)
    assert response.status_code == 400
    assert "can only be included in an Ultramarines list" in response.json()["detail"]
    # Nor can a list it's already in change Chapter away from it.
    response = await _put_list(client, list_id, subfaction="Ultramarines")
    assert response.status_code == 200, response.text
    response = await client.post("/units", json=payload)
    assert response.status_code == 201, response.text
    response = await _put_list(client, list_id, subfaction=None)
    assert "can only be included in an Ultramarines list" in response.json()["detail"]


async def test_a_supreme_commander_must_be_the_warlord(client: AsyncClient, session, tmp_path):
    from app.services.list_building.warlord import warlord_reason

    _, list_id, named = await _space_marines_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, named["A"]["models"][0]["unit_model_id"])
    model = await session.get(Model, unit_model.model_id)
    await session.refresh(model, ["abilities", "keywords"])
    model.abilities.append(
        DatasheetAbility(
            name="Supreme Commander",
            description="If this model is in your army, it must be your Warlord.",
        )
    )
    model.keywords.append(Keyword(name="CHARACTER"))
    await session.commit()
    # Saving the list: another unit can't be its Warlord, but none (yet) can.
    response = await _put_list(client, list_id, warlord_unit_id=named["X"]["unit_id"])
    assert response.status_code == 400
    response = await _put_list(client, list_id, warlord_unit_id=None)
    assert response.status_code == 200, response.text
    # Starting a game: it must be (see app/services/in_game/game.py).
    assert await warlord_reason(session, list_id, None) == "A must be the list's Warlord"
    response = await _put_list(client, list_id, warlord_unit_id=named["A"]["unit_id"])
    assert response.status_code == 200, response.text
    assert await warlord_reason(session, list_id, named["A"]["unit_id"]) is None


async def test_codex_adept_has_every_doctrine(client: AsyncClient, session, tmp_path):
    game_id, _, named = await _space_marines_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, named["A"]["models"][0]["unit_model_id"])
    model = await session.get(Model, unit_model.model_id)
    await session.refresh(model, ["abilities"])
    model.abilities.append(DatasheetAbility(name="Codex Adept", description="Codex Adept"))
    await session.commit()
    for name, (x, y) in (("A", (20, 38)), ("D", (20, 4)), ("X", (30, 38))):
        response = await _deploy(client, game_id, named[name], _row(named[name], x, y))
        assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    a, x = (deployment.find_unit(game, named[n]["unit_id"]) for n in "AX")
    assert command_phase.eligible_after(game, a, "advanced", "charge")
    assert command_phase.eligible_after(game, a, "fell_back", "shoot")
    assert not command_phase.eligible_after(game, x, "fell_back", "shoot")
    assert {"Assault Doctrine", "Devastator Doctrine", "Tactical Doctrine"} <= set(
        _rule_options(game, a)
    )
    assert "Devastator Doctrine" not in _rule_options(game, x)


def test_never_shall_the_standard_fall():
    on_objective = {"defender_positions": {"in_range_of_objective"}}
    stronger = {"step": "wound", "strength": 8, "toughness": 6}
    assert sm_conditions.standard_fall({**on_objective, **stronger})
    assert not sm_conditions.standard_fall({**on_objective, **stronger, "strength": 6})
    assert not sm_conditions.standard_fall(stronger)


def test_terminatus_assault():
    crit = {"step": "hit", "roll": 6, "charged": True}
    infantry = {"defender_keywords": {"INFANTRY"}}
    vehicle = {"defender_keywords": {"VEHICLE"}}
    claws = {"weapon_name": "Twin Lightning Claws"}
    hammer = {"weapon_name": "Thunder Hammer"}
    claws_check = sm_conditions.charged_claws_critical_vs_non_monster_vehicle
    hammer_check = sm_conditions.charged_hammer_critical_vs_monster_vehicle
    assert claws_check({**crit, **infantry, **claws})
    assert not claws_check({**crit, **vehicle, **claws})
    assert not claws_check({**crit, **infantry, **claws, "charged": False})
    assert hammer_check({**crit, **vehicle, **hammer})
    assert not hammer_check({**crit, **infantry, **hammer})
    assert not hammer_check({**crit, **vehicle, **claws})


def test_weapon_profiles():
    from types import SimpleNamespace

    from app.services.weapon_profiles import conflicting_profiles, profile_group

    assert profile_group("Plasma caliver – supercharge") == "Plasma caliver"
    assert profile_group("Smite - Witchfire") == "Smite"
    assert profile_group("Storm Bolter") is None
    weapon = lambda name: SimpleNamespace(name=name)  # noqa: E731
    both = [weapon("Plasma caliver – standard"), weapon("Plasma caliver – supercharge")]
    assert conflicting_profiles(both) == "Plasma caliver"
    # The same profile twice (two of the weapon) is fine; so are other weapons.
    assert conflicting_profiles(
        [weapon("Plasma caliver – standard"), weapon("Plasma caliver – standard"), weapon("Axe")]
    ) is None


async def test_attacking_with_both_profiles_isnt_allowed(client: AsyncClient, session, tmp_path):
    from app.models import Weapon

    game_id, _, named = await _space_marines_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, named["A"]["models"][0]["unit_model_id"])
    for profile in ("standard", "supercharge"):
        weapon = Weapon(
            name=f"Plasma gun – {profile}", weapon_type="ranged", range=24, attacks="1",
            skill=3, strength=7, ap=-2, damage="1", model_id=unit_model.model_id,
        )
        session.add(weapon)
        await session.flush()
        await session.refresh(unit_model, ["weapons"])
        unit_model.weapons.append(weapon)
    await session.commit()
    ids = [w.id for w in unit_model.weapons if w.name.startswith("Plasma gun")]
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": named["A"]["unit_id"],
            "defending_unit_id": named["D"]["unit_id"],
            "selected_weapon_ids": ids,
        },
    )
    assert response.status_code == 400
    assert "only one profile of Plasma gun" in response.json()["detail"]


def test_storm_shield_adds_a_wound():
    from types import SimpleNamespace

    from app.models import UnitModel as UM

    wounds = UM.wounds.fget
    shield = SimpleNamespace(
        model=SimpleNamespace(wounds=3), wargear=[SimpleNamespace(name="Storm Shield")]
    )
    assert wounds(shield) == 4
    assert wounds(SimpleNamespace(model=SimpleNamespace(wounds=3), wargear=[])) == 3


def test_cleave_2_is_blast_2():
    from collections import deque

    from app.combat_rules.effects import EFFECTS

    state: dict = {}
    EFFECTS["blast_2"](state, deque())
    assert state["blast"] == 2


async def test_lone_operative_only_shot_from_within_12(client: AsyncClient, session, tmp_path):
    from app.services.in_game import shooting

    game_id, _, named = await _space_marines_game(client, session, tmp_path)
    unit_model = await session.get(UnitModel, named["D"]["models"][0]["unit_model_id"])
    model = await session.get(Model, unit_model.model_id)
    await session.refresh(model, ["abilities"])
    model.abilities.append(DatasheetAbility(name="Lone Operative", description="Lone Operative"))
    await session.commit()
    for name, (x, y) in (("A", (20, 38)), ("D", (20, 4)), ("X", (40, 38))):
        response = await _deploy(client, game_id, named[name], _row(named[name], x, y))
        assert response.status_code == 200, response.text
    game = await _load_game(session, game_id)
    a, d = (deployment.find_unit(game, named[n]["unit_id"]) for n in "AD")
    assert shooting.lone_operative(game, d)
    positions = deployment.positions(game)
    # 16" away with a 24" gun: out of range of a Lone Operative...
    for m in d.unit_models:
        positions[m.id].y = 22
    assert all(w.in_range == 0 for w in shooting.reach(game, a, d).weapons)
    # ...but in range within 12".
    for m in d.unit_models:
        positions[m.id].y = 30
    assert any(w.in_range for w in shooting.reach(game, a, d).weapons)


async def test_two_supreme_commanders_either_can_be_warlord(
    client: AsyncClient, session, tmp_path
):
    from app.services.list_building.warlord import warlord_reason

    _, list_id, named = await _space_marines_game(client, session, tmp_path)
    for name in "AX":
        unit_model = await session.get(UnitModel, named[name]["models"][0]["unit_model_id"])
        model = await session.get(Model, unit_model.model_id)
        await session.refresh(model, ["abilities"])
        model.abilities.append(
            DatasheetAbility(name="Supreme Commander", description="Supreme Commander")
        )
    await session.commit()
    assert await warlord_reason(session, list_id, None) == "A or X must be the list's Warlord"
    assert await warlord_reason(session, list_id, named["X"]["unit_id"]) is None
    assert await warlord_reason(session, list_id, named["A"]["unit_id"]) is None
