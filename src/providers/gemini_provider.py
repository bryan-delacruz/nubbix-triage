"""Proveedor Gemini (Google), implementado con el SDK oficial google-genai."""

from google import genai
from google.genai import types

from src.providers.base import LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise ValueError("Falta GEMINI_API_KEY en el archivo .env")
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        response = self.client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
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
