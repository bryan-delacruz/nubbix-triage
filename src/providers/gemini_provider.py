"""Proveedor Gemini (Google), implementado con el SDK oficial google-genai."""

from google import genai
from google.genai import errors, types

from src.providers.base import LLMError, LLMProvider, LLMResponse, describe_status

TIMEOUT_MS = 30_000  # Gemini mide el timeout en milisegundos
RETRY_ATTEMPTS = 3  # incluye la llamada inicial; reintenta 408, 429 y 5xx con espera creciente


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise ValueError("Falta GEMINI_API_KEY en el archivo .env")
        self.model = model
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=RETRY_ATTEMPTS),
            ),
        )

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                ),
            )
        except errors.APIError as error:
            # Gemini responde 400 (no 401) ante una key inválida: sumamos su mensaje para que se entienda.
            detail = f"{describe_status(error.code)} (HTTP {error.code}): {error.message}"
            raise LLMError(self.name, detail) from error
        except Exception as error:
            # Errores de red (sin conexión, timeout): el SDK no los envuelve en APIError.
            raise LLMError(self.name, f"No se pudo conectar con la API: {type(error).__name__}") from error

        usage = response.usage_metadata
        # Gemini cobra los tokens de razonamiento ("thoughts") como tokens de salida.
        output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return LLMResponse(
            text=response.text or "",
            model=self.model,
            input_tokens=usage.prompt_token_count or 0,
            output_tokens=output_tokens,
        )


if __name__ == "__main__":
    from src.config import load_settings

    settings = load_settings()
    provider = GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    result = provider.complete(
        system="Eres un agente de soporte de Nubbix. Responde en una sola oración.",
        user="Hola, me cobraron dos veces la suscripción de este mes.",
        max_tokens=200,
    )
    print(result)
