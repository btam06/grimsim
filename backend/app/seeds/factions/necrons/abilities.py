# (ability name, description)
ENTRIES = [
    (
        "Reanimation Protocols",
        "If your Army Faction is NECRONS, at the end of your Command phase, each friendly unit "
        "with this ability that is on the battlefield activates its Reanimation Protocols: "
        "that unit heals D3 wounds. Each reanimated wound restores a lost wound to a wounded "
        "model, or returns a destroyed model to the battlefield with 1 wound remaining.",
    ),
]

# How the calculator handles abilities above, where that needs saying:
# {ability name: note}.
CALCULATOR_NOTES = {
    "Reanimation Protocols": "Descriptive only: healing between attacks isn't modelled.",
}
