"""SQLAlchemy declarative base for project DB models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models in the project database."""
