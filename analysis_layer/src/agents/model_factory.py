"""
Model Factory - Unified LLM Interface
======================================
Pattern adapted from MoondevRED for managing multiple LLM providers.
Supports: DeepSeek, OpenRouter (Qwen/Llama), Gemini, and fallbacks.
"""

import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class ModelFactory:
    """
    Centralized factory for creating LLM clients based on provider type.
    Handles API key management and model selection.
    """

    # Agent-to-Model mapping
    AGENT_MODELS = {
        "researcher": {
            "provider": "deepseek",
            "model": "deepseek-reasoner",  # DeepSeek R1
            "env_key": "DEEPSEEK_API_KEY",
        },
        "analyst": {
            "provider": "openrouter",
            "model": "qwen/qwen-coder-32b-free",  # Qwen Coder
            "env_key": "OPENROUTER_API_KEY",
        },
        "executor": {
            "provider": "openrouter",
            "model": "meta-llama/llama-3.1-70b-free",  # Llama 3.1
            "env_key": "OPENROUTER_API_KEY",
        },
        "risk_guardian": {
            "provider": "gemini",
            "model": "gemini-2.0-flash",  # Gemini 2.0
            "env_key": "GOOGLE_GEMINI_API_KEY",
        },
    }

    def __init__(self):
        self._clients: Dict[str, any] = {}
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize all available LLM clients"""
        for agent_name, config in self.AGENT_MODELS.items():
            try:
                api_key = os.getenv(config["env_key"])
                if not api_key:
                    logger.warning(
                        f"⚠️ No API key for {agent_name} ({config['env_key']})"
                    )
                    continue

                # Create client based on provider
                client = self._create_client(
                    config["provider"], api_key, config["model"]
                )
                if client:
                    self._clients[agent_name] = {
                        "client": client,
                        "model": config["model"],
                        "provider": config["provider"],
                    }
                    logger.info(f"✅ {agent_name.upper()} ready ({config['model']})")

            except Exception as e:
                logger.error(f"❌ Failed to initialize {agent_name}: {e}")

    def _create_client(self, provider: str, api_key: str, model: str):
        """Create the appropriate client based on provider"""
        if provider == "deepseek":
            return self._create_deepseek_client(api_key)
        elif provider == "openrouter":
            return self._create_openrouter_client(api_key)
        elif provider == "gemini":
            return self._create_gemini_client(api_key)
        else:
            logger.error(f"Unknown provider: {provider}")
            return None

    def _create_deepseek_client(self, api_key: str):
        """Create DeepSeek client"""
        try:
            from openai import OpenAI

            return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        except ImportError:
            logger.error("OpenAI library not installed (required for DeepSeek)")
            return None

    def _create_openrouter_client(self, api_key: str):
        """Create OpenRouter client (for Qwen/Llama)"""
        try:
            from openai import OpenAI

            return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        except ImportError:
            logger.error("OpenAI library not installed (required for OpenRouter)")
            return None

    def _create_gemini_client(self, api_key: str):
        """Create Gemini client"""
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            return genai
        except ImportError:
            logger.error("Google GenerativeAI library not installed")
            return None

    def get_client(self, agent_name: str) -> Optional[Dict]:
        """
        Get the client configuration for a specific agent.

        Args:
            agent_name: One of 'researcher', 'analyst', 'executor', 'risk_guardian'

        Returns:
            Dict with 'client', 'model', 'provider' or None if not available
        """
        return self._clients.get(agent_name)

    def is_agent_available(self, agent_name: str) -> bool:
        """Check if an agent's LLM is available"""
        return agent_name in self._clients

    def get_available_agents(self) -> list:
        """Get list of all available agent names"""
        return list(self._clients.keys())

    async def query_agent(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        """
        Query a specific agent's LLM.

        Args:
            agent_name: Which agent to use
            system_prompt: System instructions
            user_prompt: User query
            temperature: Sampling temperature
            max_tokens: Max response tokens

        Returns:
            str: Model response or None if failed
        """
        config = self.get_client(agent_name)
        if not config:
            logger.error(f"Agent {agent_name} not available")
            return None

        try:
            provider = config["provider"]
            client = config["client"]
            model = config["model"]

            if provider in ["deepseek", "openrouter"]:
                # OpenAI-compatible API
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content

            elif provider == "gemini":
                # Gemini API
                model_instance = client.GenerativeModel(model)
                chat = model_instance.start_chat(history=[])

                # Combine system and user prompt for Gemini
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                response = chat.send_message(full_prompt)
                return response.text

            else:
                logger.error(f"Unknown provider: {provider}")
                return None

        except Exception as e:
            logger.error(f"Error querying {agent_name}: {e}")
            return None


# Singleton instance
model_factory = ModelFactory()


def get_model_factory() -> ModelFactory:
    """Get the singleton ModelFactory instance"""
    return model_factory
