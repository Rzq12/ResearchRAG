"""
Unified LLM client for ResearchRAG.

Supports:
  - Groq  (Llama 4, Llama 3, Mixtral, DeepSeek, QwQ, …)
  - Google Gemini  (gemini-2.5-flash, gemini-2.0-flash, gemini-1.5-flash, …)

Provider is auto-detected from model name:
  - starts with "gemini-" → Google Gemini  (needs GEMINI_API_KEY)
  - anything else         → Groq           (needs GROQ_API_KEY)

Usage:
    from app.llm_client import stream_llm, call_llm, get_provider

    for token in stream_llm(model, messages, api_key, max_tokens=2000):
        print(token, end="")
"""

from __future__ import annotations
from typing import Generator


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
    """Returns 'gemini' or 'groq' based on model name."""
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
    else:
        yield from _stream_groq(model, messages, api_key, max_tokens, temperature)
