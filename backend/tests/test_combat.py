import pytest
from httpx import AsyncClient

from app.models import (
    Condition,
    Effect,
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


def _model(**overrides) -> Model:
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
    return Model(**defaults)


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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=False, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=False, in_cover=False
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
        in_range=True, in_cover=False,
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, set(), in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        in_range=True, in_cover=False,
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
        in_range=True, in_cover=False,
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
        attacker, defender, {weapon.id}, in_engagement_range=False, visible=True, in_range=True, in_cover=False
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
    )
    assert result.attack_rolls == [3]
    assert result.wound_rolls == [3]  # ignored the cover penalty and hit


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
