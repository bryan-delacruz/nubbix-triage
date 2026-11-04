"""Interfaz común para todos los proveedores de LLM."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(Exception):
    """Error al llamar a un proveedor, ya traducido a un mensaje claro.

    Cada proveedor convierte los errores de su SDK en LLMError, así el resto
    del código maneja un solo tipo de error sin conocer ningún SDK.
    """

    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}")


def describe_status(status_code: int) -> str:
    """Explica en palabras simples un código de error HTTP de la API."""
    if status_code in (401, 403):
        return "API key inválida o sin permisos. Revisa tu .env"
    if status_code == 404:
        return "Modelo no encontrado. Revisa el nombre del modelo en tu .env"
    if status_code == 429:
        return "Límite de uso alcanzado (rate limit). Espera un momento y vuelve a intentar"
    if status_code >= 500:
        return "El servicio del proveedor está con problemas. Vuelve a intentar más tarde"
    return "La API rechazó la petición"


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
