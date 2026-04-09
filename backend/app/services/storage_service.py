from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.db import db_cursor


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageService:
    def create_conversation(self, title: str = "New Chat") -> dict:
        conversation_id = f"conv_{uuid4().hex}"
        ts = now_iso()
        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title.strip() or "New Chat", ts, ts),
            )
        return {
            "id": conversation_id,
            "title": title.strip() or "New Chat",
            "created_at": ts,
            "updated_at": ts,
        }

    def list_conversations(self) -> list[dict]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_conversation(self, conversation_id: str) -> None:
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM conversation_state WHERE conversation_id = ?", (conversation_id,))
            cur.execute("DELETE FROM conversation_sources WHERE conversation_id = ?", (conversation_id,))
            cur.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cur.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def ensure_conversation(self, conversation_id: str | None) -> dict:
        if conversation_id:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                    (conversation_id,),
                )
                row = cur.fetchone()
            if row:
                return dict(row)
        return self.create_conversation()

    def add_message(self, conversation_id: str, role: str, content: str) -> dict:
        message_id = f"msg_{uuid4().hex}"
        ts = now_iso()
        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (message_id, conversation_id, role, content, ts),
            )
            cur.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (ts, conversation_id),
            )
        return {
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": ts,
        }

    def get_messages(self, conversation_id: str) -> list[dict]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def set_conversation_source(self, conversation_id: str, source_id: str) -> None:
        ts = now_iso()
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO conversation_sources (conversation_id, source_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id)
                DO UPDATE SET source_id=excluded.source_id, updated_at=excluded.updated_at
                """,
                (conversation_id, source_id, ts),
            )

    def get_conversation_source(self, conversation_id: str) -> str | None:
        with db_cursor() as cur:
            cur.execute(
                "SELECT source_id FROM conversation_sources WHERE conversation_id = ?",
                (conversation_id,),
            )
            row = cur.fetchone()
        return row["source_id"] if row else None

    def get_conversation_state(self, conversation_id: str) -> dict:
        with db_cursor() as cur:
            cur.execute(
                "SELECT state_json FROM conversation_state WHERE conversation_id = ?",
                (conversation_id,),
            )
            row = cur.fetchone()
        if not row:
            return {}
        try:
            payload = json.loads(row["state_json"])
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def set_conversation_state(self, conversation_id: str, state: dict) -> None:
        ts = now_iso()
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO conversation_state (conversation_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id)
                DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at
                """,
                (conversation_id, json.dumps(state, ensure_ascii=False), ts),
            )

    def list_sources(self) -> list[dict]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, name, kind FROM sources ORDER BY kind DESC, updated_at DESC"
            )
            return [dict(row) for row in cur.fetchall()]

    def list_upload_sources(self) -> list[dict]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, name, kind, file_path, created_at, updated_at FROM sources WHERE kind = 'upload' ORDER BY updated_at DESC"
            )
            return [dict(row) for row in cur.fetchall()]

    def get_source(self, source_id: str) -> dict | None:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, name, kind, file_path, created_at, updated_at FROM sources WHERE id = ?",
                (source_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def upsert_source(self, source_id: str, name: str, kind: str, file_path: str | None) -> dict:
        ts = now_iso()
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO sources (id, name, kind, file_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET name=excluded.name, kind=excluded.kind, file_path=excluded.file_path, updated_at=excluded.updated_at
                """,
                (source_id, name, kind, file_path, ts, ts),
            )
        return {
            "id": source_id,
            "name": name,
            "kind": kind,
            "file_path": file_path,
            "updated_at": ts,
        }

    def delete_source(self, source_id: str, allow_catalog: bool = False) -> bool:
        source = self.get_source(source_id)
        if not source:
            return False
        if source["kind"] == "catalog" and not allow_catalog:
            return False

        file_path = source.get("file_path")
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM conversation_sources WHERE source_id = ?", (source_id,))
            cur.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
            cur.execute("DELETE FROM sections WHERE source_id = ?", (source_id,))
            cur.execute("DELETE FROM sources WHERE id = ?", (source_id,))

        if file_path and source["kind"] == "upload":
            try:
                path = Path(file_path)
                if not path.is_absolute():
                    path = settings.resolve_path(file_path)
                if path.exists() and path.is_file():
                    path.unlink()
            except OSError:
                pass

        self._scrub_source_from_state(source_id)
        return True

    def clear_conversations(self) -> None:
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM conversation_state")
            cur.execute("DELETE FROM conversation_sources")
            cur.execute("DELETE FROM messages")
            cur.execute("DELETE FROM conversations")

    def clear_upload_sources(self) -> int:
        upload_sources = self.list_upload_sources()
        removed = 0
        for source in upload_sources:
            if self.delete_source(source["id"], allow_catalog=False):
                removed += 1
        return removed

    def clear_all_user_state(self) -> dict:
        self.clear_conversations()
        removed_uploads = self.clear_upload_sources()
        return {"removed_uploads": removed_uploads}

    def purge_orphan_upload_files(self) -> int:
        known_files: set[Path] = set()
        for source in self.list_upload_sources():
            path = source.get("file_path")
            if not path:
                continue
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = settings.resolve_path(path)
            known_files.add(candidate.resolve())

        removed = 0
        uploads_dir = settings.uploads_dir_path
        if not uploads_dir.exists():
            return 0
        for item in uploads_dir.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_file() and item.resolve() not in known_files:
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    continue
        return removed

    def _scrub_source_from_state(self, source_id: str) -> None:
        with db_cursor() as cur:
            cur.execute("SELECT conversation_id, state_json FROM conversation_state")
            rows = [dict(row) for row in cur.fetchall()]

        updates: list[tuple[str, str]] = []
        for row in rows:
            try:
                state = json.loads(row["state_json"])
            except json.JSONDecodeError:
                continue
            if not isinstance(state, dict):
                continue

            changed = False
            if state.get("last_primary_source_id") == source_id:
                state.pop("last_primary_source_id", None)
                changed = True
            if state.get("active_source_mode") in {"upload_personal", "exact_operational"} and not state.get("last_primary_source_id"):
                state["active_source_mode"] = "catalog_background"
                changed = True
            if changed:
                updates.append((json.dumps(state, ensure_ascii=False), row["conversation_id"]))

        if not updates:
            return
        ts = now_iso()
        with db_cursor(commit=True) as cur:
            for state_json, conversation_id in updates:
                cur.execute(
                    "UPDATE conversation_state SET state_json = ?, updated_at = ? WHERE conversation_id = ?",
                    (state_json, ts, conversation_id),
                )

    def replace_chunks(self, source_id: str, chunks: list[dict]) -> None:
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
            for chunk in chunks:
                cur.execute(
                    "INSERT INTO chunks (id, source_id, chunk_index, content, embedding_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        chunk["id"],
                        source_id,
                        int(chunk["chunk_index"]),
                        chunk["content"],
                        json.dumps(chunk.get("embedding")) if chunk.get("embedding") is not None else None,
                        chunk["created_at"],
                    ),
                )

    def replace_sections(self, source_id: str, sections: list[dict]) -> None:
        with db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM sections WHERE source_id = ?", (source_id,))
            for section in sections:
                cur.execute(
                    """
                    INSERT INTO sections (
                        id,
                        source_id,
                        section_index,
                        section_title,
                        parent_section_title,
                        page_start,
                        page_end,
                        section_type,
                        section_text,
                        keywords_json,
                        chunk_ids_json,
                        facts_json,
                        embedding_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section["id"],
                        source_id,
                        int(section["section_index"]),
                        section["section_title"],
                        section.get("parent_section_title"),
                        section.get("page_start"),
                        section.get("page_end"),
                        section["section_type"],
                        section["section_text"],
                        json.dumps(section.get("keywords", []), ensure_ascii=False),
                        json.dumps(section.get("chunk_ids", []), ensure_ascii=False),
                        json.dumps(section.get("facts", {}), ensure_ascii=False),
                        json.dumps(section.get("embedding")) if section.get("embedding") is not None else None,
                        section["created_at"],
                    ),
                )

    def get_sections(self, source_id: str) -> list[dict]:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    source_id,
                    section_index,
                    section_title,
                    parent_section_title,
                    page_start,
                    page_end,
                    section_type,
                    section_text,
                    keywords_json,
                    chunk_ids_json,
                    facts_json,
                    embedding_json,
                    created_at
                FROM sections
                WHERE source_id = ?
                ORDER BY section_index ASC
                """,
                (source_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["keywords"] = json.loads(row["keywords_json"]) if row.get("keywords_json") else []
            row["chunk_ids"] = json.loads(row["chunk_ids_json"]) if row.get("chunk_ids_json") else []
            row["facts"] = json.loads(row["facts_json"]) if row.get("facts_json") else {}
            row["embedding"] = json.loads(row["embedding_json"]) if row.get("embedding_json") else None
        return rows

    def get_chunks(self, source_id: str) -> list[dict]:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, source_id, chunk_index, content, embedding_json, created_at FROM chunks WHERE source_id = ? ORDER BY chunk_index ASC",
                (source_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            if row.get("embedding_json"):
                row["embedding"] = json.loads(row["embedding_json"])
            else:
                row["embedding"] = None
        return rows


storage_service = StorageService()
