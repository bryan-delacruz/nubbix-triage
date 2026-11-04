"""Precios por modelo y cálculo del costo estimado de cada request.

Los precios son los de la capa paga (USD por 1 millón de tokens), copiados de las
páginas oficiales en la fecha indicada. En la capa gratuita de Gemini el costo real
es $0: registramos igual el precio pago para saber cuánto costaría en producción.
"""

from dataclasses import dataclass

PRICES_VERIFIED_ON = "2026-10-29"

GEMINI_PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"
ANTHROPIC_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float  # USD por 1.000.000 de tokens de entrada
    output_per_mtok: float  # USD por 1.000.000 de tokens de salida (incluye razonamiento)
    source: str


PRICES: dict[str, ModelPrice] = {
    "gemini-3.1-flash-lite": ModelPrice(0.25, 1.50, GEMINI_PRICING_URL),
    "gemini-3.5-flash-lite": ModelPrice(0.30, 2.50, GEMINI_PRICING_URL),
    "gemini-2.5-flash-lite": ModelPrice(0.10, 0.40, GEMINI_PRICING_URL),
    # Precio para prompts de hasta 100.000 tokens; nuestros tickets usan menos de 2.000.
    "claude-haiku-5-5": ModelPrice(0.10, 0.50, ANTHROPIC_PRICING_URL),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Costo en USD de un request. Devuelve None si el modelo no está en la tabla."""
    price = PRICES.get(model)
    if price is None:
        return None
    cost = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
    return round(cost, 8)


if __name__ == "__main__":
    # Tokens reales de una llamada a claude-haiku-5-5 del commit 7.
    model, input_tokens, output_tokens = "claude-haiku-5-5", 59, 50
    price = PRICES[model]
    print(f"Modelo: {model}  (precios verificados el {PRICES_VERIFIED_ON})")
    print(f"Entrada: {input_tokens} tokens x ${price.input_per_mtok} / 1M = ${input_tokens * price.input_per_mtok / 1_000_000:.8f}")
    print(f"Salida:  {output_tokens} tokens x ${price.output_per_mtok} / 1M = ${output_tokens * price.output_per_mtok / 1_000_000:.8f}")
    print(f"Total (estimate_cost): ${estimate_cost(model, input_tokens, output_tokens):.8f}")
    print(f"Modelo desconocido:    {estimate_cost('modelo-x', 100, 100)}")
