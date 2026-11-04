"""Orquestación del triage: consulta -> prompt -> LLM -> JSON validado -> métricas."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from src.metrics import METRICS_PATH, build_record, log_request
from src.prompts import Prompt
from src.providers.base import LLMError, LLMProvider
from src.schemas import TriageResponse

MAX_ATTEMPTS = 3  # 1 intento + 2 reintentos


@dataclass
class TriageResult:
    """La respuesta para el cliente más los datos del request, para métricas y evals."""

    response: TriageResponse
    status: str  # "ok" | "invalid_response" | "api_error"
    attempts: int
    input_tokens: int
    output_tokens: int
    latency_s: float
    error: str | None = None


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


def triage(
    query: str,
    provider: LLMProvider,
    prompt: Prompt,
    metrics_path: Path | None = METRICS_PATH,
) -> TriageResult:
    """Clasifica una consulta y registra una línea de métricas.

    Si el modelo no respeta el contrato, reintenta mostrándole los errores.
    Nunca lanza errores del modelo ni de la API: en esos casos devuelve la respuesta
    de respaldo con status distinto de "ok". Con metrics_path=None no registra nada.
    """
    start = time.perf_counter()
    input_tokens = output_tokens = attempts = 0
    user_message = query
    result = None

    try:
        while result is None:
            attempts += 1
            llm_response = provider.complete(system=prompt.system, user=user_message, max_tokens=prompt.max_tokens)
            input_tokens += llm_response.input_tokens
            output_tokens += llm_response.output_tokens
            try:
                response = TriageResponse.model_validate_json(extract_json(llm_response.text))
                result = TriageResult(response, "ok", attempts, input_tokens, output_tokens, 0.0)
            except ValidationError as error:
                if attempts == MAX_ATTEMPTS:
                    result = TriageResult(
                        fallback_response("respuesta inválida del modelo"),
                        "invalid_response", attempts, input_tokens, output_tokens, 0.0,
                        error=f"la respuesta del modelo no cumple el contrato:\n{format_errors(error)}",
                    )
                else:
                    print(f"Intento {attempts}/{MAX_ATTEMPTS} inválido, reintentando:\n{format_errors(error)}", file=sys.stderr)
                    user_message = build_retry_message(query, llm_response.text, error)
    except LLMError as error:
        result = TriageResult(
            fallback_response("error de la API del proveedor"),
            "api_error", attempts, input_tokens, output_tokens, 0.0, error=str(error),
        )

    result.latency_s = time.perf_counter() - start
    if metrics_path is not None:
        record = build_record(
            provider=provider.name,
            model=provider.model,
            prompt_version=prompt.version,
            status=result.status,
            attempts=result.attempts,
            # La categoría del respaldo ("other") no la eligió el modelo: no la registramos.
            category=result.response.category if result.status == "ok" else None,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_s=result.latency_s,
        )
        log_request(record, metrics_path)
    return result


if __name__ == "__main__":
    from src.prompts import DEFAULT_PROMPT_VERSION, load_prompt
    from src.providers.base import LLMResponse

    prompt = load_prompt(DEFAULT_PROMPT_VERSION)

    class FlakyProvider(LLMProvider):
        """Proveedor simulado: devuelve respuestas inválidas antes de una válida."""

        name = "flaky"
        model = "flaky-1"

        def __init__(self, answers: list[str]):
            self.answers = answers
            self.calls = 0

        def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
            text = self.answers[self.calls]
            self.calls += 1
            return LLMResponse(text=text, model=self.model, input_tokens=100, output_tokens=20)

    valid = '{"answer": "Revisamos tu cobro.", "confidence": 0.9, "category": "billing", "actions": ["Verificar cargos"]}'
    not_json = "Claro, aquí tienes la clasificación: billing"
    bad_contract = '{"answer": "Revisamos tu cobro.", "confidence": 1.5, "category": "ventas", "actions": []}'

    print("== Caso 1: falla 2 veces y se recupera al tercer intento ==")
    result = triage("me cobraron dos veces", FlakyProvider([not_json, bad_contract, valid]), prompt, metrics_path=None)
    print(f"status={result.status} attempts={result.attempts} tokens={result.input_tokens}+{result.output_tokens}")
    print(result.response)

    print("\n== Caso 2: falla los 3 intentos ==")
    result = triage("me cobraron dos veces", FlakyProvider([not_json, bad_contract, not_json]), prompt, metrics_path=None)
    print(f"status={result.status} attempts={result.attempts} tokens={result.input_tokens}+{result.output_tokens}")
    print(result.response)
