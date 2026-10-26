import pytest
from httpx import AsyncClient

from app.combat_rules import Rule
from app.models import (
    Condition,
    DatasheetAbility,
    Effect,
    Enhancement,
    EnhancementDatasheetAbility,
    EnhancementWeaponAbility,
    Keyword,
    Model,
    Stratagem,
    Unit,
    UnitModel,
    Wargear,
    WargearAbility,
    Weapon,
    WeaponAbility,
)
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.seeds import weapon_abilities as weapon_ability_seeds
from app.seeds.factions.adeptus_mechanicus import abilities as admech_abilities
from app.seeds.factions.orks import abilities as orks_abilities
from app.services import combat


def _condition(keyword: str) -> Condition:
    return Condition(keyword=keyword, name=keyword, description=None)


def _keyword(name: str) -> Keyword:
    return Keyword(name=name)


def _effect(keyword: str) -> Effect:
    return Effect(keyword=keyword, name=keyword, description=None)


def _ability(conditions: list[Condition], effects: list[Effect]) -> WeaponAbility:
    ability = WeaponAbility(name="Test Ability", description=None)
    ability.conditions = conditions
    ability.effects = effects
    return ability


def _wargear_ability(conditions: list[Condition], effects: list[Effect]) -> WargearAbility:
    ability = WargearAbility(name="Test Wargear Ability", description=None)
    ability.conditions = conditions
    ability.effects = effects
    return ability


def _wargear(abilities: list[WargearAbility] | None = None) -> Wargear:
    gear = Wargear(name="Gear", model_id=1, description=None)
    gear.abilities = abilities or []
    return gear


def _datasheet_ability(conditions: list[Condition], effects: list[Effect]) -> DatasheetAbility:
    ability = DatasheetAbility(name="Test Datasheet Ability", description=None)
    ability.conditions = conditions
    ability.effects = effects
    return ability


def _model(**overrides) -> Model:
    keywords = overrides.pop("keywords", None)
    abilities = overrides.pop("abilities", None)
    defaults = dict(
        name="Target",
        faction_id=1,
        save=3,
        toughness=4,
        oc=1,
        movement=6,
        wounds=2,
        leadership=7,
        invulnerable=None,
        feel_no_pain=None,
    )
    defaults.update(overrides)
    model = Model(**defaults)
    model.keywords = keywords or []
    model.abilities = abilities or []
    return model


def _weapon(**overrides) -> Weapon:
    defaults = dict(
        name="Gun",
        model_id=1,
        damage="1",
        range=24,
        strength=4,
        ap=0,
        attacks="1",
        skill=3,
        weapon_type=None,
    )
    defaults.update(overrides)
    return Weapon(**defaults)


def _unit_model(
    model: Model, weapons: list[Weapon], wargear: list[Wargear] | None = None
) -> UnitModel:
    um = UnitModel(unit_id=1, model_id=1)
    um.model = model
    um.weapons = weapons
    um.wargear = wargear or []
    return um


def _unit(unit_models: list[UnitModel]) -> Unit:
    unit = Unit(faction_unit_id=1, points=100)
    unit.unit_models = unit_models
    return unit


# --- wound_threshold table ---


@pytest.mark.parametrize(
    "strength,toughness,expected",
    [
        (8, 4, 2),  # double or more -> 2+
        (6, 4, 3),  # greater -> 3+
        (4, 4, 4),  # equal -> 4+
        (3, 4, 5),  # defender tougher -> 5+
        (2, 4, 6),  # defender double or more -> 6+
    ],
)
def test_wound_threshold(strength, toughness, expected):
    assert combat.wound_threshold(strength, toughness) == expected


# --- roll_dice ---


def test_roll_dice_flat():
    assert combat.roll_dice("5") == 5


