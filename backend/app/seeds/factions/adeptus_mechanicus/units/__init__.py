from . import fulgurite_electro_priests, skitarii_rangers, tech_priest_dominus

# Unit (datasheet) names in this faction's roster.
NAMES = [
    "Belisarius Cawl",
    "Thulia Ghuld",
    "Skitarii Marshall",
    "Sydonian Skatros",
    "Tech-priest Dominus",
    "Tech-priest Manipulus",
    "Technoarchaelogist",
    "Cybernetica Datasmith",
    "Skitarii Rangers",
    "Skitarii Vanguard",
    "Skorpius Dunerider",
    "Archaeopter Fusilave",
    "Archaeopter Stratoraptor",
    "Corpuscarii Electro-priests",
    "Fulgurite Electro-priests",
    "Hastarii Exterminators",
    "Hastarii Fusiliers",
    "Kataphron Breachers",
    "Kataphron Destroyers",
    "Pteraxii Skystalkers",
    "Pteraxii Sterylizors",
    "Servitor Battleclade",
    "Sicarian Infiltrators",
    "Sicarial Ruststalkers",
    "Serberys Raiders",
    "Serberys Sulphurhounds",
    "Archaeopter Transvector",
    "Ironstrider Balistarii",
    "Kastelan Robots",
    "Onager Dunecrawler",
    "Sydonian Dragoons With Radium Jezzails",
    "Sydonian Dragoons With Taser Lances",
]

# Full datasheets (models, stats, weapons) for units above - see
# app/seeds/datasheets.py. Units without one are seeded by name only.
DATASHEETS = [fulgurite_electro_priests, skitarii_rangers, tech_priest_dominus]
