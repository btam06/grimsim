# In a game: what Space Marines detachment rules and enhancements (see
# app/data/factions/space_marines/) do beyond the combat abilities they grant.
# The factions package combines every faction's.

# How many more times than once a list that has taken a detachment can select
# an option of a once-per-battle army rule (abilities.py ONCE_PER_BATTLE):
# {detachment name: {option name: extra}} - Assault Mastery.
EXTRA_SELECTIONS = {"Assault Brethren": {"Assault Doctrine": 1}}

# What a detachment rule adds to the charge rolls of the units it reaches (see
# app/services/list_building/detachment_rules.py): {rule name: bonus} - Death
# Blow.
CHARGE_BONUSES = {"Death Blow": 1}

# Enhancements that change how the bearer's unit arrives from Strategic
# Reserves (see app/services/in_game/reinforcements.py), while the unit has a
# model with one of `keywords` (if given): it can arrive in its first movement
# phase (`first_round` - Corporeum Reliquary's ingress move), it has Deep
# Strike, and Rapid Ingress costs it `rapid_ingress_discount` CP less (Beacon
# Angelis).
ARRIVAL_ENHANCEMENTS = {
    "Corporeum Reliquary": {"first_round": True},
    "Beacon Angelis": {
        "keywords": ("KILL TEAM",),
        "deep_strike": True,
        "rapid_ingress_discount": 1,
    },
}
