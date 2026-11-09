"""CLI de triage: recibe una consulta de soporte e imprime el JSON validado."""

import argparse
import sys

from src.cache import CACHE_DIR
from src.config import SUPPORTED_PROVIDERS, load_settings
from src.prompts import DEFAULT_PROMPT_VERSION, available_versions, load_prompt
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
    parser.add_argument(
        "--prompt",
        choices=available_versions(),
        default=DEFAULT_PROMPT_VERSION,
        help=f"Versión de prompt de prompts/ (por defecto: {DEFAULT_PROMPT_VERSION})",
    )
    parser.add_argument("--no-cache", action="store_true", help="Llamar siempre al LLM, sin usar la caché")
    return parser.parse_args()


def main() -> None:
    settings = load_settings()
    args = parse_args(settings.default_provider)

    try:
        provider = build_provider(args.provider, settings)
        prompt = load_prompt(args.prompt)
    except ValueError as error:
        # Falta una key o el YAML está mal: no se llega a llamar a la API, así que no hay métricas.
        print(f"Error: {error}", file=sys.stderr)
        print(fallback_response("configuración incompleta").model_dump_json(indent=2))
        sys.exit(1)

    result = triage(args.query, provider, prompt, cache_dir=None if args.no_cache else CACHE_DIR)
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
    print(result.response.model_dump_json(indent=2))
    if result.status != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
