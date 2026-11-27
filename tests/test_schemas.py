"""Contrato de salida: qué acepta y qué rechaza TriageResponse."""

import pytest
from pydantic import ValidationError

from src.schemas import TriageResponse
from tests.conftest import VALID


def test_accepts_valid_response():
    response = TriageResponse.model_validate(VALID)
    assert response.category == "billing"


def test_strips_whitespace():
    response = TriageResponse.model_validate({**VALID, "answer": "  Hola  "})
    assert response.answer == "Hola"


@pytest.mark.parametrize(
    "change",
    [
        {"category": "ventas"},  # categoría fuera de la lista
        {"confidence": 1.5},  # mayor que 1
        {"confidence": -0.1},  # menor que 0
        {"answer": ""},  # vacío
        {"answer": "   "},  # solo espacios: queda vacío
        {"actions": []},  # sin acciones
        {"priority": "alta"},  # campo extra
    ],
)
def test_rejects_invalid_values(change):
    with pytest.raises(ValidationError):
        TriageResponse.model_validate({**VALID, **change})


@pytest.mark.parametrize("missing", ["answer", "confidence", "category", "actions"])
def test_rejects_missing_field(missing):
    data = {key: value for key, value in VALID.items() if key != missing}
    with pytest.raises(ValidationError):
        TriageResponse.model_validate(data)