def test_roll_dice_bare_die(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    assert combat.roll_dice("D6") == 4


def test_roll_dice_multi_die(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    assert combat.roll_dice("2D6") == 8


# --- _target_priority ---


def test_target_priority_orders_supports_and_leaders_last():
    normal_worst = _model(save=6)
    normal_better = _model(save=3)
    support_worst_save = _model(save=6, is_support=True)
    leader_best_save = _model(save=2, is_leader=True)

    ordered = sorted(
        [leader_best_save, support_worst_save, normal_better, normal_worst],
        key=combat._target_priority,
    )
    assert ordered == [normal_worst, normal_better, support_worst_save, leader_best_save]


def test_target_priority_uses_better_of_armor_and_invulnerable_save():
    bad_armor_great_invulnerable = _model(save=6, invulnerable=2)
    ok_armor_no_invulnerable = _model(save=4, invulnerable=None)

    ordered = sorted(
        [bad_armor_great_invulnerable, ok_armor_no_invulnerable], key=combat._target_priority
    )
    # effective save of 2 (from invulnerable) beats a plain 4+, despite the worse armor save
    assert ordered == [ok_armor_no_invulnerable, bad_armor_great_invulnerable]


# --- resolve_combat ---


def test_resolve_combat_not_visible_deals_no_damage(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="2", skill=2)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=False, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == []
    assert result.total_damage == 0


def test_resolve_combat_not_in_range_deals_no_damage(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="2", skill=2)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=False, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == []


def test_resolve_combat_in_range_is_checked_per_attacking_model(monkeypatch):
    # in_range is evaluated once per attacking model (not once for the whole unit),
    # so every model's weapons should still fire when it's True.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon_a = _weapon(attacks="2", skill=2)
    weapon_a.id = 1
    weapon_b = _weapon(attacks="3", skill=2)
    weapon_b.id = 2
    attacker = _unit(
        [
            _unit_model(_model(), [weapon_a]),
            _unit_model(_model(), [weapon_b]),
        ]
    )
    defender = _unit([_unit_model(_model(wounds=100, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon_a.id, weapon_b.id},
        in_engagement_range=False,
        visible=True,
        in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert len(result.attack_rolls) == 5  # both attacking models' weapons fired


def test_resolve_combat_rolls_dice_notation_attacks(monkeypatch):
    # The weapon's attacks characteristic is dice notation, not a fixed count - it
    # must be rolled to get the actual attack count. Every random.randint call
    # (both attack-count dice and the hit rolls that follow) returns a constant 3,
    # which is below the weapon's skill of 5, so every attack simply misses.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    weapon = _weapon(attacks="2D3", skill=5)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=100, save=7), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert len(result.attack_rolls) == 6  # "2D3" rolled as two dice of 3 each
    assert result.wound_rolls == []  # every attack missed, so no wound rolls occurred


def test_resolve_combat_unselected_weapon_does_not_attack(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="3", skill=2)
    weapon.id = 42
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=10), [])])

    result = combat.resolve_combat(
        attacker, defender, set(), in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == []


def test_resolve_combat_engagement_range_selects_melee_only(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    melee = _weapon(attacks="2", skill=2, weapon_type="melee")
    melee.id = 1
    ranged = _weapon(attacks="5", skill=2, weapon_type="ranged")
    ranged.id = 2
    attacker = _unit([_unit_model(_model(), [melee, ranged])])
    defender = _unit([_unit_model(_model(wounds=100, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {melee.id, ranged.id},
        in_engagement_range=True,
        visible=True,
        in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert len(result.attack_rolls) == 2  # only the melee weapon's attacks counted


def test_resolve_combat_not_in_engagement_range_selects_ranged_only(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    melee = _weapon(attacks="2", skill=2, weapon_type="melee")
    melee.id = 1
    ranged = _weapon(attacks="5", skill=2, weapon_type="ranged")
    ranged.id = 2
    attacker = _unit([_unit_model(_model(), [melee, ranged])])
    defender = _unit([_unit_model(_model(wounds=100, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {melee.id, ranged.id},
        in_engagement_range=False,
        visible=True,
        in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert len(result.attack_rolls) == 5  # only the ranged weapon's attacks counted


def test_resolve_combat_targets_normal_models_before_supports(monkeypatch):
    # A single attack that deals 1 damage. The normal model has only 1 wound (dies
    # if targeted), the support has 100 (would survive untouched if targeted) -
    # even though the support has a far better save. If supports were wrongly
    # targeted first, this attack would land on it and fail to kill anything.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    normal_model = _model(wounds=1, save=6, invulnerable=None, feel_no_pain=None)
    support_model = _model(wounds=100, save=2, invulnerable=None, feel_no_pain=None, is_support=True)
    defender = _unit([_unit_model(support_model, []), _unit_model(normal_model, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.models_destroyed == 1  # the 1-wound normal model, not the support
    assert result.defending_models_remaining == 1


def test_resolve_combat_targets_worst_save_before_best_save(monkeypatch):
    # Within the same (non-support/leader) tier, the worse-saving model should be
    # targeted first. Only the worst-save model has few enough wounds to die from
    # this single attack.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    worst_save = _model(wounds=1, save=6, invulnerable=None, feel_no_pain=None)
    best_save = _model(wounds=100, save=2, invulnerable=None, feel_no_pain=None)
    defender = _unit([_unit_model(best_save, []), _unit_model(worst_save, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.models_destroyed == 1  # the worst-save model, not the best-save one
    assert result.defending_models_remaining == 1


def test_resolve_combat_does_not_spill_remaining_damage_onto_next_model(monkeypatch):
    # A constant roll of 6 always hits/wounds (thresholds engineered <= 6) and the
    # save is engineered to be impossible (save_needed > 6), with no FNP to roll.
    # The weapon deals 2 damage but the first model only has 1 wound - the second
    # point should be wasted, not carried onto the second model.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="2")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender_models = [
        _unit_model(_model(wounds=1, save=2, feel_no_pain=None), []),
        _unit_model(_model(wounds=1, save=2, feel_no_pain=None), []),
    ]
    defender = _unit(defender_models)

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == [6]
    assert result.wound_rolls == [6]
    assert result.save_rolls == [6]
    assert result.total_damage == 1  # the second point of damage is wasted, not spilled
    assert result.models_destroyed == 1
    assert result.defending_models_remaining == 1  # second model untouched


def test_resolve_combat_feel_no_pain_negates_some_damage(monkeypatch):
    rolls = iter([6, 6, 1, 6, 2, 5])  # hit, wound, save(fail), fnp x3 (succeed, fail, succeed)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="3")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=4), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.save_rolls == [1]
    assert result.total_damage == 1  # only the middle fnp roll (2) failed to negate
    assert result.models_destroyed == 0
    assert result.defending_models_remaining == 1


def test_resolve_combat_next_attack_targets_next_model_with_its_own_fnp(monkeypatch):
    # First model has no FNP and dies to the first attack's single point of damage
    # (no fnp roll consumed). The *second* attack (same weapon, two attacks total)
    # then targets the second model, which does have FNP - that attack's damage
    # must be checked against the second model's own threshold.
    # Phase order: both hits, both wounds, then each wound's save (and damage) in
    # turn - attack 1's save fails (model 1 dies), attack 2's save fails, fnp fails.
    rolls = iter([6, 6, 6, 6, 1, 1, 2])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    weapon = _weapon(attacks="2", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit(
        [
            _unit_model(_model(wounds=1, save=2, feel_no_pain=None), []),
            _unit_model(_model(wounds=5, save=2, feel_no_pain=4), []),
        ]
    )

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.save_rolls == [1, 1]
    # attack 1's point kills model 1 outright (no fnp to roll); attack 2's point
    # fails model 2's own fnp roll and so also lands -> 2 points of damage total.
    assert result.total_damage == 2
    assert result.models_destroyed == 1
    assert result.defending_models_remaining == 1


# --- weapon_results: per-weapon-profile breakdown ---


def test_resolve_combat_weapon_results_breaks_down_a_single_weapon(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    weapon = _weapon(name="Boltgun", attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert len(result.weapon_results) == 1
    wr = result.weapon_results[0]
    assert wr.name == "Boltgun"
    assert wr.attack_rolls == result.attack_rolls
    assert wr.wound_rolls == result.wound_rolls
    assert wr.save_rolls == result.save_rolls
    assert wr.total_damage == result.total_damage
    assert wr.models_destroyed == result.models_destroyed


def test_resolve_combat_weapon_results_groups_same_named_weapons_across_models(monkeypatch):
    # Two different models each carry their own "Boltgun" weapon (different
    # ids, same name) - they should be grouped into a single weapon_results
    # entry rather than appearing as two separate profiles.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    weapon_a = _weapon(name="Boltgun", attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon_a.id = 1
    weapon_b = _weapon(name="Boltgun", attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon_b.id = 2
    attacker = _unit(
        [
            _unit_model(_model(), [weapon_a]),
            _unit_model(_model(), [weapon_b]),
        ]
    )
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon_a.id, weapon_b.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert len(result.weapon_results) == 1
    wr = result.weapon_results[0]
    assert wr.name == "Boltgun"
    assert len(wr.attack_rolls) == 2  # both models' Boltguns pooled into one entry
    assert wr.total_damage == 2


def test_resolve_combat_weapon_results_keeps_differently_named_weapons_separate(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    weapon_a = _weapon(name="Boltgun", attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon_a.id = 1
    weapon_b = _weapon(name="Plasma Gun", attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon_b.id = 2
    attacker = _unit([_unit_model(_model(), [weapon_a, weapon_b])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon_a.id, weapon_b.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    names = {wr.name for wr in result.weapon_results}
    assert names == {"Boltgun", "Plasma Gun"}
    for wr in result.weapon_results:
        assert len(wr.attack_rolls) == 1


# --- weapon ability conditions/effects ---


def test_resolve_combat_sustained_hits_adds_extra_hit_on_critical(monkeypatch):
    # A constant roll of 6: the hit always crits (triggering the extra-hit effect),
    # the wound threshold is engineered <= 6 so it always wounds, and the save is
    # engineered to be impossible so every wound lands as 1 point of damage.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    sustained_1 = _ability([_condition("critical_hit")], [_effect("add_extra_hit")])
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [sustained_1]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    # Only the original attack rolls a hit die; the sustained hit is granted outright.
    assert result.attack_rolls == [6]
    # Both the original hit and the sustained hit roll their own wound and save.
    assert result.wound_rolls == [6, 6]
    assert result.save_rolls == [6, 6]
    assert result.total_damage == 2


def test_resolve_combat_sustained_hits_does_nothing_on_a_non_critical_hit(monkeypatch):
    # A roll of 3 still hits (skill 2) but isn't a critical (not a 6), so the
    # sustained-hits ability should not add anything to the attack chain.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    sustained_1 = _ability([_condition("critical_hit")], [_effect("add_extra_hit")])
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [sustained_1]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == [3]
    assert result.wound_rolls == [3]
    assert result.save_rolls == [3]
    assert result.total_damage == 1


def test_resolve_combat_auto_pass_wound_skips_the_wound_roll(monkeypatch):
    # A critical hit (roll of 6) triggers an auto-pass-wound effect instead of
    # sustained hits - the wound roll should be skipped entirely for this attack.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    ability = _ability([_condition("critical_hit")], [_effect("auto_pass_wound")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [ability]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    # Strength 1 vs toughness 100 would normally never wound, but the effect
    # forces the wound to pass without a roll being made at all.
    assert result.attack_rolls == [6]
    assert result.wound_rolls == []
    assert result.save_rolls == [6]
    assert result.total_damage == 1


def test_resolve_combat_lethal_hits_auto_wounds_on_a_critical_hit(monkeypatch):
    # "Lethal Hits": critical_hit -> auto_pass_wound. Strength 1 vs toughness 100
    # would normally never wound, but a critical hit (roll of 6) should still
    # force the wound to pass without a roll being made at all.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    lethal_hits = _ability([_condition("critical_hit")], [_effect("auto_pass_wound")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [lethal_hits]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == [6]
    assert result.wound_rolls == []
    assert result.total_damage == 1


def test_resolve_combat_devastating_wounds_skips_the_save_roll_on_a_critical_wound(monkeypatch):
    # "Devastating Wounds": critical_wound -> no_save. A save of 2+ with an
    # invulnerable of 2+ would normally always succeed, but a critical wound
    # (roll of 6) should skip the save roll entirely and apply damage.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    devastating_wounds = _ability([_condition("critical_wound")], [_effect("no_save")])
    weapon = _weapon(attacks="1", skill=2, strength=10, damage="1")
    weapon.id = 1
    weapon.abilities = [devastating_wounds]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit(
        [_unit_model(_model(wounds=5, save=2, invulnerable=2, feel_no_pain=None), [])]
    )

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == [6]
    assert result.wound_rolls == [6]
    assert result.save_rolls == []  # no save roll at all - always-passing save was bypassed
    assert result.total_damage == 1


def test_resolve_combat_devastating_wounds_does_nothing_on_a_non_critical_wound(monkeypatch):
    # A wound roll of 3 (vs threshold 2, since strength 10 is double toughness 1)
    # still wounds but isn't a critical, so the save should still be rolled normally.
    rolls = iter([6, 3, 1])  # hit (crit, irrelevant here), wound (non-crit), save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    devastating_wounds = _ability([_condition("critical_wound")], [_effect("no_save")])
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=0, damage="1")
    weapon.id = 1
    weapon.abilities = [devastating_wounds]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.wound_rolls == [3]
    assert result.save_rolls == [1]  # the save was rolled normally (and failed here)
    assert result.total_damage == 1


def test_critical_wound_condition_matches_only_wound_step_sixes():
    assert combat.CONDITIONS["critical_wound"]({"step": "wound", "roll": 6}) is True
    assert combat.CONDITIONS["critical_wound"]({"step": "wound", "roll": 5}) is False
    assert combat.CONDITIONS["critical_wound"]({"step": "hit", "roll": 6}) is False


def test_resolve_combat_unmatched_condition_keyword_is_ignored(monkeypatch):
    # A condition keyword with no hardcoded implementation should simply never
    # match, rather than raising - the ability is inert.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    ability = _ability([_condition("unknown_condition")], [_effect("add_extra_hit")])
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [ability]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == [6]
    assert result.total_damage == 1  # just the one attack, no sustained hit granted


# --- always condition / in_cover / ignore_cover ---


def test_always_condition_matches_any_context():
    assert combat.CONDITIONS["always"]({}) is True
    assert combat.CONDITIONS["always"]({"step": "wound", "roll": 1}) is True


def test_resolve_combat_in_cover_worsens_ranged_hit_rolls(monkeypatch):
    # A roll of 3 would normally hit (skill 3), but a ranged attack against a
    # target in cover needs a 4 instead, so this attack should miss.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=True,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.wound_rolls == []  # the worsened hit roll missed
    assert result.total_damage == 0


def test_resolve_combat_in_cover_does_not_affect_melee(monkeypatch):
    # In cover only matters for ranged attacks - a melee attack with the same
    # roll (3) against the same skill (3) should still hit.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    weapon = _weapon(attacks="1", skill=3, weapon_type="melee", strength=10, ap=-10)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=True,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.wound_rolls == [3]  # the hit succeeded despite in_cover


def test_resolve_combat_ignore_cover_weapon_ability_negates_the_penalty(monkeypatch):
    # Same setup as the "in cover worsens ranged hits" test, but this time the
    # weapon has an "Ignores Cover" ability (always -> ignore_cover), so the
    # roll of 3 should still hit at the unworsened skill of 3.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    ignores_cover = _ability([_condition("always")], [_effect("ignore_cover")])
    weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
    weapon.id = 1
    weapon.abilities = [ignores_cover]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=True,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.wound_rolls == [3]  # ignored the cover penalty and hit


def test_resolve_combat_ignore_cover_wargear_ability_negates_the_penalty(monkeypatch):
    # The "Ignores Cover" ability lives on wargear equipped by the model instead
    # of on the weapon itself - it should still negate the cover penalty for
    # every weapon that model fires.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    ignores_cover = _wargear_ability([_condition("always")], [_effect("ignore_cover")])
    gear = _wargear([ignores_cover])
    weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon], wargear=[gear])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=True,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.wound_rolls == [3]  # ignored the cover penalty and hit


# --- anti-infantry / anti-vehicle ---


def test_anti_infantry_4_condition_checks_wound_step_roll_and_keyword():
    matching = {"step": "wound", "roll": 4, "defender_keywords": {"INFANTRY", "CHARACTER"}}
    below_threshold = {"step": "wound", "roll": 3, "defender_keywords": {"INFANTRY"}}
    wrong_step = {"step": "hit", "roll": 4, "defender_keywords": {"INFANTRY"}}
    no_keyword = {"step": "wound", "roll": 4, "defender_keywords": {"VEHICLE"}}
    assert combat.CONDITIONS["anti_infantry_4"](matching) is True
    assert combat.CONDITIONS["anti_infantry_4"](below_threshold) is False
    assert combat.CONDITIONS["anti_infantry_4"](wrong_step) is False
    assert combat.CONDITIONS["anti_infantry_4"](no_keyword) is False


def test_resolve_combat_anti_infantry_4_plus_scores_a_critical_wound_at_the_threshold(
    monkeypatch,
):
    # Anti-Infantry 4+: anti_infantry_4 -> force_critical_wound. Strength 1 vs
    # toughness 100 would normally need a natural 6 to wound, but a wound roll
    # of 4+ against an INFANTRY defender counts as a critical wound regardless.
    rolls = iter([6, 4, 1])  # hit, wound, save (AP -10 always fails regardless)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    anti_infantry = _ability([_condition("anti_infantry_4")], [_effect("force_critical_wound")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [anti_infantry]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    defender_model = _model(wounds=5, save=2, feel_no_pain=None, keywords=[_keyword("INFANTRY")])
    defender = _unit([_unit_model(defender_model, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.attack_rolls == [6]
    assert result.wound_rolls == [4]  # the roll is actually made, not skipped
    assert result.total_damage == 1


def test_resolve_combat_anti_infantry_4_plus_does_nothing_below_the_threshold(monkeypatch):
    # A wound roll below the Anti-Infantry 4+ threshold is just a normal roll.
    rolls = iter([6, 3])  # hit, wound
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    anti_infantry = _ability([_condition("anti_infantry_4")], [_effect("force_critical_wound")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [anti_infantry]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    defender_model = _model(wounds=5, save=2, feel_no_pain=None, keywords=[_keyword("INFANTRY")])
    defender = _unit([_unit_model(defender_model, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.wound_rolls == [3]
    assert result.total_damage == 0  # below both the anti-infantry and normal wound thresholds


def test_resolve_combat_anti_infantry_does_nothing_without_the_keyword(monkeypatch):
    # With a non-matching defender (no INFANTRY keyword), Anti-Infantry 4+
    # should not force anything, even on a roll that would meet its threshold.
    rolls = iter([6, 4])  # hit, wound
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    anti_infantry = _ability([_condition("anti_infantry_4")], [_effect("force_critical_wound")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [anti_infantry]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    defender_model = _model(wounds=5, save=2, feel_no_pain=None, keywords=[_keyword("VEHICLE")])
    defender = _unit([_unit_model(defender_model, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.wound_rolls == [4]
    assert result.total_damage == 0  # strength 1 vs toughness 100 needs a 6 to wound normally


def test_resolve_combat_anti_vehicle_2_plus_scores_a_critical_wound_at_the_threshold(
    monkeypatch,
):
    rolls = iter([6, 2, 1])  # hit, wound, save (AP -10 always fails regardless)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    anti_vehicle = _ability([_condition("anti_vehicle_2")], [_effect("force_critical_wound")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [anti_vehicle]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    defender_model = _model(wounds=5, save=2, feel_no_pain=None, keywords=[_keyword("VEHICLE")])
    defender = _unit([_unit_model(defender_model, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.wound_rolls == [2]
    assert result.total_damage == 1


def test_resolve_combat_anti_infantry_triggers_devastating_wounds(monkeypatch):
    # A critical wound scored via Anti-Infantry 4+ must also trigger other
    # critical_wound-dependent effects: with Devastating Wounds also attached,
    # the save roll should be skipped entirely too.
    rolls = iter([6, 4])  # hit, wound (meets the Anti-Infantry 4+ threshold)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    anti_infantry = _ability(
        [_condition("anti_infantry_4")], [_effect("force_critical_wound")]
    )
    devastating_wounds = _ability([_condition("critical_wound")], [_effect("no_save")])
    weapon = _weapon(attacks="1", skill=2, strength=1, ap=0, damage="1")
    weapon.id = 1
    weapon.abilities = [anti_infantry, devastating_wounds]
    attacker = _unit([_unit_model(_model(toughness=100), [weapon])])
    # An unbeatable save+invulnerable that would normally always succeed.
    defender_model = _model(
        wounds=5, save=2, invulnerable=2, feel_no_pain=None, keywords=[_keyword("INFANTRY")]
    )
    defender = _unit([_unit_model(defender_model, [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.wound_rolls == [4]  # the roll is actually made, not skipped
    assert result.save_rolls == []  # devastating wounds skipped the save too
    assert result.total_damage == 1


# --- heavy / reroll failed hits / +1 skill (ranged, melee) ---


def test_moved_less_than_3_condition_checks_pre_hit_step_and_flag():
    assert (
        combat.CONDITIONS["moved_less_than_3"]({"step": "pre_hit", "moved_less_than_3": True})
        is True
    )
    assert (
        combat.CONDITIONS["moved_less_than_3"]({"step": "pre_hit", "moved_less_than_3": False})
        is False
    )
    assert (
        combat.CONDITIONS["moved_less_than_3"]({"step": "hit", "moved_less_than_3": True}) is False
    )


def test_resolve_combat_heavy_grants_plus_one_to_hit_when_moved_less_than_3(monkeypatch):
    # Heavy: moved_less_than_3 -> plus_one_to_hit. Skill 4 needs a roll of 4+ to
    # hit normally, but a roll of 3 should now succeed with the +1 bonus.
    rolls = iter([3, 6, 1])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    heavy = _ability([_condition("moved_less_than_3")], [_effect("plus_one_to_hit")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [heavy]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=True, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 1


def test_resolve_combat_heavy_does_nothing_when_unit_moved_3_or_more(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    heavy = _ability([_condition("moved_less_than_3")], [_effect("plus_one_to_hit")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [heavy]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 0  # roll of 3 fails skill 4 without the Heavy bonus


def test_resolve_combat_reroll_failed_hits_rerolls_once_on_a_failure(monkeypatch):
    rolls = iter([2, 6, 6, 1])  # hit (fails), reroll (succeeds), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    reroll = _ability([_condition("always")], [_effect("reroll_failed_hits")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [reroll]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [2]  # the original failed roll
    assert result.attack_rerolls == [6]  # the reroll, kept separate
    assert result.total_damage == 1


def test_resolve_combat_reroll_failed_hits_does_not_reroll_a_success(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    reroll = _ability([_condition("always")], [_effect("reroll_failed_hits")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [reroll]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [6]  # no reroll needed
    assert result.attack_rerolls == []
    assert result.total_damage == 1


def test_resolve_combat_plus_one_skill_ranged_applies_only_to_ranged_weapons(monkeypatch):
    rolls = iter([3, 6, 1])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    bonus = _ability([_condition("always")], [_effect("plus_one_skill_ranged")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    weapon.abilities = [bonus]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 1


def test_resolve_combat_plus_one_skill_ranged_does_nothing_for_melee_weapons(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    bonus = _ability([_condition("always")], [_effect("plus_one_skill_ranged")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1", weapon_type="melee")
    weapon.id = 1
    weapon.abilities = [bonus]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 0  # no bonus for a melee weapon


def test_resolve_combat_plus_one_skill_melee_applies_only_to_melee_weapons(monkeypatch):
    rolls = iter([3, 6, 1])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    bonus = _ability([_condition("always")], [_effect("plus_one_skill_melee")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1", weapon_type="melee")
    weapon.id = 1
    weapon.abilities = [bonus]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 1


def test_resolve_combat_plus_one_skill_melee_does_nothing_for_ranged_weapons(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    bonus = _ability([_condition("always")], [_effect("plus_one_skill_melee")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    weapon.abilities = [bonus]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 0  # no bonus for a ranged weapon


# --- assault / pistol ---


def test_resolve_combat_advanced_prevents_a_ranged_weapon_from_firing(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    weapon = _weapon(attacks="2", skill=2, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=True,
    )
    assert result.attack_rolls == []
    assert result.total_damage == 0


def test_resolve_combat_assault_weapon_still_fires_when_advanced(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    assault = _ability([_condition("always")], [_effect("assault")])
    weapon = _weapon(attacks="2", skill=2, weapon_type="ranged")
    weapon.id = 1
    weapon.abilities = [assault]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=True,
    )
    assert len(result.attack_rolls) == 2


def test_resolve_combat_advanced_does_not_affect_melee_weapons(monkeypatch):
    # Advancing only restricts ranged weapons firing during the shooting
    # phase - it has no bearing on a melee weapon swinging in engagement range.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    weapon = _weapon(attacks="2", skill=2, weapon_type="melee")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=True,
    )
    assert len(result.attack_rolls) == 2


def test_resolve_combat_ranged_weapon_does_not_fire_in_engagement_range_without_pistol(
    monkeypatch,
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    weapon = _weapon(attacks="2", skill=2, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.attack_rolls == []


def test_resolve_combat_pistol_weapon_fires_in_engagement_range(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    pistol = _ability([_condition("always")], [_effect("pistol")])
    weapon = _weapon(attacks="2", skill=2, weapon_type="ranged")
    weapon.id = 1
    weapon.abilities = [pistol]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert len(result.attack_rolls) == 2


def test_resolve_combat_pistol_does_not_help_a_melee_weapon_fire_at_range(monkeypatch):
    # Pistol only ever bypasses the engagement-range restriction for a
    # ranged weapon - it never turns a melee weapon into a ranged one.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    pistol = _ability([_condition("always")], [_effect("pistol")])
    weapon = _weapon(attacks="2", skill=2, weapon_type="melee")
    weapon.id = 1
    weapon.abilities = [pistol]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.attack_rolls == []


# --- datasheet ability: unit-wide reroll failed hits ---


def test_resolve_combat_datasheet_ability_grants_unit_wide_reroll_failed_hits(monkeypatch):
    # A datasheet ability on the shooting model, rather than a weapon or
    # wargear ability, should still grant the reroll.
    rolls = iter([2, 6, 6, 1])  # hit (fails), reroll (succeeds), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    reroll = _datasheet_ability([_condition("always")], [_effect("reroll_failed_hits")])
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    shooter = _model(abilities=[reroll])
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [2]  # the original failed roll
    assert result.attack_rerolls == [6]  # the reroll, kept separate
    assert result.total_damage == 1


def test_resolve_combat_without_the_datasheet_ability_no_reroll_happens(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 2)

    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [2]  # no reroll
    assert result.attack_rerolls == []
    assert result.total_damage == 0


def test_resolve_combat_datasheet_ability_reroll_applies_to_every_model_in_the_unit(
    monkeypatch,
):
    # The "Reroll Failed Hits" datasheet ability is on model A, but it must
    # still grant model B's weapon a reroll too - it's unit-wide, not
    # per-model.
    rolls = iter([2, 6, 6, 1])  # model B: hit (fails), reroll (succeeds), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    reroll = _datasheet_ability([_condition("always")], [_effect("reroll_failed_hits")])
    model_a_weapon = _weapon(attacks="0", skill=4, strength=4, ap=-10, damage="1")
    model_a_weapon.id = 1
    model_b_weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    model_b_weapon.id = 2
    attacker = _unit(
        [
            _unit_model(_model(abilities=[reroll]), [model_a_weapon]),
            _unit_model(_model(), [model_b_weapon]),
        ]
    )
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {model_a_weapon.id, model_b_weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [2]  # model B's original failed roll
    assert result.attack_rerolls == [6]  # the reroll, kept separate
    assert result.total_damage == 1


# --- precision / rapid fire / hazardous / ignore cover (unit) ---


def _precision_combat(defender_models, apply_precision, weapon_abilities):
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = weapon_abilities
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(m, []) for m in defender_models])
    return combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        apply_precision=apply_precision,
    )


def _precision_defenders():
    # One of each targeting group, listed so normal targeting would hit the
    # trooper first.
    leader = _model(name="Leader", is_leader=True, wounds=1, save=2)
    support = _model(name="Support", is_support=True, wounds=1, save=2)
    trooper = _model(name="Trooper", wounds=1, save=2)
    return leader, support, trooper


def test_precision_order_across_multiple_attacks(monkeypatch):
    # Every roll is a 6, so a 7+ save on each model guarantees every attack
    # destroys whichever model it targets.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    precision = _ability([_condition("always")], [_effect("precision")])
    leader = _model(name="Leader", is_leader=True, wounds=1, save=7)
    support = _model(name="Support", is_support=True, wounds=1, save=7)
    trooper = _model(name="Trooper", wounds=1, save=7)

    picked = []
    original = combat._precision_target

    def spy(targets):
        target = original(targets)
        picked.append("leader" if target.is_leader else "support" if target.is_support else "other")
        return target

    monkeypatch.setattr(combat, "_precision_target", spy)
    weapon = _weapon(attacks="3", skill=2, strength=10, ap=0, damage="1")
    weapon.id = 1
    weapon.abilities = [precision]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(m, []) for m in [trooper, support, leader]])
    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        apply_precision=True,
    )
    # The wound phase checks who each attack would be allocated to (no one has
    # died yet, so the leader each time); allocation then picks leader, then
    # support, then the rest as each dies.
    assert picked[:3] == ["leader", "leader", "leader"]
    assert picked[3:] == ["leader", "support", "other"]
    assert result.models_destroyed == 3


def test_precision_not_applied_uses_normal_targeting(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    precision = _ability([_condition("always")], [_effect("precision")])
    called = []
    monkeypatch.setattr(combat, "_precision_target", lambda t: called.append(1) or t[0])

    _precision_combat(list(_precision_defenders()), False, [precision])
    assert called == []


def test_apply_precision_without_precision_weapon_uses_normal_targeting(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    called = []
    monkeypatch.setattr(combat, "_precision_target", lambda t: called.append(1) or t[0])

    _precision_combat(list(_precision_defenders()), True, [])
    assert called == []


def test_precision_target_prefers_leader_then_support():
    other = combat._Target(4, 3, None, None, 1)
    support = combat._Target(4, 3, None, None, 1, is_support=True)
    leader = combat._Target(4, 3, None, None, 1, is_leader=True)
    assert combat._precision_target(combat.deque([other, support, leader])) is leader
    assert combat._precision_target(combat.deque([other, support])) is support
    assert combat._precision_target(combat.deque([other])) is other


def test_within_half_range_condition_checks_pre_weapon_step_and_flag():
    assert combat.CONDITIONS["within_half_range"]({"step": "pre_weapon", "half_range": True}) is True
    assert combat.CONDITIONS["within_half_range"]({"step": "pre_weapon", "half_range": False}) is False
    assert combat.CONDITIONS["within_half_range"]({"step": "hit", "half_range": True}) is False


def test_resolve_combat_rapid_fire_1_adds_an_extra_attack_within_half_range(monkeypatch):
    # Rapid Fire 1: within_half_range -> add_extra_attack. The extra attack is
    # a fresh attack, not an auto-hit, so it still needs its own hit roll.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    rapid_fire = _ability([_condition("within_half_range")], [_effect("add_extra_attack")])
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [rapid_fire]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=True, moved_less_than_3=False, advanced=False,
    )
    # Two separate hit rolls (base attack + the one Rapid Fire added).
    assert result.attack_rolls == [6, 6]
    assert result.wound_rolls == [6, 6]
    assert result.total_damage == 2


def test_resolve_combat_rapid_fire_1_does_nothing_outside_half_range(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    rapid_fire = _ability([_condition("within_half_range")], [_effect("add_extra_attack")])
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [rapid_fire]
    attacker = _unit([_unit_model(_model(toughness=1), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5, save=2, feel_no_pain=None), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.attack_rolls == [6]  # just the base attack, no extra one added
    assert result.total_damage == 1


def test_resolve_combat_rapid_fire_1_grants_exactly_one_extra_attack_regardless_of_base_attacks(
    monkeypatch,
):
    # A weapon with 2 base attacks should get exactly 1 extra attack from
    # Rapid Fire 1 (3 total), not 1 extra per base attack.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # misses everything

    rapid_fire = _ability([_condition("within_half_range")], [_effect("add_extra_attack")])
    weapon = _weapon(attacks="2", skill=2)
    weapon.id = 1
    weapon.abilities = [rapid_fire]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=True, moved_less_than_3=False, advanced=False,
    )
    assert len(result.attack_rolls) == 3


def test_resolve_combat_hazardous_rolls_once_per_weapon_and_deals_no_damage_above_2(
    monkeypatch,
):
    # A weapon with 0 base attacks never makes an attack roll, isolating the
    # hazard check cleanly: this test is purely about the hazard roll itself.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    shooter = _model(keywords=[_keyword("INFANTRY")])
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.hazardous_rolls == [3]
    assert result.hazardous_wounds == 0  # a roll of 3 is safe
    assert result.attack_rolls == []  # the weapon made no attacks at all


def test_resolve_combat_hazardous_deals_1_wound_to_an_infantry_shooter(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # hazard roll - triggers

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    shooter = _model(keywords=[_keyword("INFANTRY")], feel_no_pain=None)
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.hazardous_rolls == [1]
    assert result.hazardous_wounds == 1


def test_resolve_combat_hazardous_deals_3_wounds_to_a_vehicle_shooter(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 2)  # hazard roll - triggers

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    shooter = _model(keywords=[_keyword("VEHICLE")], feel_no_pain=None)
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.hazardous_rolls == [2]
    assert result.hazardous_wounds == 3


def test_resolve_combat_hazardous_wounds_reduced_by_feel_no_pain(monkeypatch):
    # Hazard roll of 1 (triggers, 3 wounds for a VEHICLE), then 3 FNP rolls:
    # succeed, fail, succeed - only the middle point actually lands.
    rolls = iter([1, 6, 2, 6])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    shooter = _model(keywords=[_keyword("VEHICLE")], feel_no_pain=4)
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.hazardous_rolls == [1]
    assert result.hazardous_wounds == 1


def test_resolve_combat_hazardous_destroys_the_shooting_model_when_wounds_exceeded(
    monkeypatch,
):
    # A 1-wound INFANTRY shooter takes exactly 1 hazardous wound - enough to
    # destroy it outright.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # hazard roll - triggers

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    shooter = _model(wounds=1, keywords=[_keyword("INFANTRY")], feel_no_pain=None)
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.hazardous_wounds == 1
    assert result.hazardous_models_destroyed == 1


def test_resolve_combat_hazardous_does_not_destroy_a_model_that_survives(monkeypatch):
    # A 5-wound INFANTRY shooter only takes 1 hazardous wound - it survives.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # hazard roll - triggers

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    shooter = _model(wounds=5, keywords=[_keyword("INFANTRY")], feel_no_pain=None)
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False, advanced=False
    )
    assert result.hazardous_wounds == 1
    assert result.hazardous_models_destroyed == 0


def test_resolve_combat_hazardous_damage_accumulates_across_a_models_weapons(monkeypatch):
    # A 2-wound INFANTRY shooter fires two separate hazardous weapons. Neither
    # hazard roll alone (1 wound each) would kill it, but the two together do.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # both hazard rolls trigger

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon_a = _weapon(attacks="0", skill=2)
    weapon_a.id = 1
    weapon_a.abilities = [hazardous]
    weapon_b = _weapon(attacks="0", skill=2)
    weapon_b.id = 2
    weapon_b.abilities = [hazardous]
    shooter = _model(wounds=2, keywords=[_keyword("INFANTRY")], feel_no_pain=None)
    attacker = _unit([_unit_model(shooter, [weapon_a, weapon_b])])
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon_a.id, weapon_b.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.hazardous_rolls == [1, 1]
    assert result.hazardous_wounds == 2
    assert result.hazardous_models_destroyed == 1


def test_resolve_combat_hazardous_models_destroyed_only_counts_models_that_fired_hazardous(
    monkeypatch,
):
    # Model A fires a hazardous weapon and dies from it. Model B fires a
    # non-hazardous weapon and has only 1 wound itself, but should not be
    # counted since it never risked a self-inflicted wound at all.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)

    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon_a = _weapon(attacks="0", skill=2)
    weapon_a.id = 1
    weapon_a.abilities = [hazardous]
    weapon_b = _weapon(attacks="0", skill=2)
    weapon_b.id = 2
    model_a = _model(wounds=1, keywords=[_keyword("INFANTRY")], feel_no_pain=None)
    model_b = _model(wounds=1, keywords=[], feel_no_pain=None)
    attacker = _unit(
        [_unit_model(model_a, [weapon_a]), _unit_model(model_b, [weapon_b])]
    )
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon_a.id, weapon_b.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    assert result.hazardous_models_destroyed == 1




def test_resolve_combat_ignore_cover_per_model_does_not_leak_to_other_models(monkeypatch):
    # By contrast, the plain (non-unit) "Ignores Cover" wargear ability should
    # only protect the model that actually carries it.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    ignores_cover = _wargear_ability([_condition("always")], [_effect("ignore_cover")])
    gear = _wargear([ignores_cover])
    model_a_weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
    model_a_weapon.id = 1
    model_b_weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
    model_b_weapon.id = 2
    attacker = _unit(
        [
            _unit_model(_model(), [model_a_weapon], wargear=[gear]),
            _unit_model(_model(), [model_b_weapon]),
        ]
    )
    defender = _unit([_unit_model(_model(wounds=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {model_a_weapon.id, model_b_weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=True,
        half_range=False, moved_less_than_3=False, advanced=False,
    )
    # Model A's roll of 3 still hits (skill 3, cover ignored); model B's roll of
    # 3 misses (skill worsened to 4 by cover, since it doesn't carry the gear).
    assert result.attack_rolls == [3, 3]
    assert result.wound_rolls == [3]  # only model A's attack proceeded to wound


# --- API endpoint ---


async def _create_model(client: AsyncClient, faction_id: int, **overrides) -> int:
    payload = {
        "name": "Combatant",
        "faction_id": faction_id,
        "save": 3,
        "toughness": 4,
        "oc": 1,
        "movement": 6,
        "wounds": 2,
        "leadership": 7,
    }
    payload.update(overrides)
    response = await client.post("/models", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_weapon(client: AsyncClient, model_id: int, **overrides) -> int:
    payload = {
        "name": "Gun",
        "model_id": model_id,
        "damage": "1",
        "range": 24,
        "strength": 4,
        "ap": 0,
        "attacks": "1",
        "skill": 3,
    }
    payload.update(overrides)
    response = await client.post("/weapons", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_faction_unit(client: AsyncClient, faction_id: int, name: str) -> int:
    response = await client.post("/faction-units", json={"name": name, "faction_id": faction_id})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_unit(
    client: AsyncClient, faction_unit_id: int, model_id: int | None = None, weapon_id: int | None = None
) -> int:
    unit_models = []
    if model_id is not None:
        unit_models.append({"model_id": model_id, "weapon_ids": [weapon_id] if weapon_id else []})
    response = await client.post(
        "/units",
        json={"faction_unit_id": faction_unit_id, "points": 100, "unit_models": unit_models},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_combat_endpoint_applies_sustained_1_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    ability_id = next(
        a["id"]
        for a in (await client.get("/weapon-abilities")).json()
        if a["name"] == "Sustained 1"
    )

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=10,
        ap=-10,
        skill=2,
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    # One real hit roll (a crit) grants a sustained extra hit, so two wound/save
    # sequences resolve even though only one attack die was rolled for the hit.
    assert len(body["attack_rolls"]) == 1
    assert len(body["wound_rolls"]) == 2
    assert len(body["save_rolls"]) == 2


async def test_combat_endpoint_applies_seeded_devastating_wounds_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    abilities = (await client.get("/weapon-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Devastating Wounds")

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=10,
        skill=2,
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    # A save of 2+ with a 2+ invulnerable would normally always succeed.
    defender_model_id = await _create_model(
        client, faction_id, toughness=1, save=2, invulnerable=2, wounds=5
    )
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["wound_rolls"]) == 1
    assert body["save_rolls"] == []  # the critical wound skipped the save entirely
    assert body["total_damage"] == 1


async def test_combat_endpoint_applies_seeded_anti_infantry_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)
    await client.post("/keywords", json={"name": "INFANTRY"})

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    abilities = (await client.get("/weapon-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Anti-Infantry 4+")
    keyword_id = next(k["id"] for k in (await client.get("/keywords")).json() if k["name"] == "INFANTRY")

    attacker_model_id = await _create_model(client, faction_id, toughness=100)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=1,
        ap=-10,
        skill=2,
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(
        client, faction_id, save=2, wounds=5, keyword_ids=[keyword_id]
    )
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    # Strength 1 vs toughness 100 would never wound normally (needs a natural
    # 6), but the wound roll of 4+ against the INFANTRY defender counts as a
    # critical wound regardless.
    assert body["wound_rolls"] == [6]
    assert body["total_damage"] == 1


async def test_combat_endpoint_applies_seeded_heavy_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    abilities = (await client.get("/weapon-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Heavy")

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=10,
        ap=-10,
        skill=4,
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "moved_less_than_3": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    # Skill 4 would normally need a roll of 4+ to hit, but Heavy grants +1 to
    # hit since the attacking unit moved less than 3" this turn.
    assert body["attack_rolls"] == [3]
    assert body["total_damage"] == 1


async def test_combat_endpoint_applies_seeded_assault_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    abilities = (await client.get("/weapon-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Assault")

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=10,
        ap=-10,
        skill=2,
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "advanced": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    # The attacking unit advanced, which would normally stop this ranged
    # weapon from firing at all - Assault lets it fire anyway.
    assert len(body["attack_rolls"]) == 1
    assert body["total_damage"] == 1


async def test_combat_endpoint_applies_seeded_pistol_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    abilities = (await client.get("/weapon-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Pistol")

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=10,
        ap=-10,
        skill=2,
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "in_engagement_range": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    # The attacking unit is in engagement range, which would normally stop
    # this ranged weapon from firing at all - Pistol lets it fire anyway.
    assert len(body["attack_rolls"]) == 1
    assert body["total_damage"] == 1


async def test_combat_endpoint_applies_seeded_reroll_failed_hits_datasheet_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import datasheet_abilities as datasheet_abilities_seed
    from app.seeds import effects as effects_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)

    rolls = iter([2, 6, 6, 1])  # hit (fails), reroll (succeeds), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    abilities = (await client.get("/datasheet-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Reroll Failed Hits")

    attacker_model_id = await _create_model(client, faction_id, ability_ids=[ability_id])
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        strength=4,
        ap=-10,
        skill=4,
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    # The first hit roll fails (needs 4+, rolled a 2), but the unit's
    # datasheet ability re-rolls it and the second roll (6) succeeds.
    assert body["attack_rolls"] == [2]
    assert body["attack_rerolls"] == [6]
    assert body["total_damage"] == 1


async def test_combat_endpoint_applies_seeded_hazardous_and_rapid_fire_abilities(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)

    abilities = (await client.get("/weapon-abilities")).json()
    hazardous_id = next(a["id"] for a in abilities if a["name"] == "Hazardous")
    rapid_fire_id = next(a["id"] for a in abilities if a["name"] == "Rapid Fire 1")

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        skill=1,
        ability_ids=[hazardous_id, rapid_fire_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "half_range": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["half_range"] is True
    # Rapid Fire 1 adds a second attack (both hit on a roll of 1 vs skill 1).
    assert len(body["attack_rolls"]) == 2
    # Hazardous makes exactly one hazard roll for the one weapon fired, which
    # triggers on a 1 and deals 1 wound (no INFANTRY/VEHICLE keyword -> 0).
    assert len(body["hazardous_rolls"]) == 1
    assert body["hazardous_rolls"][0] == 1
    assert body["hazardous_wounds"] == 0


async def test_combat_endpoint_in_cover_worsens_ranged_hit_rolls(
    client: AsyncClient, faction_id: int, monkeypatch
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id, skill=3, weapon_type="ranged")
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "in_cover": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["in_cover"] is True
    assert body["attack_rolls"] == [3]
    assert body["wound_rolls"] == []  # a roll of 3 against skill 3 worsened to 4 misses


async def test_combat_endpoint_applies_seeded_ignores_cover_weapon_ability(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    from app.seeds import conditions as conditions_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await weapon_abilities_seed.seed(session)

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    abilities = (await client.get("/weapon-abilities")).json()
    ability_id = next(a["id"] for a in abilities if a["name"] == "Ignores Cover")

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client,
        attacker_model_id,
        skill=3,
        weapon_type="ranged",
        ability_ids=[ability_id],
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, wounds=5)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "in_cover": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attack_rolls"] == [3]
    # The hit succeeded (proceeding to a wound roll) despite in_cover, because
    # the weapon's "Ignores Cover" ability negated the +1 penalty.
    assert len(body["wound_rolls"]) == 1


async def test_combat_endpoint_groups_weapon_results_by_weapon_name(
    client: AsyncClient, faction_id: int, monkeypatch
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    attacker_model_id = await _create_model(client, faction_id)
    weapon_a_id = await _create_weapon(
        client, attacker_model_id, name="Autogun", strength=10, ap=-10, skill=2
    )
    weapon_b_id = await _create_weapon(
        client, attacker_model_id, name="Autogun", strength=10, ap=-10, skill=2
    )
    weapon_c_id = await _create_weapon(
        client, attacker_model_id, name="Las Pistol", strength=10, ap=-10, skill=2
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    response = await client.post(
        "/units",
        json={
            "faction_unit_id": attacker_fu,
            "points": 100,
            "unit_models": [
                {
                    "model_id": attacker_model_id,
                    "weapon_ids": [weapon_a_id, weapon_b_id, weapon_c_id],
                }
            ],
        },
    )
    assert response.status_code == 201
    attacker_unit_id = response.json()["id"]

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=20)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_a_id, weapon_b_id, weapon_c_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    weapon_results_by_name = {wr["name"]: wr for wr in body["weapon_results"]}
    assert set(weapon_results_by_name) == {"Autogun", "Las Pistol"}
    # Two separate "Autogun" weapon instances (same name, different ids) are
    # pooled into a single entry; "Las Pistol" stays separate.
    assert len(weapon_results_by_name["Autogun"]["attack_rolls"]) == 2
    assert len(weapon_results_by_name["Las Pistol"]["attack_rolls"]) == 1


async def test_combat_endpoint_resolves_with_calculator_defaults(
    client: AsyncClient, faction_id: int, monkeypatch
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id, strength=10, ap=-10, skill=2)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=1)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is True
    assert body["in_range"] is True
    assert len(body["attack_rolls"]) == 1
    assert body["models_destroyed"] == 1


async def test_combat_endpoint_calculator_ignores_visible_and_range_overrides(
    client: AsyncClient, faction_id: int, monkeypatch
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "game_id": None,
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "defender_visible": False,
            "defender_in_range": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is True
    assert body["in_range"] is True


async def test_combat_endpoint_game_mode_honors_visible_override(
    client: AsyncClient, faction_id: int
):
    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "game_id": 1,
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [weapon_id],
            "defender_visible": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is False
    assert body["attack_rolls"] == []


async def test_combat_endpoint_invalid_attacking_unit_returns_400(
    client: AsyncClient, faction_id: int
):
    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": 9999,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [],
        },
    )
    assert response.status_code == 400


async def test_combat_endpoint_weapon_not_equipped_by_attacker_returns_400(
    client: AsyncClient, faction_id: int
):
    attacker_model_id = await _create_model(client, faction_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id)

    other_model_id = await _create_model(client, faction_id)
    other_weapon_id = await _create_weapon(client, other_model_id)

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit_id,
            "defending_unit_id": defender_unit_id,
            "selected_weapon_ids": [other_weapon_id],
        },
    )
    assert response.status_code == 400


# --- stratagems ---


def test_resolve_combat_stratagem_grants_unit_wide_reroll_failed_hits(monkeypatch):
    rolls = iter([2, 6, 6, 1])  # hit (fails), reroll (succeeds), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    stratagem = Stratagem(name="Rerolls", description=None, cp=1, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("reroll_failed_hits")]
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        stratagems=[stratagem],
    )
    assert result.attack_rolls == [2]
    assert result.attack_rerolls == [6]
    assert result.total_damage == 1


def test_resolve_combat_stratagem_effect_applies_per_attack(monkeypatch):
    # +1 to hit is an attack-level effect, so the stratagem must also be in
    # play for each weapon, not only the unit-wide check.
    rolls = iter([3, 6, 1])  # hit (3 vs skill 4, passes with +1), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))

    stratagem = Stratagem(name="Plus One", description=None, cp=1, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("plus_one_to_hit")]
    weapon = _weapon(attacks="1", skill=4, strength=4, ap=-10, damage="1")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=5, save=2), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        stratagems=[stratagem],
    )
    assert result.total_damage == 1


async def _combat_units_in_list(client: AsyncClient, faction_id: int, detachment_ids: list[int]):
    list_id = (
        await client.post(
            "/lists",
            json={
                "name": "List",
                "points_limit": 1000,
                "faction_id": faction_id,
                "detachment_ids": detachment_ids,
            },
        )
    ).json()["id"]
    attacker_model_id = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(client, attacker_model_id)
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")
    response = await client.post(
        "/units",
        json={
            "faction_unit_id": attacker_fu,
            "points": 100,
            "list_id": list_id,
            "unit_models": [{"model_id": attacker_model_id, "weapon_ids": [weapon_id]}],
        },
    )
    assert response.status_code == 201
    attacker_unit_id = response.json()["id"]

    defender_model_id = await _create_model(client, faction_id)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)
    return attacker_unit_id, defender_unit_id, weapon_id


async def _create_detachment(client: AsyncClient, faction_id: int, name: str) -> int:
    return (
        await client.post("/detachments", json={"name": name, "faction_id": faction_id, "dp": 1})
    ).json()["id"]


async def test_combat_endpoint_accepts_core_and_own_detachment_stratagems(
    client: AsyncClient, faction_id: int
):
    detachment_id = await _create_detachment(client, faction_id, "Mine")
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(
        client, faction_id, [detachment_id]
    )
    core_id = (
        await client.post("/stratagems", json={"name": "Core", "cp": 1, "is_core": True})
    ).json()["id"]
    own_id = (
        await client.post(
            "/stratagems", json={"name": "Own", "cp": 1, "detachment_ids": [detachment_id]}
        )
    ).json()["id"]

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "stratagem_ids": [core_id, own_id],
        },
    )
    assert response.status_code == 200


async def test_combat_endpoint_rejects_other_detachment_stratagem(
    client: AsyncClient, faction_id: int
):
    mine = await _create_detachment(client, faction_id, "Mine")
    other = await _create_detachment(client, faction_id, "Other")
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(client, faction_id, [mine])
    other_id = (
        await client.post(
            "/stratagems", json={"name": "Theirs", "cp": 1, "detachment_ids": [other]}
        )
    ).json()["id"]

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "stratagem_ids": [other_id],
        },
    )
    assert response.status_code == 400


async def test_combat_endpoint_invalid_stratagem_id_returns_400(
    client: AsyncClient, faction_id: int
):
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(client, faction_id, [])
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "stratagem_ids": [9999],
        },
    )
    assert response.status_code == 400


# --- target is monster or vehicle ---


@pytest.mark.parametrize(
    "keywords,expected",
    [({"MONSTER"}, True), ({"VEHICLE"}, True), ({"INFANTRY"}, False), (set(), False)],
)
def test_target_monster_or_vehicle_condition(keywords, expected):
    condition = combat.CONDITIONS["target_monster_or_vehicle"]
    # Step-agnostic: matches (or not) the same way at every step.
    for step in ("unit_wide", "weapon_eligibility", "pre_weapon", "pre_hit", "hit", "wound", "save"):
        assert condition({"step": step, "defender_keywords": keywords}) is expected


@pytest.mark.parametrize("defender_keyword,expected_damage", [("VEHICLE", 1), ("INFANTRY", 0)])
def test_resolve_combat_plus_one_to_hit_only_against_monster_or_vehicle(
    monkeypatch, defender_keyword, expected_damage
):
    rolls = iter([3, 6, 1])  # hit (3 vs skill 4 - only passes with +1), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))

    ability = _ability([_condition("target_monster_or_vehicle")], [_effect("plus_one_to_hit")])
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, damage="1")
    weapon.id = 1
    weapon.abilities = [ability]
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit(
        [_unit_model(_model(toughness=1, wounds=5, save=2, keywords=[_keyword(defender_keyword)]), [])]
    )

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.total_damage == expected_damage


# --- Doctrina Imperatives (faction ability rule options) ---

PROTECTOR = admech_abilities.OPTIONS["Doctrina Imperatives"]["Protector Imperative"]
CONQUEROR = admech_abilities.OPTIONS["Doctrina Imperatives"]["Conqueror Imperative"]


def _doctrina_combat(
    weapon,
    attacker_rules=None,
    defender_rules=None,
    attacker_keywords=(),
    defender_keywords=(),
    **flags,
):
    weapon.id = 1
    attacker = _unit(
        [_unit_model(_model(keywords=[_keyword(k) for k in attacker_keywords]), [weapon])]
    )
    defender = _unit(
        [
            _unit_model(
                _model(
                    toughness=1,
                    wounds=10,
                    save=2,
                    keywords=[_keyword(k) for k in defender_keywords],
                ),
                [],
            )
        ]
    )
    options = dict(
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    options.update(flags)
    return combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        attacker_rules=attacker_rules,
        defender_rules=defender_rules,
        **options,
    )


def _hits(result) -> int:
    # Every test weapon is S10 against T1 with a guaranteed-failed save, so
    # each hit becomes exactly one point of damage.
    return result.total_damage


def test_protector_improves_ballistic_skill_of_ranged_weapons(monkeypatch):
    rolls = iter([3, 6, 1])  # hit 3 vs BS4 (passes only with BS+1), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="ranged")

    assert _hits(_doctrina_combat(weapon, attacker_rules=PROTECTOR)) == 1


def test_protector_does_not_improve_melee_weapon_skill(monkeypatch):
    rolls = iter([3, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="melee", range=None)

    result = _doctrina_combat(weapon, attacker_rules=PROTECTOR, in_engagement_range=True)
    assert _hits(result) == 0


def test_protector_grants_heavy_to_ranged_weapons(monkeypatch):
    rolls = iter([2, 6, 1])  # hit 2 vs BS4: needs BS+1 and Heavy's +1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="ranged")

    assert _hits(_doctrina_combat(weapon, attacker_rules=PROTECTOR, moved_less_than_3=True)) == 1


def test_protector_heavy_does_not_stack_with_a_weapon_that_already_has_heavy(monkeypatch):
    # BS5 with BS+1 and a single +1 to hit needs a 3; a doubled Heavy would
    # wrongly let a 2 through.
    rolls = iter([2, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    heavy = _ability([_condition("moved_less_than_3")], [_effect("plus_one_to_hit")])
    weapon = _weapon(attacks="1", skill=5, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [heavy]

    assert _hits(_doctrina_combat(weapon, attacker_rules=PROTECTOR, moved_less_than_3=True)) == 0


@pytest.mark.parametrize(
    "defender_keyword,weapon_type,expected",
    [
        ("BATTLELINE", "melee", 0),  # 3 vs WS3 becomes a miss at -1
        ("INFANTRY", "melee", 1),  # not BATTLELINE - no penalty
        ("BATTLELINE", "ranged", 1),  # only melee attacks are penalised
    ],
)
def test_protector_on_defender_gives_melee_attacks_against_battleline_minus_one_to_hit(
    monkeypatch, defender_keyword, weapon_type, expected
):
    rolls = iter([3, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(
        attacks="1",
        skill=3,
        strength=10,
        ap=-10,
        weapon_type=weapon_type,
        range=None if weapon_type == "melee" else 24,
    )

    result = _doctrina_combat(
        weapon,
        defender_rules=PROTECTOR,
        defender_keywords=[defender_keyword],
        in_engagement_range=weapon_type == "melee",
    )
    assert _hits(result) == expected


def test_defender_rules_do_not_apply_to_the_attacker_and_vice_versa(monkeypatch):
    # The attacker having Protector doesn't penalise its own melee attacks, and
    # the defender having Protector doesn't grant the attacker BS+1.
    rolls = iter([3, 6, 1, 3, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    melee = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="melee", range=None)
    result = _doctrina_combat(
        melee,
        attacker_rules=PROTECTOR,
        defender_keywords=["BATTLELINE"],
        in_engagement_range=True,
    )
    assert _hits(result) == 1

    ranged = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="ranged")
    assert _hits(_doctrina_combat(ranged, defender_rules=PROTECTOR)) == 0


def test_conqueror_grants_assault_to_ranged_weapons(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")

    assert _doctrina_combat(weapon, advanced=True).attack_rolls == []
    assert _doctrina_combat(weapon, attacker_rules=CONQUEROR, advanced=True).attack_rolls == [6]


def test_conqueror_improves_weapon_skill_of_melee_weapons(monkeypatch):
    rolls = iter([3, 6, 1])  # hit 3 vs WS4 passes only with WS+1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="melee", range=None)

    result = _doctrina_combat(weapon, attacker_rules=CONQUEROR, in_engagement_range=True)
    assert _hits(result) == 1


def test_conqueror_does_not_improve_ranged_weapon_skill(monkeypatch):
    rolls = iter([3, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="ranged")

    assert _hits(_doctrina_combat(weapon, attacker_rules=CONQUEROR)) == 0


@pytest.mark.parametrize("attacker_keyword,expected", [("BATTLELINE", 1), ("INFANTRY", 0)])
def test_conqueror_improves_ap_for_battleline_attackers(monkeypatch, attacker_keyword, expected):
    # Save 2+ against AP-1 needs a 3; with AP improved to -2 it needs a 4.
    rolls = iter([6, 6, 3])  # hit, wound, save 3
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-1, weapon_type="ranged")

    result = _doctrina_combat(
        weapon, attacker_rules=CONQUEROR, attacker_keywords=[attacker_keyword]
    )
    assert result.total_damage == expected


def test_improved_ap_does_not_worsen_invulnerable_save(monkeypatch):
    rolls = iter([6, 6, 4])  # hit, wound, save 4 vs a 4+ invulnerable
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-3, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit(
        [_unit_model(_model(keywords=[_keyword("BATTLELINE")]), [weapon])]
    )
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=3, invulnerable=4), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        attacker_rules=CONQUEROR,
    )
    assert result.total_damage == 0


async def _admech_setup(client: AsyncClient, *, with_doctrina: bool):
    faction_id = (await client.post("/factions", json={"name": "Adeptus Mechanicus"})).json()["id"]
    doctrina_id = (
        await client.post(
            "/faction-abilities",
            json={"name": "Doctrina Imperatives", "faction_id": faction_id},
        )
    ).json()["id"]
    attacker_model_id = await _create_model(
        client, faction_id, faction_ability_ids=[doctrina_id] if with_doctrina else []
    )
    weapon_id = await _create_weapon(
        client, attacker_model_id, strength=10, ap=-10, skill=4, weapon_type="ranged"
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Skitarii")
    attacker_unit_id = await _create_unit(client, attacker_fu, attacker_model_id, weapon_id)

    defender_model_id = await _create_model(client, faction_id, toughness=1, save=2, wounds=10)
    defender_fu = await _create_faction_unit(client, faction_id, "Targets")
    defender_unit_id = await _create_unit(client, defender_fu, defender_model_id)
    return attacker_unit_id, defender_unit_id, weapon_id


@pytest.mark.parametrize("with_doctrina,expected_damage", [(True, 1), (False, 0)])
async def test_combat_endpoint_applies_rule_option_only_to_units_with_the_faction_ability(
    client: AsyncClient, monkeypatch, with_doctrina, expected_damage
):
    rolls = iter([3, 6, 1])  # hit 3 vs BS4 - passes only with Protector's BS+1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    attacker_id, defender_id, weapon_id = await _admech_setup(
        client, with_doctrina=with_doctrina
    )

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "attacker_rule_options": ["Protector Imperative"],
        },
    )
    assert response.status_code == 200
    assert response.json()["total_damage"] == expected_damage


@pytest.mark.parametrize(
    "options",
    [["Not A Real Imperative"], ["Protector Imperative", "Conqueror Imperative"]],
)
async def test_combat_endpoint_rejects_invalid_rule_options(
    client: AsyncClient, options
):
    attacker_id, defender_id, weapon_id = await _admech_setup(client, with_doctrina=True)

    for field in ("attacker_rule_options", "defender_rule_options"):
        response = await client.post(
            "/combat",
            json={
                "attacking_unit_id": attacker_id,
                "defending_unit_id": defender_id,
                "selected_weapon_ids": [weapon_id],
                field: options,
            },
        )
        assert response.status_code == 400


# --- Waaagh! (Orks) ---

RILED_UP = orks_abilities.OPTIONS["Waaagh!"]["Riled Up"]


def _riled_up_defence(monkeypatch, save_roll, defender_rules, invulnerable=None):
    # AP-4 against a 3+ save needs a 7 - only an invulnerable save can stop it.
    rolls = iter([6, 6, save_roll])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-4, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit(
        [_unit_model(_model(toughness=1, wounds=10, save=3, invulnerable=invulnerable), [])]
    )
    return combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        defender_rules=defender_rules,
    )


def test_riled_up_defender_has_5_plus_invulnerable_save(monkeypatch):
    assert _riled_up_defence(monkeypatch, 5, RILED_UP).total_damage == 0
    assert _riled_up_defence(monkeypatch, 4, RILED_UP).total_damage == 1


def test_without_riled_up_there_is_no_invulnerable_save(monkeypatch):
    assert _riled_up_defence(monkeypatch, 5, None).total_damage == 1


def test_riled_up_keeps_a_better_existing_invulnerable_save(monkeypatch):
    assert _riled_up_defence(monkeypatch, 4, RILED_UP, invulnerable=4).total_damage == 0


def test_riled_up_attacker_ranged_weapons_have_assault(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")

    assert _doctrina_combat(weapon, advanced=True).attack_rolls == []
    assert _doctrina_combat(weapon, attacker_rules=RILED_UP, advanced=True).attack_rolls == [6]


def test_riled_up_invulnerable_is_defender_only(monkeypatch):
    # An attacking unit that's riled up doesn't hand its target a 5+ invulnerable.
    rolls = iter([6, 6, 5])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-4, weapon_type="ranged")
    assert _doctrina_combat(weapon, attacker_rules=RILED_UP).total_damage == 1


# --- Hunter: Monster/Vehicle and Close-Quarters ---


def _hunter_weapon(**overrides):
    hunter = _ability([_condition("target_not_monster_or_vehicle")], [_effect("cannot_attack")])
    weapon = _weapon(attacks="3", skill=4, strength=12, ap=-2, damage="3", **overrides)
    weapon.abilities = [hunter]
    return weapon


@pytest.mark.parametrize(
    "defender_keyword,expected_attacks", [("VEHICLE", 3), ("MONSTER", 3), ("INFANTRY", 0)]
)
def test_hunter_profile_only_attacks_monsters_and_vehicles(
    monkeypatch, defender_keyword, expected_attacks
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _hunter_weapon(weapon_type="ranged")

    result = _doctrina_combat(weapon, defender_keywords=[defender_keyword])
    assert len(result.attack_rolls) == expected_attacks
    # A profile that can't attack doesn't show up in the results at all.
    assert bool(result.weapon_results) == bool(expected_attacks)


def test_hunter_melee_profile_is_restricted_too(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _hunter_weapon(weapon_type="melee", range=None)

    result = _doctrina_combat(weapon, defender_keywords=["INFANTRY"], in_engagement_range=True)
    assert result.attack_rolls == []


def test_close_quarters_fires_in_engagement_range(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    close_quarters = _ability([_condition("always")], [_effect("pistol")])
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-2, damage="3", weapon_type="ranged")
    weapon.abilities = [close_quarters]

    result = _doctrina_combat(weapon, in_engagement_range=True)
    assert result.attack_rolls == [6]


# --- Lethal Hits: non-Monster/Vehicle ---


@pytest.mark.parametrize(
    "defender_keyword,expected_wound_rolls", [("INFANTRY", []), ("VEHICLE", [1]), ("MONSTER", [1])]
)
def test_lethal_hits_non_monster_vehicle_only_auto_wounds_other_targets(
    monkeypatch, defender_keyword, expected_wound_rolls
):
    # A critical hit auto-wounds (no wound roll) only against non-MONSTER/VEHICLE.
    rolls = iter([6, 1, 1])  # hit (critical), wound roll if one is made, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    lethal = _ability(
        [_condition("critical_hit_not_monster_or_vehicle")], [_effect("auto_pass_wound")]
    )
    weapon = _weapon(attacks="1", skill=4, strength=7, ap=-2, damage="2", weapon_type="ranged")
    weapon.abilities = [lethal]

    result = _doctrina_combat(weapon, defender_keywords=[defender_keyword])
    assert result.wound_rolls == expected_wound_rolls


def test_critical_hit_not_monster_or_vehicle_condition():
    condition = combat.CONDITIONS["critical_hit_not_monster_or_vehicle"]
    assert condition({"step": "hit", "roll": 6, "defender_keywords": {"INFANTRY"}}) is True
    assert condition({"step": "hit", "roll": 5, "defender_keywords": {"INFANTRY"}}) is False
    assert condition({"step": "hit", "roll": 6, "defender_keywords": {"VEHICLE"}}) is False
    assert condition({"step": "wound", "roll": 6, "defender_keywords": set()}) is False


# --- Big Mek Dakkarig: Even More Dakka, Blitz Dem Gitz! ---


def _even_more_dakka():
    return _datasheet_ability(
        [_condition("riled_up_ranged_critical_hit")], [_effect("add_extra_hit")]
    )


def _dakka_combat(weapon, attacker_options, **flags):
    weapon.id = 1
    attacker = _unit([_unit_model(_model(abilities=[_even_more_dakka()]), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=20, save=7), [])])
    options = dict(
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    options.update(flags)
    return combat.resolve_combat(
        attacker, defender, {weapon.id}, attacker_options=attacker_options, **options
    )


@pytest.mark.parametrize("attacker_options,expected_damage", [({"Riled Up"}, 2), (set(), 1)])
def test_even_more_dakka_gives_sustained_hits_only_when_riled_up(
    monkeypatch, attacker_options, expected_damage
):
    # One critical hit: riled up, it scores an extra (sustained) hit.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=0, damage="1", weapon_type="ranged")

    assert _dakka_combat(weapon, attacker_options).total_damage == expected_damage


def test_even_more_dakka_does_not_affect_melee_attacks(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(
        attacks="1", skill=3, strength=10, ap=0, damage="1", weapon_type="melee", range=None
    )

    result = _dakka_combat(weapon, {"Riled Up"}, in_engagement_range=True)
    assert result.total_damage == 1


@pytest.mark.parametrize(
    "defender_keyword,expected_attacks", [("INFANTRY", 8 + 6), ("VEHICLE", 8), ("MONSTER", 8)]
)
def test_blitz_dem_gitz_adds_six_attacks_against_non_monster_vehicle(
    monkeypatch, defender_keyword, expected_attacks
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # every hit misses
    blitz = _ability(
        [_condition("pre_weapon_not_monster_or_vehicle")], [_effect("add_six_attacks")]
    )
    weapon = _weapon(attacks="8", skill=4, strength=7, ap=-2, damage="2", weapon_type="ranged")
    weapon.abilities = [blitz]

    result = _doctrina_combat(weapon, defender_keywords=[defender_keyword])
    assert len(result.attack_rolls) == expected_attacks


async def test_combat_endpoint_passes_riled_up_to_datasheet_abilities(
    client: AsyncClient, session, monkeypatch
):
    # End to end: a model with Waaagh! and Even More Dakka, riled up via the
    # attacker_rule_options, gets sustained hits.
    from app.seeds import conditions as conditions_seed
    from app.seeds import datasheet_abilities as datasheet_abilities_seed
    from app.seeds import effects as effects_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)

    faction_id = (await client.post("/factions", json={"name": "Orks"})).json()["id"]
    waaagh_id = (
        await client.post("/faction-abilities", json={"name": "Waaagh!", "faction_id": faction_id})
    ).json()["id"]
    dakka_id = next(
        a["id"] for a in (await client.get("/datasheet-abilities")).json()
        if a["name"] == "Even More Dakka"
    )
    model_id = await _create_model(
        client, faction_id, faction_ability_ids=[waaagh_id], ability_ids=[dakka_id]
    )
    weapon_id = await _create_weapon(
        client, model_id, strength=10, ap=0, skill=4, weapon_type="ranged"
    )
    attacker_unit = await _create_unit(
        client, await _create_faction_unit(client, faction_id, "Dakkarig"), model_id, weapon_id
    )
    defender_model = await _create_model(client, faction_id, toughness=1, save=7, wounds=20)
    defender_unit = await _create_unit(
        client, await _create_faction_unit(client, faction_id, "Targets"), defender_model
    )

    async def damage(options):
        response = await client.post(
            "/combat",
            json={
                "attacking_unit_id": attacker_unit,
                "defending_unit_id": defender_unit,
                "selected_weapon_ids": [weapon_id],
                "attacker_rule_options": options,
            },
        )
        assert response.status_code == 200
        return response.json()["total_damage"]

    assert await damage(["Riled Up"]) == 2
    assert await damage([]) == 1


# --- Electro-infusion (defensive datasheet rule) and -1 to wound ---

ELECTRO_INFUSION = datasheet_ability_seeds.RULES["Electro-infusion"]


@pytest.mark.parametrize(
    "defender_keywords,wound_roll,expected_damage",
    [
        (["CHARACTER"], 4, 0),  # S4 vs T4 needs 4+; with -1 it needs 5+
        (["CHARACTER"], 5, 1),
        ([], 4, 1),  # no CHARACTER leading - no penalty
    ],
)
def test_electro_infusion_gives_minus_one_to_wound_while_led_by_a_character(
    monkeypatch, defender_keywords, wound_roll, expected_damage
):
    rolls = iter([6, wound_roll, 1])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit(
        [
            _unit_model(
                _model(
                    toughness=4,
                    wounds=10,
                    save=7,
                    keywords=[_keyword(k) for k in defender_keywords],
                ),
                [],
            )
        ]
    )
    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        defender_rules=ELECTRO_INFUSION,
    )
    assert result.total_damage == expected_damage


def test_minus_one_to_wound_never_stops_an_unmodified_six(monkeypatch):
    # S2 vs T4 needs 6+; at -1 that would be 7+, but a natural 6 still wounds.
    rolls = iter([6, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=2, ap=-10, damage="1", weapon_type="ranged")

    result = _doctrina_combat(
        weapon, defender_rules=ELECTRO_INFUSION, defender_keywords=["CHARACTER"]
    )
    assert result.total_damage == 1


def test_electro_infusion_does_not_affect_its_own_units_attacks(monkeypatch):
    # As the attacker's rule it does nothing, even against a CHARACTER.
    rolls = iter([6, 4, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=-10, damage="1", weapon_type="ranged")
    result = _doctrina_combat(
        weapon, attacker_rules=ELECTRO_INFUSION, defender_keywords=["CHARACTER"]
    )
    # _doctrina_combat's defender is T1, so S4 wounds on 2+: a 4 succeeds.
    assert result.total_damage == 1


@pytest.mark.parametrize("with_character,expected_damage", [(True, 0), (False, 1)])
async def test_combat_endpoint_applies_defending_units_datasheet_rules(
    client: AsyncClient, faction_id: int, monkeypatch, with_character, expected_damage
):
    rolls = iter([6, 4, 1])  # hit, wound 4 (S4 vs T4: fails only at -1), save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    infusion_id = (
        await client.post("/datasheet-abilities", json={"name": "Electro-infusion"})
    ).json()["id"]
    character_id = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]

    attacker_model = await _create_model(client, faction_id)
    weapon_id = await _create_weapon(
        client, attacker_model, strength=4, ap=-10, skill=3, weapon_type="ranged"
    )
    shooters = await _create_faction_unit(client, faction_id, "Shooters")
    attacker_unit = await _create_unit(client, shooters, attacker_model, weapon_id)
    priest = await _create_model(
        client,
        faction_id,
        toughness=4,
        save=7,
        wounds=10,
        ability_ids=[infusion_id],
        keyword_ids=[character_id] if with_character else [],
    )
    defender_unit = await _create_unit(
        client, await _create_faction_unit(client, faction_id, "Priests"), priest
    )

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_unit,
            "defending_unit_id": defender_unit,
            "selected_weapon_ids": [weapon_id],
        },
    )
    assert response.status_code == 200
    assert response.json()["total_damage"] == expected_damage


# --- feel no pain rolls in results ---


def test_fnp_rolls_are_recorded_one_per_point_of_damage(monkeypatch):
    # D3 damage rolls 3; the defender's 5+ FNP then rolls 5 (saved), 2, 6 (saved).
    rolls = iter([6, 6, 1, 3, 5, 2, 6])  # hit, wound, save, damage, fnp x3
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="D3", weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7, feel_no_pain=5), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.fnp_rolls == [5, 2, 6]
    assert result.weapon_results[0].fnp_rolls == [5, 2, 6]
    assert result.total_damage == 1


def test_no_fnp_rolls_without_feel_no_pain(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="2", weapon_type="ranged")

    assert _doctrina_combat(weapon).fnp_rolls == []


# --- Lord of the Machine Cult (leader-granted feel no pain) ---

LORD_OF_THE_MACHINE_CULT = datasheet_ability_seeds.RULES["Lord of the Machine Cult"]


def _lord_combat(monkeypatch, defender_models, fnp_rolls):
    # One 1-damage attack that always gets through to damage; the FNP rolls
    # (if any are made) come next.
    rolls = iter([6, 6, 1, *fnp_rolls])  # hit, wound, save, fnp...
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(m, []) for m in defender_models])
    return combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        defender_rules=LORD_OF_THE_MACHINE_CULT,
    )


def _dominus():
    return _model(name="Dominus", is_leader=True, wounds=4, save=7, keywords=[_keyword("CHARACTER")])


def _bodyguard(*keywords):
    return _model(name="Bodyguard", wounds=1, save=7, keywords=[_keyword(k) for k in keywords])


@pytest.mark.parametrize("fnp_roll,expected_damage", [(5, 0), (4, 1)])
def test_lord_of_the_machine_cult_gives_led_unit_fnp_5(monkeypatch, fnp_roll, expected_damage):
    result = _lord_combat(monkeypatch, [_dominus(), _bodyguard("INFANTRY")], [fnp_roll])
    assert result.fnp_rolls == [fnp_roll]
    assert result.total_damage == expected_damage


@pytest.mark.parametrize("fnp_roll,expected_damage", [(4, 0), (3, 1)])
def test_lord_of_the_machine_cult_gives_led_electro_priests_fnp_4(
    monkeypatch, fnp_roll, expected_damage
):
    result = _lord_combat(
        monkeypatch, [_dominus(), _bodyguard("INFANTRY", "ELECTRO-PRIESTS")], [fnp_roll]
    )
    assert result.total_damage == expected_damage


def test_lord_of_the_machine_cult_does_nothing_for_a_lone_dominus(monkeypatch):
    result = _lord_combat(monkeypatch, [_dominus()], [6])
    assert result.fnp_rolls == []
    assert result.total_damage == 1


def test_granted_fnp_keeps_a_models_better_own_fnp(monkeypatch):
    # The bodyguard's own FNP 3+ beats the granted 5+: a 3 still saves.
    tough = _model(name="Bodyguard", wounds=1, save=7, feel_no_pain=3)
    result = _lord_combat(monkeypatch, [_dominus(), tough], [3])
    assert result.total_damage == 0


# --- Skorpius Disintegrator: D6+1, Blast, Rapid Fire 3, Twin-linked,
#     Blistering Salvoes, Deadly Demise ---


def test_roll_dice_with_modifier(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    assert combat.roll_dice("D6+1") == 5
    assert combat.roll_dice("2D6+2") == 10


def _many_targets(n, **overrides):
    return [_model(toughness=1, wounds=1, save=7, **overrides) for _ in range(n)]


def _fire(weapon, defender_models, **flags):
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(m, []) for m in defender_models])
    options = dict(
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    options.update(flags)
    return combat.resolve_combat(attacker, defender, {weapon.id}, **options)


@pytest.mark.parametrize("models,expected_attacks", [(4, 2), (5, 3), (10, 4), (11, 4)])
def test_blast_adds_an_attack_per_five_target_models(monkeypatch, models, expected_attacks):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # every attack misses
    weapon = _weapon(attacks="2", skill=4, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("always")], [_effect("blast")])]

    assert len(_fire(weapon, _many_targets(models)).attack_rolls) == expected_attacks


@pytest.mark.parametrize("half_range,expected_attacks", [(True, 6), (False, 3)])
def test_rapid_fire_3_adds_three_attacks_within_half_range(
    monkeypatch, half_range, expected_attacks
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)
    weapon = _weapon(attacks="3", skill=4, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("within_half_range")], [_effect("add_three_attacks")])]

    result = _fire(weapon, _many_targets(1), half_range=half_range)
    assert len(result.attack_rolls) == expected_attacks


def _twin_linked():
    return _ability([_condition("always")], [_effect("reroll_failed_wounds")])


def test_twin_linked_rerolls_a_failed_wound(monkeypatch):
    # S4 vs T4 needs 4+: a 2 fails, the re-roll of 5 succeeds.
    rolls = iter([6, 2, 5, 1])  # hit, wound, wound re-roll, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, damage="1", weapon_type="ranged")
    weapon.abilities = [_twin_linked()]

    result = _fire(weapon, [_model(toughness=4, wounds=5, save=7)])
    assert result.wound_rolls == [2]
    assert result.wound_rerolls == [5]
    assert result.weapon_results[0].wound_rerolls == [5]
    assert result.total_damage == 1


def test_twin_linked_does_not_reroll_a_successful_wound(monkeypatch):
    rolls = iter([6, 4, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, damage="1", weapon_type="ranged")
    weapon.abilities = [_twin_linked()]

    result = _fire(weapon, [_model(toughness=4, wounds=5, save=7)])
    assert result.wound_rerolls == []


def test_twin_linked_reroll_of_a_six_still_triggers_devastating_wounds(monkeypatch):
    # The re-rolled 6 is a critical wound, so Devastating Wounds skips the save.
    rolls = iter([6, 1, 6])  # hit, wound 1 (fails), re-roll 6; no save roll
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, damage="1", weapon_type="ranged")
    devastating = _ability([_condition("critical_wound")], [_effect("no_save")])
    weapon.abilities = [_twin_linked(), devastating]

    result = _fire(weapon, [_model(toughness=4, wounds=5, save=2)])
    assert result.save_rolls == []
    assert result.total_damage == 1


@pytest.mark.parametrize(
    "condition,target_keyword,expected_damage",
    [
        ("target_infantry", "INFANTRY", 1),
        ("target_infantry", "VEHICLE", 0),
        ("target_monster_or_vehicle", "VEHICLE", 1),
        ("target_monster_or_vehicle", "INFANTRY", 0),
    ],
)
def test_blistering_salvoes_plus_one_to_hit_by_target_type(
    monkeypatch, condition, target_keyword, expected_damage
):
    rolls = iter([3, 6, 1])  # hit 3 vs BS4 passes only with +1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged")
    weapon.abilities = [_ability([_condition(condition)], [_effect("plus_one_to_hit")])]

    target = _model(toughness=1, wounds=5, save=7, keywords=[_keyword(target_keyword)])
    assert _fire(weapon, [target]).total_damage == expected_damage


def _deadly_demise_model(**overrides):
    demise = _datasheet_ability([_condition("always")], [_effect("deadly_demise")])
    return _model(**{"toughness": 1, "wounds": 1, "save": 7, "abilities": [demise], **overrides})


@pytest.mark.parametrize("demise_roll,explosions", [(6, 1), (5, 0)])
def test_deadly_demise_rolls_when_the_model_is_destroyed(monkeypatch, demise_roll, explosions):
    rolls = iter([6, 6, 1, demise_roll])  # hit, wound, save, deadly demise
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="1", weapon_type="ranged")

    result = _fire(weapon, [_deadly_demise_model()])
    assert result.models_destroyed == 1
    assert result.deadly_demise_rolls == [demise_roll]
    assert result.deadly_demise_explosions == explosions


def test_deadly_demise_does_not_roll_for_a_surviving_or_ordinary_model(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="1", weapon_type="ranged")

    survivor = _fire(weapon, [_deadly_demise_model(wounds=5)])
    assert survivor.deadly_demise_rolls == []
    ordinary = _fire(weapon, _many_targets(1))
    assert ordinary.models_destroyed == 1
    assert ordinary.deadly_demise_rolls == []


# --- Sicarian Infiltrators: Sustained Hits 2, Stealth ---


def test_sustained_2_scores_two_extra_hits_on_a_critical(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)  # critical hit, all wound
    weapon = _weapon(
        attacks="1", skill=4, strength=10, ap=0, damage="1", weapon_type="melee", range=None
    )
    weapon.abilities = [_ability([_condition("critical_hit")], [_effect("add_two_extra_hits")])]

    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)], in_engagement_range=True)
    assert result.attack_rolls == [6]
    assert result.total_damage == 3


STEALTH = datasheet_ability_seeds.RULES["Stealth"]


def _stealth_shot(monkeypatch, weapon_type="ranged", weapon_abilities=(), **flags):
    # Hit 3 vs skill 3: it hits, unless the target has the benefit of cover.
    rolls = iter([3, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(
        attacks="1",
        skill=3,
        strength=10,
        ap=-10,
        damage="1",
        weapon_type=weapon_type,
        range=None if weapon_type == "melee" else 24,
    )
    weapon.abilities = list(weapon_abilities)
    return _doctrina_combat(
        weapon, in_engagement_range=weapon_type == "melee", **flags
    ).total_damage


def test_stealth_gives_the_unit_cover_against_ranged_attacks(monkeypatch):
    assert _stealth_shot(monkeypatch, defender_rules=STEALTH) == 0
    # The same as the defender being in cover.
    assert _stealth_shot(monkeypatch, in_cover=True) == 0
    assert _stealth_shot(monkeypatch) == 1


def test_stealth_does_not_affect_melee_attacks(monkeypatch):
    assert _stealth_shot(monkeypatch, weapon_type="melee", defender_rules=STEALTH) == 1


@pytest.mark.parametrize(
    "flags,hits",
    [
        # +1 to hit and one -1 for cover: a 3 hits against skill 3.
        ({"in_cover": True}, 1),
        ({"defender_rules": STEALTH}, 1),
        # Stealth while in cover is still one -1, not two (which the +1/-1 cap
        # alone wouldn't show: +1 -2 caps to -1, and a 3 would miss).
        ({"in_cover": True, "defender_rules": STEALTH}, 1),
    ],
)
def test_stealth_cover_does_not_stack_with_being_in_cover(monkeypatch, flags, hits):
    rolls = iter([3, 6, 1])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="1", weapon_type="ranged")
    weapon.abilities = [_plus_one()]

    assert _doctrina_combat(weapon, **flags).total_damage == hits


def test_ignores_cover_ignores_stealth(monkeypatch):
    ignores_cover = _ability([_condition("always")], [_effect("ignore_cover")])
    damage = _stealth_shot(monkeypatch, weapon_abilities=[ignores_cover], defender_rules=STEALTH)
    assert damage == 1


def test_stealth_does_not_affect_the_stealthy_units_own_attacks(monkeypatch):
    assert _stealth_shot(monkeypatch, attacker_rules=STEALTH) == 1



# --- phase order: all hits, then all wounds, then saves/damage ---


def test_resolve_combat_rolls_all_hits_before_any_wounds(monkeypatch):
    # 3 attacks: the hit rolls come first (6, 5, 4), then the wound rolls (6, 6, 6),
    # then one save per wound - not hit/wound/save per attack.
    rolls = iter([6, 5, 4, 6, 6, 6, 1, 1, 1])
    calls = []

    def roll(a, b):
        value = next(rolls)
        calls.append(value)
        return value

    monkeypatch.setattr(combat.random, "randint", roll)
    weapon = _weapon(attacks="3", skill=4, strength=10, ap=0, damage="1", weapon_type="ranged")
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=2)])

    assert result.attack_rolls == [6, 5, 4]
    assert result.wound_rolls == [6, 6, 6]
    assert result.save_rolls == [1, 1, 1]
    assert result.total_damage == 3


def test_resolve_combat_batches_a_profile_across_models(monkeypatch):
    # Two models each with a one-attack "Gun": both hit rolls are made before
    # either wound roll.
    rolls = iter([6, 2, 6, 1])  # hit (model 1), hit (model 2, misses), wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    gun_a = _weapon(name="Gun", attacks="1", skill=4, strength=10, ap=0, damage="1")
    gun_a.id = 1
    gun_b = _weapon(name="Gun", attacks="1", skill=4, strength=10, ap=0, damage="1")
    gun_b.id = 2
    attacker = _unit([_unit_model(_model(), [gun_a]), _unit_model(_model(), [gun_b])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=2), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {1, 2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.attack_rolls == [6, 2]
    assert result.wound_rolls == [6]
    assert result.save_rolls == [1]


def test_resolve_combat_sustained_hits_join_the_hit_phase(monkeypatch):
    # 2 attacks: a critical (sustained adds a hit) and a miss; the extra hit
    # goes to the wound phase with the first, so 2 wound rolls follow both hits.
    rolls = iter([6, 1, 6, 6, 1, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="2", skill=4, strength=10, ap=0, damage="1", weapon_type="ranged")
    weapon.abilities = [_ability([_condition("critical_hit")], [_effect("add_extra_hit")])]

    result = _fire(weapon, [_model(toughness=1, wounds=10, save=2)])
    assert result.attack_rolls == [6, 1]
    assert result.wound_rolls == [6, 6]
    assert result.total_damage == 2


def test_resolve_combat_still_rolls_every_hit_after_the_unit_is_wiped(monkeypatch):
    # All the hit and wound rolls happen up front, as at the table; only the
    # saves stop once there's no one left to allocate to.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6 if b == 6 else 1)
    weapon = _weapon(attacks="3", skill=2, strength=10, ap=-10, damage="1", weapon_type="ranged")

    result = _fire(weapon, [_model(toughness=1, wounds=1, save=7)])
    assert len(result.attack_rolls) == 3
    assert len(result.wound_rolls) == 3
    assert len(result.save_rolls) == 1
    assert result.models_destroyed == 1


# --- hit roll modifiers: summed, then capped at +1/-1 ---


def _plus_one(condition="always"):
    return _ability([_condition(condition)], [_effect("plus_one_to_hit")])


def _minus_one():
    return _ability([_condition("always")], [_effect("minus_one_to_hit")])


def _hit_with(monkeypatch, hit_roll, skill, abilities=(), **flags):
    # One attack that always wounds and always gets through, so damage tells
    # us whether it hit.
    rolls = iter([hit_roll, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(
        attacks="1", skill=skill, strength=10, ap=-10, damage="1", weapon_type="ranged"
    )
    weapon.abilities = list(abilities)
    return _fire(weapon, [_model(toughness=1, wounds=10, save=7)], **flags).total_damage == 1


def test_plus_two_and_minus_one_nets_plus_one(monkeypatch):
    abilities = [_plus_one(), _plus_one(), _minus_one()]
    assert _hit_with(monkeypatch, 4, skill=5, abilities=abilities)
    assert not _hit_with(monkeypatch, 3, skill=5, abilities=abilities)


def test_two_plus_ones_are_capped_at_plus_one(monkeypatch):
    abilities = [_plus_one(), _plus_one()]
    assert _hit_with(monkeypatch, 3, skill=4, abilities=abilities)
    assert not _hit_with(monkeypatch, 2, skill=4, abilities=abilities)


def test_two_minus_ones_are_capped_at_minus_one(monkeypatch):
    # Cover counts as a -1 too: cover plus another -1 is still just -1.
    abilities = [_minus_one()]
    assert _hit_with(monkeypatch, 4, skill=3, abilities=abilities, in_cover=True)
    assert not _hit_with(monkeypatch, 3, skill=3, abilities=abilities, in_cover=True)


def test_ballistic_skill_improvement_is_outside_the_cap(monkeypatch):
    # +1 to hit (capped) plus BS improved by 1 (a characteristic change): BS4 hits on 2+.
    abilities = [
        _plus_one(),
        _plus_one(),
        _ability([_condition("always")], [_effect("plus_one_skill_ranged")]),
    ]
    assert _hit_with(monkeypatch, 2, skill=4, abilities=abilities)


def test_unmodified_one_always_misses(monkeypatch):
    abilities = [_plus_one(), _ability([_condition("always")], [_effect("plus_one_skill_ranged")])]
    assert not _hit_with(monkeypatch, 1, skill=2, abilities=abilities)


def test_unmodified_six_always_hits(monkeypatch):
    assert _hit_with(monkeypatch, 6, skill=6, abilities=[_minus_one()])


def test_a_shared_datasheet_ability_counts_once_however_many_models_have_it(monkeypatch):
    # Both models have the same +1 to hit ability; with a -1 against it, the
    # net is 0 (one +1, one -1) - not +1 from counting it per model.
    rolls = iter([3, 6, 1])  # hit 3 vs BS4: only hits at a net +1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    shared = _datasheet_ability([_condition("always")], [_effect("plus_one_to_hit")])
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    weapon.abilities = [_minus_one()]
    attacker = _unit(
        [
            _unit_model(_model(abilities=[shared]), [weapon]),
            _unit_model(_model(abilities=[shared]), []),
        ]
    )
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])

    result = combat.resolve_combat(
        attacker,
        defender,
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.total_damage == 0


# --- [HEAVY] counts once ---


def _heavy():
    return _ability([_condition("moved_less_than_3")], [_effect("heavy")])


def test_heavy_from_two_sources_is_one_plus_one(monkeypatch):
    # The weapon's own Heavy and Protector's Heavy, against a -1: net 0, so a
    # BS4 weapon still needs a 4 (Protector's BS+1 left out to isolate Heavy).
    protector_heavy = PROTECTOR[0]
    abilities = [_heavy(), _minus_one()]

    def hit(roll):
        rolls = iter([roll, 6, 1])
        monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
        weapon = _weapon(
            attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged"
        )
        weapon.id = 1
        weapon.abilities = abilities
        return combat.resolve_combat(
            _unit([_unit_model(_model(), [weapon])]),
            _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])]),
            {weapon.id},
            in_engagement_range=False,
            visible=True,
            in_range=True,
            in_cover=False,
            half_range=False,
            moved_less_than_3=True,
            advanced=False,
            attacker_rules=[protector_heavy],
        ).total_damage == 1

    assert hit(4)
    assert not hit(3)


def test_heavy_applies_when_moved_less_than_3(monkeypatch):
    assert _hit_with(monkeypatch, 3, skill=4, abilities=[_heavy()], moved_less_than_3=True)
    assert not _hit_with(monkeypatch, 3, skill=4, abilities=[_heavy()])


def test_heavy_stacks_with_a_different_plus_one_before_the_cap(monkeypatch):
    # Heavy +1 and another +1 (e.g. Blistering Salvoes) is +2, so with a -1 it
    # nets +1: BS4 hits on a 3.
    abilities = [_heavy(), _plus_one(), _minus_one()]
    assert _hit_with(monkeypatch, 3, skill=4, abilities=abilities, moved_less_than_3=True)


# --- Melta 3 ---


@pytest.mark.parametrize("half_range,expected_damage", [(True, 4 + 3), (False, 4)])
def test_melta_3_adds_three_damage_within_half_range(monkeypatch, half_range, expected_damage):
    # D6 damage rolls a 4 (the last roll); Melta 3 adds 3 within half range.
    rolls = iter([6, 6, 1, 4])  # hit, wound, save, damage
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=2, strength=14, ap=-4, damage="D6", weapon_type="ranged")
    weapon.abilities = [_ability([_condition("within_half_range")], [_effect("melta_3")])]

    result = _fire(weapon, [_model(toughness=1, wounds=20, save=7)], half_range=half_range)
    assert result.total_damage == expected_damage


def test_melta_bonus_applies_to_every_attack_of_the_weapon(monkeypatch):
    # 2 attacks, each D1 + 3 = 4 damage.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6 if b == 6 else 1)
    weapon = _weapon(attacks="2", skill=2, strength=14, ap=-4, damage="1", weapon_type="ranged")
    weapon.abilities = [_ability([_condition("within_half_range")], [_effect("melta_3")])]

    result = _fire(weapon, [_model(toughness=1, wounds=20, save=7)], half_range=True)
    assert result.total_damage == 8


# --- Belisarius Cawl's Canticles of the Omnissiah (army-wide options) ---


def test_extra_keywords_count_for_keyword_conditions(monkeypatch):
    # Mantra of Discipline makes Cawl BATTLELINE, so Conqueror's AP bonus applies.
    rolls = iter([6, 6, 3])  # hit, wound, save 3 vs Sv2+ at AP-1 (fails only at AP-2)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-1, damage="1", weapon_type="ranged")
    weapon.id = 1
    result = combat.resolve_combat(
        _unit([_unit_model(_model(), [weapon])]),
        _unit([_unit_model(_model(toughness=1, wounds=10, save=2), [])]),
        {weapon.id},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        attacker_rules=CONQUEROR,
        attacker_extra_keywords={"BATTLELINE"},
    )
    assert result.total_damage == 1


async def _cawl_army(client: AsyncClient):
    # An AdMech list with Cawl in one unit and a Ranger in another, plus a
    # Ranger unit outside the list and an allied (other faction) unit in it -
    # an Imperial Agents CHARACTER, allowed because every model is IMPERIUM.
    admech = (await client.post("/factions", json={"name": "Adeptus Mechanicus"})).json()["id"]
    allies = (await client.post("/factions", json={"name": "Imperial Agents"})).json()["id"]
    imperium = (await client.post("/keywords", json={"name": "IMPERIUM"})).json()["id"]
    character = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]
    canticles = (
        await client.post("/datasheet-abilities", json={"name": "Canticles of the Omnissiah"})
    ).json()["id"]
    doctrina = (
        await client.post(
            "/faction-abilities", json={"name": "Doctrina Imperatives", "faction_id": admech}
        )
    ).json()["id"]
    cawl = await _create_model(
        client,
        admech,
        name="Cawl",
        ability_ids=[canticles],
        faction_ability_ids=[doctrina],
        keyword_ids=[imperium],
    )
    cawl_gun = await _create_weapon(
        client, cawl, name="Cawl Gun", skill=4, strength=10, ap=-1, weapon_type="ranged"
    )
    ranger = await _create_model(
        client, admech, name="Ranger", faction_ability_ids=[doctrina], keyword_ids=[imperium]
    )
    rifle = await _create_weapon(
        client, ranger, name="Rifle", skill=4, strength=10, ap=-10, weapon_type="ranged"
    )
    ranger_gun = await _create_weapon(
        client, ranger, name="Ranger Gun", skill=4, strength=10, ap=-1, weapon_type="ranged"
    )
    agent = await _create_model(client, allies, name="Agent", keyword_ids=[imperium, character])
    pistol = await _create_weapon(
        client, agent, name="Pistol", skill=4, strength=10, ap=-10, weapon_type="ranged"
    )
    target = await _create_model(
        client, admech, name="Target", toughness=1, save=2, wounds=20, keyword_ids=[imperium]
    )
    list_id = (
        await client.post(
            "/lists", json={"name": "Army", "points_limit": 2000, "faction_id": admech}
        )
    ).json()["id"]

    async def unit(faction_id, name, model_id, weapon_id, in_list=True):
        faction_unit = await _create_faction_unit(client, faction_id, name)
        response = await client.post(
            "/units",
            json={
                "faction_unit_id": faction_unit,
                "points": 100,
                "list_id": list_id if in_list else None,
                "unit_models": [
                    {"model_id": model_id, "weapon_ids": [weapon_id] if weapon_id else []}
                ],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return {
        "cawl": (await unit(admech, "Cawl", cawl, cawl_gun), cawl_gun),
        "rangers": (await unit(admech, "Rangers", ranger, rifle), rifle),
        "rangers_ap1": (await unit(admech, "Rangers AP-1", ranger, ranger_gun), ranger_gun),
        "lone_rangers": (await unit(admech, "Lone Rangers", ranger, rifle, in_list=False), rifle),
        "agents": (await unit(allies, "Agents", agent, pistol), pistol),
        "target": (await unit(admech, "Targets", target, None, in_list=False), None),
        "target_in_list": (await unit(admech, "Listed Targets", target, None), None),
    }


async def _attack(client, attacker, defender, weapon_id, **options):
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker,
            "defending_unit_id": defender,
            "selected_weapon_ids": [weapon_id],
            **options,
        },
    )
    assert response.status_code == 200, response.json()
    return response.json()


@pytest.mark.parametrize(
    "attacker,rerolls",
    [
        ("rangers", True),  # Cawl is elsewhere in its list
        ("cawl", True),  # Cawl's own unit
        ("lone_rangers", False),  # not in Cawl's list
        ("agents", False),  # in the list, but not ADEPTUS MECHANICUS (Cawl's faction)
    ],
)
async def test_machine_vengeance_rerolls_hits_for_friendly_units_in_cawls_list(
    client: AsyncClient, monkeypatch, attacker, rerolls
):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # every hit misses
    army = await _cawl_army(client)
    unit_id, weapon_id = army[attacker]

    body = await _attack(
        client,
        unit_id,
        army["target"][0],
        weapon_id,
        attacker_rule_options=["Invocation of Machine Vengeance"],
    )
    assert (len(body["attack_rerolls"]) == 1) is rerolls


async def test_shroudpsalm_gives_the_defending_unit_stealth(client: AsyncClient, monkeypatch):
    # Hit 4 vs BS4: hits normally, misses with the Benefit of Cover.
    army = await _cawl_army(client)
    unit_id, weapon_id = army["lone_rangers"]

    async def damage(options):
        rolls = iter([4, 6, 1])
        monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
        body = await _attack(
            client, unit_id, army["target_in_list"][0], weapon_id, defender_rule_options=options
        )
        return body["total_damage"]

    assert await damage([]) == 1
    assert await damage(["Shroudpsalm"]) == 0


@pytest.mark.parametrize(
    "attacker,mantra,expected_damage",
    [
        ("cawl", True, 1),  # Cawl is BATTLELINE: Conqueror's +1 AP applies
        ("cawl", False, 0),
        ("rangers_ap1", True, 0),  # Mantra only makes Cawl BATTLELINE, not his army
    ],
)
async def test_mantra_of_discipline_makes_only_cawls_unit_battleline(
    client: AsyncClient, monkeypatch, attacker, mantra, expected_damage
):
    # An AP-1 gun against Sv2+: a save roll of 3 passes, unless Conqueror's
    # BATTLELINE AP bonus makes it AP-2.
    army = await _cawl_army(client)
    unit_id, weapon_id = army[attacker]
    rolls = iter([6, 6, 3])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    options = ["Conqueror Imperative"] + (["Mantra of Discipline"] if mantra else [])

    body = await _attack(
        client, unit_id, army["target"][0], weapon_id, attacker_rule_options=options
    )
    assert body["total_damage"] == expected_damage


async def test_canticle_options_are_validated(client: AsyncClient):
    army = await _cawl_army(client)
    unit_id, weapon_id = army["rangers"]
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": unit_id,
            "defending_unit_id": army["target"][0],
            "selected_weapon_ids": [weapon_id],
            "attacker_rule_options": ["Shroudpsalm", "Mantra of Discipline"],
        },
    )
    assert response.status_code == 400


# --- stratagem keyword requirements ---


def _restricted_stratagem(*keywords):
    # +1 to hit, but only for models with all of `keywords`.
    stratagem = Stratagem(name="Restricted", description=None, cp=1, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("plus_one_to_hit")]
    stratagem.keywords = [_keyword(k) for k in keywords]
    return stratagem


def _two_model_attack(monkeypatch, stratagem):
    # A CHARACTER and a trooper, each with a one-attack BS4 gun. Every roll is
    # a 3: it hits only with +1 to hit, then always wounds and fails its save.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
    hero_gun = _weapon(name="Hero Gun", attacks="1", skill=4, strength=10, ap=-10, damage="1")
    hero_gun.id = 1
    trooper_gun = _weapon(
        name="Trooper Gun", attacks="1", skill=4, strength=10, ap=-10, damage="1"
    )
    trooper_gun.id = 2
    attacker = _unit(
        [
            _unit_model(_model(keywords=[_keyword("CHARACTER")]), [hero_gun]),
            _unit_model(_model(keywords=[_keyword("INFANTRY")]), [trooper_gun]),
        ]
    )
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {1, 2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        stratagems=[stratagem],
    )
    return {wr.name: wr.total_damage for wr in result.weapon_results}


def test_restricted_stratagem_only_affects_models_with_its_keywords(monkeypatch):
    damage = _two_model_attack(monkeypatch, _restricted_stratagem("CHARACTER"))
    assert damage == {"Hero Gun": 1, "Trooper Gun": 0}


def test_unrestricted_stratagem_affects_every_model(monkeypatch):
    damage = _two_model_attack(monkeypatch, _restricted_stratagem())
    assert damage == {"Hero Gun": 1, "Trooper Gun": 1}


def test_restricted_stratagem_stays_out_of_the_unit_wide_check(monkeypatch):
    # A CHARACTER-only re-roll mustn't spread to the whole unit.
    stratagem = Stratagem(name="Restricted", description=None, cp=1, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("reroll_failed_hits")]
    stratagem.keywords = [_keyword("CHARACTER")]
    rolls = iter([1, 6, 6, 1])  # a missed hit - it would hit if re-rolled
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    result = combat.resolve_combat(
        _unit([_unit_model(_model(keywords=[_keyword("INFANTRY")]), [weapon])]),
        _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])]),
        {1},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        stratagems=[stratagem],
    )
    assert (result.attack_rerolls, result.total_damage) == ([], 0)


@pytest.mark.parametrize("with_character,status", [(True, 200), (False, 400)])
async def test_combat_endpoint_requires_a_model_with_the_stratagems_keywords(
    client: AsyncClient, faction_id: int, with_character, status
):
    character = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]
    stratagem_id = (
        await client.post(
            "/stratagems",
            json={"name": "Epic Challenge", "cp": 1, "is_core": True, "keyword_ids": [character]},
        )
    ).json()["id"]
    model_id = await _create_model(
        client, faction_id, keyword_ids=[character] if with_character else []
    )
    weapon_id = await _create_weapon(client, model_id)
    attacker = await _create_unit(
        client, await _create_faction_unit(client, faction_id, "Heroes"), model_id, weapon_id
    )
    defender_model = await _create_model(client, faction_id)
    defender = await _create_unit(
        client, await _create_faction_unit(client, faction_id, "Targets"), defender_model
    )

    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker,
            "defending_unit_id": defender,
            "selected_weapon_ids": [weapon_id],
            "stratagem_ids": [stratagem_id],
        },
    )
    assert response.status_code == status


# --- attacker and defender stratagems, by phase ---


def test_defender_stratagem_modifies_attacks_against_its_unit(monkeypatch):
    # A defender's -1 to hit: a 4 against skill 4 now misses.
    stratagem = Stratagem(name="Shroud", description=None, cp=1, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("minus_one_to_hit")]
    stratagem.keywords = []
    rolls = iter([4, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged")
    result = _fire(
        weapon, [_model(toughness=1, wounds=10, save=7)], defender_stratagems=[stratagem]
    )
    assert result.total_damage == 0


async def _timed_stratagem(client: AsyncClient, name: str, *timings) -> int:
    # A core stratagem usable at the given (phase, turn) timings.
    response = await client.post(
        "/stratagems",
        json={
            "name": name,
            "cp": 1,
            "is_core": True,
            "timings": [{"phase": phase, "turn": turn} for phase, turn in timings],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _usable(client, unit_id, side, in_engagement_range=False) -> set[str]:
    response = await client.get(
        "/combat/stratagems",
        params={
            "unit_id": unit_id,
            "side": side,
            "in_engagement_range": str(in_engagement_range).lower(),
        },
    )
    assert response.status_code == 200
    return {s["name"] for s in response.json()}


async def test_calculator_stratagems_split_by_side_and_phase(
    client: AsyncClient, faction_id: int
):
    attacker_id, defender_id, _ = await _combat_units_in_list(client, faction_id, [])
    await _timed_stratagem(client, "Any Time")
    await _timed_stratagem(client, "My Shooting", ("shooting", "your_turn"))
    await _timed_stratagem(client, "Their Shooting", ("shooting", "opponent_turn"))
    await _timed_stratagem(client, "Either Fight", ("fight", "either"))
    await _timed_stratagem(client, "My Command", ("command", "your_turn"))

    assert await _usable(client, attacker_id, "attacker") == {"Any Time", "My Shooting"}
    assert await _usable(client, defender_id, "defender") == {"Any Time", "Their Shooting"}
    assert await _usable(client, attacker_id, "attacker", True) == {"Any Time", "Either Fight"}
    assert await _usable(client, defender_id, "defender", True) == {"Any Time", "Either Fight"}


async def test_calculator_stratagems_check_detachment_and_keywords(
    client: AsyncClient, faction_id: int
):
    mine = await _create_detachment(client, faction_id, "Mine")
    other = await _create_detachment(client, faction_id, "Other")
    attacker_id, _, _ = await _combat_units_in_list(client, faction_id, [mine])
    await client.post("/stratagems", json={"name": "Own", "cp": 1, "detachment_ids": [mine]})
    await client.post("/stratagems", json={"name": "Theirs", "cp": 1, "detachment_ids": [other]})
    keyword_id = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]
    await client.post(
        "/stratagems",
        json={"name": "Heroes Only", "cp": 1, "is_core": True, "keyword_ids": [keyword_id]},
    )

    assert await _usable(client, attacker_id, "attacker") == {"Own"}


async def test_calculator_stratagems_invalid_unit_returns_400(client: AsyncClient):
    response = await client.get("/combat/stratagems", params={"unit_id": 9999, "side": "attacker"})
    assert response.status_code == 400


async def test_combat_endpoint_accepts_defender_stratagem(client: AsyncClient, faction_id: int):
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(client, faction_id, [])
    theirs = await _timed_stratagem(client, "Their Shooting", ("shooting", "opponent_turn"))
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "defender_stratagem_ids": [theirs],
        },
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "field,timing,in_engagement_range",
    [
        # The attacker can't use an opponent's-turn stratagem...
        ("stratagem_ids", ("shooting", "opponent_turn"), False),
        # ...the defender can't use a your-turn one...
        ("defender_stratagem_ids", ("shooting", "your_turn"), False),
        # ...and neither can use a shooting stratagem in the fight phase.
        ("stratagem_ids", ("shooting", "either"), True),
        ("defender_stratagem_ids", ("shooting", "either"), True),
    ],
)
async def test_combat_endpoint_rejects_stratagem_with_wrong_timing(
    client: AsyncClient, faction_id: int, field, timing, in_engagement_range
):
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(client, faction_id, [])
    stratagem_id = await _timed_stratagem(client, "Mistimed", timing)
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "in_engagement_range": in_engagement_range,
            field: [stratagem_id],
        },
    )
    assert response.status_code == 400
    assert "Mistimed" in response.json()["detail"]


def _bulwark_defence(monkeypatch, save_roll, invulnerable=None):
    # AP-4 against a 3+ save, with a defender stratagem giving a 4+ invulnerable.
    stratagem = Stratagem(name="Bulwark", description=None, cp=2, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("invulnerable_4")]
    stratagem.keywords = []
    rolls = iter([6, 6, save_roll])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-4, weapon_type="ranged")
    defender = _model(toughness=1, wounds=10, save=3, invulnerable=invulnerable)
    return _fire(weapon, [defender], defender_stratagems=[stratagem]).total_damage


def test_defender_stratagem_gives_4_plus_invulnerable_save(monkeypatch):
    assert _bulwark_defence(monkeypatch, 4) == 0
    assert _bulwark_defence(monkeypatch, 3) == 1


def test_4_plus_invulnerable_keeps_a_better_existing_one(monkeypatch):
    assert _bulwark_defence(monkeypatch, 3, invulnerable=3) == 0


async def test_calculator_stratagems_respect_combat_side(client: AsyncClient, faction_id: int):
    # A Fight-phase stratagem usable in either turn, but only on the unit being
    # attacked (e.g. Baleful Halo), or only on the attacking unit.
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(client, faction_id, [])
    for name, side in [("Halo", "defender"), ("Strike", "attacker"), ("Anyone", None)]:
        response = await client.post(
            "/stratagems",
            json={
                "name": name,
                "cp": 1,
                "is_core": True,
                "timings": [{"phase": "fight", "turn": "either"}],
                "combat_side": side,
            },
        )
        assert response.status_code == 201

    assert await _usable(client, attacker_id, "attacker", True) == {"Strike", "Anyone"}
    assert await _usable(client, defender_id, "defender", True) == {"Halo", "Anyone"}

    halo_id = next(s["id"] for s in (await client.get("/stratagems")).json() if s["name"] == "Halo")
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "in_engagement_range": True,
            "stratagem_ids": [halo_id],
        },
    )
    assert response.status_code == 400
    assert "only used by the defender" in response.json()["detail"]


# --- stratagem keyword exclusions ---


def test_excluded_keyword_stratagem_skips_models_with_it(monkeypatch):
    stratagem = _restricted_stratagem()
    stratagem.excluded_keywords = [_keyword("CHARACTER")]
    damage = _two_model_attack(monkeypatch, stratagem)
    assert damage == {"Hero Gun": 0, "Trooper Gun": 1}


async def test_calculator_stratagems_respect_excluded_keywords(
    client: AsyncClient, faction_id: int
):
    # The test units' models have no keywords - excluding VEHICLE leaves them
    # eligible, excluding a keyword they have doesn't.
    attacker_id, _, weapon_id = await _combat_units_in_list(client, faction_id, [])
    vehicle = (await client.post("/keywords", json={"name": "VEHICLE"})).json()["id"]
    await client.post(
        "/stratagems",
        json={"name": "Not Vehicles", "cp": 1, "is_core": True, "excluded_keyword_ids": [vehicle]},
    )
    assert await _usable(client, attacker_id, "attacker") == {"Not Vehicles"}

    unit = next(u for u in (await client.get("/units")).json() if u["id"] == attacker_id)
    model_id = unit["unit_models"][0]["model_id"]
    model = next(m for m in (await client.get("/models")).json() if m["id"] == model_id)
    model["keyword_ids"] = [vehicle]
    assert (await client.put(f"/models/{model_id}", json=model)).status_code == 200
    assert await _usable(client, attacker_id, "attacker") == set()


# --- abilities granted by enhancements and upgrades ---


def _plus_one_grant(scope, weapon_type=None):
    return EnhancementWeaponAbility(
        weapon_ability=_plus_one(), weapon_type=weapon_type, scope=scope
    )


def _enhancement(kind="enhancement", weapon_grants=(), datasheet_grants=()):
    enhancement = Enhancement(name="Relic", points=10, kind=kind, detachment_id=1)
    enhancement.weapon_ability_grants = list(weapon_grants)
    enhancement.datasheet_ability_grants = list(datasheet_grants)
    return enhancement


def _enhanced_attack(monkeypatch, enhancement=None, upgrade=None, with_trooper=True):
    # A CHARACTER (carrying `enhancement`) with a gun and a blade, and maybe a
    # trooper with a gun. Every roll is a 3 against BS/WS 4: an attack only
    # hits with +1 to hit, then always wounds and gets through.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
    stats = dict(attacks="1", skill=4, strength=10, ap=-10, damage="1")
    hero_gun = _weapon(name="Hero Gun", weapon_type="ranged", **stats)
    hero_gun.id = 1
    trooper_gun = _weapon(name="Trooper Gun", weapon_type="ranged", **stats)
    trooper_gun.id = 2
    hero = _unit_model(_model(keywords=[_keyword("CHARACTER")]), [hero_gun])
    hero.enhancement = enhancement
    unit_models = [hero]
    if with_trooper:
        unit_models.append(
            _unit_model(_model(keywords=[_keyword("INFANTRY")]), [trooper_gun])
        )
    attacker = _unit(unit_models)
    attacker.upgrade = upgrade
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {1, 2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    return {wr.name: wr.total_damage for wr in result.weapon_results}


def test_bearer_grant_only_reaches_the_bearers_weapons(monkeypatch):
    relic = _enhancement(weapon_grants=[_plus_one_grant("bearer", "ranged")])
    assert _enhanced_attack(monkeypatch, relic) == {"Hero Gun": 1, "Trooper Gun": 0}


def test_grant_limited_to_another_weapon_type_does_nothing(monkeypatch):
    relic = _enhancement(weapon_grants=[_plus_one_grant("bearer", "melee")])
    assert _enhanced_attack(monkeypatch, relic) == {"Hero Gun": 0, "Trooper Gun": 0}


def test_led_unit_grant_reaches_every_model_while_leading(monkeypatch):
    relic = _enhancement(weapon_grants=[_plus_one_grant("led_unit", "ranged")])
    assert _enhanced_attack(monkeypatch, relic) == {"Hero Gun": 1, "Trooper Gun": 1}


def test_led_unit_grant_does_nothing_without_a_unit_to_lead(monkeypatch):
    relic = _enhancement(weapon_grants=[_plus_one_grant("led_unit")])
    assert _enhanced_attack(monkeypatch, relic, with_trooper=False) == {"Hero Gun": 0}


def test_upgrade_grant_reaches_every_model(monkeypatch):
    upgrade = _enhancement("upgrade", weapon_grants=[_plus_one_grant("unit")])
    assert _enhanced_attack(monkeypatch, upgrade=upgrade) == {"Hero Gun": 1, "Trooper Gun": 1}


def test_granted_datasheet_ability_applies_to_the_unit(monkeypatch):
    ability = _datasheet_ability([_condition("always")], [_effect("plus_one_to_hit")])
    relic = _enhancement(
        datasheet_grants=[EnhancementDatasheetAbility(datasheet_ability=ability, scope="bearer")]
    )
    assert _enhanced_attack(monkeypatch, relic) == {"Hero Gun": 1, "Trooper Gun": 1}


async def test_combat_endpoint_applies_enhancement_granted_stealth(
    client: AsyncClient, faction_id: int, session, monkeypatch
):
    # Malphonic Susurrus-style: a CHARACTER leading a unit gives it Stealth -
    # the benefit of cover, so ranged attacks against it get -1 to hit, unless
    # they ignore cover. Every roll is a 4 against BS4.
    from app.seeds import conditions as conditions_seed
    from app.seeds import datasheet_abilities as datasheet_abilities_seed
    from app.seeds import effects as effects_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)
    await weapon_abilities_seed.seed(session)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)

    stealth_id = next(
        a["id"]
        for a in (await client.get("/datasheet-abilities")).json()
        if a["name"] == "Stealth"
    )
    character = (await client.post("/keywords", json={"name": "CHARACTER"})).json()["id"]
    detachment = (
        await client.post("/detachments", json={"name": "D", "faction_id": faction_id, "dp": 1})
    ).json()["id"]
    relic = await client.post(
        "/enhancements",
        json={
            "name": "Susurrus",
            "points": 20,
            "kind": "enhancement",
            "detachment_id": detachment,
            "datasheet_abilities": [{"datasheet_ability_id": stealth_id, "scope": "led_unit"}],
        },
    )
    assert relic.status_code == 201, relic.text
    list_id = (
        await client.post(
            "/lists",
            json={
                "name": "L",
                "points_limit": 1000,
                "faction_id": faction_id,
                "detachment_ids": [detachment],
            },
        )
    ).json()["id"]
    leader = await _create_model(client, faction_id, keyword_ids=[character])
    trooper = await _create_model(client, faction_id, toughness=1, wounds=5, save=7)
    defender_fu = await _create_faction_unit(client, faction_id, "Defenders")
    defender = await client.post(
        "/units",
        json={
            "faction_unit_id": defender_fu,
            "points": 100,
            "list_id": list_id,
            "unit_models": [
                {"model_id": leader, "enhancement_id": relic.json()["id"]},
                {"model_id": trooper},
            ],
        },
    )
    assert defender.status_code == 201, defender.text

    ignores_cover = next(
        a["id"]
        for a in (await client.get("/weapon-abilities")).json()
        if a["name"] == "Ignores Cover"
    )
    attacker_fu = await _create_faction_unit(client, faction_id, "Attackers")

    async def damage(ability_ids):
        attacker_model = await _create_model(client, faction_id)
        weapon_id = await _create_weapon(
            client,
            attacker_model,
            skill=4,
            strength=10,
            ap=-10,
            weapon_type="ranged",
            ability_ids=ability_ids,
        )
        attacker_id = await _create_unit(client, attacker_fu, attacker_model, weapon_id)
        response = await client.post(
            "/combat",
            json={
                "attacking_unit_id": attacker_id,
                "defending_unit_id": defender.json()["id"],
                "selected_weapon_ids": [weapon_id],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["total_damage"]

    assert await damage([]) == 0  # a 4 misses at -1 to hit
    assert await damage([ignores_cover]) == 1  # Ignores Cover negates Stealth


# --- +1 to wound ---


@pytest.mark.parametrize(
    "effects,wound_roll,wounds",
    [
        ([], 3, 0),  # S4 vs T4 needs a 4
        (["plus_one_to_wound"], 3, 1),
        (["plus_one_to_wound", "minus_one_to_wound"], 3, 0),  # they cancel out
        (["plus_one_to_wound", "minus_one_to_wound"], 4, 1),
        (["plus_one_to_wound"], 1, 0),  # an unmodified 1 always fails
    ],
)
def test_plus_one_to_wound(monkeypatch, effects, wound_roll, wounds):
    rolls = iter([6, wound_roll, 1])  # hit, wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=-10, damage="1", weapon_type="ranged")
    weapon.abilities = [_ability([_condition("always")], [_effect(e)]) for e in effects]
    result = _fire(weapon, [_model(toughness=4, wounds=10, save=7)])
    assert result.total_damage == wounds


# --- stratagem keyword options ("one X or Y unit") ---


def test_keyword_option_stratagem_applies_to_models_matching_any_option(monkeypatch):
    stratagem = _restricted_stratagem()
    stratagem.keyword_options = [[_keyword("PTERAXII")], [_keyword("CHARACTER")]]
    assert _two_model_attack(monkeypatch, stratagem) == {"Hero Gun": 1, "Trooper Gun": 0}


def test_keyword_option_needs_every_keyword_in_it(monkeypatch):
    stratagem = _restricted_stratagem()
    stratagem.keyword_options = [[_keyword("CHARACTER"), _keyword("MOUNTED")]]
    assert _two_model_attack(monkeypatch, stratagem) == {"Hero Gun": 0, "Trooper Gun": 0}


async def test_calculator_stratagems_respect_keyword_options(client: AsyncClient, faction_id: int):
    attacker_id, _, _ = await _combat_units_in_list(client, faction_id, [])
    sicarian = (await client.post("/keywords", json={"name": "SICARIAN"})).json()["id"]
    mounted = (await client.post("/keywords", json={"name": "MOUNTED"})).json()["id"]
    response = await client.post(
        "/stratagems",
        json={
            "name": "Bionic",
            "cp": 1,
            "is_core": True,
            "keyword_option_ids": [[sicarian], [mounted]],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["keyword_option_ids"] == [[sicarian], [mounted]]
    assert await _usable(client, attacker_id, "attacker") == set()

    unit = next(u for u in (await client.get("/units")).json() if u["id"] == attacker_id)
    model_id = unit["unit_models"][0]["model_id"]
    model = next(m for m in (await client.get("/models")).json() if m["id"] == model_id)
    model["keyword_ids"] = [mounted]
    assert (await client.put(f"/models/{model_id}", json=model)).status_code == 200
    assert await _usable(client, attacker_id, "attacker") == {"Bionic"}


def test_elevated_strider_can_shoot_after_advancing(monkeypatch):
    # Modelled as [ASSAULT] on every weapon, from the datasheet ability.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    strider = next(e for e in datasheet_ability_seeds.ENTRIES if e[0] == "Elevated Strider")
    ability = _datasheet_ability(
        [_condition(c) for c in strider[2]], [_effect(e) for e in strider[3]]
    )
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="ranged")
    weapon.id = 1

    def shots(abilities):
        attacker = _unit([_unit_model(_model(abilities=abilities), [weapon])])
        defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
        return combat.resolve_combat(
            attacker,
            defender,
            {1},
            in_engagement_range=False,
            visible=True,
            in_range=True,
            in_cover=False,
            half_range=False,
            moved_less_than_3=False,
            advanced=True,
        ).attack_rolls

    assert shots([]) == []
    assert shots([ability]) == [6]


# --- Breaching Command: re-roll Hit rolls of 1 (or all of them near BATTLELINE) ---


def _breaching_shot(monkeypatch, rolls, **flags):
    # One BS4 attack that always wounds and gets through once it hits, from a
    # unit with Breaching Command.
    entry = next(e for e in datasheet_ability_seeds.ENTRIES if e[0] == "Breaching Command")
    ability = _datasheet_ability(
        [_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]]
    )
    rolls = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 6))
    weapon = _weapon(attacks="1", skill=4, strength=10, ap=-10, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(abilities=[ability]), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
    return combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        **flags,
    )


def test_breaching_command_rerolls_a_hit_roll_of_1(monkeypatch):
    result = _breaching_shot(monkeypatch, [1, 4, 6, 1])  # hit 1, re-roll 4, wound, save
    assert (result.attack_rerolls, result.total_damage) == ([4], 1)


def test_breaching_command_does_not_reroll_other_misses(monkeypatch):
    result = _breaching_shot(monkeypatch, [2, 4])
    assert (result.attack_rerolls, result.total_damage) == ([], 0)


@pytest.mark.parametrize("near,rerolls", [(True, [4]), (False, [])])
def test_breaching_command_near_battleline_rerolls_any_miss(monkeypatch, near, rerolls):
    # The datasheet's code rule reads the unit's position.
    result = _breaching_shot(
        monkeypatch,
        [2, 4, 6, 1],
        attacker_rules=list(datasheet_ability_seeds.RULES["Breaching Command"]),
        attacker_positions={"near_admech_battleline"} if near else set(),
    )
    assert result.attack_rerolls == rerolls


# --- Positioning: within 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit ---


@pytest.mark.parametrize(
    "keywords,positions,ap_improved",
    [
        ((), set(), False),
        (("BATTLELINE",), set(), True),
        ((), {"near_admech_battleline"}, True),
    ],
)
def test_conqueror_imperative_counts_battleline_or_near_it(
    monkeypatch, keywords, positions, ap_improved
):
    # AP0 against a 4+ save: a 4 saves unless AP is improved to -1.
    rolls = iter([6, 6, 4])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    conqueror = admech_abilities.OPTIONS["Doctrina Imperatives"]["Conqueror Imperative"]
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="melee", range=None)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(keywords=[_keyword(k) for k in keywords]), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=4), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        attacker_rules=list(conqueror),
        attacker_positions=positions,
    )
    assert result.total_damage == (1 if ap_improved else 0)


@pytest.mark.parametrize(
    "keywords,positions,minus_one",
    [
        ((), set(), False),
        (("BATTLELINE",), set(), True),
        ((), {"near_admech_battleline"}, True),
    ],
)
def test_protector_imperative_counts_battleline_or_near_it(
    monkeypatch, keywords, positions, minus_one
):
    # A melee 3 against WS3 hits, unless it's at -1 to hit.
    rolls = iter([3, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    protector = admech_abilities.OPTIONS["Doctrina Imperatives"]["Protector Imperative"]
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="melee", range=None)
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit(
        [
            _unit_model(
                _model(toughness=1, wounds=10, save=7, keywords=[_keyword(k) for k in keywords]),
                [],
            )
        ]
    )
    result = combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=True,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        defender_rules=list(protector),
        defender_positions=positions,
    )
    assert result.total_damage == (0 if minus_one else 1)


async def test_combat_endpoint_rejects_unknown_positions(client: AsyncClient, faction_id: int):
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(client, faction_id, [])
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "attacker_positions": ["on_a_hill"],
        },
    )
    assert response.status_code == 400
    assert "on_a_hill" in response.json()["detail"]


async def test_positions_are_asked_about_only_for_units_whose_rules_use_them(
    client: AsyncClient, session
):
    # Doctrina Imperatives reads it on both sides (Conqueror attacking,
    # Protector defending); Breaching Command only when attacking; a unit with
    # neither never.
    from app.seeds import conditions as conditions_seed
    from app.seeds import datasheet_abilities as datasheet_abilities_seed
    from app.seeds import effects as effects_seed
    from app.seeds import factions as factions_seed

    await factions_seed.seed(session)
    await factions_seed.seed_abilities(session)
    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)
    admech = next(
        f["id"] for f in (await client.get("/factions")).json() if f["name"] == "Adeptus Mechanicus"
    )
    doctrina = next(
        a["id"]
        for a in (await client.get("/faction-abilities")).json()
        if a["name"] == "Doctrina Imperatives"
    )
    breaching = next(
        a["id"]
        for a in (await client.get("/datasheet-abilities")).json()
        if a["name"] == "Breaching Command"
    )
    faction_unit = await _create_faction_unit(client, admech, "Units")

    async def positions(side, **model):
        model_id = await _create_model(client, admech, **model)
        unit_id = await _create_unit(client, faction_unit, model_id)
        response = await client.get(
            "/combat/positions", params={"unit_id": unit_id, "side": side}
        )
        assert response.status_code == 200
        return [p["id"] for p in response.json()]

    near = "near_admech_battleline"
    assert near in await positions("attacker", faction_ability_ids=[doctrina])
    assert near in await positions("defender", faction_ability_ids=[doctrina])
    assert near in await positions("attacker", ability_ids=[breaching])
    assert near not in await positions("defender", ability_ids=[breaching])
    assert near not in await positions("attacker")
    # Every defender is also asked whether it's on an objective, and every
    # attacker whether it Remained Stationary.
    assert "in_range_of_objective" in await positions("defender")
    assert "remained_stationary" in await positions("attacker")
    # ...and whether it's below its Starting Strength or Below Half-strength.
    assert "below_starting_strength" in await positions("defender")
    assert "below_half_strength" in await positions("defender")
    assert "below_half_strength" not in await positions("attacker")


def test_rapid_fire_2_adds_two_attacks_within_half_range(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Rapid Fire 2")
    weapon = _weapon(attacks="2", skill=4, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    target = [_model(toughness=1, wounds=20, save=7)]
    assert len(_fire(weapon, target, half_range=True).attack_rolls) == 4
    assert len(_fire(weapon, target).attack_rolls) == 2


# --- characteristic effects (Cohort Cybernetica, Eradication Cohort, Lords of the Forge) ---


def _one_attack(monkeypatch, rolls, effects, weapon_type="ranged", defender_effects=(), **stats):
    # One attack with effects on the weapon (and maybe a defender rule), every
    # roll scripted; returns the result.
    rolls = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon_stats = dict(attacks="1", skill=3, strength=4, ap=0, damage="1")
    weapon_stats.update(stats)
    weapon = _weapon(
        weapon_type=weapon_type, range=None if weapon_type == "melee" else 24, **weapon_stats
    )
    weapon.abilities = [_ability([_condition("always")], [_effect(e)]) for e in effects]
    defender_rules = [Rule(conditions=("always",), effects=defender_effects, side="defender")]
    return _fire(
        weapon,
        [_model(toughness=4, wounds=10, save=4)],
        in_engagement_range=weapon_type == "melee",
        defender_rules=defender_rules if defender_effects else None,
    )


def test_ranged_skill_3_sets_ballistic_skill(monkeypatch):
    # A 3 misses at BS5, hits at BS3+; melee weapons keep their WS.
    assert _one_attack(monkeypatch, [3, 6, 1], [], skill=5).total_damage == 0
    assert _one_attack(monkeypatch, [3, 6, 1], ["ranged_skill_3"], skill=5).total_damage == 1
    melee = _one_attack(monkeypatch, [3, 6, 1], ["ranged_skill_3"], weapon_type="melee", skill=5)
    assert melee.total_damage == 0


def test_plus_one_strength(monkeypatch):
    # S4 vs T4 needs a 4 to wound; S5 a 3.
    assert _one_attack(monkeypatch, [6, 3, 1], []).total_damage == 0
    assert _one_attack(monkeypatch, [6, 3, 1], ["plus_one_strength"]).total_damage == 1


def test_plus_one_damage(monkeypatch):
    assert _one_attack(monkeypatch, [6, 6, 1], ["plus_one_damage"], damage="2").total_damage == 3


@pytest.mark.parametrize("ap,save_roll,saved", [(-2, 5, True), (-2, 4, False), (0, 4, True)])
def test_worsen_ap(monkeypatch, ap, save_roll, saved):
    # Against a 4+ save: AP-2 worsened to AP-1 needs a 5; AP0 stays AP0.
    result = _one_attack(
        monkeypatch, [6, 6, save_roll], [], ap=ap, defender_effects=("worsen_ap",)
    )
    assert result.total_damage == (0 if saved else 1)


def test_reroll_wound_ones(monkeypatch):
    result = _one_attack(monkeypatch, [6, 1, 4, 1], ["reroll_wound_ones"])
    assert (result.wound_rerolls, result.total_damage) == ([4], 1)
    result = _one_attack(monkeypatch, [6, 2, 4, 1], ["reroll_wound_ones"])
    assert (result.wound_rerolls, result.total_damage) == ([], 0)


def test_feel_no_pain_6(monkeypatch):
    # hit, wound, failed save, FNP roll
    fnp = ("feel_no_pain_6",)
    assert _one_attack(monkeypatch, [6, 6, 1, 6], [], defender_effects=fnp).total_damage == 0
    assert _one_attack(monkeypatch, [6, 6, 1, 5], [], defender_effects=fnp).total_damage == 1


def test_plus_two_attacks_ability_adds_two_attacks_once(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "+2 Attacks")
    weapon = _weapon(attacks="2", skill=3, strength=10, ap=-10, weapon_type="melee", range=None)
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    result = _fire(weapon, [_model(toughness=1, wounds=20, save=7)], in_engagement_range=True)
    assert len(result.attack_rolls) == 4


@pytest.mark.parametrize(
    "options,rolls,hit_rerolls,wound_rerolls",
    [
        ({"Protector Imperative"}, [1, 4, 1, 4], [4], []),  # hit 1 re-rolled
        ({"Conqueror Imperative"}, [6, 1, 4, 1], [], [4]),  # wound 1 re-rolled
        (set(), [1, 4], [], []),
    ],
)
def test_murderous_imperative(monkeypatch, options, rolls, hit_rerolls, wound_rerolls):
    from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech_datasheet

    rolls = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(), [weapon])])
    defender = _unit([_unit_model(_model(toughness=4, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        attacker_rules=list(admech_datasheet.RULES["Murderous Imperative"]),
        attacker_options=options,
    )
    assert (result.attack_rerolls, result.wound_rerolls) == (hit_rerolls, wound_rerolls)


def test_bearers_unit_grant_reaches_the_whole_unit_even_if_not_leading(monkeypatch):
    # The bearer isn't a CHARACTER, so it isn't leading - "bearers_unit" still
    # reaches every model in its unit.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
    stats = dict(attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged")
    guns = []
    for i in (1, 2):
        gun = _weapon(name=f"Gun {i}", **stats)
        gun.id = i
        guns.append(gun)
    bearer = _unit_model(_model(keywords=[_keyword("INFANTRY")]), [guns[0]])
    bearer.enhancement = _enhancement(weapon_grants=[_plus_one_grant("bearers_unit", "ranged")])
    attacker = _unit([bearer, _unit_model(_model(keywords=[_keyword("INFANTRY")]), [guns[1]])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {1, 2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert {wr.name: wr.total_damage for wr in result.weapon_results} == {"Gun 1": 1, "Gun 2": 1}


# --- stratagems lasting until your next Command phase ---


async def test_lasting_command_phase_stratagem_is_offered_whenever_the_unit_fights(
    client: AsyncClient, faction_id: int
):
    attacker_id, defender_id, _ = await _combat_units_in_list(client, faction_id, [])
    for name, duration, side in [
        ("Lasting", "until_next_command_phase", "attacker"),
        ("Lasting Defence", "until_next_command_phase", "defender"),
        ("Momentary", None, None),
    ]:
        response = await client.post(
            "/stratagems",
            json={
                "name": name,
                "cp": 1,
                "is_core": True,
                "timings": [{"phase": "command", "turn": "your_turn"}],
                "duration": duration,
                "combat_side": side,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["duration"] == duration

    for melee in (False, True):
        assert await _usable(client, attacker_id, "attacker", melee) == {"Lasting"}
        assert await _usable(client, defender_id, "defender", melee) == {"Lasting Defence"}



@pytest.mark.parametrize("on_objective,saved", [(True, True), (False, False)])
def test_scriptural_prognosis_needs_the_defender_on_an_objective(
    monkeypatch, on_objective, saved
):
    # AP-2 against a 4+ save: a 5 saves only if the AP is worsened to -1.
    rolls = iter([6, 6, 5])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    prognosis = Stratagem(name="Scriptural Prognosis", description=None, cp=1, is_core=True)
    prognosis.conditions = [_condition("defender_in_range_of_objective")]
    prognosis.effects = [_effect("worsen_ap")]
    prognosis.keywords = []
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-2, damage="1", weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=4)],
        defender_stratagems=[prognosis],
        defender_positions={"in_range_of_objective"} if on_objective else set(),
    )
    assert result.total_damage == (0 if saved else 1)


# --- enhancement weapons and keywords ---


def test_enhancement_weapon_fires_with_the_bearer(monkeypatch):
    from app.models import EnhancementWeapon

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    casket = EnhancementWeapon(
        name="TL-4Ø9",
        weapon_type="ranged",
        range=24,
        attacks="3",
        skill=2,
        strength=11,
        ap=-2,
        damage="2",
    )
    casket.id = 7
    casket.abilities = []
    relic = _enhancement()
    relic.weapons = [casket]
    gun = _weapon(name="Gun", attacks="1", skill=3, weapon_type="ranged")
    gun.id = 1
    bearer = _unit_model(_model(keywords=[_keyword("CHARACTER")]), [gun])
    bearer.enhancement = relic
    attacker = _unit([bearer])
    defender = _unit([_unit_model(_model(toughness=4, wounds=50, save=7), [])])

    def attacks(selected):
        result = combat.resolve_combat(
            attacker,
            defender,
            selected,
            in_engagement_range=False,
            visible=True,
            in_range=True,
            in_cover=False,
            half_range=False,
            moved_less_than_3=False,
            advanced=False,
        )
        return {wr.name: len(wr.attack_rolls) for wr in result.weapon_results}

    assert attacks({1, ("enhancement", 7)}) == {"Gun": 1, "TL-4Ø9": 3}
    assert attacks({1}) == {"Gun": 1}  # only when it's selected


def test_enhancement_keyword_counts_for_stratagem_targeting(monkeypatch):
    # A SKITARII-only +1 to hit stratagem reaches the bearer's whole unit once
    # the enhancement gives it SKITARII.
    from app.models import EnhancementKeyword

    stratagem = _restricted_stratagem("SKITARII")
    relic = _enhancement()
    relic.keyword_grants = [
        EnhancementKeyword(keyword=_keyword("SKITARII"), scope="bearers_unit")
    ]

    def damage(enhancement):
        monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
        gun = _weapon(
            attacks="1", skill=4, strength=10, ap=-10, damage="1", weapon_type="ranged"
        )
        gun.id = 1
        bearer = _unit_model(_model(keywords=[_keyword("TECH-PRIEST")]), [gun])
        bearer.enhancement = enhancement
        defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
        return combat.resolve_combat(
            _unit([bearer]),
            defender,
            {1},
            in_engagement_range=False,
            visible=True,
            in_range=True,
            in_cover=False,
            half_range=False,
            moved_less_than_3=False,
            advanced=False,
            stratagems=[stratagem],
        ).total_damage

    assert damage(relic) == 1
    assert damage(None) == 0


# --- charged this turn ---


@pytest.mark.parametrize("charged,wounded", [(True, True), (False, False)])
def test_lance_adds_1_to_wound_after_charging(monkeypatch, charged, wounded):
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Lance")
    rolls = iter([6, 3, 1])  # hit, wound (S4 vs T4 needs a 4), save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=-10, weapon_type="melee", range=None)
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    result = _fire(
        weapon,
        [_model(toughness=4, wounds=10, save=7)],
        in_engagement_range=True,
        charged=charged,
    )
    assert result.total_damage == (1 if wounded else 0)


@pytest.mark.parametrize("charged,wounded", [(True, True), (False, False)])
def test_servo_driven_charge_gives_lance_after_charging(monkeypatch, charged, wounded):
    rolls = iter([6, 3, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    charge = Stratagem(name="Servo-Driven Charge", description=None, cp=1, is_core=True)
    charge.conditions = [_condition("charged")]
    charge.effects = [_effect("plus_one_to_wound")]
    charge.keywords = []
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=-10, weapon_type="melee", range=None)
    result = _fire(
        weapon,
        [_model(toughness=4, wounds=10, save=7)],
        in_engagement_range=True,
        charged=charged,
        stratagems=[charge],
    )
    assert result.total_damage == (1 if wounded else 0)


# --- Feel No Pain against mortal wounds (Hazardous) ---


def _hazard(monkeypatch, fnp_roll, shooter, stratagems=()):
    # An INFANTRY shooter fails its hazard roll (1 mortal wound); then its FNP roll.
    rolls = iter([1, fnp_roll])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    hazardous = _ability([_condition("always")], [_effect("hazardous")])
    weapon = _weapon(attacks="0", skill=2)
    weapon.id = 1
    weapon.abilities = [hazardous]
    attacker = _unit([_unit_model(shooter, [weapon])])
    defender = _unit([_unit_model(_model(wounds=5), [])])
    return combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        stratagems=list(stratagems),
    ).hazardous_wounds


def test_hazardous_wounds_are_mortal_so_fnp_vs_mortals_applies(monkeypatch):
    shooter = _model(keywords=[_keyword("INFANTRY")])
    shooter.feel_no_pain_mortal = 5
    assert _hazard(monkeypatch, 5, shooter) == 0
    assert _hazard(monkeypatch, 4, shooter) == 1


def _benevolence():
    stratagem = Stratagem(name="Benevolence", description=None, cp=1, is_core=True)
    stratagem.conditions = [_condition("always")]
    stratagem.effects = [_effect("feel_no_pain_6"), _effect("feel_no_pain_mortal_5")]
    stratagem.keywords = []
    return stratagem


def test_attacker_stratagem_fnp_protects_its_own_unit_from_hazardous(monkeypatch):
    shooter = _model(keywords=[_keyword("INFANTRY")])
    assert _hazard(monkeypatch, 5, shooter, [_benevolence()]) == 0  # 5+ vs mortals
    assert _hazard(monkeypatch, 5, shooter) == 1


def test_attacker_stratagem_fnp_does_not_protect_its_target(monkeypatch):
    # Benevolence used on the attacking unit: the target doesn't get FNP 6+.
    rolls = iter([6, 6, 1, 6])  # hit, wound, failed save, (no FNP roll expected)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)], stratagems=[_benevolence()])
    assert (result.total_damage, result.fnp_rolls) == (1, [])


def test_defender_stratagem_fnp_protects_the_defender(monkeypatch):
    rolls = iter([6, 6, 1, 6])  # hit, wound, failed save, FNP 6
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")
    result = _fire(
        weapon, [_model(toughness=1, wounds=10, save=7)], defender_stratagems=[_benevolence()]
    )
    assert (result.total_damage, result.fnp_rolls) == (0, [6])


# --- Feel No Pain against mortal wounds, for attacks that allow no save ---


@pytest.mark.parametrize(
    "devastating,fnp_roll,damage",
    [
        (True, 5, 0),  # a mortal wound: FNP 5+ vs mortals beats the model's 6+
        (True, 4, 1),
        (False, 5, 1),  # an ordinary wound (failed save): only the 6+
        (False, 6, 0),
    ],
)
def test_attacks_allowing_no_save_use_fnp_vs_mortal_wounds(
    monkeypatch, devastating, fnp_roll, damage
):
    rolls = iter([6, 6, fnp_roll] if devastating else [6, 6, 1, fnp_roll])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="1", weapon_type="ranged")
    if devastating:
        weapon.abilities = [_ability([_condition("always")], [_effect("no_save")])]
    target = _model(toughness=1, wounds=10, save=7, feel_no_pain=6)
    target.feel_no_pain_mortal = 5
    assert _fire(weapon, [target]).total_damage == damage


def test_defender_stratagem_fnp_vs_mortals_counts_against_devastating_wounds(monkeypatch):
    # Benevolence (FNP 6+, 5+ vs mortals) on the defender: a 5 saves a mortal.
    rolls = iter([6, 6, 5])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="1", weapon_type="ranged")
    weapon.abilities = [_ability([_condition("always")], [_effect("no_save")])]
    result = _fire(
        weapon, [_model(toughness=1, wounds=10, save=7)], defender_stratagems=[_benevolence()]
    )
    assert result.total_damage == 0


# --- wargear scope ---


@pytest.mark.parametrize("scope,cover_ignored", [("bearers_unit", True), ("bearer", False)])
def test_bearers_unit_wargear_reaches_every_model(monkeypatch, scope, cover_ignored):
    # An Omnispex-style item on model 1 (which doesn't shoot): model 2's shot
    # ignores cover only if the item reaches the bearer's unit. A 3 hits
    # against BS3, unless the target's cover makes it -1.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)
    omnispex = _wargear([_wargear_ability([_condition("always")], [_effect("ignore_cover")])])
    omnispex.scope = scope
    gun = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="1", weapon_type="ranged")
    gun.id = 2
    attacker = _unit([_unit_model(_model(), [], [omnispex]), _unit_model(_model(), [gun])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=True,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    assert result.total_damage == (1 if cover_ignored else 0)


async def test_end_of_turn_stratagem_is_in_effect_in_later_phases_of_its_turn(
    client: AsyncClient, faction_id: int
):
    # Used in your Movement phase, until the end of the turn: in effect in your
    # Shooting and Fight phases, not for the defender (your opponent's turn).
    attacker_id, defender_id, _ = await _combat_units_in_list(client, faction_id, [])
    response = await client.post(
        "/stratagems",
        json={
            "name": "Superiority",
            "cp": 1,
            "is_core": True,
            "timings": [{"phase": "movement", "turn": "your_turn"}],
            "duration": "until_end_of_turn",
        },
    )
    assert response.status_code == 201, response.text
    for melee in (False, True):
        assert await _usable(client, attacker_id, "attacker", melee) == {"Superiority"}
        assert await _usable(client, defender_id, "defender", melee) == set()


# --- Cybernetica Datasmith and Kastelan Robots ---


def test_torrent_hits_automatically(monkeypatch):
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Torrent")
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # would miss
    weapon = _weapon(attacks="2", skill=0, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)])
    assert result.attack_rolls == []  # no hit rolls at all
    assert len(result.wound_rolls) == 2


def _kastelan_unit(datasmith_gun=None, kastelan_gun=None):
    datasmith = _model(
        name="Datasmith", keywords=[_keyword("CHARACTER"), _keyword("CYBERNETICA DATASMITH")]
    )
    kastelan = _model(name="Kastelan", keywords=[_keyword("KASTELAN ROBOTS")])
    return _unit(
        [
            _unit_model(datasmith, [datasmith_gun] if datasmith_gun else []),
            _unit_model(kastelan, [kastelan_gun] if kastelan_gun else []),
        ]
    )


def test_protector_protocol_adds_attacks_to_kastelan_ranged_weapons_only(monkeypatch):
    from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    protocol = admech.OPTIONS["Battle Protocols"]["Protector Protocol"]
    guns = []
    for i, name in ((1, "Pistol"), (2, "Blaster")):
        gun = _weapon(name=name, attacks="1", skill=3, weapon_type="ranged")
        gun.id = i
        guns.append(gun)
    attacker = _kastelan_unit(*guns)
    defender = _unit([_unit_model(_model(toughness=1, wounds=50, save=7), [])])
    result = combat.resolve_combat(
        attacker,
        defender,
        {1, 2},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        attacker_rules=list(protocol.rules),
    )
    assert {wr.name: len(wr.attack_rolls) for wr in result.weapon_results} == {
        "Pistol": 1,
        "Blaster": 3,
    }


def _shoot_kastelan_unit(monkeypatch, rolls, defender_rules, apply_precision=False):
    rolls = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=9, ap=-10, damage="1", weapon_type="ranged")
    weapon.id = 1
    if apply_precision:
        weapon.abilities = [_ability([_condition("always")], [_effect("precision")])]
    defender = _kastelan_unit()
    datasmith, kastelan = (um.model for um in defender.unit_models)
    datasmith.is_support = True  # targeted after the Kastelan
    datasmith.toughness, kastelan.toughness = 9, 9
    for model in (datasmith, kastelan):
        model.wounds, model.save = 10, 7
    attacker = _unit([_unit_model(_model(), [weapon])])
    return combat.resolve_combat(
        attacker,
        defender,
        {1},
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
        apply_precision=apply_precision,
        defender_rules=defender_rules,
    )


def test_aegis_protocol_gives_kastelans_plus_one_toughness(monkeypatch):
    from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech

    aegis = list(admech.OPTIONS["Battle Protocols"]["Aegis Protocol"].rules)
    # S9 vs T9 wounds on a 4; vs T10 it needs a 5.
    assert _shoot_kastelan_unit(monkeypatch, [6, 4, 1], []).total_damage == 1
    assert _shoot_kastelan_unit(monkeypatch, [6, 4, 1], aegis).total_damage == 0
    # The Datasmith isn't a Kastelan: still T9.
    hit_datasmith = _shoot_kastelan_unit(monkeypatch, [6, 4, 1], aegis, apply_precision=True)
    assert hit_datasmith.total_damage == 1


def test_robotic_bodyguard_gives_the_datasmith_fnp_4(monkeypatch):
    from app.seeds.factions.adeptus_mechanicus import datasheet_abilities as admech

    bodyguard = list(admech.RULES["Robotic Bodyguard"])
    # hit, wound, failed save, FNP 4 - only the Datasmith gets to roll it.
    on_datasmith = _shoot_kastelan_unit(
        monkeypatch, [6, 6, 1, 4], bodyguard, apply_precision=True
    )
    assert (on_datasmith.total_damage, on_datasmith.fnp_rolls) == (0, [4])
    on_kastelan = _shoot_kastelan_unit(monkeypatch, [6, 6, 1, 4], bodyguard)
    assert (on_kastelan.total_damage, on_kastelan.fnp_rolls) == (1, [])


# --- Imperial Knights: Knight Crusader ---


def _seeded_weapon_ability(name):
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == name)
    return _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])


@pytest.mark.parametrize("weapon_type,saved", [("ranged", True), ("melee", False)])
def test_ranged_only_invulnerable_save(monkeypatch, weapon_type, saved):
    # AP-4 vs a 3+ save needs a 7; a 5+ invulnerable (ranged only) saves a 5.
    rolls = iter([6, 6, 5])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(
        attacks="1",
        skill=3,
        strength=10,
        ap=-4,
        weapon_type=weapon_type,
        range=None if weapon_type == "melee" else 24,
    )
    knight = _model(toughness=1, wounds=10, save=3, invulnerable=5)
    knight.invulnerable_ranged_only = True
    result = _fire(weapon, [knight], in_engagement_range=weapon_type == "melee")
    assert result.total_damage == (0 if saved else 1)


@pytest.mark.parametrize("ability,bonus", [("Melta 2", 2), ("Melta 6", 6)])
def test_melta_2_and_6(monkeypatch, ability, bonus):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, damage="1", weapon_type="ranged")
    weapon.abilities = [_seeded_weapon_ability(ability)]
    target = [_model(toughness=1, wounds=20, save=7)]
    assert _fire(weapon, target, half_range=True).total_damage == 1 + bonus
    assert _fire(weapon, target).total_damage == 1


def test_rapid_fire_d6_plus_3(monkeypatch):
    # Every roll a 2: the D6+3 extra attacks come to 5.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 2)
    weapon = _weapon(attacks="1", skill=3, weapon_type="ranged")
    weapon.abilities = [_seeded_weapon_ability("Rapid Fire D6+3")]
    target = [_model(toughness=1, wounds=20, save=7)]
    assert len(_fire(weapon, target, half_range=True).attack_rolls) == 6
    assert len(_fire(weapon, target).attack_rolls) == 1


@pytest.mark.parametrize("keyword,wounded", [("FLY", True), ("INFANTRY", False)])
def test_anti_fly_2(monkeypatch, keyword, wounded):
    # S1 vs T10 needs a 6 to wound - unless Anti-Fly 2+ makes a 2 critical.
    rolls = iter([6, 2, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=1, ap=-10, weapon_type="ranged")
    weapon.abilities = [_seeded_weapon_ability("Anti-Fly 2+")]
    target = [_model(toughness=10, wounds=10, save=7, keywords=[_keyword(keyword)])]
    assert _fire(weapon, target).total_damage == (1 if wounded else 0)


@pytest.mark.parametrize("weapon_type,extra_hits", [("ranged", 1), ("melee", 0)])
def test_punishing_salvoes_gives_ranged_weapons_sustained_hits(
    monkeypatch, weapon_type, extra_hits
):
    from app.seeds.factions.imperial_knights import datasheet_abilities as knights

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    rules = list(knights.RULES["Punishing Salvoes"])
    weapon = _weapon(
        attacks="1",
        skill=3,
        strength=10,
        ap=-10,
        weapon_type=weapon_type,
        range=None if weapon_type == "melee" else 24,
    )
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=20, save=7)],
        in_engagement_range=weapon_type == "melee",
        attacker_rules=rules,
        attacker_positions={"remained_stationary"},
    )
    assert len(result.wound_rolls) == 1 + extra_hits


def test_punishing_salvoes_needs_remained_stationary(monkeypatch):
    from app.seeds.factions.imperial_knights import datasheet_abilities as knights

    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=20, save=7)],
        attacker_rules=list(knights.RULES["Punishing Salvoes"]),
    )
    assert len(result.wound_rolls) == 1


def test_remained_stationary_counts_as_moving_less_than_3_inches(monkeypatch):
    # [HEAVY]: +1 to hit, so a 2 hits at BS3.
    rolls = iter([2, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("moved_less_than_3")], [_effect("heavy")])]
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        attacker_positions={"remained_stationary"},
    )
    assert result.total_damage == 1


def test_crusaders_duty_gives_plus_one_to_hit_on_ranged_attacks(monkeypatch):
    from app.seeds.factions.imperial_knights import datasheet_abilities as knights

    option = knights.OPTIONS["Crusader's Duty (Bondsman)"]["Crusader's Duty"]
    rolls = iter([2, 6, 1])  # a 2 misses at BS3, hits at +1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=-10, weapon_type="ranged")
    target = [_model(toughness=1, wounds=10, save=7)]
    assert _fire(weapon, target, attacker_rules=list(option.rules)).total_damage == 1
    assert option.army_wide


# --- Necrons (critical hits on 5+, -1 Damage, +2 Strength, ignoring penalties) ---


def _scripted(monkeypatch, rolls):
    rolls = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))


def test_critical_hit_on_5_triggers_sustained_hits_and_always_hits(monkeypatch):
    # Hit roll 5 at BS6: a critical hit, so it hits and Sustained Hits adds one.
    _scripted(monkeypatch, [5, 6, 6, 1, 1])
    weapon = _weapon(attacks="1", skill=6, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("critical_hit")], [_effect("add_extra_hit")])]
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        attacker_rules=[Rule(conditions=("always",), effects=("critical_hit_5",))],
    )
    assert len(result.wound_rolls) == 2


def test_critical_hit_on_5_is_off_by_default(monkeypatch):
    _scripted(monkeypatch, [5])
    weapon = _weapon(attacks="1", skill=6, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("critical_hit")], [_effect("add_extra_hit")])]
    assert _fire(weapon, [_model(toughness=1, wounds=10, save=7)]).wound_rolls == []


@pytest.mark.parametrize("damage,expected", [("3", 2), ("1", 1)])
def test_minus_one_damage_has_a_minimum_of_1(monkeypatch, damage, expected):
    _scripted(monkeypatch, [6, 6, 1])
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage=damage, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        defender_rules=[
            Rule(conditions=("always",), effects=("minus_one_damage",), side="defender")
        ],
    )
    assert result.total_damage == expected


@pytest.mark.parametrize("effects,expected", [((), 0), (("plus_two_strength",), 1)])
def test_plus_two_strength(monkeypatch, effects, expected):
    # S4 vs T6 wounds on a 5+; at S6 a 4 wounds.
    _scripted(monkeypatch, [6, 4, 1])
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    rules = [Rule(conditions=("always",), effects=effects)] if effects else []
    result = _fire(weapon, [_model(toughness=6, wounds=10, save=7)], attacker_rules=rules)
    assert result.total_damage == expected


def test_ignore_hit_penalties_ignores_cover_and_minus_one_to_hit(monkeypatch):
    # A 3 at BS3, in cover and at -1 to hit: it misses, unless penalties are ignored.
    minus_one = Rule(conditions=("always",), effects=("minus_one_to_hit",), side="defender")
    ignore = Rule(conditions=("always",), effects=("ignore_hit_penalties",))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    target = [_model(toughness=1, wounds=10, save=7)]
    _scripted(monkeypatch, [3, 6, 1])
    assert _fire(weapon, target, in_cover=True, defender_rules=[minus_one]).total_damage == 0
    _scripted(monkeypatch, [3, 6, 1])
    assert (
        _fire(
            weapon, target, in_cover=True, defender_rules=[minus_one], attacker_rules=[ignore]
        ).total_damage
        == 1
    )


def test_ignore_wound_penalties_ignores_minus_one_to_wound(monkeypatch):
    # S4 vs T4 wounds on a 4+, 5+ at -1 to wound.
    minus_one = Rule(conditions=("always",), effects=("minus_one_to_wound",), side="defender")
    ignore = Rule(conditions=("always",), effects=("ignore_wound_penalties",))
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    target = [_model(toughness=4, wounds=10, save=7)]
    _scripted(monkeypatch, [6, 4, 1])
    assert _fire(weapon, target, defender_rules=[minus_one]).total_damage == 0
    _scripted(monkeypatch, [6, 4, 1])
    assert (
        _fire(weapon, target, defender_rules=[minus_one], attacker_rules=[ignore]).total_damage
        == 1
    )


@pytest.mark.parametrize("strength,expected", [(5, 0), (4, 1)])
def test_unyielding_forms_only_when_strength_exceeds_toughness(monkeypatch, strength, expected):
    # Wound roll 4 vs T4: S4 wounds on a 4+; S5 on a 3+, but 4+ at -1.
    # (S5 at -1 still wounds on a 4 - so roll a 3.)
    roll = 3 if strength == 5 else 4
    _scripted(monkeypatch, [6, roll, 1])
    rule = Rule(
        conditions=("strength_exceeds_toughness",), effects=("minus_one_to_wound",), side="defender"
    )
    weapon = _weapon(attacks="1", skill=3, strength=strength, ap=0, weapon_type="ranged")
    result = _fire(weapon, [_model(toughness=4, wounds=10, save=7)], defender_rules=[rule])
    assert result.total_damage == expected


def _fire_led(weapon, defender_models, led: bool, **flags):
    # As _fire, from a unit of a trooper (with the weapon) and, if led, a
    # CHARACTER leading it.
    weapon.id = 1
    models = [_unit_model(_model(), [weapon])]
    if led:
        models.append(_unit_model(_model(keywords=[_keyword("CHARACTER")]), []))
    attacker = _unit(models)
    defender = _unit([_unit_model(m, []) for m in defender_models])
    options = dict(
        in_engagement_range=False,
        visible=True,
        in_range=True,
        in_cover=False,
        half_range=False,
        moved_less_than_3=False,
        advanced=False,
    )
    options.update(flags)
    return combat.resolve_combat(attacker, defender, {weapon.id}, **options)


@pytest.mark.parametrize("led,expected", [(True, 1), (False, 0)])
def test_command_protocols_plus_one_to_hit_while_led(monkeypatch, led, expected):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [2, 6, 1])  # a 2 misses at BS3, hits at +1
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire_led(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        led,
        attacker_rules=list(necrons.RULES["Command Protocols"]),
    )
    assert result.total_damage == expected


@pytest.mark.parametrize("half_range,expected", [(True, 1), (False, 0)])
def test_conquering_tyrant_rerolls_hit_ones_within_half_range(monkeypatch, half_range, expected):
    _scripted(monkeypatch, [1, 6, 6, 1])
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        half_range=half_range,
        attacker_rules=[Rule(conditions=("half_range_attack",), effects=("reroll_hit_ones",))],
    )
    assert result.total_damage == expected


@pytest.mark.parametrize(
    "positions,expected",
    [({"below_half_strength"}, 1), ({"below_starting_strength"}, 0), (set(), 0)],
)
def test_spoor_of_frailty_wound_bonus_needs_below_half_strength(
    monkeypatch, positions, expected
):
    from app.seeds import stratagems as stratagem_seeds

    # S4 vs T4: a 3 wounds only at +1.
    _scripted(monkeypatch, [6, 3, 1])
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=4, wounds=10, save=7)],
        attacker_rules=stratagem_seeds.rules("The Spoor of Frailty"),
        defender_positions=positions,
    )
    assert result.total_damage == expected


