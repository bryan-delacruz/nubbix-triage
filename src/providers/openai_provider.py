"""Proveedor OpenAI, implementado con el SDK oficial openai y la Responses API."""

import openai

from src.providers.base import LLMError, LLMProvider, LLMRefusal, LLMResponse, describe_status

# URL fija de la API oficial. Se pasa explícita para que una variable OPENAI_BASE_URL
# definida en la terminal no desvíe las llamadas (igual que en el proveedor Anthropic).
OPENAI_API_URL = "https://api.openai.com/v1"
TIMEOUT_S = 30.0  # OpenAI mide el timeout en segundos
MAX_RETRIES = 2  # reintentos además de la llamada inicial; el SDK reintenta 408, 409, 429, 5xx y red

# Esfuerzo de razonamiento por defecto. "none" no gasta tokens pensando: clasificar un
# ticket es una tarea corta, y así el modelo compite en igualdad con Haiku, que tampoco
# razona. Se puede subir con OPENAI_REASONING_EFFORT si las evals lo justifican.
DEFAULT_REASONING_EFFORT = "none"
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None, model: str, reasoning_effort: str = DEFAULT_REASONING_EFFORT):
        if not api_key:
            raise ValueError("Falta OPENAI_API_KEY en el archivo .env")
        if reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(
                f"OPENAI_REASONING_EFFORT='{reasoning_effort}' no es válido. Opciones: {', '.join(REASONING_EFFORTS)}"
            )
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=OPENAI_API_URL,
            timeout=TIMEOUT_S,
            max_retries=MAX_RETRIES,
        )

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=system,
                input=user,
                max_output_tokens=max_tokens,
                reasoning={"effort": self.reasoning_effort},
                store=False,  # no guardar los tickets de clientes en los servidores de OpenAI
            )
        except openai.APIStatusError as error:
            raise LLMError(self.name, f"{describe_status(error.status_code)} (HTTP {error.status_code})") from error
        except openai.APIConnectionError as error:
            raise LLMError(self.name, f"No se pudo conectar con la API: {type(error).__name__}") from error

        reason = response.incomplete_details.reason if response.incomplete_details else None
        if reason == "content_filter":
            raise LLMRefusal(self.name, "El filtro de contenido de OpenAI bloqueó la respuesta")

        # La salida es una lista de items (razonamiento, mensajes); cada mensaje trae bloques
        # de texto o de negativa. Nos quedamos con el texto y detectamos las negativas.
        text_parts = []
        for item in response.output:
            if item.type != "message":
                continue
            for block in item.content:
                if block.type == "refusal":
                    raise LLMRefusal(self.name, "El modelo se negó a responder la consulta")
                if block.type == "output_text":
                    text_parts.append(block.text)

        usage = response.usage
        return LLMResponse(
            text="".join(text_parts),
            model=self.model,
            input_tokens=usage.input_tokens if usage else 0,
            # output_tokens ya incluye los tokens de razonamiento, que OpenAI cobra como salida.
            output_tokens=usage.output_tokens if usage else 0,
            truncated=reason == "max_output_tokens",
        )


if __name__ == "__main__":
    from src.config import load_settings

    settings = load_settings()
    provider = OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
    )
    result = provider.complete(
        system="Eres un agente de soporte de Nubbix. Responde en una sola oración.",
        user="Hola, me cobraron dos veces la suscripción de este mes.",
        max_tokens=200,
    )
    print(result)
