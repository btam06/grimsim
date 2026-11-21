# What a datasheet's units can be made of (DatasheetLoadout, from its
# datasheets.json entry - see app/data/README.md): which models, how many of
# each, what each starts with, and the wargear options that change that.
#
# A model's loadout is compared by item: a weapon by its name without its
# profile ("Plasma caliver – standard" and "– supercharge" are one plasma
# caliver), or a piece of wargear by its name, each with how many the model
# has. A model's loadout is allowed if it can be reached from what it starts
# with by taking some of its options, each at most once (in any order: an
# option can only replace what the model still has), with each taken
# option's `requires` items still there at the end; and the unit's models
# between them take each option no more than its limit allows.

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DatasheetLoadout, FactionUnit, Model
from app.services.unit_points import item_name, norm


def key(name: str) -> str:
    return norm(item_name(name))


Items = Counter  # item key -> how many


def _strip(items: Counter) -> Counter:
    return +items


def _profile(weapon) -> tuple[str, str | None]:
    # One of a weapon's profiles: by name and type (electrostatic gauntlets'
    # ranged and melee profiles are one weapon; two heavy stubbers, the same
    # name and type, are two).
    return weapon.name, weapon.weapon_type


def items_of(weapons: list, wargear: list) -> Counter:
    # A model's items: a weapon's profiles count once; a weapon listed twice
    # as the same profile (two heavy stubbers) counts twice.
    by_item: dict[str, Counter] = {}
    for weapon in weapons:
        by_item.setdefault(key(weapon.name), Counter())[_profile(weapon)] += 1
    items = Counter({k: max(names.values()) for k, names in by_item.items()})
    for gear in wargear:
        items[key(gear.name)] += 1
    return items


def default_items(model: Model) -> Counter:
    return items_of([w for w in model.weapons if w.is_default], [])


def ids_for(model: Model, items: Counter) -> tuple[list[int], list[int]]:
    # The model's weapon and wargear ids for these items (every profile of a
    # weapon; the first n copies of one it has several of).
    weapon_ids: list[int] = []
    wargear_ids: list[int] = []
    for item, count in items.items():
        weapons: dict[tuple, list[int]] = {}
        for weapon in sorted(model.weapons, key=lambda w: w.id):
            if key(weapon.name) == item:
                weapons.setdefault(_profile(weapon), []).append(weapon.id)
        for ids in weapons.values():
            weapon_ids += ids[:count]
        if not weapons:
            gear = [g.id for g in sorted(model.wargear, key=lambda g: g.id) if key(g.name) == item]
            wargear_ids += gear[:count]
    return weapon_ids, wargear_ids


def _items(names: list[str]) -> Counter:
    return Counter(key(n) for n in names)


@dataclass
class Part:
    model: Model
    min: int
    max: int
    equipped: Counter


@dataclass
class Option:
    index: int
    model: Model
    choices: list[Counter]
    choice_names: list[list[str]]
    replace: Counter
    replace_names: list[str]
    requires: Counter
    max: int | None
    per: int | None

    def limit(self, size: int) -> int | None:
        # How many models in a unit of `size` models can take it.
        if self.max is None:
            return None
        return self.max * (size // self.per) if self.per else self.max

    @property
    def label(self) -> str:
        choices = " / ".join(" and ".join(c) for c in self.choice_names)
        if self.replace_names:
            return f"{' and '.join(self.replace_names)} → {choices}"
        return f"+ {choices}"


@dataclass
class Loadout:
    models: list[Model]
    parts: list[Part] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)

    def part(self, model_id: int) -> Part | None:
        return next((p for p in self.parts if p.model.id == model_id), None)

    def sergeant_first(self) -> list[Part]:
        # Its composition, the models a unit has at most one of (its
        # sergeant) first when it has others.
        if len(self.parts) < 2:
            return list(self.parts)
        return sorted(self.parts, key=lambda p: p.max != 1)

    @property
    def auto(self) -> bool:
        # Nothing to decide: one model, exactly one of it, no options.
        return (
            len(self.parts) == 1 and self.parts[0].min == self.parts[0].max == 1
            and not self.options
        )


