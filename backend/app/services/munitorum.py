# The Munitorum Field Manual (https://mfm.warhammer-community.com): GW's
# points values for every faction, as a web app - an index page linking a
# page per faction (/en/<slug>). Each page is server-rendered by Next.js,
# and its content is in the page's React Server Components payload (the
# `self.__next_f.push([1, "..."])` scripts): rows of `<id>:<json>`, where an
# element is ["$", tag, key, props] and "$L<id>" / "$<id>" point at another
# row. Unit names and their points are in rows of their own, so the payload
# is resolved into one tree first, then read by the markup's classes.
#
# A unit's entry: a header (its name, uppercase), then sections - each a
# heading and a list of "<label> ... <n> pts" lines:
#   "YOUR UNIT COSTS" / "YOUR 1ST TO 2ND UNITS COST" / "YOUR 3RD + UNIT COSTS"
#       ("N model(s)" lines: the cost at that starting strength, for that
#       copy of the unit in an army on - see unit_points.py)
#   "WARGEAR OPTIONS" ("per <item>" lines: on top, per item taken)
#   "LEADER" / "SUPPORT" / "BODYGUARD UNITS UPDATED" (not points: ignored)
#
# Fetching needs only the standard library. Run as a script to fetch, parse
# and upsert every faction (see `main`).

from __future__ import annotations

import html
import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field

BASE = "https://mfm.warhammer-community.com"
LOCALE = "en"
# (A browser-like agent: the site serves the same page either way, but some
# CDNs turn away a bare urllib one.)
USER_AGENT = "Mozilla/5.0 (compatible; grimsim points import)"


@dataclass
class UnitCost:
    # The unit's cost at `models` starting strength, for its `from_copy`th
    # copy in an army on (1: every copy, unless a later tier says otherwise).
    # `composition`: the models by name, when the line names them ("1 Sword
    # Brother, 4 Neophytes, 5 Initiates" - `models` their total) rather than
    # "N models"; two lines can have the same total (e.g. 6 Wolf Guard
    # Headtakers, or 3 and 3 Hunting Wolves).
    from_copy: int
    models: int
    points: int
    composition: list[tuple[int, str]] | None = None


@dataclass
class WargearCost:
    # Per item taken, on top of the unit's cost - a weapon, a piece of
    # wargear, or (a "+ 1 <model>" line under a unit's costs) a model added.
    name: str
    points: int


@dataclass
class UnitEntry:
    name: str
    costs: list[UnitCost] = field(default_factory=list)
    wargear: list[WargearCost] = field(default_factory=list)


