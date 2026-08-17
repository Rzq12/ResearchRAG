"""
Unified LLM client for ResearchRAG.

Supports:
  - Groq  (Llama 4, Llama 3, Mixtral, DeepSeek, QwQ, …)
  - Google Gemini  (gemini-2.5-flash, gemini-2.0-flash, gemini-1.5-flash, …)
  - Self-hosted OpenAI-compatible endpoints (vLLM / TGI / HF Inference) —
    for serving your own fine-tuned model without changing app code.

Provider is auto-detected from model name:
  - starts with "gemini-" → Google Gemini      (needs GEMINI_API_KEY)
  - starts with "hf:"     → self-hosted server (needs HF_ENDPOINT_URL; the
                            part after "hf:" is sent as the model name)
  - anything else         → Groq               (needs GROQ_API_KEY)

Usage:
    from app.llm_client import stream_llm, call_llm, get_provider

    for token in stream_llm(model, messages, api_key, max_tokens=2000):
        print(token, end="")
"""

from __future__ import annotations
from typing import Generator
from app.logger import logger


# ─── Model catalog ────────────────────────────────────────────────────────────

# Ordered for display in the UI.
# Format: { model_id: (emoji + label, context_window_hint) }
MODEL_CATALOG: dict[str, tuple[str, str]] = {
    # ── Gemini ───────────────────────────────────────────────────────────────
    "gemini-3.5-flash": (
        "✨ Gemini 3.5 Flash (recommended)",
        "gemini",
    ),
    "gemini-3.1-flash-lite": (
        "⚡ Gemini 3.1 Flash Lite (fast, lightweight)",
        "gemini",
    ),
    "gemini-3-flash-preview": (
        "🔬 Gemini 3 Flash Preview",
        "gemini",
    ),
    "gemini-3.1-pro-preview": (
        "🧠 Gemini 3.1 Pro Preview (best quality)",
        "gemini",
    ),
    # ── Groq — Meta Llama ────────────────────────────────────────────────────
    "meta-llama/llama-4-scout-17b-16e-instruct": (
        "🚀 Llama 4 Scout 17B (Meta, groq)",
        "groq",
    ),
    "llama-3.3-70b-versatile": (
        "⭐ Llama 3.3 70B Versatile (Meta, groq)",
        "groq",
    ),
    "llama-3.1-8b-instant": (
        "⚡ Llama 3.1 8B Instant (Meta, fast)",
        "groq",
    ),
    # ── Groq — Alibaba Qwen ───────────────────────────────────────────────────
    "qwen/qwen3-32b": (
        "🌐 Qwen3 32B (Alibaba, groq)",
        "groq",
    ),
    # ── Groq — Groq native ───────────────────────────────────────────────────
    "groq/compound": (
        "🔧 Compound (Groq native)",
        "groq",
    ),
    "groq/compound-mini": (
        "🔧 Compound Mini (Groq native, fast)",
        "groq",
    ),
    # ── Groq — OpenAI on Groq ────────────────────────────────────────────────
    "openai/gpt-oss-120b": (
        "🤖 GPT OSS 120B (OpenAI on Groq)",
        "groq",
    ),
    "openai/gpt-oss-20b": (
        "🤖 GPT OSS 20B (OpenAI on Groq, fast)",
        "groq",
    ),
}

# Provider hint per model (shown in sidebar)
PROVIDER_HINTS: dict[str, tuple[str, str]] = {
    # Gemini
    "gemini-3.5-flash":       ("✅", "Gemini, context besar, gratis"),
    "gemini-3.1-flash-lite":  ("⚡", "Gemini, paling cepat & ringan"),
    "gemini-3-flash-preview": ("🔬", "Gemini, preview build"),
    "gemini-3.1-pro-preview": ("🧠", "Gemini, kualitas terbaik"),
    # Groq — Meta
    "meta-llama/llama-4-scout-17b-16e-instruct": ("✅", "Groq · Meta · 512k ctx"),
    "llama-3.3-70b-versatile":                   ("⚠️", "Groq · Meta · 12k TPM free"),
    "llama-3.1-8b-instant":                      ("⚡", "Groq · Meta · paling cepat"),
    # Groq — Alibaba
    "qwen/qwen3-32b":    ("🌐", "Groq · Alibaba · 32B"),
    # Groq — Groq native
    "groq/compound":      ("🔧", "Groq native compound model"),
    "groq/compound-mini": ("🔧", "Groq native · lebih cepat"),
    # Groq — OpenAI
    "openai/gpt-oss-120b": ("🤖", "OpenAI OSS 120B via Groq"),
    "openai/gpt-oss-20b":  ("🤖", "OpenAI OSS 20B via Groq · cepat"),
}


