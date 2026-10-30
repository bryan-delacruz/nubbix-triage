"""CLI de triage: recibe una consulta de soporte e imprime el JSON validado."""

import argparse
import sys

from pydantic import ValidationError

from src.config import SUPPORTED_PROVIDERS, load_settings
from src.providers.factory import build_provider
from src.triage import triage


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


def main() -> None:
    settings = load_settings()
    args = parse_args(settings.default_provider)
    provider = build_provider(args.provider, settings)

    try:
        result = triage(args.query, provider)
    except ValidationError as error:
        print(f"La respuesta del modelo no cumple el contrato:\n{error}", file=sys.stderr)
        sys.exit(1)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
