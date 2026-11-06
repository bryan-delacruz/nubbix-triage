"""Runner de evals: corre el dataset contra un proveedor y una versión de prompt.

Uso:
    python -m evals.runner --provider anthropic --prompt v2
    python -m evals.runner --provider gemini --prompt v1 --limit 5

Imprime el score global y por categoría, y guarda el detalle en evals/results/.
Es un script simple a propósito: sin pytest ni frameworks de testing.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from src.config import SUPPORTED_PROVIDERS, load_settings
from src.pricing import estimate_cost
from src.prompts import DEFAULT_PROMPT_VERSION, available_versions, load_prompt
from src.providers.factory import build_provider
from src.schemas import Category
from src.triage import triage

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVALS_DIR / "dataset.jsonl"
RESULTS_DIR = EVALS_DIR / "results"
CATEGORIES = get_args(Category)


def load_dataset(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def run_case(case: dict, provider, prompt) -> dict:
    """Corre un ticket y devuelve una fila con lo esperado, lo obtenido y el consumo."""
    result = triage(case["query"], provider, prompt)
    predicted = result.response.category if result.status == "ok" else None
    return {
        "id": case["id"],
        "tags": case.get("tags", []),
        "expected": case["expected_category"],
        "predicted": predicted,
        "correct": predicted == case["expected_category"],
        "status": result.status,
        "confidence": result.response.confidence if result.status == "ok" else None,
        "attempts": result.attempts,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_s": round(result.latency_s, 3),
        "cost_usd": estimate_cost(provider.model, result.input_tokens, result.output_tokens) or 0.0,
    }


def accuracy(rows: list[dict]) -> float | None:
    """Proporción de aciertos. None si no hay casos (no es lo mismo que 0 %)."""
    return sum(row["correct"] for row in rows) / len(rows) if rows else None


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(rows: list[dict]) -> dict:
    """Score global, por categoría y por tipo de caso, más consumo total."""
    by_category = defaultdict(list)
    by_tag = defaultdict(list)
    for row in rows:
        by_category[row["expected"]].append(row)
        for tag in row["tags"]:
            by_tag[tag].append(row)

    ok_rows = [row for row in rows if row["status"] == "ok"]
    return {
        "cases": len(rows),
        "accuracy": accuracy(rows),
        "valid_json_rate": len(ok_rows) / len(rows) if rows else 0.0,
        "by_category": {cat: {"n": len(by_category[cat]), "accuracy": accuracy(by_category[cat])} for cat in CATEGORIES},
        "by_tag": {tag: {"n": len(items), "accuracy": accuracy(items)} for tag, items in sorted(by_tag.items())},
        "avg_confidence_correct": average([r["confidence"] for r in ok_rows if r["correct"]]),
        "avg_confidence_wrong": average([r["confidence"] for r in ok_rows if not r["correct"]]),
        "retries": sum(row["attempts"] - 1 for row in rows),
        "avg_latency_s": average([row["latency_s"] for row in rows]),
        "total_tokens": sum(row["input_tokens"] + row["output_tokens"] for row in rows),
        "total_cost_usd": round(sum(row["cost_usd"] for row in rows), 6),
    }


def print_report(summary: dict, rows: list[dict], provider: str, model: str, prompt_version: str) -> None:
    def pct(value: float | None) -> str:
        return "    -" if value is None else f"{value * 100:5.1f}%"

    def fmt(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}"

    print(f"\n=== Evals: {provider} ({model}) · prompt {prompt_version} · {summary['cases']} casos ===\n")
    print(f"Accuracy global:   {pct(summary['accuracy'])}")
    print(f"JSON válido:       {pct(summary['valid_json_rate'])}")
    print("\nPor categoría:")
    for category, data in summary["by_category"].items():
        print(f"  {category:<10} {pct(data['accuracy'])}  (n={data['n']})")
    print("\nPor tipo de caso:")
    for tag, data in summary["by_tag"].items():
        print(f"  {tag:<12} {pct(data['accuracy'])}  (n={data['n']})")
    print(f"\nConfianza media:   aciertos {fmt(summary['avg_confidence_correct'])} · errores {fmt(summary['avg_confidence_wrong'])}")
    print(f"Reintentos:        {summary['retries']}")
    print(f"Latencia media:    {fmt(summary['avg_latency_s'])} s")
    print(f"Tokens totales:    {summary['total_tokens']}")
    print(f"Costo total:       ${summary['total_cost_usd']:.6f}")

    failures = [row for row in rows if not row["correct"]]
    if failures:
        print("\nErrores:")
        for row in failures:
            print(f"  {row['id']:<14} esperado={row['expected']:<10} obtenido={row['predicted'] or row['status']:<10} confianza={fmt(row['confidence'])}")


def parse_args(default_provider: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Corre el dataset de evals y reporta el score.")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=default_provider)
    parser.add_argument("--prompt", choices=available_versions(), default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Archivo JSONL de casos")
    parser.add_argument("--limit", type=int, help="Correr solo los primeros N casos (para pruebas rápidas)")
    return parser.parse_args()


def main() -> None:
    settings = load_settings()
    args = parse_args(settings.default_provider)
    provider = build_provider(args.provider, settings)
    prompt = load_prompt(args.prompt)
    cases = load_dataset(args.dataset)[: args.limit]

    rows = []
    for number, case in enumerate(cases, start=1):
        row = run_case(case, provider, prompt)
        mark = "✓" if row["correct"] else "✗"
        print(f"[{number}/{len(cases)}] {mark} {row['id']}: {row['predicted'] or row['status']}", file=sys.stderr)
        rows.append(row)

    summary = summarize(rows)
    print_report(summary, rows, provider.name, provider.model, prompt.version)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Una corrida parcial (--limit) va a otro archivo, para no pisar el resultado completo.
    suffix = f"_limit{args.limit}" if args.limit else ""
    output = RESULTS_DIR / f"{args.dataset.stem}_{provider.name}_{prompt.version}{suffix}.json"
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": prompt.version,
        "dataset": args.dataset.name,
        "summary": summary,
        "cases": rows,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle guardado en {output.relative_to(EVALS_DIR.parent)}")


if __name__ == "__main__":
    main()
