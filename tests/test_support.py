"""Módulos de soporte: caché, prompts, precios, métricas y configuración."""

import json

import pytest

from src import cache
from src.config import load_settings, mask
from src.metrics import build_record, log_request
from src.pricing import PRICES, estimate_cost
from src.prompts import SCHEMA_PLACEHOLDER, available_versions, load_prompt
from src.triage import fallback_response


# --- Caché ---

def test_cache_key_ignores_outer_spaces():
    assert cache.cache_key("p", "m", "s", "hola") == cache.cache_key("p", "m", "s", "  hola ")


@pytest.mark.parametrize("change", [("x", "m", "s", "hola"), ("p", "x", "s", "hola"), ("p", "m", "x", "hola"), ("p", "m", "s", "chau")])
def test_cache_key_changes_with_any_field(change):
    assert cache.cache_key(*change) != cache.cache_key("p", "m", "s", "hola")


def test_cache_roundtrip(tmp_path):
    response = fallback_response("x")
    cache.put("abc", response, tmp_path / "nuevo")  # crea la carpeta si no existe
    assert cache.get("abc", tmp_path / "nuevo") == response


def test_cache_miss_returns_none(tmp_path):
    assert cache.get("no-existe", tmp_path) is None


@pytest.mark.parametrize("content", ["{roto", '{"answer": "sin el resto"}'])
def test_corrupt_cache_file_is_a_miss(tmp_path, content):
    (tmp_path / "abc.json").write_text(content)
    assert cache.get("abc", tmp_path) is None


# --- Prompts ---

def test_both_prompt_versions_exist():
    assert {"v1", "v2"} <= set(available_versions())


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_load_prompt_injects_schema(version):
    prompt = load_prompt(version)
    assert prompt.version == version
    assert SCHEMA_PLACEHOLDER not in prompt.system
    assert '"additionalProperties": false' in prompt.system
    assert prompt.max_tokens > 0


@pytest.mark.parametrize("version", ["v9", "../../.env", "v1.yaml", ""])
def test_load_prompt_rejects_unknown_versions(version):
    with pytest.raises(ValueError, match="No existe el prompt"):
        load_prompt(version)


# --- Precios y métricas ---

def test_estimate_cost():
    # 1M de tokens de entrada y 1M de salida de Haiku: $0.10 + $0.50
    assert estimate_cost("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)


def test_estimate_cost_unknown_model():
    assert estimate_cost("modelo-x", 10, 10) is None


@pytest.mark.parametrize("model", ["gemini-3.1-flash-lite", "claude-haiku-5-5", "gpt-6-luna"])
def test_default_models_have_price(model):
    assert model in PRICES


def test_build_record_fields():
    record = build_record(
        provider="openai", model="gpt-6-luna", prompt_version="v2", status="ok", attempts=1,
        category="billing", input_tokens=1000, output_tokens=100, latency_s=1.23456,
    )
    assert record["total_tokens"] == 1100
    assert record["latency_s"] == 1.235
    assert record["cost_usd"] == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1_000_000)
    assert record["cache_hit"] is False
    assert {"timestamp", "price_input_per_mtok", "prices_verified_on"} <= record.keys()


def test_build_record_unknown_model_has_no_price():
    record = build_record(
        provider="x", model="modelo-x", prompt_version="v2", status="ok", attempts=1,
        category=None, input_tokens=1, output_tokens=1, latency_s=0,
    )
    assert record["cost_usd"] is None and record["price_input_per_mtok"] is None


def test_log_request_appends(tmp_path):
    path = tmp_path / "sub" / "metrics.jsonl"
    log_request({"n": 1}, path)
    log_request({"n": 2}, path)
    assert [json.loads(line)["n"] for line in path.read_text().splitlines()] == [1, 2]


# --- Configuración ---

def test_settings_defaults(monkeypatch):
    for name in ["LLM_PROVIDER", "GEMINI_MODEL", "ANTHROPIC_MODEL", "OPENAI_MODEL", "OPENAI_REASONING_EFFORT"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("src.config.load_dotenv", lambda: None)  # ignorar el .env real
    settings = load_settings()
    assert settings.default_provider == "gemini"
    assert settings.openai_model == "gpt-6-luna"
    assert settings.openai_reasoning_effort == "none"


def test_settings_provider_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", " OpenAI ")
    assert load_settings().default_provider == "openai"


def test_settings_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    with pytest.raises(ValueError, match="no es válido"):
        load_settings()


def test_mask_hides_secret():
    assert mask("sk-proj-secreto") == "sk-pro…"
    assert mask(None) == "(no configurada)"


# --- Prompts con YAML defectuoso ---

@pytest.fixture
def prompts_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("src.prompts.PROMPTS_DIR", tmp_path)
    return tmp_path


def write_prompt(folder, name, version, system):
    (folder / f"{name}.yaml").write_text(
        f"version: {version}\ntechnique: t\ndescription: d\nmax_tokens: 10\nsystem: '{system}'\n",
        encoding="utf-8",
    )


def test_prompt_version_must_match_file_name(prompts_dir):
    write_prompt(prompts_dir, "v7", "v8", "texto {schema}")
    with pytest.raises(ValueError, match="debería ser v7"):
        load_prompt("v7")


def test_prompt_must_include_schema_placeholder(prompts_dir):
    write_prompt(prompts_dir, "v7", "v7", "texto sin marcador")
    with pytest.raises(ValueError, match="debe incluir"):
        load_prompt("v7")
