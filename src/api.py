"""API HTTP del triage (extra credit): la misma lógica que la CLI, expuesta como POST /triage.

Uso:
    uvicorn src.api:app --reload
    curl -X POST localhost:8000/triage -H "Content-Type: application/json" \\
         -d '{"query": "me cobraron dos veces"}'

Documentación interactiva en http://localhost:8000/docs (la genera FastAPI).

Protección básica, configurable en .env:
- API_TOKEN: si tiene valor, cada request debe mandar el header X-API-Key con ese token.
- RATE_LIMIT_PER_MINUTE: requests por minuto por IP (por defecto 30).
"""

import os
import sys
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.cache import CACHE_DIR
from src.config import SUPPORTED_PROVIDERS, load_settings
from src.prompts import DEFAULT_PROMPT_VERSION, Prompt, load_prompt
from src.providers.base import LLMProvider
from src.providers.factory import build_provider
from src.schemas import TriageResponse
from src.triage import fallback_response, triage

settings = load_settings()
API_TOKEN = os.getenv("API_TOKEN") or None
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

app = FastAPI(title="Nubbix Triage", description="Triage de tickets de soporte con LLMs.")
_providers: dict[str, LLMProvider] = {}  # se crean una vez y se reusan entre requests
_requests_by_ip: dict[str, deque] = defaultdict(deque)  # momentos de los últimos requests de cada IP


class TriageRequest(BaseModel):
    query: str = Field(min_length=1, description="Consulta del cliente en texto libre")
    provider: Literal[SUPPORTED_PROVIDERS] | None = Field(None, description="Por defecto: LLM_PROVIDER del .env")
    prompt: str = Field(DEFAULT_PROMPT_VERSION, description="Versión de prompt de prompts/ (v1, v2)")


def get_provider(name: str) -> LLMProvider:
    if name not in _providers:
        _providers[name] = build_provider(name, settings)
    return _providers[name]


@lru_cache
def get_prompt(version: str) -> Prompt:
    """Carga cada versión de prompt una sola vez: los YAML no cambian mientras el servidor corre."""
    return load_prompt(version)


def check_access(client_ip: str, api_key: str | None) -> None:
    """Rechaza el request si falta el token (401) o si la IP superó el límite por minuto (429)."""
    if API_TOKEN and api_key != API_TOKEN:
        raise HTTPException(status_code=401, detail="Falta el header X-API-Key o es incorrecto")
    now = time.monotonic()
    recent = _requests_by_ip[client_ip]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Demasiados requests: espera un minuto")
    recent.append(now)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage", response_model=TriageResponse)
def triage_ticket(
    request: TriageRequest,
    http_request: Request,
    response: Response,
    x_api_key: str | None = Header(default=None),
) -> TriageResponse:
    """Devuelve siempre el contrato. El header X-Triage-Status dice si fue "ok" o por qué no."""
    check_access(http_request.client.host if http_request.client else "desconocido", x_api_key)
    try:
        provider = get_provider(request.provider or settings.default_provider)
        prompt = get_prompt(request.prompt)
    except ValueError as error:
        # Falta una key o el prompt no existe. El detalle va al log del servidor, no al cliente.
        print(f"Error de configuración: {error}", file=sys.stderr)
        response.headers["X-Triage-Status"] = "config_error"
        return fallback_response("configuración incompleta")

    result = triage(request.query, provider, prompt, cache_dir=CACHE_DIR)
    response.headers["X-Triage-Status"] = result.status
    return result.response
