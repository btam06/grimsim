from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules import Rule, RuleOption
from app.combat_rules.conditions import (
    ALWAYS,
    RANGED_ATTACK,
    RILED_UP_RANGED_CRITICAL_HIT,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
    TARGET_HAS_CHARACTER,
    TARGET_LED_BY_CHARACTER,
)
from app.combat_rules.effects import (
    ASSAULT,
    ADD_EXTRA_HIT,
    BENEFIT_OF_COVER,
    DEADLY_DEMISE,
    FEEL_NO_PAIN_4,
    FEEL_NO_PAIN_5,
    MINUS_ONE_TO_WOUND,
    REROLL_FAILED_HITS,
)
from app.models import Condition, DatasheetAbility, Effect

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Reroll Failed Hits",
        "This unit may always re-roll failed hit rolls.",
        [ALWAYS],
        [REROLL_FAILED_HITS],
    ),
    (
        "Even More Dakka",
        "If this unit is riled up, this unit's ranged attacks have [SUSTAINED HITS 1].",
        [RILED_UP_RANGED_CRITICAL_HIT],
        [ADD_EXTRA_HIT],
    ),
    (
        "Electro-infusion",
        "While a CHARACTER model is leading this unit, each time an attack targets this unit, "
        "subtract 1 from the Wound roll.",
        [],
        [],
    ),
    (
        "Lord of the Machine Cult",
        "While this model is leading a unit, models in that unit have the Feel No Pain 5+ "
        "ability. If that unit has the ELECTRO-PRIESTS keyword, models in that unit have the "
        "Feel No Pain 4+ ability instead.",
        [],
        [],
    ),
    (
        # Descriptive only: a start-of-Fight-phase action outside the attack
        # sequence the combat engine resolves.
        "Data-spike",
        "At the start of the Fight phase, you can select one enemy VEHICLE unit within "
        "Engagement Range of this model's unit and roll one D6: on a 4+, that enemy unit "
        "suffers D6 mortal wounds and, until the end of the phase, the Weapon Skill "
        "characteristic of melee weapons equipped by that enemy unit is worsened by 1.",
        [],
        [],
    ),
    (
        # Only whether it explodes is resolved, not the D3 mortal wounds.
        "Deadly Demise D3",
        "When this model is destroyed, roll one D6. On a 6, each unit within 6\" of it "
        "suffers D3 mortal wounds.",
        [ALWAYS],
        [DEADLY_DEMISE],
    ),
    (
        # Only whether it explodes is resolved, not the mortal wound.
        "Deadly Demise 1",
        "When this model is destroyed, roll one D6. On a 6, each unit within 6\" of it "
        "suffers 1 mortal wound.",
        [ALWAYS],
        [DEADLY_DEMISE],
    ),
    (
        # Shooting after Advancing is modelled as every weapon having
        # [ASSAULT]; Falling Back and Desperate Escape aren't modelled.
        "Elevated Strider",
        "This unit is eligible to shoot in a turn in which it Fell Back or Advanced, and you "
        "can re-roll Desperate Escape tests taken for models in this unit.",
        [ALWAYS],
        [ASSAULT],
    ),
    (
        # Descriptive only: gaining CP is outside the combat engine.
        "Broad Spectrum Data-tether",
        "Each time you target this unit with a Stratagem, roll one D6: on a 5+, you gain 1CP.",
        [],
        [],
    ),
    (
        "Stealth",
        "Each time a ranged attack targets this unit, this unit has the Benefit of Cover.",
        [],
        [],
    ),
    (
        # Descriptive only: a deployment rule.
        "Infiltrators",
        "During deployment, this unit can be set up anywhere on the battlefield that is more "
        "than 9\" horizontally away from the enemy deployment zone and all enemy models.",
        [],
        [],
    ),
    (
        # Descriptive only: Battle-shock is outside the combat engine.
        "Voices in the Code",
        "At the start of the Fight phase, each enemy unit within Engagement Range of one or more "
        "units with this ability must take a Battle-shock test.",
        [],
        [],
    ),
    (
        # Descriptive only: Battle-shock/Leadership is outside the combat engine.
        "Neurostatic Interference (Aura)",
        "While an enemy unit is within 6\" of this unit, each time a Battle-shock or Leadership "
        "test is taken for that unit, subtract 1 from that test. While this unit is within 6\" "
        "of one or more friendly ADEPTUS MECHANICUS BATTLELINE units, subtract 2 from that test "
        "instead.",
        [],
        [],
    ),
    (
        # Its options are in OPTIONS below.
        "Canticles of the Omnissiah",
        "At the start of your Command phase, select one of the abilities in the Canticles of "
        "the Omnissiah section. Until the start of your next Command phase, this model has that "
        "ability.",
        [],
        [],
    ),
    (
        # Descriptive only: targeting restrictions aren't modelled.
        "Mechanicus Bodyguard",
        "While this model is within 3\" of one or more other friendly ADEPTUS MECHANICUS units, "
        "this model has the Lone Operative ability.",
        [],
        [],
    ),
    (
        # Descriptive only: healing between turns is outside the combat engine.
        "Self-repair Mechanisms",
        "At the start of your Command phase, this model regains up to D3 lost wounds.",
        [],
        [],
    ),
]

