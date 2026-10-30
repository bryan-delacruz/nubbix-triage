"""Contrato de salida del servicio: {answer, confidence, category, actions}."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Category = Literal["billing", "technical", "account", "other"]


class TriageResponse(BaseModel):
    """Respuesta que recibe el agente de soporte. Este contrato no cambia."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1, description="Respuesta propuesta para el cliente")
    confidence: float = Field(ge=0, le=1, description="Confianza del modelo, de 0 a 1")
    category: Category = Field(description="Tipo de consulta")
    actions: list[str] = Field(min_length=1, description="Acciones sugeridas para el agente")


if __name__ == "__main__":
    valid = """{
        "answer": "Lamentamos el doble cobro. Ya derivamos tu caso a facturación.",
        "confidence": 0.92,
        "category": "billing",
        "actions": ["Verificar cargos duplicados", "Iniciar reintegro"]
    }"""
    print("Caso válido:")
    print(TriageResponse.model_validate_json(valid))

    invalid = """{
        "answer": "",
        "confidence": 1.7,
        "category": "ventas",
        "actions": [],
        "priority": "alta"
    }"""
    print("\nCaso inválido:")
    try:
        TriageResponse.model_validate_json(invalid)
    except ValidationError as error:
        print(error)