def test_below_half_strength_also_counts_as_below_starting_strength():
    from app.combat_rules.conditions import CONDITIONS

    check = CONDITIONS["defender_below_starting_strength"]
    assert check({"defender_positions": {"below_half_strength"}})
    assert check({"defender_positions": {"below_starting_strength"}})
    assert not check({"defender_positions": set()})


@pytest.mark.parametrize(
    "keywords,positions,expected",
    [
        (["NECRONS"], {"cold_fervour_triggered"}, True),
        (["NECRONS"], set(), False),
        (["NECRONS", "DESTROYER CULT"], {"cold_fervour_triggered"}, False),
        (["NECRONS", "MONSTER"], {"cold_fervour_triggered"}, False),
    ],
)
def test_cold_fervour_spread_excludes_destroyer_cult_and_monsters(keywords, positions, expected):
    from app.combat_rules.conditions import CONDITIONS

    context = {"attacker_model_keywords": set(keywords), "attacker_positions": positions}
    assert CONDITIONS["cold_fervour_spread"](context) is expected


def test_enaegic_dermal_bond_protects_only_character_models(monkeypatch):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    # Every roll a 4: hits, wounds, fails a 7+ save - and passes a 4+ FNP.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    weapon = _weapon(attacks="2", skill=3, strength=10, ap=0, weapon_type="ranged")
    rules = list(necrons.RULES["Enaegic Dermal Bond"])
    trooper = _fire(weapon, [_model(toughness=1, wounds=10, save=7)], defender_rules=rules)
    character = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7, keywords=[_keyword("CHARACTER")])],
        defender_rules=rules,
    )
    assert trooper.total_damage == 2
    assert character.total_damage == 0


