"""ORM model registry — import all models so Alembic can detect metadata."""

from app.models.base import Base
from app.models.data_source import DataSource
from app.models.message import Message
from app.models.query_history import QueryHistory
from app.models.schema_embedding import SchemaEmbedding
from app.models.session import ChatSession

__all__ = [
    "Base",
    "ChatSession",
    "DataSource",
    "Message",
    "QueryHistory",
    "SchemaEmbedding",
]