async def loadout_for(session: AsyncSession, faction_unit_id: int) -> Loadout | None:
    # The datasheet's loadout, its models looked up (by name, in the
    # datasheet's faction); None if the data has nothing on it.
    row = await session.get(DatasheetLoadout, faction_unit_id)
    if row is None:
        return None
    faction_id = await session.scalar(
        select(FactionUnit.faction_id).where(FactionUnit.id == faction_unit_id)
    )
    found = {
        m.name: m
        for m in (
            await session.execute(
                select(Model)
                .options(selectinload(Model.weapons), selectinload(Model.wargear))
                .where(Model.faction_id == faction_id, Model.name.in_(row.models))
            )
        ).scalars()
    }
    loadout = Loadout(models=[found[n] for n in row.models if n in found])
    for part in row.composition:
        model = found.get(part["model"])
        if model is None:
            continue
        equipped = part.get("equipped")
        loadout.parts.append(Part(
            model=model, min=part["min"], max=part["max"],
            equipped=default_items(model) if equipped is None else _items(equipped),
        ))
    for index, option in enumerate(row.options):
        model = found.get(option["model"])
        if model is None:
            continue
        loadout.options.append(Option(
            index=index, model=model,
            choices=[_items(c) for c in option["with"]], choice_names=option["with"],
            replace=_items(option.get("replace", [])),
            replace_names=option.get("replace", []),
            requires=_items(option.get("requires", [])),
            max=option.get("max"), per=option.get("per"),
        ))
    return loadout


def ways(start: Counter, options: list[Option], target: Counter) -> list[frozenset[int]]:
    # Each set of options (by index) that takes a model from `start` to
    # `target`.
    start, target = _strip(start), _strip(target)
    found: set[frozenset[int]] = set()
    seen: set = set()

    def walk(current: Counter, used: frozenset[int]) -> None:
        state = (frozenset(current.items()), used)
        if state in seen:
            return
        seen.add(state)
        if current == target and all(
            not (o.requires - current) for o in options if o.index in used
        ):
            found.add(used)
        for option in options:
            if option.index in used or option.replace - current:
                continue
            for choice in option.choices:
                walk(_strip(current - option.replace + choice), used | {option.index})

    walk(start, frozenset())
    return sorted(found, key=len)


@dataclass
class Variant:
    # One way a model can be equipped: the options it took, its items, and
    # which choice of each of the model's option groups it is (`picks`).
    model: Model
    used: frozenset[int]
    items: Counter
    name: str
    picks: list[int] = field(default_factory=list)


@dataclass
class GroupChoice:
    used: frozenset[int]
    items: Counter
    name: str


@dataclass
class Group:
    # Options of a model that depend on each other (one replaces or requires
    # what another replaces or adds), picked between together; a model's
    # groups are picked independently.
    model: Model
    options: list[int]
    name: str
    choices: list[GroupChoice]


# (More than this many ways to equip one model aren't listed.)
MAX_VARIANTS = 200


def _display_names(model: Model) -> dict[str, str]:
    names = {key(w.name): item_name(w.name) for w in model.weapons}
    names.update({key(g.name): g.name for g in model.wargear})
    return names


def _keys(counter: Counter) -> set[str]:
    return set(_strip(counter))


def _depends(a: Option, b: Option) -> bool:
    # Whether `a` needs what `b` replaces or adds.
    needs = _keys(a.replace) | _keys(a.requires)
    touched = _keys(b.replace).union(*(_keys(c) for c in b.choices))
    return bool(needs & touched)


def option_groups(options: list[Option]) -> list[list[Option]]:
    # The options split into groups that don't depend on each other, in
    # the order the data lists them.
    groups: list[list[Option]] = []
    for option in options:
        joined = [g for g in groups if any(_depends(option, o) or _depends(o, option) for o in g)]
        merged = [o for g in joined for o in g] + [option]
        groups = [g for g in groups if g not in joined]
        groups.append(sorted(merged, key=lambda o: o.index))
    return sorted(groups, key=lambda g: g[0].index)


def _walk(start: Counter, options: list[Option]) -> dict[frozenset, frozenset[int]]:
    # Every item set reachable from `start`, with the fewest options that
    # reach it.
    found: dict[frozenset, frozenset[int]] = {}
    seen: set = set()

    def walk(current: Counter, used: frozenset[int]) -> None:
        state = (frozenset(current.items()), used)
        if state in seen or len(found) >= MAX_VARIANTS:
            return
        seen.add(state)
        items = frozenset(current.items())
        if all(not (o.requires - current) for o in options if o.index in used):
            if items not in found or len(used) < len(found[items]):
                found[items] = used
        for option in options:
            if option.index in used or option.replace - current:
                continue
            for choice in option.choices:
                walk(_strip(current - option.replace + choice), used | {option.index})

    walk(start, frozenset())
    return found


def _label(start: Counter, items: Counter, names: dict[str, str]) -> str:
    # What a loadout has that it doesn't start with ("" for as equipped).
    extra = items - start
    label = ", ".join(
        (f"{n} {names.get(k, k)}" if n > 1 else names.get(k, k))
        for k, n in sorted(extra.items(), key=lambda kv: names.get(kv[0], kv[0]))
    )
    if not label and start - items:
        label = "without " + ", ".join(names.get(k, k) for k in start - items)
    return label


