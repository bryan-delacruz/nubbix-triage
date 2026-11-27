"""Evaluación del guardrail sin llamar al LLM: cuántos ataques frena y cuántos clientes bloquea por error.

Uso:
    python -m evals.guardrails_eval

Cuesta $0 y tarda menos de un segundo. Mide 3 cosas:

1. Guardrail de entrada contra 2 conjuntos:
   - Ataques: los de evals/adversarial.jsonl.
   - Tickets legítimos: los de evals/dataset.jsonl y los de evals/legit_hard.jsonl. Los
     "difíciles" usan palabras que también aparecen en ataques ("instrucciones", "sistema",
     "ignorar", "prompt").
   Con eso calcula detección (ataques frenados), falsos positivos (clientes frenados) y precisión
   (de lo que frena, cuánto era de verdad un ataque).
2. Defensa por capa: lee los resultados guardados de la suite adversarial (evals/results/
   adversarial_*.json) y cuenta qué capa frenó cada ataque: entrada, modelo o salida.
3. Falsos positivos de salida: en las corridas guardadas del dataset (evals/results/dataset_*.json),
   cuenta los tickets legítimos cuya respuesta bloqueó el guardrail de salida.
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evals.adversarial import ADVERSARIAL_DATASET
from evals.runner import DEFAULT_DATASET, EVALS_DIR, RESULTS_DIR, load_dataset
from src.guardrails import check_input

HARD_LEGIT_DATASET = EVALS_DIR / "legit_hard.jsonl"
OUTPUT = RESULTS_DIR / "guardrails_eval.json"
LAYERS = {"blocked_input": "entrada", "resisted": "modelo", "blocked_output": "salida", "succeeded": "pasó", "error": "error"}


def ratio(part: int, total: int) -> float | None:
    return part / total if total else None


def evaluate_input(attacks: list[dict], legit: list[dict]) -> dict:
    """Matriz de confusión del guardrail de entrada. Positivo = bloqueado."""
    attack_rows = [{**case, "blocked": not check_input(case["query"]).allowed} for case in attacks]
    legit_rows = []
    for case in legit:
        check = check_input(case["query"])
        legit_rows.append({**case, "blocked": not check.allowed, "reason": check.reason, "matched": check.matched})

    true_positives = sum(row["blocked"] for row in attack_rows)
    false_positives = sum(row["blocked"] for row in legit_rows)
    by_type = defaultdict(lambda: [0, 0])  # tipo -> [bloqueados, total]
    for row in attack_rows:
        by_type[row["attack_type"]][0] += row["blocked"]
        by_type[row["attack_type"]][1] += 1

    return {
        "attacks": len(attack_rows),
        "legit": len(legit_rows),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "detection_rate": ratio(true_positives, len(attack_rows)),
        "false_positive_rate": ratio(false_positives, len(legit_rows)),
        "precision": ratio(true_positives, true_positives + false_positives),
        "by_attack_type": {name: {"blocked": b, "total": t} for name, (b, t) in sorted(by_type.items())},
        "missed_attacks": [{"id": r["id"], "technique": r["technique"]} for r in attack_rows if not r["blocked"]],
        "false_positive_cases": [
            {"id": r["id"], "query": r["query"], "reason": r["reason"], "matched": r["matched"]}
            for r in legit_rows if r["blocked"]
        ],
    }


def layers_from_results(results_dir: Path) -> list[dict]:
    """Qué capa frenó cada ataque, según las corridas guardadas de la suite adversarial (con guardrails)."""
    summaries = []
    for path in sorted(results_dir.glob("adversarial_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        counts = Counter(row["outcome"] for row in report["with_guardrails"])
        summaries.append({
            "file": path.name,
            "model": report["model"],
            "prompt_version": report["prompt_version"],
            "attacks": len(report["with_guardrails"]),
            "layers": {LAYERS[outcome]: counts[outcome] for outcome in LAYERS},
        })
    return summaries


def output_false_positives(results_dir: Path) -> list[dict]:
    """Tickets legítimos del dataset cuya respuesta frenó el guardrail de salida."""
    summaries = []
    for path in sorted(results_dir.glob("dataset_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        cases = report["cases"]
        blocked = [case["id"] for case in cases if case["status"] == "blocked_output"]
        summaries.append({"file": path.name, "model": report["model"], "cases": len(cases), "blocked_output": blocked})
    return summaries


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def print_report(input_eval: dict, layers: list[dict], outputs: list[dict]) -> None:
    print("\n=== Guardrail de entrada (sin LLM) ===\n")
    print(f"Ataques frenados:      {input_eval['true_positives']}/{input_eval['attacks']}  detección {pct(input_eval['detection_rate'])}")
    print(f"Clientes frenados:     {input_eval['false_positives']}/{input_eval['legit']}  falsos positivos {pct(input_eval['false_positive_rate'])}")
    print(f"Precisión:             {pct(input_eval['precision'])}  (de lo que frena, cuánto era un ataque)")

    print(f"\n{'tipo de ataque':<15} frenados")
    for name, row in input_eval["by_attack_type"].items():
        print(f"{name:<15} {row['blocked']}/{row['total']}")

    print("\nAtaques que pasan la entrada (los define el modelo o el guardrail de salida):")
    for row in input_eval["missed_attacks"]:
        print(f"  {row['id']}  {row['technique']}")

    print("\nFalsos positivos:")
    for row in input_eval["false_positive_cases"] or [{"id": "ninguno", "matched": ""}]:
        print(f"  {row['id']}  {row.get('matched') or ''}")

    print("\n=== Defensa por capa (corridas guardadas de la suite adversarial, con guardrails) ===\n")
    header = "  ".join(f"{name:>7}" for name in LAYERS.values())
    print(f"{'modelo':<24} {'prompt':<7} {'ataques':>7}  {header}")
    for row in layers:
        cells = "  ".join(f"{row['layers'][name]:>7}" for name in LAYERS.values())
        print(f"{row['model']:<24} {row['prompt_version']:<7} {row['attacks']:>7}  {cells}")

    print("\n=== Guardrail de salida sobre tickets legítimos (corridas guardadas del dataset) ===\n")
    for row in outputs:
        blocked = ", ".join(row["blocked_output"]) or "ninguno"
        print(f"{row['file']:<32} {len(row['blocked_output'])}/{row['cases']} bloqueados  ({blocked})")


def main() -> None:
    attacks = load_dataset(ADVERSARIAL_DATASET)
    legit = load_dataset(DEFAULT_DATASET) + load_dataset(HARD_LEGIT_DATASET)
    input_eval = evaluate_input(attacks, legit)
    layers = layers_from_results(RESULTS_DIR)
    outputs = output_false_positives(RESULTS_DIR)
    print_report(input_eval, layers, outputs)

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": input_eval,
        "layers": layers,
        "output_false_positives": outputs,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle guardado en {OUTPUT.relative_to(EVALS_DIR.parent)}")


if __name__ == "__main__":
    main()
