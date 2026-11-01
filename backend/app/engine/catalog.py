from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Mapper

from app.models import Base

# What a game is played with, read from the database once: its armies (units,
# models, weapons, abilities, ...), stratagems, mission cards and terrain. The
# engine (see app/engine/__init__.py) plays on plain copies of those rows - a
# "mirror" of each - so nothing during a game goes back to the database.
#
# A mirror has the same name, columns and relationships as the ORM class it
# copies, and its properties and methods (e.g. Unit.label), but isn't mapped:
# it's read-only by convention. Only what was loaded is copied - a
# relationship that wasn't loaded is missing from the mirror, rather than
# loaded later - so the catalog is what the game code reads, no more. It's
# saved with a game's autosaves (see app/engine/saves.py) as a table of rows
# by class and primary key, relationships by key.

_mirrors: dict[type, type] = {}
_by_name: dict[str, Mapper] = {}


class Mirror:
    # The ORM class mirrored (set on each mirror class).
    _orm: type

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {_key(self)}>"

    # Shared, never copied: a copy of a game's state (see
    # app/engine/__init__.py) refers to the same catalog.
    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


def mirror_class(orm_class: type) -> type:
    found = _mirrors.get(orm_class)
    if found is not None:
        return found
    mapper = inspect(orm_class)
    mapped = set(mapper.attrs.keys())
    namespace: dict[str, Any] = {"_orm": orm_class, "__module__": orm_class.__module__}
    # Its own (and its plain base classes') properties and methods - not the
    # mapped attributes, nor SQLAlchemy's own machinery.
    for klass in reversed(orm_class.__mro__):
        if klass in (object, Base) or not issubclass(klass, Base):
            continue
        for name, value in vars(klass).items():
            if name in mapped or name.startswith("_") or name in ("metadata", "registry"):
                continue
            if isinstance(value, (property, staticmethod, classmethod)) or callable(value):
                namespace[name] = value
            elif not hasattr(value, "__get__"):
                namespace[name] = value  # class constants
    mirror = type(orm_class.__name__, (Mirror,), namespace)
    _mirrors[orm_class] = mirror
    _by_name[orm_class.__name__] = mapper
    return mirror


def _key(obj) -> tuple:
    # A mirror's (or ORM object's) primary key.
    mapper = inspect(obj._orm if isinstance(obj, Mirror) else type(obj))
    return tuple(getattr(obj, c.key) for c in mapper.primary_key)


def _orm_key(state) -> tuple:
    return tuple(state.mapper.primary_key_from_instance(state.obj()))


class Catalog:
    def __init__(self) -> None:
        # {class name: {primary key: mirror}}
        self.rows: dict[str, dict[tuple, Any]] = {}

    # Looking things up.

    def get(self, class_name: str, *key):
        return self.rows.get(class_name, {}).get(tuple(key))

    def all(self, class_name: str) -> list:
        return list(self.rows.get(class_name, {}).values())

    # Copying ORM objects in.

    def add(self, orm_obj):
        # The mirror of `orm_obj` (and of everything loaded with it).
        memo: dict[int, Any] = {}
        return self._mirror(orm_obj, memo)

    def _mirror(self, orm_obj, memo):
        if orm_obj is None:
            return None
        found = memo.get(id(orm_obj))
        if found is not None:
            return found
        state = inspect(orm_obj)
        name = type(orm_obj).__name__
        key = _orm_key(state)
        table = self.rows.setdefault(name, {})
        existing = table.get(key)
        mirror = existing if existing is not None else mirror_class(type(orm_obj)).__new__(
            mirror_class(type(orm_obj))
        )
        memo[id(orm_obj)] = mirror
        table[key] = mirror
        unloaded = state.unloaded
        for column in state.mapper.column_attrs:
            if column.key not in unloaded:
                mirror.__dict__[column.key] = state.dict.get(column.key)
        for rel in state.mapper.relationships:
            if rel.key in unloaded or rel.key not in state.dict:
                continue
            value = state.dict[rel.key]
            if rel.uselist:
                mirror.__dict__[rel.key] = [self._mirror(v, memo) for v in value]
            else:
                mirror.__dict__[rel.key] = self._mirror(value, memo)
        return mirror

    # Saving and restoring.

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, table in self.rows.items():
            mapper = _by_name[name]
            rels = {r.key: r for r in mapper.relationships}
            rows = []
            for mirror in table.values():
                row: dict[str, Any] = {}
                for attr, value in mirror.__dict__.items():
                    if attr in rels:
                        target = rels[attr].mapper.class_.__name__
                        if isinstance(value, list):
                            row[attr] = {"to": target, "many": [list(_key(v)) for v in value]}
                        else:
                            row[attr] = {
                                "to": target, "one": None if value is None else list(_key(value))
                            }
                    elif isinstance(value, datetime):
                        row[attr] = {"datetime": value.isoformat()}
                    else:
                        row[attr] = value
                rows.append(row)
            out[name] = rows
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Catalog:
        catalog = cls()
        mappers = {m.class_.__name__: m for m in Base.registry.mappers}
        pending = []
        for name, rows in data.items():
            mapper = mappers[name]
            mirror = mirror_class(mapper.class_)
            rels = {r.key for r in mapper.relationships}
            pk = [c.key for c in mapper.primary_key]
            table = catalog.rows.setdefault(name, {})
            for row in rows:
                obj = mirror.__new__(mirror)
                for attr, value in row.items():
                    if attr in rels:
                        pending.append((obj, attr, value))
                    elif isinstance(value, dict) and "datetime" in value:
                        obj.__dict__[attr] = datetime.fromisoformat(value["datetime"])
                    else:
                        obj.__dict__[attr] = value
                table[tuple(obj.__dict__[k] for k in pk)] = obj
        for obj, attr, ref in pending:
            rows = catalog.rows.get(ref["to"], {})
            if "many" in ref:
                obj.__dict__[attr] = [rows[tuple(k)] for k in ref["many"]]
            else:
                obj.__dict__[attr] = None if ref["one"] is None else rows[tuple(ref["one"])]
        return catalog