@pytest.mark.parametrize("name,expected", [("Tesla Sphere", 1), ("Particle Beam", 0)])
def test_cosmic_storm_improves_ap_of_tesla_sphere_weapons_only(monkeypatch, name, expected):
    # A 4+ save against AP-1 needs a 5; at AP-2 a 5 fails.
    _scripted(monkeypatch, [6, 6, 5])
    weapon = _weapon(name=name, attacks="1", skill=3, strength=10, ap=-1, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=4)],
        attacker_rules=[Rule(conditions=("tesla_sphere_weapon",), effects=("improve_ap",))],
    )
    assert result.total_damage == expected


@pytest.mark.parametrize("positions,expected", [({"target_unravelling"}, 1), (set(), 0)])
def test_cosmic_distortion_improves_ap_against_unravelling_targets(
    monkeypatch, positions, expected
):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [6, 6, 3])  # a 3+ save at AP0 holds; at AP-1 a 3 fails
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=3)],
        attacker_rules=list(necrons.RULES["Cosmic Distortion"]),
        attacker_positions=positions,
    )
    assert result.total_damage == expected


@pytest.mark.parametrize(
    "weapon_type,positions,expected",
    [("ranged", {"set_up_this_turn"}, 1), ("ranged", set(), 0), ("melee", {"set_up_this_turn"}, 0)],
)
def test_transdimensional_deployment_plus_one_to_hit_after_arriving(
    monkeypatch, weapon_type, positions, expected
):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [2, 6, 1])  # a 2 misses at BS3, hits at +1
    weapon = _weapon(
        attacks="1", skill=3, strength=10, ap=0, weapon_type=weapon_type,
        range=None if weapon_type == "melee" else 24,
    )
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        in_engagement_range=weapon_type == "melee",
        attacker_rules=list(necrons.RULES["Transdimensional Deployment"]),
        attacker_positions=positions,
    )
    assert result.total_damage == expected


