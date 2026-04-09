from __future__ import annotations

from typing import Literal
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app: str
    ollama_ok: bool
    chat_model: str
    embedding_model: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    source_id: str | None = None


class Citation(BaseModel):
    chunk_id: str
    source_id: str
    score: float
    preview: str
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    source_id: str
    reply: str
    citations: list[Citation] = Field(default_factory=list)


class UploadResult(BaseModel):
    source_id: str
    name: str
    kind: str
    chunks_indexed: int
    ingest_mode: str | None = None
    ingest_note: str | None = None


class UploadResponse(BaseModel):
    uploaded: list[UploadResult] = Field(default_factory=list)


class UploadUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    title: str = "New Chat"
    source_id: str | None = None


class ConversationDeleteRequest(BaseModel):
    conversation_id: str


SettingsAction = Literal[
    "delete_source",
    "clear_uploads",
    "clear_conversations",
    "clear_all",
    "reset_local_state",
]


class SettingsActionRequest(BaseModel):
    action: SettingsAction
    source_id: str | None = None
    admin_password: str | None = None


class SettingsActionResponse(BaseModel):
    ok: bool = True
    removed_sources: int = 0
    removed_conversations: int = 0
    removed_files: int = 0
    message: str = ""


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class SourceOut(BaseModel):
    id: str
    name: str
    kind: str


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationsResponse(BaseModel):
    conversations: list[ConversationOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    active_source_id: str | None = None
    messages: list[MessageOut] = Field(default_factory=list)


class StreamRequest(ChatRequest):
    pass


def as_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}
