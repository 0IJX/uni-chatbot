from __future__ import annotations

import math
import re
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.services.provider import provider
from app.services.storage_service import now_iso, storage_service


WORD_RE = re.compile(r"[A-Za-z0-9_]+")
COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,5}\s?\d{3}\b")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "with",
}

QUERY_EXPANSIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bai\b", re.I), "artificial intelligence"),
    (re.compile(r"\bcs\b", re.I), "computer science"),
    (re.compile(r"\breqs?\b", re.I), "requirements"),
    (re.compile(r"\bstudyplan\b", re.I), "study plan"),
    (re.compile(r"\bsched\b", re.I), "schedule"),
    (re.compile(r"\byr\s*1\b", re.I), "year 1"),
    (re.compile(r"\byr\s*2\b", re.I), "year 2"),
    (re.compile(r"\bpre-?reqs?\b", re.I), "prerequisites"),
    (re.compile(r"\bmidterm\b", re.I), "midterm exam"),
    (re.compile(r"\bfinal\b", re.I), "final exam"),
    (re.compile(r"\bfinals\b", re.I), "final exam schedule"),
    (re.compile(r"\bexam hall\b", re.I), "exam location room hall"),
    (re.compile(r"\bexam room\b", re.I), "exam location room"),
    (re.compile(r"\binvigilation\b", re.I), "exam schedule"),
    (re.compile(r"\bcgpa\b", re.I), "cgpa grade point average"),
    (re.compile(r"\blabs?\b", re.I), "laboratory lab"),
]


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    n = len(clean)
    while start < n:
        end = min(start + max_chars, n)
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text)}


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class RetrievalService:
    def _expand_query(self, query: str) -> str:
        output = f" {query or ''} "
        for pattern, replacement in QUERY_EXPANSIONS:
            if pattern.search(output):
                output = f"{output} {replacement}"
        lowered = output.lower()
        if "artificial intelligence" in lowered and " ai " not in f" {lowered} ":
            output = f"{output} ai"
        if "computer science" in lowered and " cs " not in f" {lowered} ":
            output = f"{output} cs"
        return re.sub(r"\s+", " ", output).strip()

    def _lexical_score(self, query_tokens: set[str], text: str) -> float:
        if not query_tokens:
            return 0.0
        filtered_query = {token for token in query_tokens if token not in STOPWORDS}
        if not filtered_query:
            filtered_query = query_tokens
        text_tokens = tokenize(text)
        if not text_tokens:
            return 0.0
        overlap = len(filtered_query & text_tokens)
        return overlap / max(len(filtered_query), 1)

    def _normalize_section(self, section: Any, fallback_index: int) -> dict[str, Any]:
        if isinstance(section, dict):
            title = (section.get("section_title") or f"Section {fallback_index + 1}").strip()
            parent = section.get("parent_section_title")
            page_start = section.get("page_start")
            page_end = section.get("page_end")
            section_type = section.get("section_type") or "general"
            section_text = (section.get("section_text") or "").strip()
            keywords = list(section.get("keywords") or [])
            facts = dict(section.get("facts") or {})
        else:
            title = (getattr(section, "section_title", None) or f"Section {fallback_index + 1}").strip()
            parent = getattr(section, "parent_section_title", None)
            page_start = getattr(section, "page_start", None)
            page_end = getattr(section, "page_end", None)
            section_type = getattr(section, "section_type", "general") or "general"
            section_text = (getattr(section, "section_text", "") or "").strip()
            keywords = list(getattr(section, "keywords", []) or [])
            facts = dict(getattr(section, "facts", {}) or {})
        return {
            "section_title": title,
            "parent_section_title": parent,
            "page_start": page_start,
            "page_end": page_end,
            "section_type": section_type,
            "section_text": section_text,
            "keywords": keywords,
            "facts": facts,
        }

    def index_source_document(self, source_id: str, transcript: str, sections: list[Any] | None = None) -> int:
        source_sections: list[dict[str, Any]] = []
        for idx, raw in enumerate(sections or []):
            parsed = self._normalize_section(raw, idx)
            if parsed["section_text"]:
                source_sections.append(parsed)

        if not source_sections:
            fallback = (transcript or "").strip()
            if fallback:
                source_sections.append(
                    {
                        "section_title": "Document",
                        "parent_section_title": None,
                        "page_start": None,
                        "page_end": None,
                        "section_type": "general",
                        "section_text": fallback,
                        "keywords": [],
                        "facts": {},
                    }
                )

        if not source_sections:
            storage_service.replace_chunks(source_id, [])
            storage_service.replace_sections(source_id, [])
            return 0

        chunk_rows: list[dict[str, Any]] = []
        section_rows: list[dict[str, Any]] = []
        piece_texts: list[str] = []
        ts = now_iso()

        for section_index, section in enumerate(source_sections):
            section_id = f"sec_{uuid4().hex}"
            pieces = chunk_text(section["section_text"], settings.max_chunk_chars, settings.chunk_overlap_chars)
            if not pieces and section["section_text"]:
                pieces = [section["section_text"]]

            chunk_ids: list[str] = []
            for piece in pieces:
                chunk_id = f"chunk_{uuid4().hex}"
                chunk_rows.append(
                    {
                        "id": chunk_id,
                        "chunk_index": len(chunk_rows),
                        "content": piece,
                        "embedding": None,
                        "created_at": ts,
                    }
                )
                chunk_ids.append(chunk_id)
                piece_texts.append(piece)

            section_rows.append(
                {
                    "id": section_id,
                    "section_index": section_index,
                    "section_title": section["section_title"],
                    "parent_section_title": section["parent_section_title"],
                    "page_start": section["page_start"],
                    "page_end": section["page_end"],
                    "section_type": section["section_type"],
                    "section_text": section["section_text"],
                    "keywords": section["keywords"],
                    "chunk_ids": chunk_ids,
                    "facts": section.get("facts") or {},
                    "embedding": None,
                    "created_at": ts,
                }
            )

        chunk_embeddings = provider.embed(piece_texts) if piece_texts else []
        for idx, row in enumerate(chunk_rows):
            row["embedding"] = chunk_embeddings[idx] if idx < len(chunk_embeddings) else None

        section_embedding_inputs = [
            (
                f"{section['section_title']} "
                f"{' '.join(section.get('keywords') or [])} "
                f"{' '.join(sum([values for values in (section.get('facts') or {}).values() if isinstance(values, list)], []))} "
                f"{section['section_text'][:1200]}"
            ).strip()
            for section in section_rows
        ]
        section_embeddings = provider.embed(section_embedding_inputs) if section_embedding_inputs else []
        for idx, row in enumerate(section_rows):
            row["embedding"] = section_embeddings[idx] if idx < len(section_embeddings) else None

        storage_service.replace_chunks(source_id, chunk_rows)
        storage_service.replace_sections(source_id, section_rows)
        return len(chunk_rows)

    def index_source_text(self, source_id: str, text: str) -> int:
        return self.index_source_document(source_id=source_id, transcript=text, sections=None)

    def _query_course_codes(self, query_text: str) -> list[str]:
        return [re.sub(r"\s+", " ", value).strip() for value in COURSE_CODE_RE.findall(query_text)]

    def _facts_bonus(self, query_text: str, facts: dict[str, list[str]]) -> float:
        text = (query_text or "").lower()
        bonus = 0.0
        facts = facts or {}

        if "week" in text and facts.get("weeks"):
            bonus += 0.12
        if any(token in text for token in ("when", "date", "deadline", "due")) and facts.get("dates"):
            bonus += 0.16
        if any(token in text for token in ("time", "when")) and facts.get("times"):
            bonus += 0.12
        if any(token in text for token in ("where", "location", "room")) and facts.get("locations"):
            bonus += 0.16
        if any(token in text for token in ("exam", "midterm", "final")) and (facts.get("dates") or facts.get("times") or facts.get("locations")):
            bonus += 0.12
        course_codes = self._query_course_codes(text)
        section_codes = {code.upper() for code in facts.get("course_codes", [])}
        if course_codes and any(code.upper() in section_codes for code in course_codes):
            bonus += 0.22
        return bonus

    def _score_sections(
        self,
        sections: list[dict],
        query_tokens: set[str],
        query_vector: list[float] | None,
        query_text: str,
        mode: str,
        state: dict | None,
    ) -> list[dict]:
        query_text_lc = (query_text or "").lower()
        filtered_query = {token for token in query_tokens if token not in STOPWORDS} or query_tokens
        effective_query_size = len(filtered_query)
        wants_requirements = any(token in query_text_lc for token in ("requirement", "requirements", "req", "admission", "prerequisite"))
        wants_study_plan = any(token in query_text_lc for token in ("study plan", "semester", "schedule", "courses", "course list", "year 1", "year 2"))
        wants_policy = any(token in query_text_lc for token in ("policy", "attendance", "regulation", "guideline", "rule"))
        wants_program = any(token in query_text_lc for token in ("program", "major", "degree", "course"))
        previous_sections = set((state or {}).get("last_section_ids") or [])

        scored: list[dict] = []
        for section in sections:
            section_title_lc = (section.get("section_title") or "").lower()
            searchable = " ".join(
                [
                    section.get("section_title") or "",
                    section.get("section_type") or "",
                    " ".join(section.get("keywords") or []),
                    " ".join(sum([values for values in (section.get("facts") or {}).values() if isinstance(values, list)], [])),
                    (section.get("section_text") or "")[:1400],
                ]
            )
            lexical = self._lexical_score(query_tokens, searchable)
            semantic = 0.0
            section_embedding = section.get("embedding")
            if query_vector is not None and section_embedding is not None:
                semantic = max(cosine(query_vector, section_embedding), 0.0)
            if lexical == 0.0 and effective_query_size >= 3:
                continue
            if lexical == 0.0 and semantic < 0.35:
                continue
            score = (0.62 * lexical) + (0.30 * semantic)

            section_type = (section.get("section_type") or "").lower()
            if wants_requirements and section_type == "requirements":
                score += 0.12
            if wants_requirements and "requirement" in section_title_lc:
                score += 0.08
            if wants_study_plan and section_type in {"courses", "schedule"}:
                score += 0.12
            if wants_study_plan and ("study plan" in section_title_lc or "semester" in section_title_lc):
                score += 0.12
            if wants_policy and section_type == "policy":
                score += 0.10
            if wants_program and section_type == "program":
                score += 0.08
            if mode == "exact_operational":
                score += self._facts_bonus(query_text, section.get("facts") or {})
                if section_type in {"schedule", "courses", "table_or_list"}:
                    score += 0.08
            if section.get("id") in previous_sections:
                score += 0.08
            if score <= 0:
                continue
            scored.append({"section": section, "score": score})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored

    def _search_flat(
        self,
        source_id: str,
        query_tokens: set[str],
        query_vector: list[float] | None,
        top_k: int,
        sections: list[dict] | None = None,
        query_text: str = "",
        mode: str = "default",
    ) -> list[dict]:
        chunks = storage_service.get_chunks(source_id)
        if not chunks:
            return []
        filtered_query = {token for token in query_tokens if token not in STOPWORDS} or query_tokens
        effective_query_size = len(filtered_query)
        section_lookup: dict[str, dict] = {}
        if sections:
            for section in sections:
                for chunk_id in section.get("chunk_ids", []):
                    section_lookup[chunk_id] = section

        scored: list[dict] = []
        for row in chunks:
            section = section_lookup.get(row["id"])
            searchable = row["content"]
            if section:
                searchable = " ".join(
                    [
                        section.get("section_title") or "",
                        " ".join(section.get("keywords") or []),
                        " ".join(sum([values for values in (section.get("facts") or {}).values() if isinstance(values, list)], [])),
                        searchable,
                    ]
                )
            lexical = self._lexical_score(query_tokens, searchable)
            semantic = 0.0
            if query_vector is not None and row.get("embedding") is not None:
                semantic = max(cosine(query_vector, row["embedding"]), 0.0)
            if lexical == 0.0 and effective_query_size >= 3:
                continue
            if lexical == 0.0 and semantic < 0.35:
                continue
            score = (0.60 * lexical) + (0.40 * semantic)
            if section and mode == "exact_operational":
                score += self._facts_bonus(query_text, section.get("facts") or {})
            if score < settings.retrieval_min_score:
                continue
            preview = row["content"][:280].strip()
            scored.append(
                {
                    "chunk_id": row["id"],
                    "source_id": source_id,
                    "score": round(score, 6),
                    "preview": preview,
                    "text": row["content"],
                    "section_id": section.get("id") if section else None,
                    "section_title": section.get("section_title") if section else None,
                    "section_type": section.get("section_type") if section else None,
                    "page_start": section.get("page_start") if section else None,
                    "page_end": section.get("page_end") if section else None,
                    "facts": section.get("facts") if section else {},
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def search(
        self,
        source_id: str,
        query: str,
        top_k: int | None = None,
        mode: str = "default",
        state: dict | None = None,
    ) -> list[dict]:
        top_k = top_k or settings.retrieval_top_k
        expanded_query = self._expand_query(query or "")
        query_tokens = tokenize(expanded_query)
        query_vector = provider.embed([expanded_query])[0]

        sections = storage_service.get_sections(source_id)
        if not sections:
            return self._search_flat(source_id, query_tokens, query_vector, top_k, query_text=expanded_query, mode=mode)

        chunk_rows = storage_service.get_chunks(source_id)
        if not chunk_rows:
            return []
        chunk_by_id = {row["id"]: row for row in chunk_rows}

        scored_sections = self._score_sections(sections, query_tokens, query_vector, expanded_query, mode, state)
        filtered_query = {token for token in query_tokens if token not in STOPWORDS} or query_tokens
        effective_query_size = len(filtered_query)
        section_limit = max(3, min(8, top_k + 2))
        candidate_sections = scored_sections[:section_limit]

        results: list[dict] = []
        seen_chunk_ids: set[str] = set()

        for section_item in candidate_sections:
            section = section_item["section"]
            section_score = float(section_item["score"])
            facts = section.get("facts") or {}
            for chunk_id in section.get("chunk_ids", []):
                if chunk_id in seen_chunk_ids:
                    continue
                row = chunk_by_id.get(chunk_id)
                if row is None:
                    continue
                seen_chunk_ids.add(chunk_id)

                searchable = " ".join(
                    [
                        section.get("section_title") or "",
                        " ".join(section.get("keywords") or []),
                        " ".join(sum([values for values in facts.values() if isinstance(values, list)], [])),
                        row["content"],
                    ]
                )
                lexical = self._lexical_score(query_tokens, searchable)
                semantic = 0.0
                if query_vector is not None and row.get("embedding") is not None:
                    semantic = max(cosine(query_vector, row["embedding"]), 0.0)
                if lexical == 0.0 and effective_query_size >= 3:
                    continue
                if lexical == 0.0 and semantic < 0.35:
                    continue
                score = (0.50 * lexical) + (0.28 * semantic) + (0.14 * section_score)
                if mode == "exact_operational":
                    score += self._facts_bonus(expanded_query, facts)
                if score < (settings.retrieval_min_score * 0.8):
                    continue

                preview = row["content"][:280].strip()
                if section.get("section_title"):
                    preview = f"[{section['section_title']}] {preview}"

                results.append(
                    {
                        "chunk_id": row["id"],
                        "source_id": source_id,
                        "score": round(score, 6),
                        "preview": preview,
                        "text": row["content"],
                        "section_id": section.get("id"),
                        "section_title": section.get("section_title"),
                        "section_type": section.get("section_type"),
                        "page_start": section.get("page_start"),
                        "page_end": section.get("page_end"),
                        "facts": facts,
                    }
                )

        results.sort(key=lambda item: item["score"], reverse=True)
        if results:
            return results[:top_k]
        return self._search_flat(
            source_id,
            query_tokens,
            query_vector,
            top_k,
            sections=sections,
            query_text=expanded_query,
            mode=mode,
        )


retrieval_service = RetrievalService()
