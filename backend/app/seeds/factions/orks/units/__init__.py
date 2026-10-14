from . import big_mek_dakkarig, tankbustas

# Unit (datasheet) names in this faction's roster.
NAMES = [
    "Big Mek Dakkarig",
    "Tankbustas",
]

# Full datasheets (models, stats, weapons) for units above - see
# app/seeds/datasheets.py. Units without one are seeded by name only.
DATASHEETS = [big_mek_dakkarig, tankbustas]
