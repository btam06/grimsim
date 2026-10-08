import pytest
from httpx import AsyncClient

from app.models import (
    Condition,
    DatasheetAbility,
    Effect,
    Keyword,
    Model,
    Unit,
    UnitModel,
    Wargear,
    WargearAbility,
    Weapon,
    WeaponAbility,
)
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=False, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=False, in_cover=False, half_range=False, moved_less_than_3=False
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
        in_range=True, in_cover=False, half_range=False, moved_less_than_3=False,
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, set(), in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        in_range=True, in_cover=False, half_range=False, moved_less_than_3=False,
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
        in_range=True, in_cover=False, half_range=False, moved_less_than_3=False,
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
    rolls = iter([6, 6, 1, 6, 6, 1, 2])  # attack1: hit,wound,save(fail); attack2: hit,wound,save(fail),fnp(fail)
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
    )
    assert result.save_rolls == [1, 1]
    # attack 1's point kills model 1 outright (no fnp to roll); attack 2's point
    # fails model 2's own fnp roll and so also lands -> 2 points of damage total.
    assert result.total_damage == 2
    assert result.models_destroyed == 1
    assert result.defending_models_remaining == 1


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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        half_range=False, moved_less_than_3=False,
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
        half_range=False, moved_less_than_3=False,
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
        half_range=False, moved_less_than_3=False,
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
        half_range=False, moved_less_than_3=False,
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        moved_less_than_3=True,
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
        moved_less_than_3=False,
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
        moved_less_than_3=False,
    )
    assert result.attack_rolls == [2, 6]  # both the failed roll and the reroll are recorded
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
        moved_less_than_3=False,
    )
    assert result.attack_rolls == [6]  # no reroll needed
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
        moved_less_than_3=False,
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
        moved_less_than_3=False,
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
        moved_less_than_3=False,
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
        moved_less_than_3=False,
    )
    assert result.attack_rolls == [3]
    assert result.total_damage == 0  # no bonus for a ranged weapon


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
        moved_less_than_3=False,
    )
    assert result.attack_rolls == [2, 6]  # both the failed roll and the reroll are recorded
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
        moved_less_than_3=False,
    )
    assert result.attack_rolls == [2]  # no reroll
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
        moved_less_than_3=False,
    )
    assert result.attack_rolls == [2, 6]
    assert result.total_damage == 1


# --- precision / rapid fire / hazardous / ignore cover (unit) ---


def test_precision_weapon_ability_has_no_conditions_or_effects():
    # "Precision" is seeded with empty condition/effect lists - confirm that an
    # ability with nothing attached simply never triggers anything.
    precision = _ability([], [])
    weapon = _weapon(attacks="1", skill=2)
    weapon.id = 1
    weapon.abilities = [precision]
    state: dict = {}
    combat._apply_triggered_effects([precision], {"step": "hit", "roll": 6}, state, combat.deque())
    assert state == {}


def test_within_half_range_condition_checks_pre_weapon_step_and_flag():
    assert combat.CONDITIONS["within_half_range"]({"step": "pre_weapon", "half_range": True}) is True
    assert combat.CONDITIONS["within_half_range"]({"step": "pre_weapon", "half_range": False}) is False
    assert combat.CONDITIONS["within_half_range"]({"step": "hit", "half_range": True}) is False


def test_resolve_combat_rapid_fire_1_adds_an_extra_attack_within_half_range(monkeypatch):
    # RAPID FIRE 1: within_half_range -> add_extra_attack. The extra attack is
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
        half_range=True, moved_less_than_3=False,
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
        half_range=False, moved_less_than_3=False,
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
        half_range=True, moved_less_than_3=False,
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False, half_range=False, moved_less_than_3=False
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
        half_range=False, moved_less_than_3=False,
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
        half_range=False, moved_less_than_3=False,
    )
    assert result.hazardous_models_destroyed == 1


def test_resolve_combat_ignore_cover_unit_wargear_applies_to_every_model_in_the_unit(
    monkeypatch,
):
    # The "Ignore Cover (Unit)" ability is equipped on model A's wargear, but
    # it must still negate the cover penalty for model B's weapon too.
    monkeypatch.setattr(combat.random, "randint", lambda a, b: 3)

    ignore_cover_unit = _wargear_ability([_condition("always")], [_effect("ignore_cover_unit")])
    gear = _wargear([ignore_cover_unit])
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
        half_range=False, moved_less_than_3=False,
    )
    # Both weapons hit on a roll of 3 (unworsened skill 3), proving the unit-wide
    # effect applied to model B's weapon even though the wargear is on model A.
    assert result.attack_rolls == [3, 3]
    assert result.wound_rolls == [3, 3]


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
        half_range=False, moved_less_than_3=False,
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

    ability_id = (
        await client.get("/weapon-abilities")
    ).json()[0]["id"]

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
    from app.seeds import keywords as keywords_seed
    from app.seeds import weapon_abilities as weapon_abilities_seed

    await conditions_seed.seed(session)
    await effects_seed.seed(session)
    await keywords_seed.seed(session)
    await weapon_abilities_seed.seed(session)

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
    assert body["attack_rolls"] == [2, 6]
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
    rapid_fire_id = next(a["id"] for a in abilities if a["name"] == "RAPID FIRE 1")

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
