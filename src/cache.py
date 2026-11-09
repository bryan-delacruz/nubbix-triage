"""Caché de respuestas: si llega la misma consulta con la misma configuración, no se vuelve a llamar al LLM.

La clave es un hash MD5 de todo lo que cambia la respuesta: proveedor, modelo, texto completo
del prompt y la consulta. Si se edita el YAML del prompt o se cambia de modelo, la clave cambia
y la caché vieja deja de usarse sola.

MD5 no es seguro para contraseñas o firmas, pero acá solo se usa como identificador: es rápido
y da siempre los mismos 32 caracteres para el mismo texto.

Cada entrada es un archivo data/cache/<md5>.json con la respuesta validada.
"""

import hashlib
from pathlib import Path

from src.schemas import TriageResponse

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def cache_key(provider: str, model: str, system_prompt: str, query: str) -> str:
    """MD5 de la configuración y la consulta. Los espacios al inicio y al final no cuentan."""
    raw = "\n".join([provider, model, system_prompt, query.strip()])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get(key: str, cache_dir: Path = CACHE_DIR) -> TriageResponse | None:
    """Respuesta guardada, o None si no existe o el archivo está dañado (se trata como "no hay")."""
    path = cache_dir / f"{key}.json"
    try:
        return TriageResponse.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # OSError: no existe o no se puede leer. ValueError: incluye el ValidationError de Pydantic.
        return None


def put(key: str, response: TriageResponse, cache_dir: Path = CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(response.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    base = cache_key("anthropic", "claude-haiku-5-5", "prompt v2", "me cobraron dos veces")
    print(f"consulta original:      {base}")
    print(f"con espacios extra:     {cache_key('anthropic', 'claude-haiku-5-5', 'prompt v2', '  me cobraron dos veces  ')}")
    print(f"otra consulta:          {cache_key('anthropic', 'claude-haiku-5-5', 'prompt v2', 'me cobraron tres veces')}")
    print(f"otro modelo:            {cache_key('gemini', 'gemini-3.1-flash-lite', 'prompt v2', 'me cobraron dos veces')}")