def test_necrodermis_subtracts_one_damage(monkeypatch):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [6, 6, 1])
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="3", weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        defender_rules=list(necrons.RULES["Necrodermis"]),
    )
    assert result.total_damage == 2


@pytest.mark.parametrize("led,expected_wound_rolls", [(True, 2), (False, 0)])
def test_lokhust_lord_destroyer_cult_critical_hits_on_5_while_leading(
    monkeypatch, led, expected_wound_rolls
):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    # A 5 at BS6 only hits as a critical hit - then Sustained Hits adds one.
    _scripted(monkeypatch, [5, 6, 6, 1, 1])
    weapon = _weapon(attacks="1", skill=6, strength=10, ap=0, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("critical_hit")], [_effect("add_extra_hit")])]
    result = _fire_led(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        led,
        attacker_rules=list(necrons.RULES["Destroyer Cult"]),
    )
    assert len(result.wound_rolls) == expected_wound_rolls


@pytest.mark.parametrize(
    "keywords,positions,expected",
    [
        (["CHARACTER"], {"below_half_strength"}, 1),
        (["CHARACTER"], set(), 0),
        ([], {"below_half_strength"}, 0),
    ],
)
def test_driven_by_hatred_rerolls_for_the_character_against_below_half_strength(
    monkeypatch, keywords, positions, expected
):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [2, 6, 6, 1])  # a 2 misses at BS3; the re-roll hits
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(keywords=[_keyword(k) for k in keywords]), [weapon])])
    defender = _unit([_unit_model(_model(toughness=1, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker, defender, {1},
        in_engagement_range=False, visible=True, in_range=True, in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False,
        attacker_rules=list(necrons.RULES["Driven by Hatred"]),
        defender_positions=positions,
    )
    assert result.total_damage == expected


@pytest.mark.parametrize(
    "rolls,positions,expected",
    [
        ([1, 6, 6, 1], {"targeting_closest_eligible"}, 1),  # a 1 is re-rolled
        ([2, 6, 6, 1], {"targeting_closest_eligible"}, 0),  # a 2 isn't
        ([1, 6, 6, 1], set(), 0),
    ],
)
def test_hard_wired_for_destruction_rerolls_hit_ones_against_the_closest_target(
    monkeypatch, rolls, positions, expected
):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, rolls)
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        attacker_rules=list(necrons.RULES["Hard-wired for Destruction"]),
        attacker_positions=positions,
    )
    assert result.total_damage == expected


def test_hard_wired_for_destruction_rerolls_any_miss_against_a_target_on_an_objective(
    monkeypatch,
):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [2, 6, 6, 1])
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        attacker_rules=list(necrons.RULES["Hard-wired for Destruction"]),
        attacker_positions={"targeting_closest_eligible"},
        defender_positions={"in_range_of_objective"},
    )
    assert result.total_damage == 1