def get_provider(model: str) -> str:
    """Returns 'gemini', 'hf' (self-hosted), or 'groq' based on model name."""
    if model.startswith("hf:"):
        return "hf"
    if model.startswith("gemini"):
        return "gemini"
    return "groq"


def get_model_label(model: str) -> str:
    entry = MODEL_CATALOG.get(model)
    return entry[0] if entry else model


# ─── Message format conversion ────────────────────────────────────────────────

def _messages_to_gemini(messages: list[dict]) -> tuple[str, list]:
    """
    Convert OpenAI-style messages → Gemini SDK format.
    Returns (system_instruction_str, contents_list).
    """
    system_parts: list[str] = []
    contents: list[dict]   = []

    for msg in messages:
        role    = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            system_parts.append(content)
        elif role == "user":
            contents.append({"role": "user",  "parts": [{"text": content}]})
        elif role in ("assistant", "model"):
            contents.append({"role": "model", "parts": [{"text": content}]})

    return "\n\n".join(system_parts), contents


# ─── Groq calls ──────────────────────────────────────────────────────────────

def _call_groq(
    model: str,
    messages: list[dict],
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> str:
    from groq import Groq
    client   = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model       = model,
        messages    = messages,
        temperature = temperature,
        max_tokens  = max_tokens,
    )
    tokens = response.usage.total_tokens
    logger.info(f"llm_call provider=groq model={model} tokens={tokens} est_cost=${tokens * 0.00001:.4f}")
    return response.choices[0].message.content


