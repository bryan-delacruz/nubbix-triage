"""Interfaz común para todos los proveedores de LLM."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    """Lo que devuelve cualquier proveedor, en el mismo formato."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int


class LLMProvider(ABC):
    """Contrato que debe cumplir cada proveedor (Gemini, Anthropic, ...).

    La lógica de negocio solo conoce esta interfaz, nunca un SDK concreto.
    """

    name: str

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
        """Envía un system prompt y un mensaje de usuario, y devuelve la respuesta."""


if __name__ == "__main__":

    class EchoProvider(LLMProvider):
        """Proveedor de prueba: devuelve el mismo mensaje, sin llamar a ninguna API."""

        name = "echo"

        def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse:
            return LLMResponse(text=user, model="echo-1", input_tokens=0, output_tokens=0)

    print("1) Proveedor que cumple la interfaz:")
    print(EchoProvider().complete(system="Eres soporte", user="hola", max_tokens=100))

    print("\n2) Intentar usar la interfaz directamente:")
    try:
        LLMProvider()
    except TypeError as error:
        print(f"TypeError: {error}")

    print("\n3) Proveedor que olvida implementar complete():")

    class IncompleteProvider(LLMProvider):
        name = "incompleto"

    try:
        IncompleteProvider()
    except TypeError as error:
        print(f"TypeError: {error}")
