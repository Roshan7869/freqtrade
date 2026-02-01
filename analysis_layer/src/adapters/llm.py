# llm_layer.py
"""
Multi-Agent LLM Layer with Load Balancing
==========================================
Uses 4 different API keys to distribute load and avoid rate limits.

Key Assignment:
- Key 1: Researcher Agent (DeepSeek R1)
- Key 2: Analyst Agent (Qwen Coder)
- Key 3: Executor Agent (Llama 3.1)
- Key 4: Fallback (Gemini 2.0)
"""

import os
import asyncio
import httpx
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import random
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    OPENROUTER = "openrouter"
    GEMINI = "gemini"


class LLMConfig(BaseModel):
    provider: LLMProvider
    api_key: Optional[str]
    model: str
    temperature: float = 0.7
    max_tokens: int = 2000


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    latency_ms: float
    api_key_used: str = "hidden"  # For debugging (last 4 chars)


class MultiAgentLLM:
    """
    Universal LLM interface with multi-provider and multi-key support.

    Features:
    - 4 different API keys for load balancing
    - Automatic fallback on failure
    - Per-agent key assignment to avoid congestion
    """

    def __init__(self):
        # Load 4 different API keys
        self.api_keys = {
            "researcher": os.getenv("OPENROUTER_API_KEY_1") or os.getenv("OPENROUTER_API_KEY"),
            "analyst": os.getenv("OPENROUTER_API_KEY_2") or os.getenv("OPENROUTER_API_KEY"),
            "executor": os.getenv("OPENROUTER_API_KEY_3") or os.getenv("OPENROUTER_API_KEY"),
            "fallback": os.getenv("OPENROUTER_API_KEY_4") or os.getenv("OPENROUTER_API_KEY"),
        }

        # All keys for round-robin if needed
        self.all_keys = [
            k
            for k in [
                os.getenv("OPENROUTER_API_KEY_1"),
                os.getenv("OPENROUTER_API_KEY_2"),
                os.getenv("OPENROUTER_API_KEY_3"),
                os.getenv("OPENROUTER_API_KEY_4"),
            ]
            if k
        ]

        # Agent configurations
        self.configs = {
            "researcher": LLMConfig(
                provider=LLMProvider.OPENROUTER,
                api_key=self.api_keys["researcher"],
                model=os.getenv("LLM_RESEARCHER_MODEL", "deepseek/deepseek-r1:free"),
            ),
            "analyst": LLMConfig(
                provider=LLMProvider.OPENROUTER,
                api_key=self.api_keys["analyst"],
                model=os.getenv("LLM_ANALYST_MODEL", "qwen/qwen-coder-32b-free"),
            ),
            "executor": LLMConfig(
                provider=LLMProvider.OPENROUTER,
                api_key=self.api_keys["executor"],
                model=os.getenv("LLM_EXECUTOR_MODEL", "meta-llama/llama-3.1-70b-free"),
            ),
        }

        # Fallback config (uses Key 4 or Gemini)
        self.fallback_config = LLMConfig(
            provider=LLMProvider.GEMINI
            if os.getenv("GOOGLE_GEMINI_API_KEY")
            else LLMProvider.OPENROUTER,
            api_key=os.getenv("GOOGLE_GEMINI_API_KEY") or self.api_keys["fallback"],
            model=os.getenv("LLM_FALLBACK_MODEL", "gemini-2.0-flash"),
        )

        self.session = None
        self._log_key_status()

    def _log_key_status(self):
        """Log which keys are configured"""
        for agent, key in self.api_keys.items():
            if key:
                logger.info(f"✅ {agent.upper()} Agent: Key configured (***{key[-4:]})")
            else:
                logger.warning(f"⚠️ {agent.upper()} Agent: No key configured")

    async def initialize(self):
        """Initialize async HTTP session"""
        if self.session is None:
            self.session = httpx.AsyncClient(timeout=30)

    async def close(self):
        """Close session"""
        if self.session:
            await self.session.aclose()
            self.session = None

    def _get_random_key(self) -> Optional[str]:
        """Get a random key for load balancing"""
        if self.all_keys:
            return random.choice(self.all_keys)
        return None

    async def query(
        self,
        agent_type: str,
        prompt: str,
        retry_with_fallback: bool = True,
        use_random_key: bool = False,
    ) -> LLMResponse:
        """
        Query LLM for specified agent.

        Args:
            agent_type: 'researcher', 'analyst', or 'executor'
            prompt: The prompt to send
            retry_with_fallback: Try fallback key/provider on failure
            use_random_key: Use random key for extra load balancing
        """
        config = self.configs.get(agent_type, self.configs["researcher"])

        # Option to use random key for even more distribution
        if use_random_key and self.all_keys:
            config = LLMConfig(
                provider=config.provider,
                api_key=self._get_random_key(),
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

        # If no API key for primary, use fallback
        if not config.api_key:
            if retry_with_fallback and self.fallback_config.api_key:
                logger.warning(f"[FALLBACK] No key for {agent_type}, using fallback...")
                return await self._query_with_config(self.fallback_config, prompt)
            raise ValueError(f"No API key found for {agent_type}")

        try:
            # Implement exponential backoff for the primary attempt
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    return await self._query_with_config(config, prompt)
                except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                    if attempt == max_retries - 1:
                        raise

                    # Backoff: 1s, 2s, 4s...
                    wait_time = (2**attempt) + (random.random() * 0.1)
                    logger.warning(
                        f"[RETRY] {agent_type} attempt {attempt + 1} failed ({str(e)}), retrying in {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(
                f"[ERROR] {agent_type} failed after primary retries with key ***{config.api_key[-4:] if config.api_key else 'None'}: {str(e)}"
            )

            if retry_with_fallback:
                # Try with a different key
                for backup_key in self.all_keys:
                    if backup_key != config.api_key:
                        try:
                            logger.info(f"[RETRY] Trying with different key ***{backup_key[-4:]}")
                            backup_config = LLMConfig(
                                provider=LLMProvider.OPENROUTER,
                                api_key=backup_key,
                                model=config.model,
                            )
                            return await self._query_with_config(backup_config, prompt)
                        except:
                            continue

                # Final fallback
                if self.fallback_config.api_key:
                    logger.info(f"[FALLBACK] Using fallback provider...")
                    return await self._query_with_config(self.fallback_config, prompt)
            raise

    async def _query_with_config(self, config: LLMConfig, prompt: str) -> LLMResponse:
        """Execute query with given config"""
        if config.provider == LLMProvider.OPENROUTER:
            return await self._query_openrouter(config, prompt)
        elif config.provider == LLMProvider.GEMINI:
            return await self._query_gemini(config, prompt)
        else:
            raise ValueError(f"Unknown provider: {config.provider}")

    async def _query_openrouter(self, config: LLMConfig, prompt: str) -> LLMResponse:
        """Query OpenRouter API"""
        start_time = datetime.now()

        payload = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a financial trading expert. Respond only with valid JSON when asked for structured data.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://a2a-trading-bot.local",
            "X-Title": "A2A Trading Bot",
        }

        if self.session is None:
            await self.initialize()

        response = await self.session.post(
            "https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers
        )

        if response.status_code != 200:
            response.raise_for_status()

        data = response.json()
        latency = (datetime.now() - start_time).total_seconds() * 1000

        content = data["choices"][0]["message"]["content"]

        logger.info(
            f"✅ Query completed: model={config.model}, latency={latency:.0f}ms, key=***{config.api_key[-4:]}"
        )

        return LLMResponse(
            content=content,
            model=config.model,
            provider="openrouter",
            latency_ms=latency,
            api_key_used=f"***{config.api_key[-4:]}",
        )

    async def _query_gemini(self, config: LLMConfig, prompt: str) -> LLMResponse:
        """Query Google Gemini API"""
        start_time = datetime.now()

        # Determine model name for API
        model_name = config.model
        if "/" in model_name:
            model_name = model_name.split("/")[-1]

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
            },
        }

        if self.session is None:
            await self.initialize()

        response = await self.session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={config.api_key}",
            json=payload,
        )

        if response.status_code != 200:
            response.raise_for_status()

        data = response.json()
        latency = (datetime.now() - start_time).total_seconds() * 1000

        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            content = ""
            if (
                "candidates" in data
                and data["candidates"]
                and "finishReason" in data["candidates"][0]
            ):
                content = f"[Stopped: {data['candidates'][0]['finishReason']}]"

        logger.info(f"✅ Gemini query completed: latency={latency:.0f}ms")

        return LLMResponse(
            content=content,
            model=config.model,
            provider="gemini",
            latency_ms=latency,
            api_key_used="gemini",
        )


# Convenience function
def get_multi_agent_llm() -> MultiAgentLLM:
    """Get a new MultiAgentLLM instance"""
    return MultiAgentLLM()
