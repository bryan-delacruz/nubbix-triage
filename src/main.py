"""CLI de triage: recibe una consulta de soporte e imprime el JSON validado."""

import argparse
import sys

from pydantic import ValidationError

from src.config import load_settings
from src.providers.gemini_provider import GeminiProvider
from src.triage import triage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clasifica una consulta de soporte de Nubbix y devuelve JSON."
    )
    parser.add_argument("query", help='Consulta del cliente, entre comillas. Ej: "me cobraron dos veces"')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    provider = GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)

    try:
        result = triage(args.query, provider)
    except ValidationError as error:
        print(f"La respuesta del modelo no cumple el contrato:\n{error}", file=sys.stderr)
        sys.exit(1)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
