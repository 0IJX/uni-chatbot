from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

import requests

from app.core.config import settings


class OllamaProvider:
    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.chat_model = settings.ollama_chat_model
        self.embedding_model = settings.ollama_embedding_model
        self.timeout = settings.ollama_timeout_seconds

    def health(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=8)
            return response.ok
        except requests.RequestException:
            return False

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return (
            data.get("message", {}).get("content", "").strip()
            or "I could not generate a response."
        )

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.2},
        }
        with requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    packet = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                token = packet.get("message", {}).get("content")
                if token:
                    yield token

    def embed(self, texts: Iterable[str]) -> list[list[float] | None]:
        vectors: list[list[float] | None] = []
        for text in texts:
            try:
                payload = {"model": self.embedding_model, "prompt": text}
                response = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload,
                    timeout=self.timeout,
                )
                if not response.ok:
                    vectors.append(None)
                    continue
                data = response.json()
                embedding = data.get("embedding")
                if isinstance(embedding, list) and embedding:
                    vectors.append([float(v) for v in embedding])
                else:
                    vectors.append(None)
            except (requests.RequestException, ValueError, TypeError):
                vectors.append(None)
        return vectors


provider = OllamaProvider()
