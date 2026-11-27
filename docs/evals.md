# Resultados de evals

**Dataset:** [`evals/dataset.jsonl`](../evals/dataset.jsonl), con 40 tickets ficticios etiquetados: 10 por categoría. Incluye casos claros (25), informales o con errores de tipeo (6), ambiguos o con dos temas (7), vagos (2) y uno en inglés. Varios casos son "trampas" con palabras de otra categoría (por ejemplo, un error 403 al generar una factura es `technical`, no `billing`).

**Métrica principal:** accuracy de `category`. Un ticket cuenta como acierto si el modelo devolvió JSON válido y la categoría esperada.

## v1 contra v2 (Anthropic, `claude-haiku-5-5`)

| Métrica | v1 zero-shot | v2 few-shot + reglas |
|---|---|---|
| **Accuracy global** | 90,0 % | **97,5 %** |
| billing | 100 % | 100 % |
| technical | 80 % | 90 % |
| account | 100 % | 100 % |
| other | 80 % | 100 % |
| Casos ambiguos (n=5) | 60 % | **100 %** |
| JSON válido | 100 % | 100 % |
| Reintentos | 0 | 0 |
| Confianza media en aciertos / errores | 0,75 / 0,66 | 0,86 / 0,70 |
| Latencia media | 3,23 s | **2,52 s** |
| Tokens por ticket (entrada / salida) | 561 / 536 | 1.864 / 421 |
| Costo por ticket | $0,00032 | $0,00040 |
| Costo de la corrida (40 casos) | $0,0130 | $0,0159 |

Fuente: [`evals/results/dataset_anthropic_v1.json`](../evals/results/dataset_anthropic_v1.json) y [`dataset_anthropic_v2.json`](../evals/results/dataset_anthropic_v2.json). v1 se corrió 2 veces y dio el mismo 90 % con los mismos 4 errores.

**Errores de v1:** `technical-04` (error 403 tomado como permisos de cuenta), `technical-09` (falla de sincronización con Mercado Pago tomada como cobro), `other-03` (consulta de precios antes de contratar tomada como facturación) y `other-09` (pregunta comercial sobre la API tomada como técnica).

**Error de v2:** solo `technical-04`. Es un caso discutible: un 403 puede leerse como falta de permisos.

**El reintento funciona en casos reales:** en una corrida de verificación con Anthropic (2026-11-09), 8 respuestas no cumplieron el contrato en el primer intento y las 8 se recuperaron en el segundo, gracias al reintento que le devuelve los errores al modelo (ver `attempts: 2` en `data/metrics.jsonl`).

## Decisión: v2 es el prompt por defecto

- **Clasifica mejor:** +7,5 puntos en total, y resuelve todos los casos ambiguos, que son donde v1 fallaba.
- **Es más rápido:** 22 % menos de latencia, porque escribe respuestas más cortas.
- **Su confianza es más útil:** separa más los aciertos (0,86) de los errores (0,70).
- **Cuesta 23 % más por ticket:** los 4 ejemplos agregan unos 1.300 tokens de entrada por request. Para el volumen de Nubbix (400 tickets por día) son unos $4,80 por mes con v2 contra $3,90 con v1. La mejora en calidad justifica esa diferencia.

**Técnica de context engineering elegida: few-shot con reglas explícitas.** Los ejemplos fijan el formato y el criterio de clasificación; las reglas cierran los problemas observados en v1 (inventar menús y herramientas, voseo, promesas al cliente, respuestas largas). Cada regla de [`prompts/v2.yaml`](../prompts/v2.yaml) está asociada al problema que corrige en el comentario inicial del archivo.

**Limitaciones de esta comparación:**
- 40 casos son pocos: un caso equivale a 2,5 puntos. La diferencia entre v1 y v2 (3 casos) es consistente, pero no estadísticamente fuerte.
- Las etiquetas las propuso el asistente de IA, sin una segunda revisión independiente; en los casos ambiguos otra persona podría decidir distinto (ver el campo `note` del dataset).
- 2 casos (`account-09`, `technical-09`) se parecen a reglas de desempate de v2. Sin ellos, v2 sigue ganando: 97,4 % contra 92,1 %.

