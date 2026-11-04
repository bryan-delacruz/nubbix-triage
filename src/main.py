"""CLI de triage: recibe una consulta de soporte e imprime el JSON validado."""

import argparse
import sys

from pydantic import ValidationError

from src.config import SUPPORTED_PROVIDERS, load_settings
from src.providers.base import LLMError
from src.providers.factory import build_provider
from src.triage import fallback_response, triage


def parse_args(default_provider: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clasifica una consulta de soporte de Nubbix y devuelve JSON."
    )
    parser.add_argument("query", help='Consulta del cliente, entre comillas. Ej: "me cobraron dos veces"')
    parser.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        default=default_provider,
        help=f"Proveedor de LLM (por defecto: {default_provider}, definido en LLM_PROVIDER)",
    )
    return parser.parse_args()


def fail(reason: str, detail: str) -> None:
    """Explica el error en stderr, imprime el JSON de respaldo en stdout y termina con código 1."""
    print(f"Error: {detail}", file=sys.stderr)
    print(fallback_response(reason).model_dump_json(indent=2))
    sys.exit(1)


def main() -> None:
    settings = load_settings()
    args = parse_args(settings.default_provider)

    try:
        provider = build_provider(args.provider, settings)
        result = triage(args.query, provider)
    except ValidationError as error:
        fail("respuesta inválida del modelo", f"la respuesta del modelo no cumple el contrato:\n{error}")
    except ValueError as error:
        # Va después de ValidationError: Pydantic define ValidationError como un tipo de ValueError.
        fail("configuración incompleta", str(error))
    except LLMError as error:
        fail("error de la API del proveedor", str(error))

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
