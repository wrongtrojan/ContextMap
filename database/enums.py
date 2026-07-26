from __future__ import annotations

import enum


class AssetModality(str, enum.Enum):
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"


class AssetStatus(str, enum.Enum):
    UPLOADING = "uploading"
    RAW = "raw"
    RECOGNIZING = "recognizing"
    EMBEDDING = "embedding"
    STRUCTURING = "structuring"
    KG_EXTRACTING = "kg_extracting"
    INGESTING = "ingesting"
    READY = "ready"
    FAILED = "failed"


class KgStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ContentType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    TRANSCRIPT = "transcript"
    FRAME = "frame"
    TRANSCRIPT_CONTEXT = "transcript_context"


class ChatStatus(str, enum.Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RESEARCHING = "researching"
    EVALUATING = "evaluating"
    STRENGTHENING = "strengthening"
    FINALIZING = "finalizing"
    FAILED = "failed"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class PipelineEventType(str, enum.Enum):
    STATUS_CHANGE = "status_change"
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    STEP_FAILED = "step_failed"
    RETRY = "retry"


class ChatTurnEventType(str, enum.Enum):
    STATUS_CHANGE = "status_change"
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    STEP_FAILED = "step_failed"
    EVALUATION = "evaluation"
    REFETCH = "refetch"
    EVIDENCE_SNAPSHOT = "evidence_snapshot"
    INFER_RESULT = "infer_result"
    TOKEN = "token"
    COMPLETED = "completed"
    ERROR = "error"
