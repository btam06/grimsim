# Adeptus Mechanicus stratagems' code-defined parts, by stratagem name (see
# app/seeds/stratagems.py, which combines every faction's).

# Rule options a stratagem makes active for the unit it's used on, as if they'd
# been picked under the calculator's Faction Rules (only for a unit with the
# ability they belong to): {stratagem name: (option name, ...)}.
GRANTED_OPTIONS = {
    # "The Conqueror Imperative and Protector Imperative are both active."
    "Transcendent Cogitation": ("Protector Imperative", "Conqueror Imperative"),
}

# How stratagems with a game action carry it out, where that depends on the
# stratagem (see app/services/in_game/stratagem_actions.py): {stratagem name:
# config}.
ACTIONS = {
    # Consolidation moves of up to 6", provided the unit ends within range of
    # its Acquisition objective marker - not for a unit within 3" of an enemy.
    "Priority Reclamation": {
        "distance": 6.0,
        "ending_within": "Acquisition",
        "enemy_clear": 3.0,
    },
    # An objective marker within 24" of the TECH-PRIEST model is also an
    # Acquisition one.
    "Infoslave Skull": {
        "selection": "Acquisition",
        "model_keywords": ("TECH-PRIEST",),
        "within": 24.0,
    },
    # The unit must be within range of its Acquisition objective marker, and
    # the transport ADEPTUS MECHANICUS.
    "Reactive Safeguard": {
        "within": "Acquisition",
        "transport_keywords": ("ADEPTUS MECHANICUS",),
    },
}
