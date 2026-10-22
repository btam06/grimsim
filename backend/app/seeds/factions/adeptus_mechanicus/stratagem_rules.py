# Adeptus Mechanicus stratagems' code-defined parts, by stratagem name (see
# app/seeds/stratagems.py, which combines every faction's).

# Rule options a stratagem makes active for the unit it's used on, as if they'd
# been picked under the calculator's Faction Rules (only for a unit with the
# ability they belong to): {stratagem name: (option name, ...)}.
GRANTED_OPTIONS = {
    # "The Conqueror Imperative and Protector Imperative are both active."
    "Transcendent Cogitation": ("Protector Imperative", "Conqueror Imperative"),
}
