"""
=============================================================
COGNITIVE ENGINE — ReAct Framework via Ollama
=============================================================
Calls Qwen 2.5:7B locally through Ollama REST API.
Forces THOUGHT → ACTION structured output (JSON).
=============================================================
"""

import json
import logging
import requests

log = logging.getLogger(__name__)

import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
OLLAMA_PORT = os.environ.get("OLLAMA_PORT", "11434")
OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate"
OLLAMA_TAGS_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags"


class CognitiveEngine:
    def __init__(self, model: str = "qwen2.5:7b"):
        self.model = model
        self._verify_connection()

    def _verify_connection(self):
        try:
            r = requests.get(OLLAMA_TAGS_URL, timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            if not any(self.model in m for m in models):
                log.warning(f"⚠️  Model '{self.model}' not found in Ollama. Run: ollama pull {self.model}")
            else:
                log.info(f"✅ Ollama connected | Model: {self.model}")
        except Exception as e:
            log.error(f"❌ Cannot connect to Ollama: {e}")
            log.error("   Make sure Ollama is running: ollama serve")

    def reason(self, prompt: str) -> dict:
        """
        Send prompt to Qwen via Ollama.
        Returns parsed dict: {thought, payload, finish}
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,    # lower = more deterministic for payloads
                "num_predict": 512,
                "top_p": 0.9,
            }
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
            resp.raise_for_status()
            raw_text = resp.json().get("response", "")
            log.debug(f"Raw LLM output: {raw_text[:300]}")
            return self._parse_response(raw_text)

        except requests.exceptions.Timeout:
            log.error("Ollama timeout — model may be overloaded.")
            return {"thought": "timeout", "payload": "", "finish": False}
        except Exception as e:
            log.error(f"Cognitive Engine error: {e}")
            return {"thought": "error", "payload": "", "finish": False}

    def _parse_response(self, text: str) -> dict:
        """
        Robustly parse LLM JSON output.
        Handles markdown fences and partial output.
        """
        import re
        
        # Strip markdown code blocks if present using regex
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            json_text = match.group(1)
        else:
            json_text = text

        # Find first JSON object
        start = json_text.find("{")
        end   = json_text.rfind("}") + 1
        if start == -1 or end == 0:
            log.warning("No JSON found in LLM response — extracting payload manually.")
            return self._fallback_extract(text)

        try:
            parsed = json.loads(json_text[start:end])
            return {
                "thought" : str(parsed.get("thought", "")),
                "payload" : str(parsed.get("payload", "")).strip(),
                "action_type": str(parsed.get("action_type", "HTTP_INJECT")).strip(),
                "strategy_category": str(parsed.get("strategy_category", "unknown")).strip(),
                "finish"  : bool(parsed.get("finish", False)),
                "action"  : str(parsed.get("payload", ""))  # alias for logging
            }
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse error: {e} — trying fallback.")
            return self._fallback_extract(text)

    def _fallback_extract(self, text: str) -> dict:
        """Last-resort: extract payload from raw text using keyword search."""
        payload = ""
        action_type = "HTTP_INJECT"
        strategy_category = "unknown"
        lines = text.split("\n")
        for line in lines:
            if "payload" in line.lower() and ":" in line:
                payload = line.split(":", 1)[-1].strip().strip('"').strip("'")
            if "action_type" in line.lower() and ":" in line:
                action_type = line.split(":", 1)[-1].strip().strip('"').strip("'")
            if "strategy_category" in line.lower() and ":" in line:
                strategy_category = line.split(":", 1)[-1].strip().strip('"').strip("'")
        return {
            "thought" : "fallback parse — check raw log",
            "payload" : payload,
            "action_type": action_type,
            "strategy_category": strategy_category,
            "finish"  : False,
            "action"  : payload
        }