@pytest.mark.parametrize(
    "keywords,positions,expected",
    [
        (["DESTROYER CULT"], set(), True),
        ([], {"targeting_closest_eligible"}, True),
        ([], set(), False),
        (["DESTROYER CULT", "MONSTER"], set(), False),
    ],
)
def test_infectious_murder_madness_sustained_hits(keywords, positions, expected):
    from app.combat_rules.conditions import CONDITIONS

    context = {
        "step": "hit",
        "roll": 6,
        "attacker_model_keywords": set(keywords),
        "attacker_positions": positions,
    }
    assert CONDITIONS["murder_madness_critical_hit"](context) is expected


def test_nullstone_field_gives_feel_no_pain_against_mortal_wounds(monkeypatch):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    option = necrons.OPTIONS["Nullstone Field Generator (Aura)"]["Nullstone Field"]
    assert option.army_wide
    # Devastating Wounds: a 6 to wound allows no save - then a 5 passes FNP 5+.
    rolls = iter([6, 6, 5])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("critical_wound")], [_effect("no_save")])]
    result = _fire(
        weapon, [_model(toughness=1, wounds=10, save=2)], defender_rules=list(option.rules)
    )
    assert result.total_damage == 0


def _listed_unit(unit_id, faction_id, models):
    from app.models import FactionUnit

    unit = _unit([_unit_model(m, []) for m in models])
    unit.id = unit_id
    unit.faction_unit = FactionUnit(name="Unit", faction_id=faction_id)
    return unit


