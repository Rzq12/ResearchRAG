"""
Math-formatting contract between the model and the chat renderer.

The React chat renders answers through `remark-math` + `rehype-katex`, which
only recognises `$...$` and `$$...$$`. Two failure modes follow from that, and
both are invisible server-side, so they are pinned here:

  M1  the model emits no delimiters at all (or an exotic one) and formulas
      arrive as unreadable plain text
  M2  the model writes a literal dollar amount, and everything between two
      amounts is swallowed into a formula
"""

from __future__ import annotations

import app.rag as rag
from app.rag import SYSTEM_PROMPT


class _Stub:
    """Minimal stand-in for Settings — _system_prompt only reads one flag."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _settings(*, enable_reasoning: bool) -> _Stub:
    return _Stub(enable_reasoning=enable_reasoning)


# ─── M1: the renderer's delimiters are actually requested ────────────────────

def test_system_prompt_requests_dollar_delimiters_for_math():
    assert "$$" in SYSTEM_PROMPT
    assert "LaTeX" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_inline_from_display_math():
    """Display math must be asked for separately, or every formula lands inline."""
    lowered = SYSTEM_PROMPT.lower()
    assert "inline" in lowered
    assert "display" in lowered


# ─── M2: literal currency is escaped ─────────────────────────────────────────

def test_system_prompt_requires_escaping_literal_dollar_amounts():
    assert r"\$" in SYSTEM_PROMPT


# ─── the rule survives prompt assembly ───────────────────────────────────────

def test_math_rule_present_when_reasoning_disabled(monkeypatch):
    monkeypatch.setattr(rag, "get_settings", lambda: _settings(enable_reasoning=False))
    assert "$$" in rag._system_prompt()


def test_math_rule_present_when_reasoning_enabled(monkeypatch):
    monkeypatch.setattr(rag, "get_settings", lambda: _settings(enable_reasoning=True))
    prompt = rag._system_prompt()
    assert "$$" in prompt
    assert "<think>" in prompt
