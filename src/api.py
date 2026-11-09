"""API HTTP del triage (extra credit): la misma lógica que la CLI, expuesta como POST /triage.

Uso:
    uvicorn src.api:app --reload
    curl -X POST localhost:8000/triage -H "Content-Type: application/json" \\
         -d '{"query": "me cobraron dos veces"}'

Documentación interactiva en http://localhost:8000/docs (la genera FastAPI).
"""

from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel, Field

from src.cache import CACHE_DIR
from src.config import load_settings
from src.prompts import DEFAULT_PROMPT_VERSION, load_prompt
from src.providers.base import LLMProvider
from src.providers.factory import build_provider
from src.schemas import TriageResponse
from src.triage import fallback_response, triage

settings = load_settings()
app = FastAPI(title="Nubbix Triage", description="Triage de tickets de soporte con LLMs.")
_providers: dict[str, LLMProvider] = {}  # se crean una vez y se reusan entre requests


class TriageRequest(BaseModel):
    query: str = Field(min_length=1, description="Consulta del cliente en texto libre")
    provider: Literal["gemini", "anthropic"] | None = Field(None, description="Por defecto: LLM_PROVIDER del .env")
    prompt: str = Field(DEFAULT_PROMPT_VERSION, description="Versión de prompt de prompts/")


def get_provider(name: str) -> LLMProvider:
    if name not in _providers:
        _providers[name] = build_provider(name, settings)
    return _providers[name]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage", response_model=TriageResponse)
def triage_ticket(request: TriageRequest, response: Response) -> TriageResponse:
    """Devuelve siempre el contrato. El header X-Triage-Status dice si fue "ok" o por qué no."""
    try:
        provider = get_provider(request.provider or settings.default_provider)
        prompt = load_prompt(request.prompt)
    except ValueError as error:
        # Falta una key o el prompt no existe: mismo respaldo que la CLI.
        response.headers["X-Triage-Status"] = "config_error"
        response.headers["X-Triage-Error"] = str(error)
        return fallback_response("configuración incompleta")

    result = triage(request.query, provider, prompt, cache_dir=CACHE_DIR)
    response.headers["X-Triage-Status"] = result.status
    return result.response
