from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin
from database.enums import (
    AssetModality,
    AssetStatus,
    ChatStatus,
    ChatTurnEventType,
    ContentType,
    KgStatus,
    MessageRole,
    PipelineEventType,
)

_ENUM_VALUES = lambda enum_cls: [member.value for member in enum_cls]  # noqa: E731


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    modality: Mapped[AssetModality] = mapped_column(
        Enum(AssetModality, name="asset_modality", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name="asset_status", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
        default=AssetStatus.UPLOADING,
    )
    kg_status: Mapped[KgStatus] = mapped_column(
        Enum(KgStatus, name="kg_status", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
        default=KgStatus.PENDING,
    )
    raw_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    processed_path: Mapped[str | None] = mapped_column(String(1000))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triple_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    content_units: Mapped[list["ContentUnit"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    pipeline_events: Mapped[list["PipelineEvent"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class ContentUnit(Base):
    __tablename__ = "content_units"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, name="content_type", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
    )
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_tokens: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_ref: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    timestamp_anchor: Mapped[float] = mapped_column(Double, nullable=False, default=0.0)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship(back_populates="content_units")


class Outline(Base):
    __tablename__ = "outlines"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str | None] = mapped_column(String(500))
    tree: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    model_id: Mapped[str | None] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    chat_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ChatStatus] = mapped_column(
        Enum(ChatStatus, name="chat_status", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
        default=ChatStatus.IDLE,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    evidences: Mapped[list["ChatEvidence"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    turn_events: Mapped[list["ChatTurnEvent"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class ChatEvidence(Base):
    __tablename__ = "chat_evidences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    content_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_units.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Double, nullable=False)
    base_vector_score: Mapped[float | None] = mapped_column(Double)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="pgvector")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="evidences")


class ChatTurnEvent(Base):
    __tablename__ = "chat_turn_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    turn_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[ChatTurnEventType] = mapped_column(
        Enum(ChatTurnEventType, name="chat_turn_event_type", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
    )
    step_name: Mapped[str | None] = mapped_column(String(64))
    from_status: Mapped[ChatStatus | None] = mapped_column(
        Enum(ChatStatus, name="chat_status", native_enum=True, create_constraint=False, values_callable=_ENUM_VALUES)
    )
    to_status: Mapped[ChatStatus | None] = mapped_column(
        Enum(ChatStatus, name="chat_status", native_enum=True, create_constraint=False, values_callable=_ENUM_VALUES)
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="turn_events")


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[PipelineEventType] = mapped_column(
        Enum(PipelineEventType, name="pipeline_event_type", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
    )
    from_status: Mapped[AssetStatus | None] = mapped_column(
        Enum(AssetStatus, name="asset_status", native_enum=True, create_constraint=False, values_callable=_ENUM_VALUES)
    )
    to_status: Mapped[AssetStatus | None] = mapped_column(
        Enum(AssetStatus, name="asset_status", native_enum=True, create_constraint=False, values_callable=_ENUM_VALUES)
    )
    step_name: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship(back_populates="pipeline_events")


class KgJob(Base):
    __tablename__ = "kg_jobs"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[KgStatus] = mapped_column(
        Enum(KgStatus, name="kg_status", native_enum=True, values_callable=_ENUM_VALUES),
        nullable=False,
        default=KgStatus.PENDING,
    )
    chunks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triples_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