def test_prophet_of_destruction_reaches_other_units_in_the_army_list():
    from app.models import ArmyList, DatasheetAbility
    from app.routers.combat import _army_rules

    prophet = DatasheetAbility(name="Prophet of Destruction", description=None)
    ammentar = _listed_unit(1, 1, [_model(abilities=[prophet])])
    destroyers = _listed_unit(2, 1, [_model()])
    other_faction = _listed_unit(3, 2, [_model()])
    army_list = ArmyList(name="List", faction_id=1, points_limit=2000)
    army_list.units = [ammentar, destroyers, other_faction]
    for unit in army_list.units:
        unit.army_list = army_list

    assert [r.conditions for r in _army_rules(destroyers)] == [("prophet_of_destruction_target",)]
    assert _army_rules(ammentar) == []  # "one other friendly DESTROYER CULT unit"
    assert _army_rules(other_faction) == []


@pytest.mark.parametrize(
    "keywords,positions,expected",
    [
        (["DESTROYER CULT"], {"near_prophet_of_destruction"}, 1),
        (["DESTROYER CULT"], set(), 0),
        ([], {"near_prophet_of_destruction"}, 0),
    ],
)
def test_prophet_of_destruction_rerolls_wound_ones(monkeypatch, keywords, positions, expected):
    from app.seeds.factions.necrons import datasheet_abilities as necrons

    _scripted(monkeypatch, [6, 1, 6, 1])  # a wound roll of 1, re-rolled to a 6
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    weapon.id = 1
    attacker = _unit([_unit_model(_model(keywords=[_keyword(k) for k in keywords]), [weapon])])
    defender = _unit([_unit_model(_model(toughness=4, wounds=10, save=7), [])])
    result = combat.resolve_combat(
        attacker, defender, {1},
        in_engagement_range=False, visible=True, in_range=True, in_cover=False,
        half_range=False, moved_less_than_3=False, advanced=False,
        attacker_rules=list(necrons.ARMY_RULES["Prophet of Destruction"]),
        attacker_positions=positions,
    )
    assert result.total_damage == expected