## Mismo prompt, 3 modelos

| Métrica | Haiku 5.5 · v1 | Haiku 5.5 · v2 | Gemini 3.1 Flash-Lite · v1 | Gemini 3.1 Flash-Lite · v2 | GPT-6 Luna · v1 | GPT-6 Luna · v2 |
|---|---|---|---|---|---|---|
| **Accuracy global** | 90,0 % | **97,5 %** | 92,5 % | **97,5 %** | 95,0 % | **100 %** |
| Casos ambiguos (n=5) | 60 % | 100 % | 60 % | 80 % | 80 % | 100 % |
| JSON válido | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |
| Confianza media en aciertos / errores | 0,75 / 0,66 | 0,86 / 0,70 | 0,98 / 0,98 | 0,93 / 0,95 | 0,95 / 0,97 | 0,91 / sin errores |
| Latencia mediana / máxima | 3,2 s / 4,7 s | 2,4 s / 4,6 s | 1,3 s / 32,3 s | 3,7 s / 15,8 s | 1,9 s / 4,5 s | 1,5 s / 2,8 s |
| Tokens por ticket (entrada / salida) | 561 / 536 | 1.864 / 421 | 358 / 157 | 1.166 / 109 | 394 / 118 | 1.168 / 101 |
| Costo por ticket a precio pago | $0,00032 | $0,00040 | $0,00033 | $0,00046 | $0,00010 | $0,00017 |
| Costo real de la corrida | $0,013 | $0,016 | $0 (capa gratuita) | $0 (capa gratuita) | $0,004 | $0,007 |

Fuente: los 6 archivos `dataset_*` de [`evals/results/`](../evals/results/). GPT-6 Luna se corrió el 2026-11-26 con `OPENAI_REASONING_EFFORT=none`, así que no gasta tokens de razonamiento. Gemini se corrió con `--delay 4`; sin esa espera, una primera corrida tuvo 7 de 80 requests rechazados por la API, consistentes con el rate limit de la capa gratuita.

**Lectura:**
- **Calidad:** con v2, Haiku y Gemini empatan en 97,5 % y GPT-6 Luna llega a 100 %. Es 1 caso de diferencia (Haiku falló `technical-04`, el error 403 discutible; Gemini falló `account-10`), así que no es una ventaja fuerte. v2 mejora a los 3, lo que confirma que la mejora viene del prompt y no del modelo.
- **Costo pagando:** GPT-6 Luna con v2 cuesta $0,00017 por ticket, 58 % menos que Haiku ($0,00040). Tiene el mismo precio por token que Haiku, pero usa 37 % menos tokens de entrada y 76 % menos de salida. Entre Haiku y Gemini, Haiku es 13 % más barato. Cada modelo cuenta tokens con su propio tokenizador (el mismo prompt v1 son 561 tokens en Haiku y 358 en Gemini), así que el costo solo se puede comparar midiendo, no estimando con los precios por token.
- **Costo en pruebas:** Gemini es gratis.
- **Confianza:** la de Haiku separa aciertos de errores. La de Gemini no sirve: puso 0,98 también en sus errores. La de GPT-6 Luna tampoco: con v1 puso 0,97 en sus 2 errores, más que en los aciertos. Con v2 no tuvo errores, así que no se puede medir.
- **Latencia:** GPT-6 Luna es el más rápido y el más estable (máximo 2,8 s). Haiku también es estable. En la capa gratuita, Gemini tuvo picos de 15 a 32 segundos, probablemente por los reintentos automáticos del SDK ante el rate limit.

**Recomendación:** prompt v2 con GPT-6 Luna para producción (el más barato pagando, el más rápido y el mejor en la suite adversarial). Haiku 5.5 si el equipo va a priorizar tickets por `confidence`. Gemini con la capa gratuita para desarrollo y pruebas.
