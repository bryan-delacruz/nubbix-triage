"""Los 3 proveedores con su SDK simulado: ninguna prueba llama a internet.

Cada proveedor guarda su cliente en self.client. Los tests lo reemplazan por un MagicMock
(un objeto falso que acepta cualquier llamada) y deciden qué responde o qué error lanza.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import openai
import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from openai.types.responses import Response

from src.config import load_settings
from src.providers.anthropic_provider import AnthropicProvider
from src.providers.base import LLMError, LLMProvider, LLMRefusal
from src.providers.factory import build_provider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_provider import OpenAIProvider

REQUEST = httpx.Request("POST", "https://api.example.com")


def http_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=REQUEST)


# --- Interfaz y factory ---

def test_interface_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LLMProvider()


@pytest.mark.parametrize("name, cls", [("gemini", GeminiProvider), ("anthropic", AnthropicProvider), ("openai", OpenAIProvider)])
def test_factory_builds_each_provider(monkeypatch, name, cls):
    for key in ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.setenv(key, "test-key")
    provider = build_provider(name, load_settings())
    assert isinstance(provider, cls)
    assert provider.name == name


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Proveedor desconocido"):
        build_provider("mistral", load_settings())


@pytest.mark.parametrize("cls", [GeminiProvider, AnthropicProvider, OpenAIProvider])
def test_missing_key_is_a_clear_error(cls):
    with pytest.raises(ValueError, match="API_KEY"):
        cls(api_key=None, model="x")


# --- OpenAI ---

def openai_response(output, incomplete=None, usage=True):
    return Response.model_validate({
        "id": "r1", "object": "response", "created_at": 0, "model": "gpt-6-luna",
        "status": "incomplete" if incomplete else "completed",
        "incomplete_details": {"reason": incomplete} if incomplete else None,
        "output": output, "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "usage": {
            "input_tokens": 120, "output_tokens": 45, "total_tokens": 165,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 5},
        } if usage else None,
    })


def message(*blocks):
    return {"type": "message", "id": "m1", "role": "assistant", "status": "completed", "content": list(blocks)}


def text_block(text):
    return {"type": "output_text", "text": text, "annotations": []}


@pytest.fixture
def openai_provider():
    provider = OpenAIProvider(api_key="test-key", model="gpt-6-luna")
    provider.client = MagicMock()
    return provider


def test_openai_joins_text_and_skips_reasoning(openai_provider):
    openai_provider.client.responses.create.return_value = openai_response(
        [{"type": "reasoning", "id": "rs", "summary": []}, message(text_block('{"a":'), text_block("1}"))]
    )
    result = openai_provider.complete("sistema", "ticket", 100)
    assert result.text == '{"a":1}'
    assert (result.input_tokens, result.output_tokens) == (120, 45)
    assert not result.truncated


def test_openai_sends_expected_parameters(openai_provider):
    openai_provider.client.responses.create.return_value = openai_response([message(text_block("x"))])
    openai_provider.complete("sistema", "ticket", 100)
    sent = openai_provider.client.responses.create.call_args.kwargs
    assert sent["instructions"] == "sistema"
    assert sent["input"] == "ticket"
    assert sent["max_output_tokens"] == 100
    assert sent["reasoning"] == {"effort": "none"}
    assert sent["store"] is False


def test_openai_truncated(openai_provider):
    openai_provider.client.responses.create.return_value = openai_response([message(text_block("{"))], incomplete="max_output_tokens")
    assert openai_provider.complete("s", "u", 10).truncated


def test_openai_refusal_block(openai_provider):
    openai_provider.client.responses.create.return_value = openai_response([message({"type": "refusal", "refusal": "no"})])
    with pytest.raises(LLMRefusal):
        openai_provider.complete("s", "u", 10)


def test_openai_content_filter(openai_provider):
    openai_provider.client.responses.create.return_value = openai_response([], incomplete="content_filter")
    with pytest.raises(LLMRefusal, match="filtro"):
        openai_provider.complete("s", "u", 10)


def test_openai_without_usage(openai_provider):
    openai_provider.client.responses.create.return_value = openai_response([message(text_block("x"))], usage=False)
    assert openai_provider.complete("s", "u", 10).input_tokens == 0


@pytest.mark.parametrize(
    "code, expected",
    [(None, "rate limit"), ("insufficient_quota", "no tiene créditos"), ("credit_balance_exhausted", "no tiene créditos")],
)
def test_openai_429_rate_limit_vs_no_credits(openai_provider, code, expected):
    body = {"code": code} if code else None
    openai_provider.client.responses.create.side_effect = openai.RateLimitError("429", response=http_response(429), body=body)
    with pytest.raises(LLMError, match=expected):
        openai_provider.complete("s", "u", 10)


def test_openai_invalid_key(openai_provider):
    openai_provider.client.responses.create.side_effect = openai.AuthenticationError("401", response=http_response(401), body=None)
    with pytest.raises(LLMError, match="API key inválida"):
        openai_provider.complete("s", "u", 10)


def test_openai_connection_error(openai_provider):
    openai_provider.client.responses.create.side_effect = openai.APIConnectionError(request=REQUEST)
    with pytest.raises(LLMError, match="conectar"):
        openai_provider.complete("s", "u", 10)


def test_openai_rejects_unknown_reasoning_effort():
    with pytest.raises(ValueError, match="OPENAI_REASONING_EFFORT"):
        OpenAIProvider(api_key="k", model="x", reasoning_effort="turbo")


# --- Anthropic ---

def anthropic_message(blocks, stop_reason="end_turn"):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=80, output_tokens=30),
    )


@pytest.fixture
def anthropic_provider():
    provider = AnthropicProvider(api_key="test-key", model="claude-haiku-5-5")
    provider.client = MagicMock()
    return provider


def test_anthropic_keeps_only_text_blocks(anthropic_provider):
    anthropic_provider.client.messages.create.return_value = anthropic_message([
        SimpleNamespace(type="thinking", thinking="..."),
        SimpleNamespace(type="text", text="hola"),
    ])
    result = anthropic_provider.complete("s", "u", 10)
    assert result.text == "hola"
    assert (result.input_tokens, result.output_tokens) == (80, 30)


def test_anthropic_truncated(anthropic_provider):
    anthropic_provider.client.messages.create.return_value = anthropic_message([SimpleNamespace(type="text", text="{")], "max_tokens")
    assert anthropic_provider.complete("s", "u", 10).truncated


def test_anthropic_refusal(anthropic_provider):
    anthropic_provider.client.messages.create.return_value = anthropic_message([], "refusal")
    with pytest.raises(LLMRefusal):
        anthropic_provider.complete("s", "u", 10)


def test_anthropic_status_error(anthropic_provider):
    anthropic_provider.client.messages.create.side_effect = anthropic.APIStatusError("500", response=http_response(500), body=None)
    with pytest.raises(LLMError, match="HTTP 500"):
        anthropic_provider.complete("s", "u", 10)


def test_anthropic_connection_error(anthropic_provider):
    anthropic_provider.client.messages.create.side_effect = anthropic.APIConnectionError(request=REQUEST)
    with pytest.raises(LLMError, match="conectar"):
        anthropic_provider.complete("s", "u", 10)


# --- Gemini ---

def gemini_response(text="hola", finish=genai_types.FinishReason.STOP, block_reason=None, usage=True, candidates=True):
    return SimpleNamespace(
        text=text,
        prompt_feedback=SimpleNamespace(block_reason=block_reason) if block_reason else None,
        candidates=[SimpleNamespace(finish_reason=finish)] if candidates else [],
        usage_metadata=SimpleNamespace(prompt_token_count=70, candidates_token_count=20, thoughts_token_count=5) if usage else None,
    )


@pytest.fixture
def gemini_provider():
    provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
    provider.client = MagicMock()
    return provider


def test_gemini_counts_thoughts_as_output(gemini_provider):
    gemini_provider.client.models.generate_content.return_value = gemini_response()
    result = gemini_provider.complete("s", "u", 10)
    assert result.text == "hola"
    assert (result.input_tokens, result.output_tokens) == (70, 25)


def test_gemini_truncated(gemini_provider):
    gemini_provider.client.models.generate_content.return_value = gemini_response(finish=genai_types.FinishReason.MAX_TOKENS)
    assert gemini_provider.complete("s", "u", 10).truncated


def test_gemini_without_usage(gemini_provider):
    gemini_provider.client.models.generate_content.return_value = gemini_response(usage=False, text=None)
    result = gemini_provider.complete("s", "u", 10)
    assert (result.text, result.input_tokens, result.output_tokens) == ("", 0, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"finish": genai_types.FinishReason.SAFETY},
        {"block_reason": "PROHIBITED_CONTENT"},
        {"candidates": False},
    ],
)
def test_gemini_refusals(gemini_provider, kwargs):
    gemini_provider.client.models.generate_content.return_value = gemini_response(**kwargs)
    with pytest.raises(LLMRefusal):
        gemini_provider.complete("s", "u", 10)


def test_gemini_api_error_includes_message(gemini_provider):
    error = genai_errors.APIError(400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}})
    gemini_provider.client.models.generate_content.side_effect = error
    with pytest.raises(LLMError, match="API key not valid"):
        gemini_provider.complete("s", "u", 10)


def test_gemini_network_error(gemini_provider):
    gemini_provider.client.models.generate_content.side_effect = TimeoutError()
    with pytest.raises(LLMError, match="TimeoutError"):
        gemini_provider.complete("s", "u", 10)


def test_describe_status_other_4xx():
    from src.providers.base import describe_status

    assert describe_status(400) == "La API rechazó la petición"
    assert "servicio" in describe_status(503)
    assert "Modelo no encontrado" in describe_status(404)
