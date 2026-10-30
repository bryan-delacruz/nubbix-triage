"""Orquestación del triage: consulta -> prompt -> LLM -> JSON validado."""

import json

from src.providers.base import LLMProvider
from src.schemas import TriageResponse

MAX_TOKENS = 1024

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


def triage(query: str, provider: LLMProvider) -> TriageResponse:
    """Clasifica una consulta y devuelve la respuesta validada contra el contrato."""
    llm_response = provider.complete(system=SYSTEM_PROMPT, user=query, max_tokens=MAX_TOKENS)
    return TriageResponse.model_validate_json(extract_json(llm_response.text))
