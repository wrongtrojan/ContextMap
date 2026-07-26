"""Pydantic schemas for database reads/writes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from database.enums import AssetModality, AssetStatus, ChatStatus, ChatTurnEventType, ContentType, KgStatus, MessageRole


class AssetCreate(BaseModel):
    name: str
    modality: AssetModality
    raw_path: str
    processed_path: str | None = None
    file_size_bytes: int | None = None
    file_hash: str | None = None
    status: AssetStatus = AssetStatus.INGESTING
    kg_status: KgStatus = KgStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    modality: AssetModality
    status: AssetStatus
    kg_status: KgStatus
    raw_path: str
    processed_path: str | None
    file_size_bytes: int | None
    file_hash: str | None
    retry_count: int
    triple_count: int
    error_message: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ContentUnitCreate(BaseModel):
    asset_id: uuid.UUID
    content_type: ContentType
    search_text: str
    search_tokens: str | None = None
    content_ref: str
    embedding: list[float] | None = None
    timestamp_anchor: float = 0.0
    chunk_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    content_type: ContentType
    search_text: str
    search_tokens: str | None = None
    content_ref: str
    embedding: list[float] | None
    timestamp_anchor: float
    chunk_index: int
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime


class VectorSearchResult(BaseModel):
    unit: ContentUnitRead
    score: float


class OutlineCreate(BaseModel):
    asset_id: uuid.UUID
    title: str | None = None
    tree: list[dict[str, Any]] = Field(default_factory=list)
    model_id: str | None = None


class OutlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    title: str | None
    tree: list[dict[str, Any]]
    model_id: str | None
    generated_at: datetime
    updated_at: datetime


class ChatSessionCreate(BaseModel):
    external_id: str
    chat_name: str = "New Academic Chat"
    status: ChatStatus = ChatStatus.IDLE
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    chat_name: str
    status: ChatStatus
    retry_count: int
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    seq: int
    created_at: datetime


class ChatEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID | None
    content_unit_id: uuid.UUID | None
    content: str
    score: float
    base_vector_score: float | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    rank: int
    source: str
    created_at: datetime


class ChatTurnEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID | None
    turn_seq: int
    event_type: ChatTurnEventType
    step_name: str | None
    from_status: ChatStatus | None
    to_status: ChatStatus | None
    detail: dict[str, Any]
    created_at: datetime
