"""Proveedor Gemini (Google), implementado con el SDK oficial google-genai."""

from google import genai
from google.genai import errors, types

from src.providers.base import LLMError, LLMProvider, LLMRefusal, LLMResponse, describe_status

TIMEOUT_MS = 30_000  # Gemini mide el timeout en milisegundos
RETRY_ATTEMPTS = 3  # incluye la llamada inicial; reintenta 408, 429 y 5xx con espera creciente
# Motivos de corte que significan que Gemini se negó a responder por seguridad.
REFUSAL_REASONS = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.SPII,
}


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

        # Gemini puede bloquear la consulta (sin candidatos) o cortar la respuesta por seguridad.
        feedback = response.prompt_feedback
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = candidate.finish_reason if candidate else None
        if (feedback and feedback.block_reason) or candidate is None or finish_reason in REFUSAL_REASONS:
            raise LLMRefusal(self.name, "El modelo se negó a responder la consulta")

        # usage_metadata puede venir vacío: en ese caso se registran 0 tokens.
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage else 0
        # Gemini cobra los tokens de razonamiento ("thoughts") como tokens de salida.
        output_tokens = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
        return LLMResponse(
            text=response.text or "",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            truncated=finish_reason == types.FinishReason.MAX_TOKENS,
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
