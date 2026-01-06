"""
DataSight Ollama Provider — local LLM inference via Ollama.

Requires: pip install datasight-ai[ollama]
Requires: Ollama running locally (https://ollama.com)
"""

from __future__ import annotations

import logging

import requests

from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.llm.ollama")


class OllamaProvider:
    """LLM provider that calls a local Ollama instance."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.ollama_base_url
        self.model = settings.llm_model

        # Verify Ollama is reachable
        try:
            resp = requests.get(self.base_url, timeout=3)
            if resp.ok:
                logger.info("Ollama connected at %s", self.base_url)
            else:
                logger.warning("Ollama returned status %d", resp.status_code)
        except requests.exceptions.ConnectionError:
            logger.warning(
                "Cannot reach Ollama at %s — make sure it's running", self.base_url
            )

    def complete(self, prompt: str, system_prompt: str = "") -> str:
        """
        Send a completion request to Ollama's /api/chat endpoint.

        Args:
            prompt: The user message
            system_prompt: Optional system instructions

        Returns:
            The assistant's response text
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 2048,
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out after 120s")
            return "Error: LLM request timed out"
        except requests.exceptions.ConnectionError:
            logger.error("Lost connection to Ollama")
            return "Error: Cannot connect to Ollama"
        except Exception as e:
            logger.error("Ollama error: %s", e)
            return f"Error: {e}"