def test_roll_dice_faces_returns_each_die():
    assert combat.roll_dice_faces("3") == (3, [])


def test_roll_dice_faces_adds_the_modifier(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 4)
    assert combat.roll_dice_faces("D6+2") == (6, [4])
    assert combat.roll_dice_faces("2D6") == (8, [4, 4])


def test_damage_rolls_are_recorded_for_random_damage_only(monkeypatch):
    # Hit 6, wound 6, save 1 (fails), damage die 3: D6+2 deals 5.
    _scripted(monkeypatch, [6, 6, 1, 3])
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="D6+2", weapon_type="ranged")
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)])
    assert result.weapon_results[0].damage == "D6+2"
    assert result.weapon_results[0].damage_rolls == [3]
    assert result.total_damage == 5

    _scripted(monkeypatch, [6, 6, 1])
    flat = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="2", weapon_type="ranged")
    assert _fire(flat, [_model(toughness=1, wounds=10, save=7)]).weapon_results[0].damage_rolls == []


def test_damage_is_not_rolled_for_a_saved_attack(monkeypatch):
    _scripted(monkeypatch, [6, 6, 6])  # the save passes
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, damage="D6", weapon_type="ranged")
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=3)])
    assert result.weapon_results[0].damage_rolls == []


def test_transcendent_cogitation_grants_both_imperatives():
    from app.seeds import stratagems as stratagem_seeds

    granted = stratagem_seeds.granted_options("Transcendent Cogitation")
    assert {"Protector Imperative", "Conqueror Imperative"} <= set(granted)
    assert stratagem_seeds.granted_options("Not a Stratagem") == []


@pytest.mark.parametrize("use_stratagem,expected_damage", [(True, 1), (False, 0)])
async def test_transcendent_cogitation_feeds_murderous_imperative(
    client: AsyncClient, session, monkeypatch, use_stratagem, expected_damage
):
    # Both Imperatives active: Murderous Imperative re-rolls a Hit roll of 1
    # (Protector) and a Wound roll of 1 (Conqueror).
    from app.seeds import conditions as conditions_seed
    from app.seeds import datasheet_abilities as datasheet_abilities_seed
    from app.seeds import effects as effects_seed
    from app.seeds import factions as factions_seed

    await factions_seed.seed(session)
    await factions_seed.seed_abilities(session)
    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)
    admech = next(
        f["id"] for f in (await client.get("/factions")).json() if f["name"] == "Adeptus Mechanicus"
    )
    doctrina = next(
        a["id"]
        for a in (await client.get("/faction-abilities")).json()
        if a["name"] == "Doctrina Imperatives"
    )
    murderous = next(
        a["id"]
        for a in (await client.get("/datasheet-abilities")).json()
        if a["name"] == "Murderous Imperative"
    )
    stratagem_id = (
        await client.post(
            "/stratagems", json={"name": "Transcendent Cogitation", "cp": 1, "is_core": True}
        )
    ).json()["id"]
    model_id = await _create_model(
        client, admech, faction_ability_ids=[doctrina], ability_ids=[murderous]
    )
    weapon_id = await _create_weapon(client, model_id, weapon_type="ranged")
    attacker = await _create_unit(
        client, await _create_faction_unit(client, admech, "Skitarii"), model_id, weapon_id
    )
    defender = await _create_unit(
        client,
        await _create_faction_unit(client, admech, "Targets"),
        await _create_model(client, admech),
    )

    # Hit 1 (re-rolled to 6), wound 1 (re-rolled to 6), save 1.
    rolls = iter([1, 6, 1, 6, 1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker,
            "defending_unit_id": defender,
            "selected_weapon_ids": [weapon_id],
            "stratagem_ids": [stratagem_id] if use_stratagem else [],
        },
    )
    assert response.status_code == 200
    assert response.json()["total_damage"] == expected_damage


@pytest.mark.parametrize("battle_shocked,expected", [(True, 1), (False, 0)])
def test_dread_doom_plus_one_to_wound_against_battle_shocked(monkeypatch, battle_shocked, expected):
    from app.seeds.factions.chaos_knights import abilities as chaos_knights

    _scripted(monkeypatch, [6, 3, 1])  # S4 vs T4: a 3 wounds only at +1
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=4, wounds=10, save=7)],
        attacker_rules=list(chaos_knights.OPTIONS["Harbingers of Dread"]["Doom"]),
        defender_battle_shocked=battle_shocked,
    )
    assert result.total_damage == expected


def test_dread_options_are_doom_attacking_and_darkness_defending():
    from app.seeds.factions.chaos_knights import abilities as chaos_knights

    options = chaos_knights.OPTIONS["Harbingers of Dread"]
    assert {r.side for r in options["Doom"]} == {"attacker"}
    assert {r.side for r in options["Darkness"]} == {"defender"}


# --- Chaos Knights ---


async def _seed_combat_catalog(session):
    from app.seeds import conditions as conditions_seed
    from app.seeds import datasheet_abilities as datasheet_abilities_seed
    from app.seeds import effects as effects_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await datasheet_abilities_seed.seed(session)


@pytest.mark.parametrize(
    "option,rolls,expected",
    [
        # Lethal Hits: a 6 to hit wounds automatically - then the save fails.
        ("Diabolic Power: Lethal Hits", [6, 1], 1),
        # Without it, that wound roll of 1 fails.
        (None, [6, 1, 1], 0),
    ],
)
async def test_malefic_surge_options_come_from_the_detachment_rule(
    client: AsyncClient, faction_id: int, session, monkeypatch, option, rolls, expected
):
    await _seed_combat_catalog(session)
    surge = next(
        a for a in (await client.get("/datasheet-abilities")).json() if a["name"] == "Malefic Surge"
    )
    assert "Diabolic Power: Lethal Hits" in surge["rule_options"]
    detachment_id = await _create_detachment(client, faction_id, "Infernal Lance")
    response = await client.post(
        "/detachment-rules",
        json={
            "detachment_id": detachment_id,
            "name": "Malefic Surge",
            "datasheet_ability_ids": [surge["id"]],
        },
    )
    assert response.status_code == 201
    attacker_id, defender_id, weapon_id = await _combat_units_in_list(
        client, faction_id, [detachment_id]
    )
    # The calculator is told the unit has the ability, so it offers its options.
    granted = await client.get("/combat/granted-abilities", params={"unit_id": attacker_id})
    assert surge["id"] in granted.json()

    rolls = iter(rolls)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker_id,
            "defending_unit_id": defender_id,
            "selected_weapon_ids": [weapon_id],
            "attacker_rule_options": [option] if option else [],
        },
    )
    assert response.status_code == 200
    assert response.json()["total_damage"] == expected


async def test_granted_abilities_are_only_the_lists_detachments(
    client: AsyncClient, faction_id: int, session
):
    await _seed_combat_catalog(session)
    attacker_id, _, _ = await _combat_units_in_list(client, faction_id, [])
    response = await client.get("/combat/granted-abilities", params={"unit_id": attacker_id})
    assert response.json() == []


@pytest.mark.parametrize("weapon_type,save_roll,expected", [("ranged", 4, 0), ("melee", 4, 1), ("melee", 5, 0)])
def test_veil_of_medrengard_invulnerable_saves(monkeypatch, weapon_type, save_roll, expected):
    from app.seeds.factions.chaos_knights import datasheet_abilities as chaos_knights

    _scripted(monkeypatch, [6, 6, save_roll])
    weapon = _weapon(
        attacks="1", skill=3, strength=10, ap=-6, weapon_type=weapon_type,
        range=None if weapon_type == "melee" else 24,
    )
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        in_engagement_range=weapon_type == "melee",
        defender_rules=list(chaos_knights.RULES["Veil of Medrengard"]),
    )
    assert result.total_damage == expected


@pytest.mark.parametrize("keywords,expected", [(["VEHICLE", "TITANIC"], 1), (["VEHICLE"], 0)])
def test_titanic_duel_rerolls_any_miss_against_titanic(monkeypatch, keywords, expected):
    from app.seeds import stratagems as stratagem_seeds

    _scripted(monkeypatch, [2, 6, 6, 1])  # a 2 misses at BS3; re-rolled only vs TITANIC
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7, keywords=[_keyword(k) for k in keywords])],
        attacker_rules=stratagem_seeds.rules("Titanic Duel"),
    )
    assert result.total_damage == expected


@pytest.mark.parametrize(
    "keywords,positions,expected",
    [
        (["WAR DOG"], {"marked_prey_target"}, True),
        (["WAR DOG"], set(), False),
        (["TITANIC"], {"marked_prey_target"}, False),
    ],
)
def test_marked_prey_sustained_hits_for_war_dogs(keywords, positions, expected):
    from app.combat_rules.conditions import CONDITIONS

    context = {
        "step": "hit",
        "roll": 6,
        "attacker_model_keywords": set(keywords),
        "attacker_positions": positions,
    }
    assert CONDITIONS["marked_prey_critical_hit"](context) is expected


@pytest.mark.parametrize(
    "options,charged,expected",
    [
        ({"Diabolic Power: Lethal Hits"}, True, True),
        ({"Diabolic Power: Sustained Hits 1"}, True, True),
        ({"Unnatural Fortitude: 5+ Invulnerable"}, True, False),
        ({"Diabolic Power: Lethal Hits"}, False, False),
    ],
)
def test_knight_diabolus_lance_while_using_diabolic_power(options, charged, expected):
    from app.combat_rules.conditions import CONDITIONS

    context = {"is_ranged": False, "charged": charged, "attacker_options": options}
    assert CONDITIONS["diabolic_power_charged_melee"](context) is expected


@pytest.mark.parametrize("half_range,expected", [(True, 5), (False, 1)])
def test_melta_4_adds_four_damage_within_half_range(monkeypatch, half_range, expected):
    _scripted(monkeypatch, [6, 6, 1, 1])  # hit, wound, failed save, D6 damage of 1
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Melta 4")
    weapon = _weapon(attacks="1", skill=3, strength=12, ap=-4, damage="D6", weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    result = _fire(weapon, [_model(toughness=1, wounds=20, save=7)], half_range=half_range)
    assert result.total_damage == expected


@pytest.mark.parametrize("damaged,expected", [(True, 0), (False, 1)])
def test_damaged_profile_minus_one_to_hit(monkeypatch, damaged, expected):
    rules = list(datasheet_ability_seeds.RULES["Damaged: 1-5 Wounds Remaining"])
    _scripted(monkeypatch, [3, 6, 1])  # a 3 hits at BS3, misses at -1
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    result = _fire(
        weapon,
        [_model(toughness=1, wounds=10, save=7)],
        attacker_rules=rules,
        attacker_damaged=damaged,
    )
    assert result.total_damage == expected


@pytest.mark.parametrize(
    "is_ranged,positions,expected",
    [(True, {"in_range_of_objective"}, True), (True, set(), False), (False, {"in_range_of_objective"}, False)],
)
def test_brigand_ignores_cover_against_targets_on_objectives(is_ranged, positions, expected):
    from app.combat_rules.conditions import CONDITIONS

    context = {"is_ranged": is_ranged, "defender_positions": positions}
    assert CONDITIONS["ranged_vs_objective_target"](context) is expected


def test_sustained_d3_adds_d3_hits_on_a_critical(monkeypatch):
    # Hit 6, then the D3 rolls a 2: three hits in all.
    _scripted(monkeypatch, [6, 2, 6, 6, 6, 1, 1, 1])
    entry = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Sustained D3")
    weapon = _weapon(attacks="1", skill=3, strength=10, ap=0, weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    result = _fire(weapon, [_model(toughness=1, wounds=20, save=7)])
    assert len(result.wound_rolls) == 3


@pytest.mark.parametrize("half_range,expected_wound_rolls", [(False, 2), (True, 0)])
def test_conversion_critical_hits_on_4_beyond_half_range(
    monkeypatch, half_range, expected_wound_rolls
):
    # A 4 at BS6 only hits as a critical hit - then Sustained Hits adds one.
    _scripted(monkeypatch, [4, 6, 6, 1, 1])
    conversion = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Conversion")
    weapon = _weapon(attacks="1", skill=6, strength=10, ap=0, weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in conversion[2]], [_effect(e) for e in conversion[3]]),
        _ability([_condition("critical_hit")], [_effect("add_extra_hit")]),
    ]
    result = _fire(weapon, [_model(toughness=1, wounds=20, save=7)], half_range=half_range)
    assert len(result.wound_rolls) == expected_wound_rolls


@pytest.mark.parametrize("positions,expected", [({"isolated_target"}, 1), (set(), 0)])
def test_stalker_plus_one_to_wound_against_an_isolated_target(monkeypatch, positions, expected):
    from app.seeds.factions.chaos_knights import datasheet_abilities as chaos_knights

    entry = next(e for e in chaos_knights.ENTRIES if e[0] == "Stalker")
    _scripted(monkeypatch, [6, 3, 1])  # S4 vs T4: a 3 wounds only at +1
    weapon = _weapon(attacks="1", skill=3, strength=4, ap=0, weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in entry[2]], [_effect(e) for e in entry[3]])
    ]
    result = _fire(
        weapon, [_model(toughness=4, wounds=10, save=7)], attacker_positions=positions
    )
    assert result.total_damage == expected


def test_anti_walker_2_condition_checks_wound_roll_and_keyword():
    from app.combat_rules.conditions import CONDITIONS

    check = CONDITIONS["anti_walker_2"]
    assert check({"step": "wound", "roll": 2, "defender_keywords": {"WALKER"}})
    assert not check({"step": "wound", "roll": 1, "defender_keywords": {"WALKER"}})
    assert not check({"step": "wound", "roll": 6, "defender_keywords": {"VEHICLE"}})
    assert not check({"step": "hit", "roll": 6, "defender_keywords": {"WALKER"}})


@pytest.mark.parametrize(
    "option,keyword,expected_damage",
    [("The Fires of Mars", "SKITARII", 1), (None, "SKITARII", 0), ("The Fires of Mars", None, 0)],
)
async def test_fires_of_mars_makes_both_imperatives_active_for_another_unit(
    client: AsyncClient, session, monkeypatch, option, keyword, expected_damage
):
    # Thulia Ghuld's Rod of the War Forge, elsewhere in the list: The Fires of
    # Mars makes both Imperatives active for the SKITARII (or THULIA GHULD)
    # unit it's chosen for, so Murderous Imperative re-rolls a Hit roll of 1
    # (Protector) and a Wound roll of 1 (Conqueror). Another unit can't be
    # chosen.
    from app.seeds import factions as factions_seed

    await factions_seed.seed(session)
    await factions_seed.seed_abilities(session)
    await _seed_combat_catalog(session)
    admech = next(
        f["id"] for f in (await client.get("/factions")).json() if f["name"] == "Adeptus Mechanicus"
    )
    abilities = {a["name"]: a["id"] for a in (await client.get("/datasheet-abilities")).json()}
    doctrina = next(
        a["id"]
        for a in (await client.get("/faction-abilities")).json()
        if a["name"] == "Doctrina Imperatives"
    )
    list_id = (
        await client.post(
            "/lists",
            json={"name": "Forge", "points_limit": 2000, "faction_id": admech, "detachment_ids": []},
        )
    ).json()["id"]

    async def listed_unit(model_id, weapon_ids=()):
        faction_unit = await _create_faction_unit(client, admech, f"Unit {model_id}")
        response = await client.post(
            "/units",
            json={
                "faction_unit_id": faction_unit,
                "points": 100,
                "list_id": list_id,
                "unit_models": [{"model_id": model_id, "weapon_ids": list(weapon_ids)}],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    thulia = await _create_model(client, admech, ability_ids=[abilities["Rod of the War Forge"]])
    await listed_unit(thulia)
    keyword_ids = []
    if keyword:
        keyword_ids = [(await client.post("/keywords", json={"name": keyword})).json()["id"]]
    skitarii = await _create_model(
        client,
        admech,
        faction_ability_ids=[doctrina],
        ability_ids=[abilities["Murderous Imperative"]],
        keyword_ids=keyword_ids,
    )
    weapon_id = await _create_weapon(client, skitarii, weapon_type="ranged")
    attacker = await listed_unit(skitarii, [weapon_id])
    defender = await _create_unit(
        client,
        await _create_faction_unit(client, admech, "Targets"),
        await _create_model(client, admech),
    )

    rolls = iter([1, 6, 1, 6, 1])  # hit 1 re-rolled to 6, wound 1 re-rolled to 6, save 1
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls, 1))
    response = await client.post(
        "/combat",
        json={
            "attacking_unit_id": attacker,
            "defending_unit_id": defender,
            "selected_weapon_ids": [weapon_id],
            "attacker_rule_options": [option] if option else [],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_damage"] == expected_damage


# --- snap shooting (e.g. Fire Overwatch) ---


def test_snap_shots_only_hit_on_an_unmodified_six(monkeypatch):
    rolls = iter([5, 6, 6, 6])  # hit rolls 5 (a miss, even at 2+) and 6; then wound, save
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))
    weapon = _weapon(attacks="2", skill=2, strength=10, ap=-10, weapon_type="ranged")
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)], snap_shots=True)
    assert result.attack_rolls == [5, 6]
    assert len(result.wound_rolls) == 1


def test_snap_shots_are_not_rerolled(monkeypatch):
    rolls = iter([5, 6, 6, 6])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(rolls))
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("always")], [_effect("reroll_failed_hits")])]
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)], snap_shots=True)
    assert (result.attack_rolls, result.attack_rerolls, result.wound_rolls) == ([5], [], [])


def test_snap_shots_trigger_no_hit_abilities(monkeypatch):
    # A 6 hits, but Sustained Hits adds nothing.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 6)
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [_ability([_condition("critical_hit")], [_effect("add_extra_hit")])]
    result = _fire(weapon, [_model(toughness=1, wounds=10, save=7)], snap_shots=True)
    assert (result.attack_rolls, len(result.wound_rolls)) == ([6], 1)


def test_snap_shots_keep_torrent_and_rapid_fire(monkeypatch):
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 1)  # would miss
    torrent = next(e for e in weapon_ability_seeds.ENTRIES if e[0] == "Torrent")
    weapon = _weapon(attacks="1", skill=2, strength=10, ap=-10, weapon_type="ranged")
    weapon.abilities = [
        _ability([_condition(c) for c in torrent[2]], [_effect(e) for e in torrent[3]]),
        _ability([_condition("within_half_range")], [_effect("add_extra_attack")]),
    ]
    result = _fire(
        weapon, [_model(toughness=1, wounds=10, save=7)], snap_shots=True, half_range=True
    )
    # Both attacks (its own and Rapid Fire's) hit automatically.
    assert (result.attack_rolls, len(result.wound_rolls)) == ([], 2)
