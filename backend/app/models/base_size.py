from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BaseSize(Base):
    # A base a model can be on, as written on datasheets - e.g. "32mm",
    # "105 x 70mm" (oval) or "Use model" (no base). Models pick one of these.
    __tablename__ = "base_sizes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
