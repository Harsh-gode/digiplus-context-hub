"""Thin, provider-agnostic LLM client that always returns JSON (or a clean failure).

Supported providers: Gemini, Anthropic (Claude), OpenAI — selected via AI_PROVIDER or by
whichever API key is present. Every call is logged with task, provider, model, latency,
attempt count and outcome. Prompts and responses are NOT logged (they can contain personal
data); only their sizes are.
"""
import json
import re
import time
from dataclasses import dataclass

import httpx

from ..config import settings
from ..logging_setup import get_logger

log = get_logger("ai")


class AIError(Exception):
    pass


@dataclass
class AIResult:
    data: dict | None
    status: str  # ok | fallback | disabled
    message: str = ""
    latency_ms: int = 0


def _extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or ``` fences; pull out the first JSON object."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _call_gemini(system: str, user: str, client: httpx.Client) -> tuple[str, dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    r = client.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key})
    r.raise_for_status()
    payload = r.json()
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    usage = payload.get("usageMetadata", {})
    return text, {"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")}


def _call_anthropic(system: str, user: str, client: httpx.Client) -> tuple[str, dict]:
    body = {
        "model": settings.anthropic_model,
        "max_tokens": 2000,
        "temperature": 0.2,
        "system": system + "\nRespond with a single JSON object only, no prose.",
        "messages": [{"role": "user", "content": user}],
    }
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        json=body,
        headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
    )
    r.raise_for_status()
    payload = r.json()
    text = "".join(block.get("text", "") for block in payload["content"] if block.get("type") == "text")
    usage = payload.get("usage", {})
    return text, {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}


def _call_openai(system: str, user: str, client: httpx.Client) -> tuple[str, dict]:
    body = {
        "model": settings.openai_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    r = client.post(
        "https://api.openai.com/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
    )
    r.raise_for_status()
    payload = r.json()
    usage = payload.get("usage", {})
    return payload["choices"][0]["message"]["content"], {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
    }


PROVIDERS = {"gemini": _call_gemini, "anthropic": _call_anthropic, "openai": _call_openai}
MODELS = {"gemini": lambda: settings.gemini_model, "anthropic": lambda: settings.anthropic_model, "openai": lambda: settings.openai_model}


def ai_enabled() -> bool:
    return settings.resolved_provider() in PROVIDERS


def provider_info() -> dict:
    p = settings.resolved_provider()
    return {"provider": p, "model": MODELS[p]() if p in MODELS else None, "enabled": p in PROVIDERS}


def call_json(task: str, system: str, user: str, validate=None) -> AIResult:
    """Call the configured model and return parsed JSON.

    `validate` is an optional callable that raises if the JSON doesn't have the expected
    shape; a validation failure counts as a failed attempt and is retried.
    """
    provider = settings.resolved_provider()
    if provider not in PROVIDERS:
        log.info("ai.call", task=task, provider="none", outcome="disabled")
        return AIResult(None, "disabled", "No AI provider configured; used the built-in fallback.")

    model = MODELS[provider]()
    attempts = settings.ai_max_retries + 1
    last_error = ""
    started = time.perf_counter()

    with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
        for attempt in range(1, attempts + 1):
            t0 = time.perf_counter()
            try:
                text, usage = PROVIDERS[provider](system, user, client)
                data = _extract_json(text)
                if validate:
                    validate(data)
                latency = int((time.perf_counter() - t0) * 1000)
                log.info(
                    "ai.call", task=task, provider=provider, model=model, attempt=attempt, outcome="success",
                    latency_ms=latency, prompt_chars=len(system) + len(user), response_chars=len(text), **usage,
                )
                return AIResult(data, "ok", latency_ms=int((time.perf_counter() - started) * 1000))
            except httpx.TimeoutException:
                last_error = "AI provider timed out"
            except httpx.HTTPStatusError as e:
                last_error = f"AI provider returned HTTP {e.response.status_code}"
                if e.response.status_code in (400, 401, 403, 404):
                    # Not retryable: bad key, bad model name, bad request.
                    log.warning("ai.call", task=task, provider=provider, model=model, attempt=attempt,
                                outcome="error", error=last_error,
                                latency_ms=int((time.perf_counter() - t0) * 1000))
                    break
            except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as e:
                last_error = f"AI returned an unusable response ({type(e).__name__})"
            except httpx.HTTPError as e:
                last_error = f"Could not reach AI provider ({type(e).__name__})"

            log.warning(
                "ai.call", task=task, provider=provider, model=model, attempt=attempt,
                outcome="retry" if attempt < attempts else "error", error=last_error,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            if attempt < attempts:
                time.sleep(0.6 * attempt)

    total = int((time.perf_counter() - started) * 1000)
    log.warning("ai.fallback", task=task, provider=provider, reason=last_error, total_latency_ms=total)
    return AIResult(None, "fallback", f"{last_error}. Showing a rule-based result instead — please review it.", total)
