"""Small structured-text provider boundary. Ollama is primary; no SDK dependency."""
import asyncio
import json
import logging
import os
import time

import httpx
from pydantic import ValidationError

LOG = logging.getLogger("uvicorn.error")


def provider_name():
    return os.getenv("AI_PROVIDER", "ollama").strip().lower()


def ai_available():
    if os.getenv("NEURAL_OFFLINE") == "1":
        return False
    return provider_name() == "ollama" or provider_name() == "openai" and bool(os.getenv("OPENAI_API_KEY"))


def model_for(task):
    """Route heavyweight offline preparation away from the resident gameplay model."""
    if provider_name() == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    keys = {"scenario": "OLLAMA_SCENARIO_MODEL", "forge": "OLLAMA_FORGE_MODEL", "battle": "OLLAMA_BATTLE_MODEL"}
    defaults = {"scenario": "qwen3:4b", "forge": "qwen3:1.7b", "battle": "qwen3:1.7b"}
    return os.getenv(keys[task]) or os.getenv("OLLAMA_MODEL") or defaults[task]


def deadline(task):
    defaults = {"scenario": 45.0, "forge": 20.0, "battle": 10.0}
    try:
        return min({"battle":10,"forge":20,"scenario":600}[task], max(0.2, float(os.getenv(f"{task.upper()}_AI_TIMEOUT", defaults[task]))))
    except ValueError:
        return defaults[task]


class OllamaProvider:
    async def generate(self, client, schema, instructions, payload, budget, task):
        response = await client.post(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/chat", json={
            "model": model_for(task),
            "messages": [{"role": "system", "content": instructions + " Return only the specified JSON object. /no_think"}, {"role": "user", "content": json.dumps(payload)}],
            "format": schema.model_json_schema(), "stream": False, "think": False, "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": budget},
        })
        response.raise_for_status()
        return response.json()["message"]["content"]


class OpenAIProvider:
    async def generate(self, client, schema, instructions, payload, budget, task):
        response = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, json={
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "store": False,
            "instructions": instructions, "input": json.dumps(payload),
            "text": {"format": {"type": "json_schema", "name": schema.__name__, "strict": True, "schema": schema.model_json_schema()}},
            "max_output_tokens": budget,
        })
        response.raise_for_status()
        return "".join(c.get("text", "") for item in response.json().get("output", []) if item.get("type") == "message" for c in item.get("content", []) if c.get("type") == "output_text")


def _diagnostic(diagnostics, reason, detail=""):
    if diagnostics is not None:
        diagnostics.update(reason=reason, detail=detail[:240])


async def structured(schema, instructions, payload, timeout, retries=1, budget=900, validator=None, task="forge", diagnostics=None):
    label = task.capitalize()
    if not ai_available():
        _diagnostic(diagnostics, "offline_or_unconfigured")
        return None
    provider = OllamaProvider() if provider_name() == "ollama" else OpenAIProvider()
    for attempt in range(retries+1):
        started = time.monotonic()
        try:
            # Every attempt has its own bound; callers also enforce a total deadline.
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=min(1.0, timeout)), trust_env=False) as client:
                raw = await asyncio.wait_for(provider.generate(client, schema, instructions, payload, budget, task), timeout)
            LOG.info("[AI] %s raw response received - elapsed=%.2fs attempt=%d", label, time.monotonic()-started, attempt+1)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            _diagnostic(diagnostics, "timeout", str(exc))
            LOG.warning("[AI] %s timeout after %.2fs", label, timeout)
            continue
        except httpx.HTTPError as exc:
            _diagnostic(diagnostics, "provider_unavailable", f"{type(exc).__name__}: {exc}")
            LOG.warning("[AI] %s provider unavailable: %s", label, type(exc).__name__)
            continue
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            _diagnostic(diagnostics, "provider_envelope_error", f"{type(exc).__name__}: {exc}")
            LOG.warning("[AI] %s provider response error: %s", label, str(exc)[:180])
            continue
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            _diagnostic(diagnostics, "invalid_json", str(exc))
            LOG.warning("[AI] %s JSON parse failed: %s", label, str(exc)[:180])
            continue
        try:
            result = schema.model_validate(decoded).model_dump()
        except ValidationError as exc:
            _diagnostic(diagnostics, "schema_validation", str(exc))
            LOG.warning("[AI] %s schema validation failed: %s", label, str(exc).replace("\n", " ")[:220])
            continue
        try:
            result = validator(result) if validator else result
        except ValueError as exc:
            _diagnostic(diagnostics, "semantic_validation", str(exc))
            LOG.warning("[AI] %s semantic validation failed: %s", label, str(exc)[:180])
            continue
        _diagnostic(diagnostics, "ok")
        LOG.info("[AI] %s parsed successfully", label)
        return result
    return None


async def provider_status():
    models = {task: model_for(task) for task in ("scenario", "forge", "battle")}
    offline = os.getenv("NEURAL_OFFLINE") == "1"
    result = {"provider": provider_name(), "model": models["forge"], "models": models,
              "forge_model": models["forge"], "battle_model": models["battle"], "scenario_model": models["scenario"],
              "forge_timeout": deadline("forge"), "battle_timeout": deadline("battle"), "offline": offline,
              "available": False, "scenario_available": False}
    if not ai_available():
        return result
    if provider_name() == "openai":
        return {**result, "available": True, "scenario_available": True}
    try:
        async with httpx.AsyncClient(timeout=0.8, trust_env=False) as client:
            response = await client.get(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/tags")
            response.raise_for_status()
            installed = {m.get("name") or m.get("model") for m in response.json()["models"]}
            result["available"] = result["models"]["forge"] in installed and result["models"]["battle"] in installed
            result["scenario_available"] = result["models"]["scenario"] in installed
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return result


async def warm_gameplay_model():
    """Warm once in the background. Startup and play remain available if this fails."""
    if provider_name() != "ollama" or not ai_available():
        return
    model = model_for("forge")
    LOG.info("[AI] Gameplay model: %s", model)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25, connect=1), trust_env=False) as client:
            response = await client.post(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/chat", json={
                "model": model, "messages": [{"role": "user", "content": "Return OK."}],
                "stream": False, "think": False, "keep_alive": "30m",
                "options": {"temperature": 0, "num_predict": 4},
            })
            response.raise_for_status()
        LOG.info("[AI] Gameplay model warm - %s - %.2fs", model, time.monotonic() - started)
    except (httpx.HTTPError, asyncio.TimeoutError, ValueError, KeyError, TypeError):
        LOG.info("[AI] Model warm-up unavailable - gameplay fallback remains ready")
