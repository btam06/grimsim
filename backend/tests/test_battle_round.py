import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import DatasheetAbility, Detachment, DetachmentRule, Model, UnitModel
from app.services.in_game.battle_round import rounds_for
from tests.test_deployment import _deploy, _deployment, _game, _row, _unit_named

EVERY = "At the start of the battle round, you can select one friendly unit."
FIRST = (
    "At the start of the first battle round, before the first turn begins, this unit can make "
    'a Normal move of up to 6".'
)
ODD = "At the start of the first, third and fifth battle rounds, you can select one ability."


@pytest.mark.parametrize(
    "text,expected",
    [
        (EVERY, {1, 2, 3, 4, 5}),
        ("At the start of each battle round, roll one D6.", {1, 2, 3, 4, 5}),
        (FIRST, {1}),
        (ODD, {1, 3, 5}),
        ("At the start of the second or fourth battle round, gain 1CP.", {2, 4}),
        ("At the start of your Command phase, gain 1CP.", None),
        ("Until the end of the battle round, this unit has Stealth.", None),
        (None, None),
    ],
)
def test_rounds_for(text, expected):
    assert rounds_for(text) == expected


async def _ability(session, unit, name, description):
    # Gives the unit's models a datasheet ability.
    unit_model = (
        await session.execute(
            select(UnitModel).where(UnitModel.id == unit["models"][0]["unit_model_id"])
        )
    ).scalar_one()
    model = await session.get(Model, unit_model.model_id)
    await session.refresh(model, ["abilities"])
    model.abilities.append(DatasheetAbility(name=name, description=description))
    await session.commit()


async def _ready(client, session, tmp_path, abilities=(), detachment_rules=()):
    # A game whose units ("A" and "D") get `abilities` ([(unit, name,
    # description)]) and whose seat 2 detachment gets `detachment_rules`
    # ([(name, description)]) - then deployed, so its first battle round
    # begins.
    game = await _game(client, session, tmp_path, units={1: [("A", 1, {})], 2: [("D", 1, {})]})
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    for unit_name, name, description in abilities:
        await _ability(session, _unit_named(deployment, unit_name), name, description)
    if detachment_rules:
        # Seat 2's list's detachment (see tests/test_games.py's _setup).
        query = select(Detachment).where(Detachment.name == "Detachment 2")
        detachment = (await session.execute(query)).scalar_one()
        for name, description in detachment_rules:
            session.add(
                DetachmentRule(detachment_id=detachment.id, name=name, description=description)
            )
        await session.commit()
    for name, (x, y) in (("A", (20, 38)), ("D", (20, 4))):
        unit = _unit_named(deployment, name)
        response = await _deploy(client, game_id, unit, _row(unit, x, y))
        assert response.status_code == 200, response.text
    return response.json()


async def _round_start(client, game_id):
    return (await client.get(f"/games/{game_id}/round-start")).json()


async def _to_next_round(client, game_id):
    # Through both turns of the current battle round.
    game = (await client.get(f"/games/{game_id}")).json()
    battle_round = game["battle_round"]
    while game["battle_round"] == battle_round:
        game = (await client.post(f"/games/{game_id}/advance")).json()
    return game


async def test_no_rules_no_start_of_round(client: AsyncClient, session, tmp_path):
    game = await _ready(client, session, tmp_path)
    assert (game["battle_round"], game["phase"]) == (1, "command")
    rules = await _round_start(client, game["id"])
    assert all(p["rules"] == [] for p in rules["players"])


async def test_start_of_the_first_battle_round(client: AsyncClient, session, tmp_path):
    game = await _ready(client, session, tmp_path, abilities=[("D", 'Scouts 6"', FIRST)])
    game_id = game["id"]
    assert (game["battle_round"], game["phase"], game["turn_seat"]) == (1, "start_of_round", 2)
    rules = await _round_start(client, game_id)
    by_seat = {p["seat"]: p["rules"] for p in rules["players"]}
    assert by_seat[1] == []
    [rule] = by_seat[2]
    assert (rule["kind"], rule["name"], rule["description"], rule["units"]) == (
        "ability", 'Scouts 6"', FIRST, ["D"]
    )
    assert rule["options"] == []
    # D's Scouts move (seat 2 goes first): it can make one, then says it's
    # done. On to the first turn: its command phase, with its CP.
    assert game["scouting_seat"] == 2
    response = await client.post(f"/games/{game_id}/scouts/done", json={"seat": 2})
    assert response.status_code == 200, response.text
    cp = {p["seat"]: p["cp"] for p in game["players"]}
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "command"
    assert {p["seat"]: p["cp"] for p in game["players"]} == {s: c + 1 for s, c in cp.items()}
    # Only the first battle round.
    game = await _to_next_round(client, game_id)
    assert (game["battle_round"], game["phase"]) == (2, "command")


