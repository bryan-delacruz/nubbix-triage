# Uso de IA en el desarrollo

El proyecto se construyó con **Claude Code** (Anthropic) como asistente de programación, en una conversación continua. La consigna permite usar IA siempre que se documenten los prompts y cómo influyeron en las decisiones. Este archivo lo resume.

## Cómo se trabajó

La regla fue **aprender, no delegar**: cada commit siguió el mismo ciclo.

1. **Explicar** el concepto del commit: qué problema resuelve y qué parte de la rúbrica cubre.
2. **Implementar** solo los archivos de ese commit.
3. **Verificar** con comandos reales: llamadas a la API, evals, casos de error.
4. **Commitear** solo después de la aprobación explícita.

Las explicaciones se pidieron en 2 niveles: una vista de negocio y una vista técnica, con énfasis en la sintaxis de Python y en el comportamiento implícito de las librerías (por ejemplo, el atributo `model_config` de Pydantic o la variable `ANTHROPIC_BASE_URL` que lee el SDK).

## Prompts principales y qué decidieron

| Prompt (resumido) | Qué salió de ahí |
|---|---|
| Se compartieron la guía, la consigna, los ejemplos de tickets, los entregables y la rúbrica, y se pidió "un plan de acción antes de meter código" | Plan de 20 commits por etapas, con un hito funcional en cada etapa, y este README con vista de producto y vista técnica |
| "Avanzar paso a paso, commit por commit, para entender cómo hacerlo" | El ciclo explicar → implementar → verificar → commitear |
| "Necesitamos usar los modelos más económicos para las pruebas" | Búsqueda de precios en las páginas oficiales |
| "Asegura bien la información que das y según eso decidimos" | Segunda verificación, literal, de cada precio y fecha de retiro. Se descartó `gpt-5-nano` (OpenAI lo apaga el 2026-12-11) y se eligió Gemini (capa gratuita) + Anthropic Haiku 5.5 |
| "¿Es obligatorio usar OpenAI y Anthropic, o podemos usar Google?" | Confirmación en la consigna de que los proveedores son un ejemplo, no un requisito |
| "Hagamos el test con Gemini para validar cuál sale menos" | Evals con los 2 modelos: con v2 empatan en 97,5 %. Pagando, Haiku es 13 % más barato por ticket; en pruebas, Gemini es gratis |
| "¿También tienes la comparativa entre 2 modelos con el mismo prompt?" | La tabla de 2 modelos × 2 prompts del README (extra credit) |
| "¿Con qué modelos probaste?" (sobre los guardrails) | Las pruebas de seguridad se repitieron con Gemini, y ahí apareció el resultado clave: sin guardrails, Gemini cae en 3 de 10 ataques |

## Lo que la IA propuso y se corrigió con datos

La IA se equivocó varias veces; cada error se detectó al medir o al probar, no al leer el código:

- **Costo de Gemini mal estimado:** se estimó que Gemini era 2,7 veces más caro por ticket, usando los tokens de Haiku. Al medir, cada modelo cuenta tokens distinto (el mismo prompt v1: 561 tokens en Haiku, 358 en Gemini) y el costo resultó casi igual. Conclusión documentada: el costo entre modelos solo se compara midiendo.
- **Un bug del runner que encontró el usuario:** correr `--limit 3` pisaba el resultado completo de 40 casos, y mostraba `0,0 %` en categorías sin casos. Se corrigió antes de entregar.
- **Falsos positivos del guardrail:** la primera versión bloqueaba tickets legítimos ("¿**Dan** capacitaciones?", "la app **actúa como** si no tuviera internet"). Se encontraron corriendo el guardrail sobre el dataset y se ajustaron los patrones.
- **Un fragmento del prompt que nunca coincidía:** el guardrail de salida buscaba "nivel 1", pero la normalización convierte el "1" en "i" (leetspeak). Se vio en la prueba y se corrigió.
- **Rechazos contados como errores:** la suite adversarial mostró que un `stop_reason: refusal` de Claude se registraba como error de API. Se agregó el status `refused`.
- **La key de Gemini dejó de funcionar a mitad del proyecto:** el proyecto de Google Cloud se había borrado, y con él la key. El manejo de errores del commit 9 lo reportó con un mensaje claro y sin romper la CLI.

## Quién decidió qué

| Decisión | Quién |
|---|---|
| Trabajar paso a paso, un commit a la vez, con explicación de cada pieza | El usuario |
| Usar los modelos más económicos y verificar cada dato antes de decidir | El usuario |
| Sumar Gemini y medir cuál sale más barato, en vez de estimarlo | El usuario |
| Gemini como proveedor por defecto (costo cero en pruebas) | El usuario, con los precios verificados |
| v2 como prompt por defecto | Propuesta de la IA, aceptada con los números de los evals a la vista |
| Los 40 tickets del dataset, los 10 ataques y sus etiquetas | Propuestos por la IA. El criterio de cada caso ambiguo quedó escrito en el campo `note` para que se pueda revisar; no hubo una segunda revisión independiente |
| El código | Escrito por la IA y revisado en cada commit con pruebas reales |