def groups(part: Part, options: list[Option]) -> list[Group]:
    # The model's option groups, each with its choices: as equipped first
    # (named by what its options replace, or "None" when they only add),
    # then by how many options they take.
    start = _strip(part.equipped)
    names = _display_names(part.model)
    out = []
    for group in option_groups(options):
        replaced = sorted(set().union(*(_keys(o.replace) for o in group)) & set(start))
        added = sorted(set().union(*(_keys(c) for o in group for c in o.choices)) - set(start))
        title = ", ".join(names.get(k, k) for k in (replaced or added))
        choices = [
            GroupChoice(
                used=used, items=Counter(dict(items)),
                name=_label(start, Counter(dict(items)), names)
                or (title if replaced else "None"),
            )
            for items, used in _walk(start, group).items()
        ]
        choices.sort(key=lambda c: (len(c.used), c.name))
        out.append(Group(model=part.model, options=[o.index for o in group], name=title, choices=choices))
    return out


def variants(part: Part, options: list[Option]) -> list[Variant]:
    # Every loadout the model can have - a choice from each of its option
    # groups; as equipped first, then by how many options it takes - each
    # named by what it has that it doesn't start with (or just the model's
    # name, if it has no options).
    start = _strip(part.equipped)
    names = _display_names(part.model)
    found: dict[frozenset, Variant] = {}
    combos: list[tuple[list[int], frozenset[int], dict]] = [([], frozenset(), dict(start))]
    for group in groups(part, options):
        combos = [
            (picks + [i], used | choice.used, {
                k: items.get(k, 0) + choice.items.get(k, 0) - start.get(k, 0)
                for k in set(items) | set(choice.items)
            })
            for picks, used, items in combos
            for i, choice in enumerate(group.choices)
        ][:MAX_VARIANTS]
    for picks, used, items in combos:
        items = _strip(Counter(items))
        frozen = frozenset(items.items())
        if frozen in found and len(found[frozen].used) <= len(used):
            continue
        found[frozen] = Variant(
            model=part.model, used=used, items=items, picks=picks,
            name=f"{part.model.name} — {_label(start, items, names) or 'as equipped'}",
        )
    out = list(found.values())
    if len(out) == 1:
        # (No other way to equip it: just its name.)
        out[0].name = part.model.name
    return sorted(out, key=lambda v: (len(v.used), v.name))


def check(loadout: Loadout, members: list[tuple[Model, list, list]]) -> str | None:
    # Why a unit of these (model, weapons, wargear) isn't one this datasheet
    # allows, or None.
    allowed = {m.id for m in loadout.models}
    for model, _, _ in members:
        if allowed and model.id not in allowed:
            return f"{model.name} isn't one of this datasheet's models"
    if not loadout.parts:
        return None

    counts = Counter(model.id for model, _, _ in members)
    for model_id in counts:
        if loadout.part(model_id) is None:
            model = next(m for m, _, _ in members if m.id == model_id)
            return f"{model.name} isn't in this datasheet's unit composition"
    for part in loadout.parts:
        n = counts.get(part.model.id, 0)
        if not part.min <= n <= part.max:
            wanted = str(part.min) if part.min == part.max else f"{part.min}-{part.max}"
            return f"the unit needs {wanted} {part.model.name} (has {n})"

    size = len(members)
    per_model: list[list[frozenset[int]]] = []
    for model, weapons, wargear in members:
        mine = [o for o in loadout.options if o.model.id == model.id]
        found = ways(loadout.part(model.id).equipped, mine, items_of(weapons, wargear))
        if not found:
            return f"{model.name}: that wargear isn't one of its options"
        per_model.append(found)

    limits = {o.index: o.limit(size) for o in loadout.options}
    taken: Counter = Counter()

    def assign(i: int) -> bool:
        if i == len(per_model):
            return True
        for used in per_model[i]:
            if all(limits[o] is None or taken[o] < limits[o] for o in used):
                taken.update(used)
                if assign(i + 1):
                    return True
                taken.subtract(used)
        return False

    if assign(0):
        return None
    # (An option the models must take more often than it can be.)
    for option in loadout.options:
        limit = limits[option.index]
        needing = sum(1 for found in per_model if all(option.index in w for w in found))
        if limit is not None and needing > limit:
            return f"only {limit} {option.model.name} can take {option.label}"
    return "too many models have taken the same wargear options"
