"""Carga de prompts versionados desde prompts/*.yaml."""

import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.schemas import TriageResponse

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_PROMPT_VERSION = "v1"
SCHEMA_PLACEHOLDER = "{schema}"


class Prompt(BaseModel):
    """Una versión de prompt. Se valida al cargarla, para detectar errores en el YAML."""

    version: str
    technique: str
    description: str
    max_tokens: int = Field(gt=0)
    system: str


def available_versions() -> list[str]:
    """Versiones disponibles, según los archivos de prompts/ (v1.yaml -> "v1")."""
    return sorted(path.stem for path in PROMPTS_DIR.glob("*.yaml"))


def load_prompt(version: str) -> Prompt:
    """Lee prompts/<version>.yaml, lo valida y completa el JSON Schema del contrato."""
    path = PROMPTS_DIR / f"{version}.yaml"
    if not path.exists():
        raise ValueError(f"No existe el prompt '{version}'. Disponibles: {', '.join(available_versions())}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    prompt = Prompt.model_validate(data)
    if prompt.version != version:
        raise ValueError(f"{path.name} declara version: {prompt.version}; debería ser {version}")
    if SCHEMA_PLACEHOLDER not in prompt.system:
        raise ValueError(f"{path.name}: el system prompt debe incluir {SCHEMA_PLACEHOLDER}")

    schema = json.dumps(TriageResponse.model_json_schema(), ensure_ascii=False)
    return prompt.model_copy(update={"system": prompt.system.replace(SCHEMA_PLACEHOLDER, schema)})


if __name__ == "__main__":
    print(f"Versiones disponibles: {available_versions()}")
    prompt = load_prompt(DEFAULT_PROMPT_VERSION)
    print(f"version={prompt.version}  technique={prompt.technique}  max_tokens={prompt.max_tokens}")
    print(f"description: {prompt.description}")
    print(f"\n--- system prompt (primeros 400 caracteres) ---\n{prompt.system[:400]}...")