# Code-defined rules for abilities above, by name - for rules the
# conditions/effects stored on the row can't express, chiefly defensive ones
# ("each time an attack targets this unit"): a stored ability only ever
# modifies its own unit's attacks, while a Rule with side="defender" modifies
# attacks made against its unit. Applied to a unit if any of its models has the
# ability. Rows listed here are seeded with no conditions/effects of their own.
RULES = {
    # "While a CHARACTER model is leading this unit" - leader attachment isn't
    # modelled, so: while the unit contains a CHARACTER model.
    "Electro-infusion": [
        Rule(conditions=(TARGET_HAS_CHARACTER,), effects=(MINUS_ONE_TO_WOUND,), side="defender"),
    ],
    # "While this model is leading a unit": the unit has this CHARACTER plus
    # other models. FNP 4+ for ELECTRO-PRIESTS (the better of the two is kept).
    "Lord of the Machine Cult": [
        Rule(conditions=(TARGET_LED_BY_CHARACTER,), effects=(FEEL_NO_PAIN_5,), side="defender"),
        Rule(
            conditions=(TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,),
            effects=(FEEL_NO_PAIN_4,),
            side="defender",
        ),
    ],
    "Stealth": [
        Rule(conditions=(RANGED_ATTACK,), effects=(BENEFIT_OF_COVER,), side="defender"),
    ],
}


async def seed(session: AsyncSession) -> None:
    for name, description, condition_keywords, effect_keywords in ENTRIES:
        existing = (
            await session.execute(
                select(DatasheetAbility.id).where(DatasheetAbility.name == name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        conditions = (
            await session.execute(select(Condition).where(Condition.keyword.in_(condition_keywords)))
        ).scalars().all()
        effects = (
            await session.execute(select(Effect).where(Effect.keyword.in_(effect_keywords)))
        ).scalars().all()
        if len(conditions) != len(condition_keywords) or len(effects) != len(effect_keywords):
            continue  # conditions/effects haven't been seeded yet

        session.add(
            DatasheetAbility(
                name=name,
                description=description,
                conditions=list(conditions),
                effects=list(effects),
            )
        )
    await session.commit()


# Selectable options for abilities above: {ability name: {option name:
# RuleOption}}. Like faction ability options (e.g. Doctrina Imperatives), the
# active one is chosen per combat. Aura ranges ("within 6\"") aren't modelled:
# an army-wide option reaches every unit of the same faction in the army list.
OPTIONS = {
    "Canticles of the Omnissiah": {
        # The defending unit is taken to be the Machine Vengeance target, so
        # friendly units' attacks against it can re-roll the Hit roll.
        "Invocation of Machine Vengeance": RuleOption(
            rules=(
                Rule(conditions=(ALWAYS,), effects=(REROLL_FAILED_HITS,)),
            ),
            army_wide=True,
        ),
        # This model has BATTLELINE. (Binharic Courage, its OC/Battle-shock
        # aura, is outside the combat engine.)
        "Mantra of Discipline": RuleOption(keywords=("BATTLELINE",)),
        # Friendly units within 6" have Stealth.
        "Shroudpsalm": RuleOption(rules=tuple(RULES["Stealth"]), army_wide=True),
    },
}

# {option name: ability name} - which ability each option belongs to. Option
# names are unique across every ability (and every faction ability's options).
OPTION_OWNERS = {
    option_name: ability_name
    for ability_name, options in OPTIONS.items()
    for option_name in options
}