@dataclass
class FactionPage:
    slug: str
    title: str
    version: str | None
    units: list[UnitEntry]
    # Lines that weren't understood ("<section>: <label> <points>"), to check.
    unparsed: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def fetch(url: str, timeout: float = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def faction_slugs(index_html: str, locale: str = LOCALE) -> list[str]:
    # The faction pages the index links to, in its order.
    found = []
    for slug in re.findall(rf'href="/{locale}/([a-z0-9-]+)"', index_html):
        if slug not in found:
            found.append(slug)
    return found


# --- the RSC payload ---------------------------------------------------------


def payload_rows(page_html: str) -> dict[str, object]:
    # The payload's rows, by id: each JSON (rows that aren't - module
    # references, text chunks - are left out).
    stream = ""
    for chunk in re.findall(r"self\.__next_f\.push\((\[.*?\])\)</script>", page_html, flags=re.S):
        try:
            entry = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if len(entry) > 1 and isinstance(entry[1], str):
            stream += entry[1]
    rows: dict[str, object] = {}
    for match in re.finditer(r"(?m)^([0-9a-f]+):(.*)$", stream):
        body = match.group(2)
        if body[:1] not in ("[", "{", '"'):
            continue
        try:
            rows[match.group(1)] = json.loads(body)
        except json.JSONDecodeError:
            continue
    return rows


@dataclass
class Node:
    tag: str
    key: str | None
    cls: str
    children: list

    def text(self) -> str:
        return text_of(self.children)


_REF = re.compile(r"\$L?([0-9a-f]+)")


def resolve(value, rows: dict, seen: frozenset = frozenset()):
    # The value with each row reference replaced by its row, and each element
    # as a Node (its children always a list).
    if isinstance(value, str):
        match = _REF.fullmatch(value)
        if match and match.group(1) in rows and match.group(1) not in seen:
            ref = match.group(1)
            return resolve(rows[ref], rows, seen | {ref})
        return value
    if isinstance(value, list):
        if len(value) == 4 and value[0] == "$" and isinstance(value[3], dict):
            props = value[3]
            children = resolve(props.get("children"), rows, seen)
            if not isinstance(children, list):
                children = [] if children is None else [children]
            return Node(
                tag=str(value[1]), key=value[2], cls=props.get("className") or "",
                children=children,
            )
        return [resolve(v, rows, seen) for v in value]
    return value


def text_of(value) -> str:
    if isinstance(value, str):
        return "" if value.startswith("$") else html.unescape(value)
    if isinstance(value, Node):
        return value.text()
    if isinstance(value, list):
        return " ".join(t for t in (text_of(v) for v in value) if t.strip()).strip()
    return ""


def walk(value):
    if isinstance(value, Node):
        yield value
        for child in value.children:
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


# --- a faction page ----------------------------------------------------------

_POINTS = re.compile(r"^(\d[\d,]*)\s*pts$", re.I)
_MODELS = re.compile(r"^(\d+)\s+models?$", re.I)
_PART = re.compile(r"^(\d+)\s+(\D.*)$")
_EXTRA = re.compile(r"^\+\s*(\d+)\s+(\D.*)$")
_FROM_COPY = re.compile(r"(\d+)(?:ST|ND|RD|TH)\s*\+", re.I)
_VERSION = re.compile(r"^v\d+(?:\.\d+)*$")


def _is_unit(node: Node) -> bool:
    # A unit's entry: a card whose first child is its name's header.
    if node.tag != "div" or "print:break-inside-avoid-page" not in node.cls:
        return False
    first = next((c for c in node.children if isinstance(c, Node)), None)
    return first is not None and "bg-slate-500" in first.cls and "text-xl" in first.cls


def _sections(unit: Node):
    # Each section of a unit's entry: (heading, [(label, points text)]).
    for node in walk(unit.children[1:]):
        if node.tag != "div" or "space-y-1" not in node.cls:
            continue
        heading = None
        lines = []
        for child in walk(node.children):
            if heading is None and child.tag in ("div", "span") and (
                "bg-slate-200" in child.cls or "justify-between" in child.cls
            ):
                heading = child.text()
            elif child.tag == "li":
                spans = [c for c in child.children if isinstance(c, Node) and c.tag == "span"]
                if len(spans) >= 2:
                    lines.append((spans[0].text(), spans[-1].text()))
                else:
                    lines.append((child.text(), ""))
        if heading:
            yield heading, lines


def clean(name: str) -> str:
    # Typographic apostrophes as plain ones, spaces collapsed.
    return re.sub(r"\s+", " ", name.replace("\u2019", "'").replace("\u2018", "'")).strip()


def points_of(text: str) -> int | None:
    match = _POINTS.match(text.strip())
    return int(match.group(1).replace(",", "")) if match else None


def composition_of(label: str) -> list[tuple[int, str]] | None:
    # "1 Sword Brother, 4 Neophytes" -> [(1, "Sword Brother"), (4, "Neophytes")].
    parts = []
    for part in label.split(","):
        match = _PART.match(part.strip())
        if not match:
            return None
        parts.append((int(match.group(1)), clean(match.group(2))))
    return parts or None


def from_copy(heading: str) -> int:
    # "YOUR 3RD + UNIT COSTS" -> 3; "YOUR UNIT COSTS", "YOUR 1ST TO 2ND
    # UNITS COST" -> 1.
    match = _FROM_COPY.search(heading)
    return int(match.group(1)) if match else 1


def parse_unit(unit: Node, unparsed: list[str]) -> UnitEntry:
    header = next(c for c in unit.children if isinstance(c, Node))
    entry = UnitEntry(name=clean(header.text()))
    for heading, lines in _sections(unit):
        upper = heading.upper()
        if "COST" in upper:
            copy = from_copy(upper)
            for label, points in lines:
                label, cost = clean(label), points_of(points)
                models, extra = _MODELS.match(label), _EXTRA.match(label)
                parts = None if (models or extra) else composition_of(label)
                if cost is None:
                    unparsed.append(f"{entry.name} / {heading}: {label} {points}")
                elif models:
                    entry.costs.append(UnitCost(copy, int(models.group(1)), cost))
                elif extra:
                    # (Per model added: "+ 1 Tidewall Defence Platform".)
                    if not any(w.name == clean(extra.group(2)) for w in entry.wargear):
                        entry.wargear.append(
                            WargearCost(clean(extra.group(2)), cost // int(extra.group(1)))
                        )
                elif parts:
                    entry.costs.append(UnitCost(copy, sum(n for n, _ in parts), cost, parts))
                else:
                    unparsed.append(f"{entry.name} / {heading}: {label} {points}")
        elif "WARGEAR" in upper:
            for label, points in lines:
                cost = points_of(points)
                name = clean(re.sub(r"^per\s+", "", label.strip(), flags=re.I))
                if cost is not None and name:
                    entry.wargear.append(WargearCost(name, cost))
                else:
                    unparsed.append(f"{entry.name} / {heading}: {label} {points}")
        # (LEADER, SUPPORT, BODYGUARD...: who it attaches to - not points.)
    return entry


def parse_faction(slug: str, page_html: str) -> FactionPage:
    rows = payload_rows(page_html)
    units: dict[str, UnitEntry] = {}
    unparsed: list[str] = []
    title, version = slug, None
    # (The same card is reachable from more than one row: kept by its key.)
    for row in rows.values():
        tree = resolve(row, rows)
        for node in walk(tree):
            if node.tag == "h1" and title == slug:
                title = node.text() or slug
            if version is None and _VERSION.match(node.text()) and not node.children[1:]:
                version = node.text()
            if _is_unit(node):
                key = node.key or text_of(node.children[:1])
                if key not in units:
                    units[key] = parse_unit(node, unparsed)
    return FactionPage(slug=slug, title=title, version=version,
                       units=list(units.values()), unparsed=unparsed)


def fetch_all(locale: str = LOCALE, only: list[str] | None = None) -> list[FactionPage]:
    # Every faction page the index links to (or just `only`'s slugs), parsed.
    slugs = faction_slugs(fetch(f"{BASE}/{locale}"), locale)
    if only:
        slugs = [s for s in slugs if s in only]
    return [parse_faction(slug, fetch(f"{BASE}/{locale}/{slug}")) for slug in slugs]
