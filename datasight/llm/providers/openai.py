"""
DataSight OpenAI Provider — cloud LLM inference via OpenAI API.

Requires: pip install datasight-ai[openai]
Requires: DATASIGHT_OPENAI_API_KEY set in environment
"""

from __future__ import annotations

import logging

from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.llm.openai")


class OpenAIProvider:
    """LLM provider that calls the OpenAI API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not set. Set DATASIGHT_OPENAI_API_KEY in your environment."
            )

        try:
            import openai
            self.client = openai.OpenAI(api_key=self.api_key)
            logger.info("OpenAI provider initialized with model=%s", self.model)
        except ImportError:
            raise ImportError(
                "OpenAI SDK not installed. Run: pip install datasight-ai[openai]"
            )

    def complete(self, prompt: str, system_prompt: str = "") -> str:
        """
        Send a completion request to the OpenAI Chat API.

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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
                max_tokens=2048,
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            return f"Error: {e}"
