import os
import time
from typing import Dict, Any, Optional, Generator
from openai import OpenAI
from src.core.llm_provider import LLMProvider


class MimoProvider(LLMProvider):
    """
    LLM Provider for Xiaomi MiMo API.

    Compatible with OpenAI API protocol.
    Base URL: https://token-plan-sgp.xiaomimimo.com/v1
    """

    def __init__(
        self,
        model_name: str = "mimo-v2.5-pro",
        api_key: Optional[str] = None,
        base_url: str = "https://token-plan-sgp.xiaomimimo.com/v1",
    ):
        """
        Initialize the MiMo provider.

        Args:
            model_name: The MiMo model to use (e.g., mimo-v2.5-pro).
            api_key: MiMo API key.
            base_url: Base URL for the MiMo API endpoint.
        """
        super().__init__(model_name, api_key)

        resolved_key = api_key or os.getenv("MIMO_API_KEY")
        if not resolved_key:
            raise ValueError("Missing MIMO_API_KEY in environment or .env")

        self.base_url = base_url
        self.client = OpenAI(
            api_key=resolved_key,
            base_url=base_url,
        )

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        start_time = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
        )

        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)

        content = response.choices[0].message.content
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        return {
            "content": content,
            "usage": usage,
            "latency_ms": latency_ms,
            "provider": "mimo",
        }

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
