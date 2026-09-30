"""Small structured-text provider boundary. Ollama is primary; no SDK dependency."""
import asyncio
import json
import logging
import os
import time

import httpx

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
    defaults = {"scenario": 45.0, "forge": 8.0, "battle": 3.0}
    try:
        # A battle cannot silently become a ten-second model wait.
        return min({"battle":4,"forge":20,"scenario":600}[task], max(0.2, float(os.getenv(f"{task.upper()}_AI_TIMEOUT", defaults[task]))))
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


async def structured(schema, instructions, payload, timeout, retries=1, budget=900, validator=None, task="forge"):
    if not ai_available():
        return None
    provider = OllamaProvider() if provider_name() == "ollama" else OpenAIProvider()
    for _ in range(retries+1):
        try:
            # Every attempt has its own bound; callers also enforce a total deadline.
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=min(1.0, timeout)), trust_env=False) as client:
                raw = await asyncio.wait_for(provider.generate(client, schema, instructions, payload, budget, task), timeout)
            result = schema.model_validate_json(raw).model_dump()
            return validator(result) if validator else result
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, asyncio.TimeoutError):
            continue
    return None


async def provider_status():
    models = {task: model_for(task) for task in ("scenario", "forge", "battle")}
    result = {"provider": provider_name(), "model": models["forge"], "models": models, "available": False, "scenario_available": False}
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
        LOG.info("[AI] Model warm-up: %.2fs", time.monotonic() - started)
    except (httpx.HTTPError, asyncio.TimeoutError, ValueError, KeyError, TypeError):
        LOG.info("[AI] Model warm-up unavailable - gameplay fallback remains ready")
