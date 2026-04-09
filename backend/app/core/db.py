from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app.core.config import settings


@contextmanager
def db_cursor(commit: bool = False):
    conn = sqlite3.connect(settings.sqlite_path_resolved)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        yield cursor
        if commit:
            conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_cursor(commit=True) as cur:
        def ensure_column(table: str, column_name: str, column_sql: str) -> None:
            cur.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cur.fetchall()}
            if column_name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              kind TEXT NOT NULL,
              file_path TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              chunk_index INTEGER NOT NULL,
              content TEXT NOT NULL,
              embedding_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sections (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              section_index INTEGER NOT NULL,
              section_title TEXT NOT NULL,
              parent_section_title TEXT,
              page_start INTEGER,
              page_end INTEGER,
              section_type TEXT NOT NULL,
              section_text TEXT NOT NULL,
              keywords_json TEXT,
              chunk_ids_json TEXT,
              facts_json TEXT,
              embedding_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_sources (
              conversation_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
              FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_state (
              conversation_id TEXT PRIMARY KEY,
              state_json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )

        ensure_column("sections", "facts_json", "facts_json TEXT")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sections_source ON sections(source_id)")