def _stream_groq(
    model: str,
    messages: list[dict],
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> Generator[str, None, None]:
    from groq import Groq
    client = Groq(api_key=api_key)
    stream = client.chat.completions.create(
        model       = model,
        messages    = messages,
        temperature = temperature,
        max_tokens  = max_tokens,
        stream      = True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ─── Gemini calls ─────────────────────────────────────────────────────────────

def _call_gemini(
    model: str,
    messages: list[dict],
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError(
            "google-genai package not installed. "
            "Add 'google-genai' to requirements.txt and rebuild."
        )

    client = genai.Client(api_key=api_key)
    system_instruction, contents = _messages_to_gemini(messages)

    config_kwargs: dict = {
        "max_output_tokens": max_tokens,
        "temperature":       temperature,
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    response = client.models.generate_content(
        model    = model,
        contents = contents,
        config   = types.GenerateContentConfig(**config_kwargs),
    )
    return response.text


def _stream_gemini(
    model: str,
    messages: list[dict],
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> Generator[str, None, None]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError(
            "google-genai package not installed. "
            "Add 'google-genai' to requirements.txt and rebuild."
        )

    client = genai.Client(api_key=api_key)
    system_instruction, contents = _messages_to_gemini(messages)

    config_kwargs: dict = {
        "max_output_tokens": max_tokens,
        "temperature":       temperature,
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    for chunk in client.models.generate_content_stream(
        model    = model,
        contents = contents,
        config   = types.GenerateContentConfig(**config_kwargs),
    ):
        if chunk.text:
            yield chunk.text


# ─── Self-hosted (OpenAI-compatible: vLLM / TGI / HF Inference) ───────────────

def _hf_endpoint_and_headers(api_key: str | None) -> tuple[str, dict]:
    from app.config import get_settings
    cfg = get_settings()
    endpoint = (cfg.hf_endpoint_url or "").rstrip("/")
    if not endpoint:
        raise ValueError(
            "Model prefix 'hf:' requires HF_ENDPOINT_URL in .env "
            "(an OpenAI-compatible server such as vLLM or TGI)."
        )
    token   = api_key or cfg.hf_api_token
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return f"{endpoint}/v1/chat/completions", headers


def _call_hf(
    model: str,
    messages: list[dict],
    api_key: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    import httpx
    url, headers = _hf_endpoint_and_headers(api_key)
    payload = {
        "model":       model.removeprefix("hf:"),
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }
    with httpx.Client(timeout=120) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _stream_hf(
    model: str,
    messages: list[dict],
    api_key: str | None,
    max_tokens: int,
    temperature: float,
) -> Generator[str, None, None]:
    import json as _json
    import httpx
    url, headers = _hf_endpoint_and_headers(api_key)
    payload = {
        "model":       model.removeprefix("hf:"),
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "stream":      True,
    }
    with httpx.Client(timeout=120) as client:
        with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    delta = _json.loads(data)["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, ValueError):
                    continue
                if delta:
                    yield delta


# ─── Error classification ─────────────────────────────────────────────────────

def friendly_llm_error(exc: Exception) -> tuple[str, str]:
    """
    Map a raw provider exception to a user-friendly chat message.

    Args:
        exc: Exception raised by any provider call (Groq / Gemini / self-hosted).

    Returns:
        Tuple of (category, markdown_message) where category is one of
        "rate_limit", "auth", "context", "model_unavailable", "network",
        "unknown" — and markdown_message is safe to show to end users
        (no stack trace, no raw API payload).
    """
    err = str(exc).lower()

    if any(s in err for s in (
        "429", "resource_exhausted", "rate limit", "rate_limit", "rate-limit",
        "quota", "too many requests",
    )):
        return "rate_limit", (
            "⏳ **Kuota API tercapai (rate limit).**\n\n"
            "Model yang dipilih sudah mencapai batas pemakaian untuk saat ini.\n\n"
            "**Yang bisa dilakukan:**\n"
            "- Tunggu beberapa menit lalu kirim ulang pertanyaan\n"
            "- Ganti model lain di sidebar (mis. ⚡ Llama 3.1 8B Instant via Groq)\n"
            "- Atau gunakan API key dengan kuota lebih besar"
        )

    if any(s in err for s in (
        "401", "403", "api key", "api_key", "invalid_api_key",
        "permission_denied", "unauthorized", "authentication",
    )):
        return "auth", (
            "🔑 **API key tidak valid atau tidak punya akses.**\n\n"
            "Periksa kembali API key di sidebar — pastikan key sesuai dengan "
            "provider model yang dipilih (Gemini key untuk model Gemini, "
            "Groq key untuk model Groq)."
        )

    if any(s in err for s in (
        "413", "context_length", "request too large", "payload too large",
        "token count exceeds", "tokens per minute", "input is too long",
    )):
        return "context", (
            "⚠️ **Konteks terlalu besar untuk model ini.**\n\n"
            "✨ **Solusi terbaik:** Pilih model Gemini di sidebar — context window besar\n"
            "⚡ **Alternatif:** Llama 3.1 8B Instant (Groq) — paling cepat\n"
            "🔧 **Atau:** Turunkan `TOP_K_RETRIEVAL` di `.env` ke `5`"
        )

    if any(s in err for s in (
        "404", "not_found", "not found", "decommissioned", "does not exist",
        "deprecated",
    )):
        return "model_unavailable", (
            "❓ **Model tidak tersedia.**\n\n"
            "Model yang dipilih mungkin sudah dinonaktifkan oleh provider. "
            "Pilih model lain di sidebar."
        )

    if any(s in err for s in (
        "timeout", "timed out", "connection", "unavailable", "503",
        "network", "dns", "unreachable",
    )):
        return "network", (
            "🌐 **Gagal terhubung ke server LLM.**\n\n"
            "Periksa koneksi internet, atau coba lagi beberapa saat — "
            "server provider mungkin sedang sibuk."
        )

    return "unknown", (
        "⚠️ **Terjadi kesalahan saat menghasilkan jawaban.**\n\n"
        "Silakan coba lagi. Jika masih gagal, ganti model di sidebar."
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def call_llm(
    model: str,
    messages: list[dict],
    api_key: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    """Non-streaming unified LLM call."""
    provider = get_provider(model)
    if provider == "gemini":
        return _call_gemini(model, messages, api_key, max_tokens, temperature)
    if provider == "hf":
        return _call_hf(model, messages, api_key, max_tokens, temperature)
    return _call_groq(model, messages, api_key, max_tokens, temperature)


def stream_llm(
    model: str,
    messages: list[dict],
    api_key: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> Generator[str, None, None]:
    """Streaming unified LLM call. Yields text tokens."""
    provider = get_provider(model)
    if provider == "gemini":
        yield from _stream_gemini(model, messages, api_key, max_tokens, temperature)
    elif provider == "hf":
        yield from _stream_hf(model, messages, api_key, max_tokens, temperature)
    else:
        yield from _stream_groq(model, messages, api_key, max_tokens, temperature)
