"""Crea el proveedor de LLM pedido, a partir de su nombre y la configuración."""

from src.config import Settings
from src.providers.anthropic_provider import AnthropicProvider
from src.providers.base import LLMProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_provider import OpenAIProvider


def build_provider(name: str, settings: Settings) -> LLMProvider:
    if name == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if name == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    if name == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort,
        )
    raise ValueError(f"Proveedor desconocido: {name}")
