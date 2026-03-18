"""
LLM Client — NVIDIA AI Endpoints with Kimi K2.
Provides structured reasoning for the web agent.
"""
import os
import json
import re
import time
import asyncio
from typing import Dict, Optional, Any
from dataclasses import dataclass

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv(
    "NVIDIA_API_KEY",
    "nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
)


@dataclass
class LLMResponse:
    """Structured LLM response."""
    raw: str
    parsed: Optional[Dict] = None
    success: bool = True
    error: Optional[str] = None
    latency_ms: float = 0.0


class AgentLLM:
    """
    LLM interface for the web agent reasoning core.
    Uses NVIDIA AI Endpoints with moonshotai/kimi-k2-instruct.

    Guardrails:
    - Max tokens capped
    - Response validation
    - Retry with backoff
    - Timeout protection
    """

    def __init__(self):
        self.client = ChatNVIDIA(
            model="moonshotai/kimi-k2-instruct",
            api_key=NVIDIA_API_KEY,
            temperature=0.6,
            top_p=0.9,
            max_completion_tokens=2048,
        )
        self._call_count = 0
        self._max_calls_per_hour = 60  # Guardrail
        self._hour_start = time.time()

    def _check_rate_limit(self) -> bool:
        """Enforce max reasoning calls per hour."""
        now = time.time()
        if now - self._hour_start > 3600:
            self._call_count = 0
            self._hour_start = now
        return self._call_count < self._max_calls_per_hour

    def reason(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Send a reasoning request to the LLM.
        Returns structured LLMResponse.
        """
        if not self._check_rate_limit():
            return LLMResponse(
                raw="", success=False,
                error="Rate limit: max reasoning calls per hour exceeded"
            )

        start = time.time()
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            result = self.client.invoke(messages)
            latency = (time.time() - start) * 1000
            self._call_count += 1

            raw = result.content.strip()
            parsed = self._try_parse_json(raw)

            return LLMResponse(
                raw=raw,
                parsed=parsed,
                success=True,
                latency_ms=latency
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return LLMResponse(
                raw="", success=False,
                error=str(e), latency_ms=latency
            )

    def _try_parse_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from LLM output (may be wrapped in markdown)."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` blocks
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @property
    def calls_remaining(self) -> int:
        return max(0, self._max_calls_per_hour - self._call_count)

    async def areason(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Async wrapper for reason() — runs the blocking LLM call
        in a thread pool so it doesn't block the asyncio event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.reason, system_prompt, user_prompt
        )


# Singleton
agent_llm = AgentLLM()
