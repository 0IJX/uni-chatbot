from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.provider import provider
from app.services.retrieval_service import retrieval_service
from app.services.storage_service import storage_service


COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,5}\s?\d{3}\b")
COMPARE_RE = re.compile(
    r"(?:compare|difference between|differences between|compare between)\s+(.+?)\s+(?:and|with|vs\.?|versus)\s+(.+)",
    re.I,
)
LIVE_EXTERNAL_RE = re.compile(
    r"\b(weather|temperature|forecast|news|headline|stock|stocks|bitcoin|btc|eth|traffic|today's weather|latest news)\b",
    re.I,
)
GREETING_RE = re.compile(r"^\s*(hi|hello|hey|heyy|helo|good morning|good afternoon|good evening)\b[!. ]*$", re.I)
CAPABILITY_RE = re.compile(
    r"\b(what can you do|help me|who are you|your name|capabilities|how can you help)\b",
    re.I,
)
SHORT_FOLLOW_UP_RE = re.compile(
    r"^\s*(and\s+)?(what about|how about|and|then|also|too)?\s*(it|that|this|them|major|program|the second one|the first one|year two|year 2|requirements|labs?|schedule|week|exam|attendance)\b",
    re.I,
)

PERSONAL_HINTS = (
    "my syllabus",
    "my exam",
    "my schedule",
    "my course",
    "my file",
    "this file",
    "uploaded file",
    "uploaded syllabus",
    "uploaded schedule",
    "this week",
    "my week",
)
INSTITUTIONAL_HINTS = (
    "institution",
    "catalog",
    "official",
    "program",
    "major",
    "degree",
    "requirements",
    "admission",
    "study plan",
    "curriculum",
)
ACADEMIC_HINTS = (
    "course",
    "courses",
    "major",
    "program",
    "requirement",
    "requirements",
    "schedule",
    "semester",
    "cgpa",
    "lab",
    "labs",
    "prerequisite",
    "credits",
    "attendance",
    "exam",
)
EXACT_HINTS = (
    "when",
    "date",
    "time",
    "where",
    "location",
    "room",
    "deadline",
    "due",
    "attendance",
    "week",
    "exam",
    "midterm",
    "final",
)
LIST_HINTS = ("list", "all", "which", "show me")
SUMMARY_HINTS = ("summarize", "summary", "briefly explain", "short summary")
STUDY_PLAN_HINTS = ("study plan", "plan my semester", "plan my courses", "what should i take", "make me a study plan")
COMPARE_HINTS = ("compare", "difference", "vs", "versus")
NO_LIVE_FACT_GUIDANCE = (
    "I can help with academic topics, your uploaded files, and general academic guidance, "
    "but I can't verify live external facts like weather or current news from this local setup."
)

ENTITY_ALIASES = {
    "ai": "Artificial Intelligence",
    "artificial intelligence": "Artificial Intelligence",
    "bs of ai": "Bachelor of Science in Artificial Intelligence",
    "computer science": "Computer Science",
    "cs": "Computer Science",
    "business administration": "Business Administration",
    "ba": "Business Administration",
    "architecture": "Architecture",
    "psychology": "Psychology",
    "biotechnology": "Biotechnology",
    "mechanical engineering": "Mechanical Engineering",
    "electrical engineering": "Electrical and Electronics Engineering",
    "civil engineering": "Civil Engineering",
    "chemical engineering": "Chemical Engineering",
}


@dataclass
class TurnPlan:
    mode: str
    answer_mode: str
    primary_source_id: str | None
    secondary_source_ids: list[str]
    selected_source_id: str | None
    selected_upload_source_id: str | None
    query_text: str
    active_entity: str | None
    comparison_pair: list[str]
    topic_hint: str | None
    exact_target: str | None
    live_external: bool
    greeting: bool
    capability: bool
    prefers_list: bool


