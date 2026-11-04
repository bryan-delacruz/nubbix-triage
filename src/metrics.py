"""Registro de métricas: una línea JSON por request en data/metrics.jsonl (append-only).

Cada campo responde una pregunta concreta:
- timestamp: ¿cuándo se hizo el request?
- provider, model: ¿qué modelo generó este costo y esta latencia?
- status, attempts: ¿funcionó? ¿cuántas llamadas al LLM hicieron falta?
- category: ¿qué tipo de ticket fue? (permite ver costo y latencia por categoría)
- prompt_tokens, completion_tokens, total_tokens: ¿cuánto consumió?
- latency_s: ¿cuánto tardó, sumando todos los intentos?
- cost_usd: ¿cuánto costó?
- price_*_per_mtok, prices_verified_on: ¿con qué precios se calculó? (para auditar cost_usd)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.pricing import PRICES, PRICES_VERIFIED_ON, estimate_cost

METRICS_PATH = Path(__file__).resolve().parent.parent / "data" / "metrics.jsonl"


def build_record(
    *,
    provider: str,
    model: str,
    status: str,
    attempts: int,
    category: str | None,
    input_tokens: int,
    output_tokens: int,
    latency_s: float,
) -> dict:
    price = PRICES.get(model)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "status": status,
        "attempts": attempts,
        "category": category,
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_s": round(latency_s, 3),
        "cost_usd": estimate_cost(model, input_tokens, output_tokens),
        "price_input_per_mtok": price.input_per_mtok if price else None,
        "price_output_per_mtok": price.output_per_mtok if price else None,
        "prices_verified_on": PRICES_VERIFIED_ON,
    }


def log_request(record: dict, path: Path = METRICS_PATH) -> None:
    """Agrega una línea al final del archivo. Nunca modifica las líneas anteriores."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
