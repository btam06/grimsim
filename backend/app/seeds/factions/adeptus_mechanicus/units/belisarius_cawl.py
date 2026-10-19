from app.seeds.datasheets import ModelSpec, WeaponSpec

NAME = "Belisarius Cawl"

MODELS = [
    ModelSpec(
        name="Belisarius Cawl",
        movement=8,
        toughness=8,
        save=2,
        wounds=10,
        leadership=6,
        oc=3,
        invulnerable=4,
        keywords=(
            "MONSTER",
            "CHARACTER",
            "MOBILE",
            "EPIC HERO",
            "IMPERIUM",
            "TECH-PRIEST",
            "CULT MECHANICUS",
            "BELISARIUS CAWL",
        ),
        faction_abilities=("Doctrina Imperatives",),
        abilities=(
            "Canticles of the Omnissiah",
            "Mechanicus Bodyguard",
            "Self-repair Mechanisms",
        ),
        weapons=(
            WeaponSpec(
                name="Solar atomiser",
                weapon_type="ranged",
                range=18,
                attacks="3",
                skill=2,
                strength=14,
                ap=-4,
                damage="D6",
                abilities=("Melta 3",),
            ),
            WeaponSpec(
                name="Arc scourge",
                weapon_type="melee",
                attacks="4",
                skill=2,
                strength=5,
                ap=-1,
                damage="1",
                abilities=("Anti-Vehicle 4+", "Devastating Wounds", "Extra Attacks"),
            ),
            WeaponSpec(
                name="Cawl’s Omnissian axe",
                weapon_type="melee",
                attacks="4",
                skill=2,
                strength=8,
                ap=-2,
                damage="2",
            ),
            WeaponSpec(
                name="Mechadendrite hive",
                weapon_type="melee",
                attacks="2D6",
                skill=3,
                strength=4,
                ap=0,
                damage="1",
                abilities=("Extra Attacks",),
            ),
        ),
    ),
]
