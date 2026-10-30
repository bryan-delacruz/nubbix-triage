"""Proveedor Anthropic (Claude), implementado con el SDK oficial anthropic."""

import anthropic

from src.providers.base import LLMProvider, LLMResponse

# URL fija de la API oficial. Se pasa explícita para que una variable ANTHROPIC_BASE_URL
# definida en la terminal (por ejemplo, por otras herramientas) no desvíe las llamadas.
ANTHROPIC_API_URL = "https://api.anthropic.com"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise ValueError("Falta ANTHROPIC_API_KEY en el archivo .env")
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, base_url=ANTHROPIC_API_URL)

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # La respuesta es una lista de bloques (texto, razonamiento, ...): nos quedamos con el texto.
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


if __name__ == "__main__":
    from src.config import load_settings

    settings = load_settings()
    provider = AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    result = provider.complete(
        system="Eres un agente de soporte de Nubbix. Responde en una sola oración.",
        user="Hola, me cobraron dos veces la suscripción de este mes.",
        max_tokens=200,
    )
    print(result)
