from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def is_loaded(obj, attr: str) -> bool:
    # Whether obj's `attr` was loaded with it - for an ORM object, or a plain
    # copy of one in a game's catalog (see app/engine/catalog.py), which only
    # has what was loaded.
    try:
        return attr not in inspect(obj).unloaded
    except NoInspectionAvailable:
        return attr in vars(obj)
