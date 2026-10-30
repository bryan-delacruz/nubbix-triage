"""Crea el proveedor de LLM pedido, a partir de su nombre y la configuración."""

from src.config import Settings
from src.providers.anthropic_provider import AnthropicProvider
from src.providers.base import LLMProvider
from src.providers.gemini_provider import GeminiProvider


def build_provider(name: str, settings: Settings) -> LLMProvider:
    if name == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if name == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    raise ValueError(f"Proveedor desconocido: {name}")
