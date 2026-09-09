"""LLM provider abstraction for API-based and local completion backends."""

import os
import json
import logging
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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

        models_to_try = [self.model_name] if self.model_name else []
        for cand in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-1.5-flash", "gemma-4-26b-a4b-it"]:
            if cand not in models_to_try:
                models_to_try.append(cand)

        last_err = None
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.model_name = model
                    return data["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in [404, 400, 429]:
                    logger.debug(f"Gemini model {model} failed ({e.code}), trying next candidate...")
                    continue
                raise
        if last_err:
            raise last_err
        return ""


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

    def generate_multimodal(
        self,
        prompt: str,
        images: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """Generate response with multimodal image context (supported natively on Gemini)."""
        if self.provider_type == "builtin":
            detected = self._detect_provider()
            if detected != "builtin":
                self.provider_type = detected

        if self.provider_type != "gemini":
            # Fallback to text-only generation if provider is not Gemini
            return self.generate(prompt, system_prompt=system_prompt, temperature=temperature)

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return self.generate(prompt, system_prompt=system_prompt, temperature=temperature)

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will answer strictly using the verified evidence, tables, and images provided."}]})

        user_parts: List[Dict[str, Any]] = [{"text": prompt}]
        for img in images:
            b64_data = img.get("data", "")
            mime = img.get("mime_type", "image/png")
            if b64_data:
                user_parts.append({
                    "inlineData": {
                        "mimeType": mime,
                        "data": b64_data
                    }
                })

        contents.append({"role": "user", "parts": user_parts})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature}
        }

        models_to_try = [self.model_name] if self.model_name else []
        for cand in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-1.5-flash", "gemma-4-26b-a4b-it"]:
            if cand not in models_to_try:
                models_to_try.append(cand)

        last_err = None
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.model_name = model
                    return data["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in [404, 400, 429]:
                    logger.debug(f"Multimodal Gemini model {model} failed ({e.code}), trying next...")
                    continue
                break
            except Exception as e:
                logger.warning(f"Multimodal Gemini call error on {model}: {e}")
                break

        logger.warning(f"All multimodal Gemini candidate calls failed. Falling back to text generation. Last error: {last_err}")
        return self.generate(prompt, system_prompt=system_prompt, temperature=temperature)

    def set_api_key(self, api_key: str, provider: str = "gemini"):
        """Dynamically configure API key at runtime and persist to .env."""
        clean_key = api_key.strip()
        if provider == "gemini":
            os.environ["GEMINI_API_KEY"] = clean_key
            self.provider_type = "gemini" if clean_key else self._detect_provider()
            self.model_name = "gemini-3.6-flash"
        elif provider == "openai":
            os.environ["OPENAI_API_KEY"] = clean_key
            self.provider_type = "openai" if clean_key else self._detect_provider()
            self.model_name = "gpt-4o-mini"


        # Try persisting to .env file in workspace root
        try:
            env_path = Path(".env")
            lines = []
            key_var = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
            key_found = False
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith(f"{key_var}="):
                            lines.append(f'{key_var}="{clean_key}"\n')
                            key_found = True
                        else:
                            lines.append(line)
            if not key_found:
                lines.append(f'{key_var}="{clean_key}"\n')
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            logger.warning(f"Could not persist API key to .env: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Return runtime status of LLM provider."""
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        masked_key = (gemini_key[:4] + "..." + gemini_key[-4:]) if len(gemini_key) > 8 else ("Set" if gemini_key else "")
        return {
            "provider": self.provider_type,
            "is_active": self.is_active(),
            "model_name": self.model_name or ("gemini-1.5-flash" if self.provider_type == "gemini" else "builtin"),
            "has_gemini": bool(gemini_key),
            "masked_key": masked_key
        }


default_llm_provider = LLMProvider()