@dataclass
class PreparedTurn:
    conversation_id: str
    source_id: str
    user_message: str
    plan: TurnPlan
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    messages: list[dict[str, str]]
    reply_override: str | None
    next_state: dict[str, Any]


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def dedupe_keep_order(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = normalize_text(value)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        output.append(clean)
        seen.add(key)
    return output


def clean_reply(text: str) -> str:
    cleaned = (text or "").strip()
    patterns = [
        r"^based on (?:the )?(?:retrieved|provided|available) (?:evidence|information|context)[,:]?\s*",
        r"^from (?:the )?(?:retrieved|provided|available) (?:evidence|information|context)[,:]?\s*",
        r"^according to (?:the )?(?:retrieved|provided|available) (?:evidence|information|context)[,:]?\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.I)
    return cleaned.strip() or "I couldn't put together a useful answer from the current material."


def source_label(source_id: str | None) -> str:
    if not source_id:
        return "general context"
    source = storage_service.get_source(source_id)
    return source["name"] if source else source_id


class ChatService:
    def complete(
        self,
        user_message: str,
        conversation_id: str | None = None,
        requested_source_id: str | None = None,
    ) -> dict[str, Any]:
        turn = self._prepare_turn(
            user_message=user_message,
            conversation_id=conversation_id,
            requested_source_id=requested_source_id,
        )

        reply = turn.reply_override
        if reply is None:
            try:
                reply = clean_reply(provider.chat(turn.messages))
            except Exception:
                reply = self._build_provider_failure_reply(turn)

        self._save_assistant_reply(turn.conversation_id, reply)

        return {
            "conversation_id": turn.conversation_id,
            "source_id": turn.source_id,
            "reply": reply,
            "citations": turn.citations,
        }

    def stream(
        self,
        user_message: str,
        conversation_id: str | None = None,
        requested_source_id: str | None = None,
    ) -> dict[str, Any]:
        turn = self._prepare_turn(
            user_message=user_message,
            conversation_id=conversation_id,
            requested_source_id=requested_source_id,
        )

        if turn.reply_override is not None:
            reply = turn.reply_override

            def token_iterator() -> Any:
                yield reply

            return {
                "conversation_id": turn.conversation_id,
                "source_id": turn.source_id,
                "evidence": turn.citations,
                "token_iterator": token_iterator,
            }

        def token_iterator() -> Any:
            try:
                yielded = False
                for token in provider.stream_chat(turn.messages):
                    yielded = True
                    yield token
                if not yielded:
                    yield self._build_provider_failure_reply(turn)
            except Exception:
                yield self._build_provider_failure_reply(turn)

        return {
            "conversation_id": turn.conversation_id,
            "source_id": turn.source_id,
            "evidence": turn.citations,
            "token_iterator": token_iterator,
        }

    def save_stream_reply(self, conversation_id: str, reply: str) -> None:
        self._save_assistant_reply(conversation_id, clean_reply(reply))

    def _save_assistant_reply(self, conversation_id: str, reply: str) -> None:
        storage_service.add_message(conversation_id, "assistant", reply)

    def _prepare_turn(
        self,
        user_message: str,
        conversation_id: str | None,
        requested_source_id: str | None,
    ) -> PreparedTurn:
        conversation = storage_service.ensure_conversation(conversation_id)
        conversation_id = conversation["id"]

        if requested_source_id and storage_service.get_source(requested_source_id):
            storage_service.set_conversation_source(conversation_id, requested_source_id)

        prior_messages = storage_service.get_messages(conversation_id)
        previous_state = storage_service.get_conversation_state(conversation_id)

        storage_service.add_message(conversation_id, "user", user_message)

        plan = self._plan_turn(
            user_message=user_message,
            conversation_id=conversation_id,
            requested_source_id=requested_source_id,
            previous_state=previous_state,
            prior_messages=prior_messages,
        )

        evidence = self._collect_evidence(plan, previous_state)
        citations = [
            {
                "chunk_id": item["chunk_id"],
                "source_id": item["source_id"],
                "score": float(item["score"]),
                "preview": item["preview"],
                "section_title": item.get("section_title"),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
            }
            for item in evidence
        ]

        reply_override: str | None = None
        exact_summary = None

        if plan.greeting:
            reply_override = (
                "Hello. I can help with catalog questions, your uploaded syllabus or schedule, "
                "and general academic guidance."
            )
        elif plan.capability:
            reply_override = (
                "I can explain academic programs, compare majors, answer questions from your uploaded files, "
                "help with study planning, and tell you clearly when the current material is missing something important."
            )
        elif plan.live_external:
            reply_override = NO_LIVE_FACT_GUIDANCE
        elif plan.mode == "general_reasoning":
            reply_override = None
        elif plan.mode == "exact_operational":
            exact_summary = self._analyze_exact_evidence(user_message, evidence)
            if exact_summary["status"] != "exact":
                reply_override = self._build_exact_guard_reply(plan, evidence, exact_summary)
        elif not evidence:
            reply_override = self._build_no_evidence_reply(plan)

        model_messages: list[dict[str, str]] = []
        if reply_override is None:
            model_messages = self._build_model_messages(
                user_message=user_message,
                plan=plan,
                evidence=evidence,
                prior_messages=prior_messages,
                exact_summary=exact_summary,
            )

        next_state = self._build_next_state(previous_state, plan, evidence, user_message)
        storage_service.set_conversation_state(conversation_id, next_state)

        source_id = plan.primary_source_id or plan.selected_source_id or "general"

        return PreparedTurn(
            conversation_id=conversation_id,
            source_id=source_id,
            user_message=user_message,
            plan=plan,
            evidence=evidence,
            citations=citations,
            messages=model_messages,
            reply_override=reply_override,
            next_state=next_state,
        )

    def _plan_turn(
        self,
        user_message: str,
        conversation_id: str,
        requested_source_id: str | None,
        previous_state: dict[str, Any],
        prior_messages: list[dict[str, Any]],
    ) -> TurnPlan:
        text = normalize_text(user_message)
        text_lc = text.lower()

        sources = {row["id"]: row for row in storage_service.list_sources()}
        catalog_source_id = next((sid for sid, row in sources.items() if row.get("kind") == "catalog"), None)
        stored_source_id = storage_service.get_conversation_source(conversation_id)
        requested_exists = requested_source_id if requested_source_id in sources else None
        selected_source_id = requested_exists or (stored_source_id if stored_source_id in sources else None)
        explicit_upload_selection = bool(
            requested_exists and sources[requested_exists]["kind"] == "upload"
        )

        selected_upload_source_id: str | None = None
        candidate_uploads = [
            requested_exists if requested_exists and sources[requested_exists]["kind"] == "upload" else None,
            selected_source_id if selected_source_id and sources[selected_source_id]["kind"] == "upload" else None,
            previous_state.get("last_primary_source_id")
            if previous_state.get("last_primary_source_id") in sources
            and sources[previous_state["last_primary_source_id"]]["kind"] == "upload"
            else None,
        ]
        for candidate in candidate_uploads:
            if candidate:
                selected_upload_source_id = candidate
                break

        greeting = bool(GREETING_RE.match(text))
        capability = bool(CAPABILITY_RE.search(text))
        live_external = bool(LIVE_EXTERNAL_RE.search(text_lc))

        personal = any(phrase in text_lc for phrase in PERSONAL_HINTS)
        institutional = any(token in text_lc for token in INSTITUTIONAL_HINTS)
        compare = any(token in text_lc for token in COMPARE_HINTS) or bool(COMPARE_RE.search(text))
        summary = any(token in text_lc for token in SUMMARY_HINTS)
        study_guidance = any(token in text_lc for token in STUDY_PLAN_HINTS)
        open_guidance = (
            "study better" in text_lc
            or text_lc.startswith("how can i study")
            or text_lc.startswith("how should i study")
            or "study tips" in text_lc
        )
        academic = (
            institutional
            or any(token in text_lc for token in ACADEMIC_HINTS)
            or bool(COURSE_CODE_RE.search(text))
            or compare
            or study_guidance
        )
        prefers_list = any(token in text_lc for token in LIST_HINTS)
        exact_operational = any(token in text_lc for token in EXACT_HINTS)
        mixed = (
            ("catalog" in text_lc or "institution" in text_lc or "official" in text_lc)
            and ("my " in text_lc or "uploaded" in text_lc or "this file" in text_lc)
        ) or ("based on my" in text_lc and ("catalog" in text_lc or "institution" in text_lc))

        is_follow_up = self._looks_like_follow_up(text, previous_state)
        comparison_pair = self._extract_comparison_pair(text, previous_state)
        active_entity = self._extract_active_entity(text, previous_state, comparison_pair)
        topic_hint = self._extract_topic_hint(text, previous_state, active_entity)
        exact_target = self._extract_exact_target(text, previous_state)

        answer_mode = "direct_answer"
        if compare:
            answer_mode = "compare"
        elif summary:
            answer_mode = "summary"
        elif study_guidance:
            answer_mode = "study_guidance"
        elif exact_operational:
            answer_mode = "exact_detail"

        mode = "general_reasoning"
        primary_source_id: str | None = None
        secondary_source_ids: list[str] = []

        if live_external:
            mode = "general_reasoning"
        elif mixed and selected_upload_source_id and catalog_source_id:
            mode = "exact_operational" if exact_operational else "mixed_academic"
            primary_source_id = selected_upload_source_id
            secondary_source_ids = [catalog_source_id]
        elif exact_operational and selected_upload_source_id and (personal or is_follow_up or not institutional):
            mode = "exact_operational"
            primary_source_id = selected_upload_source_id
            if institutional and catalog_source_id and catalog_source_id != primary_source_id:
                secondary_source_ids = [catalog_source_id]
        elif open_guidance and not personal and not exact_operational:
            mode = "general_reasoning"
        elif selected_upload_source_id and not institutional and (
            personal
            or is_follow_up
            or summary
            or (academic and explicit_upload_selection)
            or (study_guidance and explicit_upload_selection)
        ):
            mode = "upload_personal"
            primary_source_id = selected_upload_source_id
        elif catalog_source_id and (
            institutional
            or compare
            or (study_guidance and not explicit_upload_selection and not personal)
            or (academic and not selected_upload_source_id)
        ):
            mode = "exact_operational" if exact_operational else "catalog_background"
            primary_source_id = catalog_source_id
        elif selected_upload_source_id and academic and explicit_upload_selection:
            mode = "upload_personal"
            primary_source_id = selected_upload_source_id
        elif catalog_source_id and previous_state.get("active_source_mode") in {"catalog_background", "mixed_academic"} and is_follow_up:
            mode = "catalog_background"
            primary_source_id = catalog_source_id

        if primary_source_id and catalog_source_id and catalog_source_id != primary_source_id:
            if mixed or (
                mode in {"upload_personal", "exact_operational"}
                and ("catalog" in text_lc or "official" in text_lc)
            ):
                secondary_source_ids = dedupe_keep_order([*secondary_source_ids, catalog_source_id])

        if is_follow_up and not primary_source_id:
            previous_primary = previous_state.get("last_primary_source_id")
            if previous_primary in sources:
                primary_source_id = previous_primary
                if previous_state.get("active_source_mode") == "exact_operational":
                    mode = "exact_operational"
                elif sources[previous_primary]["kind"] == "catalog":
                    mode = "catalog_background"
                else:
                    mode = "upload_personal"

        query_parts = [text]
        if active_entity and active_entity.lower() not in text_lc:
            query_parts.append(active_entity)
        if topic_hint and topic_hint.lower() not in text_lc:
            query_parts.append(topic_hint)
        if exact_target and exact_target not in text_lc and mode == "exact_operational":
            query_parts.append(exact_target)
        if comparison_pair:
            for item in comparison_pair:
                if item.lower() not in text_lc:
                    query_parts.append(item)
        if is_follow_up and previous_state.get("last_user_message"):
            query_parts.append(previous_state["last_user_message"])

        query_text = " ".join(dedupe_keep_order(query_parts))

        return TurnPlan(
            mode=mode,
            answer_mode=answer_mode,
            primary_source_id=primary_source_id,
            secondary_source_ids=dedupe_keep_order(secondary_source_ids),
            selected_source_id=selected_source_id,
            selected_upload_source_id=selected_upload_source_id,
            query_text=query_text,
            active_entity=active_entity,
            comparison_pair=comparison_pair,
            topic_hint=topic_hint,
            exact_target=exact_target,
            live_external=live_external,
            greeting=greeting,
            capability=capability,
            prefers_list=prefers_list,
        )

    def _looks_like_follow_up(self, text: str, previous_state: dict[str, Any]) -> bool:
        text_lc = text.lower()
        if SHORT_FOLLOW_UP_RE.match(text):
            return True
        if any(token in text_lc for token in ("this one", "that one", "the second one", "the first one", "that course")):
            return True
        return False

    def _extract_active_entity(
        self,
        text: str,
        previous_state: dict[str, Any],
        comparison_pair: list[str],
    ) -> str | None:
        course_codes = dedupe_keep_order([re.sub(r"\s+", " ", value).strip() for value in COURSE_CODE_RE.findall(text)])
        if course_codes:
            return course_codes[0]

        lowered = text.lower()
        for alias, label in ENTITY_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return label

        if "second one" in lowered and len(comparison_pair) >= 2:
            return comparison_pair[1]
        if "first one" in lowered and comparison_pair:
            return comparison_pair[0]
        if any(token in lowered for token in ("this course", "that course", "it", "this one", "that one")):
            return previous_state.get("active_entity")
        return previous_state.get("active_entity")

    def _extract_comparison_pair(self, text: str, previous_state: dict[str, Any]) -> list[str]:
        match = COMPARE_RE.search(text)
        if match:
            left = self._normalize_entity_phrase(match.group(1))
            right = self._normalize_entity_phrase(match.group(2))
            return [item for item in [left, right] if item]
        if any(token in text.lower() for token in ("second one", "first one")):
            existing = previous_state.get("active_compare_pair") or []
            return [item for item in existing if item]
        existing = previous_state.get("active_compare_pair") or []
        return [item for item in existing if item]

    def _normalize_entity_phrase(self, text: str) -> str:
        value = normalize_text(text).strip("?.!,;:")
        lowered = value.lower()
        for alias, label in ENTITY_ALIASES.items():
            if lowered == alias:
                return label
        return value

    def _extract_topic_hint(self, text: str, previous_state: dict[str, Any], active_entity: str | None) -> str | None:
        lowered = text.lower()
        if "requirements" in lowered or "requirement" in lowered:
            return f"{active_entity or previous_state.get('last_grounded_topic') or 'program'} requirements"
        if "study plan" in lowered or "year 1" in lowered or "year one" in lowered or "year 2" in lowered or "year two" in lowered:
            return f"{active_entity or previous_state.get('last_grounded_topic') or 'program'} study plan"
        if "labs" in lowered or "lab" in lowered:
            return f"{active_entity or previous_state.get('last_grounded_topic') or 'course'} labs"
        if "attendance" in lowered:
            return f"{active_entity or previous_state.get('last_grounded_topic') or 'course'} attendance policy"
        if "exam" in lowered:
            return f"{active_entity or previous_state.get('last_grounded_topic') or 'course'} exam"
        return active_entity or previous_state.get("last_grounded_topic")

    def _extract_exact_target(self, text: str, previous_state: dict[str, Any]) -> str | None:
        lowered = text.lower()
        if "where" in lowered or "location" in lowered or "room" in lowered:
            return "location"
        if "time" in lowered:
            return "time"
        if "deadline" in lowered or "due" in lowered:
            return "deadline"
        if "attendance" in lowered:
            return "attendance"
        if "week" in lowered or "this week" in lowered:
            return "week"
        if "exam" in lowered or "midterm" in lowered or "final" in lowered:
            return previous_state.get("last_exact_target") or "exam date"
        if "when" in lowered or "date" in lowered:
            return previous_state.get("last_exact_target") or "date"
        return previous_state.get("last_exact_target")

    def _collect_evidence(self, plan: TurnPlan, previous_state: dict[str, Any]) -> list[dict[str, Any]]:
        if not plan.primary_source_id and not plan.secondary_source_ids:
            return []

        source_ids = dedupe_keep_order(
            [value for value in [plan.primary_source_id, *plan.secondary_source_ids] if value]
        )
        aggregated: list[dict[str, Any]] = []
        per_source_limit = max(settings.retrieval_top_k, 4)

        for source_id in source_ids:
            hits = retrieval_service.search(
                source_id=source_id,
                query=plan.query_text,
                top_k=per_source_limit,
                mode=plan.mode,
                state=previous_state,
            )
            role_boost = 0.08 if source_id == plan.primary_source_id else 0.03
            for hit in hits:
                adjusted = dict(hit)
                adjusted["score"] = round(float(hit["score"]) + role_boost, 6)
                aggregated.append(adjusted)

        if len(source_ids) > 1:
            primary = [item for item in aggregated if item["source_id"] == plan.primary_source_id][:4]
            secondary = [item for item in aggregated if item["source_id"] != plan.primary_source_id][:3]
            combined = primary + secondary
            combined.sort(key=lambda item: float(item["score"]), reverse=True)
            if combined:
                return combined[: settings.retrieval_top_k]

        aggregated.sort(key=lambda item: float(item["score"]), reverse=True)
        if aggregated:
            return aggregated[: settings.retrieval_top_k]

        if plan.primary_source_id and plan.comparison_pair:
            comparison_hits: list[dict[str, Any]] = []
            for item in plan.comparison_pair:
                comparison_hits.extend(
                    retrieval_service.search(
                        source_id=plan.primary_source_id,
                        query=item,
                        top_k=2,
                        mode=plan.mode,
                        state=previous_state,
                    )
                )
            deduped: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in sorted(comparison_hits, key=lambda row: float(row["score"]), reverse=True):
                if item["chunk_id"] in seen:
                    continue
                deduped.append(item)
                seen.add(item["chunk_id"])
            if deduped:
                return deduped[: settings.retrieval_top_k]

        if plan.primary_source_id and plan.answer_mode == "summary":
            return self._seed_source_evidence(plan.primary_source_id)

        return []

    def _seed_source_evidence(self, source_id: str, limit: int = 3) -> list[dict[str, Any]]:
        sections = storage_service.get_sections(source_id)
        section_lookup: dict[str, dict[str, Any]] = {}
        for section in sections:
            for chunk_id in section.get("chunk_ids", []):
                section_lookup[chunk_id] = section

        output: list[dict[str, Any]] = []
        for row in storage_service.get_chunks(source_id)[:limit]:
            section = section_lookup.get(row["id"], {})
            preview = row["content"][:280].strip()
            if section.get("section_title"):
                preview = f"[{section['section_title']}] {preview}"
            output.append(
                {
                    "chunk_id": row["id"],
                    "source_id": source_id,
                    "score": 0.25,
                    "preview": preview,
                    "text": row["content"],
                    "section_id": section.get("id"),
                    "section_title": section.get("section_title"),
                    "section_type": section.get("section_type"),
                    "page_start": section.get("page_start"),
                    "page_end": section.get("page_end"),
                    "facts": section.get("facts") or {},
                }
            )
        return output

    def _build_model_messages(
        self,
        user_message: str,
        plan: TurnPlan,
        evidence: list[dict[str, Any]],
        prior_messages: list[dict[str, Any]],
        exact_summary: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        system_prompt = (
            "You are the Local Academic AI Assistant. Treat the catalog as institutional knowledge, "
            "treat uploaded files as user-specific context, and answer like a thoughtful academic assistant instead of a search engine.\n"
            "\n"
            "Rules:\n"
            "- Answer the user's real intent first.\n"
            "- Use evidence for factual claims, but do not say phrases like 'based on the retrieved evidence'.\n"
            "- If both catalog and uploads are used, make the relationship clear: upload = personal context, catalog = institutional baseline.\n"
            "- Explain what is known, and state uncertainty plainly when evidence is partial.\n"
            "- Do not invent dates, times, locations, deadlines, or academic rules.\n"
            "- Use natural prose by default. Use bullets only when the question is clearly list-shaped or a comparison really benefits from structure.\n"
            "- If the question asks why a course matters, explain its purpose and how it fits the path supported by the evidence.\n"
        )

        history_messages = [
            {"role": row["role"], "content": row["content"]}
            for row in prior_messages[-6:]
            if row["role"] in {"user", "assistant"} and row["content"].strip()
        ]

        source_context_lines: list[str] = [
            f"Intent mode: {plan.mode}",
            f"Answer mode: {plan.answer_mode}",
        ]
        if plan.primary_source_id:
            source_context_lines.append(
                f"Primary source: {source_label(plan.primary_source_id)}"
            )
        if plan.secondary_source_ids:
            source_context_lines.append(
                "Secondary source(s): " + ", ".join(source_label(item) for item in plan.secondary_source_ids)
            )
        if plan.active_entity:
            source_context_lines.append(f"Active entity/topic: {plan.active_entity}")
        if plan.comparison_pair:
            source_context_lines.append("Comparison target(s): " + " vs ".join(plan.comparison_pair))
        if exact_summary:
            source_context_lines.append(
                f"Exact-detail evidence status: {exact_summary['status']}"
            )

        if evidence:
            evidence_lines = []
            for index, item in enumerate(evidence, start=1):
                section_bits = [source_label(item["source_id"])]
                if item.get("section_title"):
                    section_bits.append(f"section: {item['section_title']}")
                if item.get("page_start"):
                    if item.get("page_end") and item["page_end"] != item["page_start"]:
                        section_bits.append(f"pages {item['page_start']}-{item['page_end']}")
                    else:
                        section_bits.append(f"page {item['page_start']}")
                evidence_lines.append(
                    f"[{index}] {' | '.join(section_bits)}\n{normalize_text(item.get('text') or item.get('preview') or '')[:520]}"
                )
            evidence_block = "\n\n".join(evidence_lines)
        else:
            evidence_block = "No document evidence is required for this answer."

        presentation = "Use bullets." if plan.prefers_list or plan.answer_mode == "compare" else "Answer in natural prose."
        user_prompt = (
            "\n".join(source_context_lines)
            + "\n\n"
            + f"Presentation: {presentation}\n"
            + "\nEvidence:\n"
            + evidence_block
            + "\n\n"
            + f"User question: {user_message}\n"
        )

        return [{"role": "system", "content": system_prompt}, *history_messages, {"role": "user", "content": user_prompt}]

    def _build_next_state(
        self,
        previous_state: dict[str, Any],
        plan: TurnPlan,
        evidence: list[dict[str, Any]],
        user_message: str,
    ) -> dict[str, Any]:
        next_state = dict(previous_state or {})

        if plan.mode != "general_reasoning" or evidence:
            next_state["active_source_mode"] = plan.mode
        if plan.active_entity:
            next_state["active_entity"] = plan.active_entity
        if plan.comparison_pair:
            next_state["active_compare_pair"] = plan.comparison_pair
        if plan.topic_hint:
            next_state["last_grounded_topic"] = plan.topic_hint
        elif plan.active_entity:
            next_state["last_grounded_topic"] = plan.active_entity
        if plan.exact_target:
            next_state["last_exact_target"] = plan.exact_target
        if plan.primary_source_id:
            next_state["last_primary_source_id"] = plan.primary_source_id
        if evidence:
            next_state["last_section_ids"] = [item.get("section_id") for item in evidence if item.get("section_id")]
            next_state["last_section_titles"] = [item.get("section_title") for item in evidence if item.get("section_title")]
        next_state["last_user_message"] = normalize_text(user_message)
        return next_state

    def _analyze_exact_evidence(self, user_message: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        target = self._extract_exact_target(user_message, {})
        details_by_kind: dict[str, list[str]] = {"dates": [], "times": [], "locations": [], "weeks": []}
        per_source: dict[str, dict[str, list[str]]] = {}

        for item in evidence:
            source_id = item["source_id"]
            per_source.setdefault(source_id, {"dates": [], "times": [], "locations": [], "weeks": []})
            facts = item.get("facts") or {}
            for key in details_by_kind:
                values = facts.get(key) or []
                details_by_kind[key].extend(values)
                per_source[source_id][key].extend(values)

        for key in details_by_kind:
            details_by_kind[key] = dedupe_keep_order(details_by_kind[key])
        for source_id, values in per_source.items():
            for key in values:
                values[key] = dedupe_keep_order(values[key])

        relevant_keys = ["dates"]
        if target == "time":
            relevant_keys = ["times"]
        elif target == "location":
            relevant_keys = ["locations"]
        elif target == "week":
            relevant_keys = ["weeks"]
        elif target == "deadline":
            relevant_keys = ["dates", "times"]
        elif target == "exam date":
            relevant_keys = ["dates", "times", "locations", "weeks"]

        distinct_values = dedupe_keep_order(
            sum((details_by_kind[key] for key in relevant_keys), start=[])
        )
        non_empty_sources = {
            source_id: dedupe_keep_order(sum((values[key] for key in relevant_keys), start=[]))
            for source_id, values in per_source.items()
        }
        populated_sources = {sid: vals for sid, vals in non_empty_sources.items() if vals}

        supporting_any = any(details_by_kind[key] for key in details_by_kind)

        if target == "attendance" and evidence:
            status = "exact"
        elif len({tuple(values) for values in populated_sources.values() if values}) > 1:
            status = "conflict"
        elif distinct_values:
            status = "exact"
        elif supporting_any:
            status = "partial"
        else:
            status = "missing"

        return {
            "target": target or "exact detail",
            "status": status,
            "details": details_by_kind,
            "per_source": populated_sources,
        }

    def _build_exact_guard_reply(
        self,
        plan: TurnPlan,
        evidence: list[dict[str, Any]],
        exact_summary: dict[str, Any],
    ) -> str:
        target = exact_summary["target"]
        status = exact_summary["status"]

        if status == "conflict":
            source_bits = []
            for source_id, values in exact_summary["per_source"].items():
                source_bits.append(f"{source_label(source_id)} says {', '.join(values)}")
            return (
                f"I found conflicting {target} details in the current material. "
                + "; ".join(source_bits)
                + ". I wouldn't guess which one is correct without checking the latest official source."
            )

        if status == "partial" and evidence:
            snippets = []
            if exact_summary["details"]["dates"]:
                snippets.append("date: " + ", ".join(exact_summary["details"]["dates"][:2]))
            if exact_summary["details"]["times"]:
                snippets.append("time: " + ", ".join(exact_summary["details"]["times"][:2]))
            if exact_summary["details"]["locations"]:
                snippets.append("location: " + ", ".join(exact_summary["details"]["locations"][:2]))
            if exact_summary["details"]["weeks"]:
                snippets.append("week: " + ", ".join(exact_summary["details"]["weeks"][:2]))

            supported = "; ".join(snippets)
            if supported:
                return (
                    f"I found a likely match, but I can't fully verify the {target}. "
                    f"What the current material supports is {supported}. "
                    "If you want the exact confirmed detail, upload the specific schedule or exam notice."
                )
            return (
                f"I found related material, but not enough verified detail to answer the {target} confidently. "
                "I don't want to guess on something operational."
            )

        if plan.answer_mode == "exact_detail":
            return (
                f"I couldn't verify the {target} from the current catalog or uploaded file. "
                "I don't want to guess on an academic detail like that. "
                "If you upload the exact schedule, syllabus, or exam notice, I can check it precisely."
            )

        return self._build_no_evidence_reply(plan)

    def _build_no_evidence_reply(self, plan: TurnPlan) -> str:
        if plan.answer_mode == "study_guidance":
            return (
                "I couldn't find relevant evidence in the current material to build a verified study plan. "
                "If you want, I can still suggest a general study approach based on a typical course load."
            )
        if plan.answer_mode == "compare":
            return (
                "I couldn't find relevant evidence in the current source to make a reliable comparison. "
                "If you point me to the official catalog section or upload the program material, I can compare them properly."
            )
        if plan.mode == "exact_operational":
            return (
                "I couldn't find relevant evidence for that exact academic detail in the current material. "
                "I don't want to guess on dates, locations, deadlines, or rules."
            )
        return (
            "I couldn't find relevant evidence in the current catalog or selected file for that question. "
            "If you want, I can still help with a general explanation or tell you what source would answer it better."
        )

    def _build_provider_failure_reply(self, turn: PreparedTurn) -> str:
        evidence = turn.evidence
        if not evidence:
            return (
                "I couldn't reach Ollama just now, and I also don't have strong grounded evidence for a safe fallback answer. "
                "Please try again once Ollama is running."
            )

        if turn.plan.mode == "exact_operational":
            exact_summary = self._analyze_exact_evidence(turn.user_message, evidence)
            if exact_summary["status"] != "exact":
                return self._build_exact_guard_reply(turn.plan, evidence, exact_summary)

        strongest = evidence[:3]
        sections = dedupe_keep_order([item.get("section_title") or item["preview"][:80] for item in strongest])
        source_names = dedupe_keep_order([source_label(item["source_id"]) for item in strongest])

        if turn.plan.answer_mode == "compare":
            return (
                "Ollama is unavailable right now, but I did find relevant material. "
                f"The strongest evidence comes from {', '.join(source_names)} and focuses on {', '.join(sections[:3])}. "
                "I can turn that into a cleaner comparison once the model is back."
            )

        return (
            "Ollama is unavailable right now, but I did find relevant material. "
            f"The strongest sections are {', '.join(sections[:3])} from {', '.join(source_names)}."
        )


chat_service = ChatService()