AUTOMATIC = (
    "At the start of the first battle round, if this unit is an attached unit, this unit has "
    "MOBILE until the end of the battle."
)


async def test_a_rule_without_a_decision_doesnt_stop_the_game(
    client: AsyncClient, session, tmp_path
):
    # E.g. Vingh's Wafers of Dynamism: it just happens.
    game = await _ready(client, session, tmp_path, abilities=[("D", "Wafers", AUTOMATIC)])
    assert (game["battle_round"], game["phase"]) == (1, "command")
    # It's still a start-of-round rule, just not one to decide anything about.
    [rule] = [r for p in (await _round_start(client, game["id"]))["players"] for r in p["rules"]]
    assert (rule["name"], rule["decision"]) == ("Wafers", False)


async def test_a_rule_with_a_decision_lists_the_others_too(
    client: AsyncClient, session, tmp_path
):
    game = await _ready(
        client,
        session,
        tmp_path,
        abilities=[("D", "Wafers", AUTOMATIC), ("A", 'Scouts 6"', FIRST)],
    )
    assert game["phase"] == "start_of_round"
    players = (await _round_start(client, game["id"]))["players"]
    rules = {r["name"]: r["decision"] for p in players for r in p["rules"]}
    assert rules == {"Wafers": False, 'Scouts 6"': True}


async def test_every_battle_round(client: AsyncClient, session, tmp_path):
    game = await _ready(client, session, tmp_path, abilities=[("A", "Thrallnet", EVERY)])
    game_id = game["id"]
    assert game["phase"] == "start_of_round"
    await client.post(f"/games/{game_id}/advance")
    game = await _to_next_round(client, game_id)
    assert (game["battle_round"], game["phase"]) == (2, "start_of_round")
    [player] = [p for p in (await _round_start(client, game_id))["players"] if p["rules"]]
    assert (player["seat"], player["rules"][0]["name"]) == (1, "Thrallnet")


async def test_detachment_rule_on_some_rounds(client: AsyncClient, session, tmp_path):
    game = await _ready(client, session, tmp_path, detachment_rules=[("Dread", ODD)])
    game_id = game["id"]
    phases = [game["phase"]]
    await client.post(f"/games/{game_id}/advance")
    for _ in range(2):
        game = await _to_next_round(client, game_id)
        phases.append(game["phase"])
        if game["phase"] == "start_of_round":
            await client.post(f"/games/{game_id}/advance")
    # Rounds 1 and 3, not 2.
    assert phases == ["start_of_round", "command", "start_of_round"]
    rules = await _round_start(client, game_id)
    [rule] = [r for p in rules["players"] for r in p["rules"]]
    assert (rule["kind"], rule["name"], rule["units"]) == ("detachment rule", "Dread", [])


async def test_army_rule_at_the_start_of_every_round(client: AsyncClient, session, tmp_path):
    # E.g. Doctrina Imperatives: "At the start of the battle round, you can
    # select one of the Doctrina Imperatives below."
    from app.models import FactionAbility

    game = await _game(client, session, tmp_path, units={1: [("A", 1, {})], 2: [("D", 1, {})]})
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a = _unit_named(deployment, "A")
    unit_model = await session.get(UnitModel, a["models"][0]["unit_model_id"])
    model = await session.get(Model, unit_model.model_id)
    await session.refresh(model, ["faction_abilities"])
    model.faction_abilities.append(
        FactionAbility(name="Imperatives", description=EVERY, faction_id=model.faction_id)
    )
    await session.commit()
    for name, (x, y) in (("A", (20, 38)), ("D", (20, 4))):
        unit = _unit_named(deployment, name)
        game = (await _deploy(client, game_id, unit, _row(unit, x, y))).json()
    assert game["phase"] == "start_of_round"
    rules = await _round_start(client, game_id)
    [rule] = [r for p in rules["players"] for r in p["rules"]]
    assert (rule["kind"], rule["name"], rule["units"]) == ("army rule", "Imperatives", ["A"])


# --- choosing army rule options (e.g. Doctrina Imperatives) ---

DOCTRINA = "Doctrina Imperatives"
PROTECTOR, CONQUEROR = "Protector Imperative", "Conqueror Imperative"


