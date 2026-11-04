"""Orquestación del triage: consulta -> prompt -> LLM -> JSON validado."""

import json
import sys

from pydantic import ValidationError

from src.providers.base import LLMProvider
from src.schemas import TriageResponse

MAX_TOKENS = 1024
MAX_ATTEMPTS = 3  # 1 intento + 2 reintentos

# Prompt provisorio: en el commit 12 se mueve a prompts/*.yaml y se versiona.
SYSTEM_PROMPT = f"""Eres el asistente de soporte de nivel 1 de Nubbix, un SaaS de gestión para pymes de LATAM.
Clasifica la consulta del cliente, redacta una respuesta breve y sugiere acciones para el agente humano.

Categorías:
- billing: cobros, pagos, facturas, suscripción, reintegros
- technical: errores, fallas, caídas, integraciones
- account: usuarios, permisos, datos o acceso a la cuenta
- other: cualquier otra consulta

Responde SOLO con un objeto JSON que cumpla este JSON Schema, sin texto adicional:
{json.dumps(TriageResponse.model_json_schema(), ensure_ascii=False)}"""


def extract_json(text: str) -> str:
    """Quita el bloque ```json ... ``` si el modelo envolvió la respuesta en uno."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def format_errors(error: ValidationError) -> str:
    """Resume los errores de Pydantic en una línea por campo, para devolvérselos al modelo."""
    lines = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"]) or "(json)"
        lines.append(f"- {field}: {item['msg']}")
    return "\n".join(lines)


def build_retry_message(query: str, previous_answer: str, error: ValidationError) -> str:
    """Repite la consulta original y le explica al modelo qué corregir."""
    return f"""{query}

---
Tu respuesta anterior no cumplió el formato pedido.
Respuesta anterior:
{previous_answer}

Errores:
{format_errors(error)}

Corrige los errores y responde SOLO con el objeto JSON válido."""


def fallback_response(reason: str) -> TriageResponse:
    """Respuesta de respaldo cuando el servicio no pudo procesar la consulta.

    Respeta el mismo contrato, así quien consume el JSON nunca recibe otro formato.
    confidence=0 indica que no la generó el modelo y que la debe revisar un humano.
    """
    return TriageResponse(
        answer="Recibimos tu consulta. Un agente de soporte la revisará a la brevedad.",
        confidence=0.0,
        category="other",
        actions=[f"Revisar manualmente: el triage automático falló ({reason})"],
    )


def triage(query: str, provider: LLMProvider) -> TriageResponse:
    """Clasifica una consulta y devuelve la respuesta validada contra el contrato.

    Si el modelo no respeta el contrato, reintenta mostrándole los errores.
    Después de MAX_ATTEMPTS intentos fallidos, propaga el último ValidationError.
    """
    user_message = query
    for attempt in range(1, MAX_ATTEMPTS + 1):
        llm_response = provider.complete(system=SYSTEM_PROMPT, user=user_message, max_tokens=MAX_TOKENS)
        try:
            return TriageResponse.model_validate_json(extract_json(llm_response.text))
        except ValidationError as error:
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"Intento {attempt}/{MAX_ATTEMPTS} inválido, reintentando:\n{format_errors(error)}", file=sys.stderr)
            user_message = build_retry_message(query, llm_response.text, error)


if __name__ == "__main__":
    from src.providers.base import LLMResponse

    class FlakyProvider(LLMProvider):
        """Proveedor simulado: devuelve respuestas inválidas antes de una válida."""

        name = "flaky"

        def __init__(self, answers: list[str]):
            self.answers = answers
            self.calls = 0

        def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
            text = self.answers[self.calls]
            self.calls += 1
            return LLMResponse(text=text, model="flaky-1", input_tokens=0, output_tokens=0)

    valid = '{"answer": "Revisamos tu cobro.", "confidence": 0.9, "category": "billing", "actions": ["Verificar cargos"]}'
    not_json = "Claro, aquí tienes la clasificación: billing"
    bad_contract = '{"answer": "Revisamos tu cobro.", "confidence": 1.5, "category": "ventas", "actions": []}'

    print("== Caso 1: falla 2 veces y se recupera al tercer intento ==")
    provider = FlakyProvider([not_json, bad_contract, valid])
    print(triage("me cobraron dos veces", provider))
    print(f"Llamadas al LLM: {provider.calls}")

    print("\n== Caso 2: falla los 3 intentos ==")
    provider = FlakyProvider([not_json, bad_contract, not_json])
    try:
        triage("me cobraron dos veces", provider)
    except ValidationError:
        print(f"ValidationError final después de {provider.calls} llamadas")
