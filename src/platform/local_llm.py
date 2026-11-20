"""Optional Ollama chat client restricted to a local loopback endpoint."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class LocalLLMUnavailable(RuntimeError):
    pass


class LocalOllamaChat:
    def __init__(self) -> None:
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", "gemma4:e2b").strip()
        self.enabled = os.environ.get("SUPPORT_LLM_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
        try:
            self.timeout = min(180, max(5, int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90"))))
        except ValueError:
            self.timeout = 90
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("OLLAMA_BASE_URL must point to a local HTTP loopback address.")

    def status(self) -> dict[str, str | bool]:
        if not self.enabled:
            return {"enabled": False, "ready": False, "provider": "ollama", "model": self.model, "message": "Local LLM is disabled."}
        try:
            data = self._request("/api/tags", timeout=2)
        except (LocalLLMUnavailable, TimeoutError, OSError):
            return {"enabled": True, "ready": False, "provider": "ollama", "model": self.model, "message": "Ollama is not running locally. Documentation search remains available."}
        names = {str(item.get("name", "")) for item in data.get("models", []) if isinstance(item, dict)}
        ready = self.model in names or any(name.startswith(self.model + ":") or self.model.startswith(name + ":") for name in names)
        message = "Local model ready. Ticket context stays on this computer." if ready else f"Ollama is running, but {self.model} is not downloaded. Documentation search remains available."
        return {"enabled": True, "ready": ready, "provider": "ollama", "model": self.model, "message": message}

    def chat(self, system_prompt: str, history: list[dict[str, str]], question: str) -> str:
        if not self.enabled:
            raise LocalLLMUnavailable("Local LLM is disabled.")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-8:])
        messages.append({"role": "user", "content": question})
        try:
            data = self._request("/api/chat", payload={"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0.2}}, timeout=self.timeout)
        except (TimeoutError, OSError) as error:
            raise LocalLLMUnavailable("The local model could not be reached. Documentation search is still available.") from error
        except LocalLLMUnavailable:
            raise
        answer = data.get("message", {}).get("content") if isinstance(data.get("message"), dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise LocalLLMUnavailable("The local model returned an empty answer. Documentation search is still available.")
        return answer.strip()[:4_000]

    def _request(self, path: str, *, payload: dict | None = None, timeout: int) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + path, data=data, headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read(1_000_000).decode("utf-8"))
        except HTTPError as error:
            detail = error.read(2_000).decode("utf-8", "replace")
            raise LocalLLMUnavailable(f"Ollama request failed ({error.code}): {detail[:300]}") from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise LocalLLMUnavailable("Ollama is not reachable on this computer.") from error
        if not isinstance(result, dict):
            raise LocalLLMUnavailable("Ollama returned an invalid response.")
        return result