async def _doctrina_game(client, session, tmp_path):
    # Seat 1's faction is the Adeptus Mechanicus, and its unit A has Doctrina
    # Imperatives (its options are the AdMech seed's: Protector or
    # Conqueror). D has a gun. Deployed: at the start of the first round.
    from app.models import Faction, FactionAbility

    units = {1: [("A", 1, {})], 2: [("D", 1, {"weapon_range": 24})]}
    game = await _game(client, session, tmp_path, units=units)
    game_id = game["id"]
    deployment = await _deployment(client, game_id)
    a = _unit_named(deployment, "A")
    unit_model = await session.get(UnitModel, a["models"][0]["unit_model_id"])
    model = await session.get(Model, unit_model.model_id)
    faction = await session.get(Faction, model.faction_id)
    faction.name = "Adeptus Mechanicus"
    await session.refresh(model, ["faction_abilities"])
    ability = FactionAbility(name=DOCTRINA, description=EVERY, faction_id=faction.id)
    model.faction_abilities.append(ability)
    await session.commit()
    for name, (x, y) in (("A", (20, 38)), ("D", (20, 4))):
        unit = _unit_named(deployment, name)
        game = (await _deploy(client, game_id, unit, _row(unit, x, y))).json()
    assert game["phase"] == "start_of_round"
    return game_id, ability.id, deployment


def _doctrina(rules):
    return next(r for p in rules["players"] for r in p["rules"] if r["name"] == DOCTRINA)


async def _choose(client, game_id, ability_id, option, seat=1):
    return await client.post(
        f"/games/{game_id}/round-start/choice",
        json={"seat": seat, "faction_ability_id": ability_id, "option": option},
    )


async def test_choose_a_doctrina_imperative(client: AsyncClient, session, tmp_path):
    game_id, ability_id, _ = await _doctrina_game(client, session, tmp_path)
    rule = _doctrina(await _round_start(client, game_id))
    assert (rule["faction_ability_id"], rule["options"], rule["chosen"]) == (
        ability_id, [PROTECTOR, CONQUEROR], None
    )
    assert set(rule["option_descriptions"]) <= {PROTECTOR, CONQUEROR}
    # Required: one or the other, no "none".
    assert rule["required"]

    response = await _choose(client, game_id, ability_id, PROTECTOR)
    assert response.status_code == 200, response.text
    assert _doctrina(response.json())["chosen"] == PROTECTOR
    # Changing it - but not back to none.
    assert _doctrina((await _choose(client, game_id, ability_id, CONQUEROR)).json())[
        "chosen"
    ] == CONQUEROR
    response = await _choose(client, game_id, ability_id, None)
    assert "must have one of its options chosen" in response.json()["detail"]
    assert _doctrina(await _round_start(client, game_id))["chosen"] == CONQUEROR

    # Not an option, not their rule, and only at the start of the round.
    assert (await _choose(client, game_id, ability_id, "Nope")).status_code == 400
    assert (await _choose(client, game_id, ability_id, PROTECTOR, seat=2)).status_code == 400
    await client.post(f"/games/{game_id}/advance")
    response = await _choose(client, game_id, ability_id, PROTECTOR)
    assert "start of the battle round" in response.json()["detail"]


async def test_chosen_imperative_goes_to_the_calculator(
    client: AsyncClient, session, tmp_path, monkeypatch
):
    # D (seat 2, whose turn it is first) shoots A, whose player chose the
    # Protector Imperative: the calculator gets it as the defender's option.
    from tests.test_shooting import _place, _shoot

    game_id, ability_id, deployment = await _doctrina_game(client, session, tmp_path)
    await _choose(client, game_id, ability_id, PROTECTOR)
    seen = []
    import app.routers.games as games_router

    real = games_router.calculate_combat

    async def capture(session_, payload, **kwargs):
        seen.append((payload.attacker_rule_options, payload.defender_rule_options))
        return await real(session_, payload, **kwargs)

    monkeypatch.setattr(games_router, "calculate_combat", capture)
    a, d = _unit_named(deployment, "A"), _unit_named(deployment, "D")
    await _place(session, a, [(20, 22)])
    for _ in ("command", "movement", "shooting"):
        await client.post(f"/games/{game_id}/advance")
    response = await _shoot(client, game_id, d, a)
    assert response.status_code == 200, response.text
    assert seen == [([], [PROTECTOR])]


async def test_first_turn_waits_for_a_required_choice(client: AsyncClient, session, tmp_path):
    game_id, ability_id, _ = await _doctrina_game(client, session, tmp_path)
    response = await client.post(f"/games/{game_id}/advance")
    assert response.status_code == 400
    assert "choose an option first for Alice's Doctrina Imperatives" in response.json()["detail"]
    await _choose(client, game_id, ability_id, PROTECTOR)
    game = (await client.post(f"/games/{game_id}/advance")).json()
    assert game["phase"] == "command"


async def test_faction_ability_says_its_option_is_required(client: AsyncClient, session, tmp_path):
    await _doctrina_game(client, session, tmp_path)
    abilities = (await client.get("/faction-abilities")).json()
    doctrina = next(a for a in abilities if a["name"] == DOCTRINA)
    assert (doctrina["rule_options"], doctrina["required"]) == ([PROTECTOR, CONQUEROR], True)
