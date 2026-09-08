"""LLM provider abstraction for API-based and local completion backends."""

import os
import json
import logging
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class LLMProvider:
    """Provider for LLM completion across Gemini, OpenAI, Ollama, and builtin fallbacks."""

    def __init__(self, provider_type: str = "auto", model_name: Optional[str] = None):
        self.provider_type = provider_type
        self.model_name = model_name

        if self.provider_type == "auto":
            self.provider_type = self._detect_provider()

    def _detect_provider(self) -> str:
        if os.getenv("GEMINI_API_KEY"):
            return "gemini"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                if models:
                    if not self.model_name:
                        self.model_name = models[0]
                    logger.info(f"Ollama detected with active model '{self.model_name}'")
                    return "ollama"
        except Exception:
            pass
        return "builtin"

    def is_active(self) -> bool:
        """Check if a generative LLM backend is available."""
        return self.provider_type in ["gemini", "openai", "ollama"]

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        as_json: bool = False
    ) -> str:
        """Generate text completion from the configured LLM backend."""
        # Re-detect if previously builtin in case an engine was started
        if self.provider_type == "builtin":
            detected = self._detect_provider()
            if detected != "builtin":
                self.provider_type = detected

        if self.provider_type == "gemini":
            return self._call_gemini(prompt, system_prompt, temperature, as_json=as_json)
        elif self.provider_type == "openai":
            return self._call_openai(prompt, system_prompt, temperature, as_json=as_json)
        elif self.provider_type == "ollama":
            return self._call_ollama(prompt, system_prompt, as_json=as_json)
        return ""

    def _call_gemini(self, prompt: str, system_prompt: Optional[str], temperature: float, as_json: bool = False) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        model = self.model_name or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        gen_config: Dict[str, Any] = {"temperature": temperature}
        if as_json:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": contents,
            "generationConfig": gen_config
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_openai(self, prompt: str, system_prompt: Optional[str], temperature: float, as_json: bool = False) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        model = self.model_name or "gpt-4o-mini"
        url = "https://api.openai.com/v1/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        if as_json:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def _call_ollama(self, prompt: str, system_prompt: Optional[str], as_json: bool = False) -> str:
        url = "http://localhost:11434/api/generate"
        payload: Dict[str, Any] = {
            "model": self.model_name or "llama3.2",
            "prompt": prompt,
            "system": system_prompt or "You are a professional Document Intelligence AI assistant. Answer accurately based on verified facts.",
            "stream": False
        }
        if as_json:
            payload["format"] = "json"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
