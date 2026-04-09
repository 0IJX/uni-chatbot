from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationsResponse,
    HealthResponse,
    SettingsActionRequest,
    SettingsActionResponse,
    UploadUrlRequest,
    UploadResponse,
)
from app.services.admin_service import admin_service
from app.services.chat_service import chat_service
from app.services.ingest_service import ingest_service
from app.services.provider import provider
from app.services.storage_service import storage_service


router = APIRouter()


def _upload_file_count() -> int:
    uploads_dir = settings.uploads_dir_path
    if not uploads_dir.exists():
        return 0
    return len([item for item in uploads_dir.iterdir() if item.is_file() and not item.name.startswith(".")])


def _require_admin_password(password: str | None) -> None:
    if not admin_service.verify_password(password):
        raise HTTPException(status_code=403, detail="Admin password is required for this action.")


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="local-academic-ai-assistant",
        ollama_ok=provider.health(),
        chat_model=provider.chat_model,
        embedding_model=provider.embedding_model,
    )


@router.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = chat_service.complete(
            user_message=payload.message,
            conversation_id=payload.conversation_id,
            requested_source_id=payload.source_id,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(**result)


@router.post("/api/chat/stream")
def stream_chat(payload: ChatRequest) -> StreamingResponse:
    try:
        stream_ctx = chat_service.stream(
            user_message=payload.message,
            conversation_id=payload.conversation_id,
            requested_source_id=payload.source_id,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    citations = [
        {
            "chunk_id": row["chunk_id"],
            "source_id": row["source_id"],
            "score": float(row["score"]),
            "preview": row["preview"],
            "section_title": row.get("section_title"),
            "page_start": row.get("page_start"),
            "page_end": row.get("page_end"),
        }
        for row in stream_ctx["evidence"]
    ]

    def event_stream() -> Iterator[str]:
        meta = {
            "conversation_id": stream_ctx["conversation_id"],
            "source_id": stream_ctx["source_id"],
            "citations": citations,
        }
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"

        pieces: list[str] = []
        try:
            for token in stream_ctx["token_iterator"]():
                pieces.append(token)
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
        except Exception:
            fallback = (
                "I couldn't reach Ollama right now. Please make sure Ollama is running, "
                "then try again."
            )
            pieces.append(fallback)
            yield f"event: token\ndata: {json.dumps({'token': fallback})}\n\n"

        reply = "".join(pieces).strip()
        chat_service.save_stream_reply(stream_ctx["conversation_id"], reply)

        done = {
            "conversation_id": stream_ctx["conversation_id"],
            "source_id": stream_ctx["source_id"],
            "reply": reply,
            "citations": citations,
        }
        yield f"event: done\ndata: {json.dumps(done)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/upload", response_model=UploadResponse)
async def upload(
    files: list[UploadFile] = File(...),
    conversation_id: str | None = Query(default=None),
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    uploaded: list[dict] = []
    for file in files:
        try:
            item = await ingest_service.ingest_upload(file)
            uploaded.append(item)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}") from exc

    if conversation_id and uploaded:
        storage_service.set_conversation_source(conversation_id, uploaded[-1]["source_id"])

    return UploadResponse(uploaded=uploaded)


@router.post("/api/upload-url", response_model=UploadResponse)
def upload_url(payload: UploadUrlRequest) -> UploadResponse:
    try:
        uploaded = ingest_service.ingest_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.conversation_id:
        storage_service.set_conversation_source(payload.conversation_id, uploaded["source_id"])
    return UploadResponse(uploaded=[uploaded])


@router.get("/api/conversations", response_model=ConversationsResponse)
def list_conversations(conversation_id: str | None = Query(default=None)) -> ConversationsResponse:
    conversations = storage_service.list_conversations()
    sources = storage_service.list_sources()
    messages: list[dict] = []
    active_source_id: str | None = None

    if conversation_id:
        messages = storage_service.get_messages(conversation_id)
        active_source_id = storage_service.get_conversation_source(conversation_id)

    return ConversationsResponse(
        conversations=conversations,
        sources=sources,
        active_source_id=active_source_id,
        messages=messages,
    )


@router.post("/api/conversations", response_model=dict)
def create_conversation(payload: ConversationCreateRequest) -> dict:
    created = storage_service.create_conversation(payload.title)
    if payload.source_id:
        source = storage_service.get_source(payload.source_id)
        if source:
            storage_service.set_conversation_source(created["id"], payload.source_id)
    return {"conversation": created}


@router.delete("/api/conversations", response_model=dict)
def delete_conversation(conversation_id: str = Query(...)) -> dict:
    storage_service.delete_conversation(conversation_id)
    return {"ok": True}


@router.delete("/api/sources", response_model=dict)
def delete_source(source_id: str = Query(...)) -> dict:
    source = storage_service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")
    if source["kind"] == "catalog":
        raise HTTPException(status_code=400, detail="Catalog source cannot be deleted.")
    removed = storage_service.delete_source(source_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Source not found.")
    storage_service.purge_orphan_upload_files()
    return {"ok": True}


@router.post("/api/settings/actions", response_model=SettingsActionResponse)
def settings_actions(payload: SettingsActionRequest) -> SettingsActionResponse:
    action = payload.action
    removed_sources = 0
    removed_conversations = 0
    removed_files = 0

    conversations_before = len(storage_service.list_conversations())
    files_before = _upload_file_count()

    if action == "delete_source":
        if not payload.source_id:
            raise HTTPException(status_code=400, detail="source_id is required for delete_source.")
        source = storage_service.get_source(payload.source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found.")
        if source["kind"] == "catalog":
            raise HTTPException(status_code=400, detail="Catalog source cannot be deleted.")
        if storage_service.delete_source(payload.source_id):
            removed_sources = 1
    elif action == "clear_uploads":
        _require_admin_password(payload.admin_password)
        removed_sources = storage_service.clear_upload_sources()
    elif action == "clear_conversations":
        storage_service.clear_conversations()
        removed_conversations = conversations_before
    elif action in {"clear_all", "reset_local_state"}:
        _require_admin_password(payload.admin_password)
        result = storage_service.clear_all_user_state()
        removed_sources = result["removed_uploads"]
        removed_conversations = conversations_before
    else:
        raise HTTPException(status_code=400, detail="Unsupported settings action.")

    removed_files += storage_service.purge_orphan_upload_files()
    files_after = _upload_file_count()
    if files_before > files_after:
        removed_files = max(removed_files, files_before - files_after)

    message = "Action completed."
    if action == "delete_source":
        message = "Source deleted."
    elif action == "clear_uploads":
        message = "All uploaded files and indexed upload sources were cleared."
    elif action == "clear_conversations":
        message = "All conversation history was cleared."
    elif action == "clear_all":
        message = "All uploaded files and conversation history were cleared."
    elif action == "reset_local_state":
        message = "Local app state was reset while preserving catalog knowledge."

    return SettingsActionResponse(
        ok=True,
        removed_sources=removed_sources,
        removed_conversations=removed_conversations,
        removed_files=removed_files,
        message=message,
    )
