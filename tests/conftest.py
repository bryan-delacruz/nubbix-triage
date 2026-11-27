"""Piezas compartidas por todos los tests.

pytest carga este archivo solo. Cada función marcada con @pytest.fixture se puede pedir
como parámetro de un test, y pytest la crea antes de correrlo.
"""

import json

import pytest

from src.prompts import load_prompt
from src.providers.base import LLMError, LLMProvider, LLMResponse

VALID = {
    "answer": "Revisamos tu cobro duplicado.",
    "confidence": 0.9,
    "category": "billing",
    "actions": ["Verificar los cargos"],
}
VALID_JSON = json.dumps(VALID, ensure_ascii=False)


class FakeProvider(LLMProvider):
    """Proveedor falso: devuelve respuestas preparadas en orden y anota cada llamada.

    Cada respuesta puede ser un texto, un LLMResponse completo o una excepción para lanzar.
    """

    name = "fake"
    model = "fake-1"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        answer = self.answers[len(self.calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, LLMResponse):
            return answer
        return LLMResponse(text=answer, model=self.model, input_tokens=100, output_tokens=20)


@pytest.fixture
def prompt():
    return load_prompt("v2")


@pytest.fixture
def api_error():
    return LLMError("fake", "HTTP 500")
