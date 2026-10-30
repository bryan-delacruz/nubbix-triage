"""Configuración del servicio, cargada desde variables de entorno (.env)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

SUPPORTED_PROVIDERS = ("gemini", "anthropic")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    anthropic_api_key: str | None
    default_provider: str
    gemini_model: str
    anthropic_model: str


def load_settings() -> Settings:
    """Lee .env (si existe) y devuelve la configuración validada."""
    load_dotenv()

    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER='{provider}' no es válido. Opciones: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        default_provider=provider,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
    )


def mask(secret: str | None) -> str:
    """Muestra solo los primeros 6 caracteres de una credencial."""
    if not secret:
        return "(no configurada)"
    return f"{secret[:6]}…"


if __name__ == "__main__":
    settings = load_settings()
    print(f"Proveedor por defecto: {settings.default_provider}")
    print(f"Gemini:    modelo={settings.gemini_model}  key={mask(settings.gemini_api_key)}")
    print(f"Anthropic: modelo={settings.anthropic_model}  key={mask(settings.anthropic_api_key)}")
