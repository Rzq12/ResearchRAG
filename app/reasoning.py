"""
<think> reasoning-tag helpers for ResearchRAG.

The RAG prompt asks the model to reason inside <think>...</think> before the
final answer (notebook pattern). These helpers separate reasoning from answer:

- parse_think(text)          → for non-streaming responses
- split_think_stream(gen)    → for streaming: swallows the think block while
                               it streams, exposes it via a holder dict, and
                               yields only the final answer tokens — so raw
                               tags never leak to the user mid-stream.
"""

from __future__ import annotations

import re
from typing import Generator, Iterable

THINK_OPEN  = "<think>"
THINK_CLOSE = "</think>"

# If a think block grows past this without closing, assume the model ignored
# the format and flush everything as answer (never swallow a whole response).
_MAX_THINK_CHARS = 8000

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def parse_think(text: str) -> tuple[str, str]:
    """
    Split a complete response into (reasoning, answer).
    No think block → ("", full text). Unclosed think block → treated as answer.
    """
    if not text:
        return "", ""
    match = _THINK_RE.search(text)
    if not match:
        return "", text.strip()
    reasoning = match.group(1).strip()
    answer    = (text[:match.start()] + text[match.end():]).strip()
    return reasoning, answer


def _looks_like_open_tag_prefix(text: str) -> bool:
    """True while text could still turn into '<think>' as more tokens arrive."""
    stripped = text.lstrip()
    if not stripped:
        return True
    return THINK_OPEN.startswith(stripped[: len(THINK_OPEN)])


def split_think_stream(
    token_gen: Iterable[str],
) -> tuple[Generator[str, None, None], dict]:
    """
    Wrap a token stream: capture the leading <think>...</think> block into
    holder["think"], yield only the answer tokens.

    Returns (answer_generator, holder). Read holder["think"] AFTER the
    generator is fully consumed (e.g. after st.write_stream returns).

    Behavior:
    - No think block          → tokens pass through unchanged (tiny initial
                                buffering until '<think>' is ruled out).
    - Think block present     → swallowed; answer starts after '</think>'.
    - Tag split across tokens → handled (buffering is char-based).
    - Never-closed think      → after _MAX_THINK_CHARS, or at end of stream,
                                the whole buffer is flushed as answer so no
                                content is ever lost.
    """
    holder: dict = {"think": ""}

    def _gen() -> Generator[str, None, None]:
        buffer = ""
        state  = "detect"          # detect → in_think → answer
        strip_leading = False      # eat whitespace tokens right after </think>

        for token in token_gen:
            if state == "answer":
                if strip_leading:
                    token = token.lstrip("\n ")
                    if not token:
                        continue
                    strip_leading = False
                yield token
                continue

            buffer += token

            if state == "detect":
                if not _looks_like_open_tag_prefix(buffer):
                    # Definitely not a think block — flush and pass through.
                    state = "answer"
                    if buffer:
                        yield buffer
                    buffer = ""
                elif buffer.lstrip().startswith(THINK_OPEN):
                    state = "in_think"
                # else: still ambiguous prefix — keep buffering.

            if state == "in_think":
                if THINK_CLOSE in buffer:
                    inside, _, rest = buffer.partition(THINK_CLOSE)
                    holder["think"] = inside.split(THINK_OPEN, 1)[-1].strip()
                    state  = "answer"
                    buffer = ""
                    rest   = rest.lstrip("\n ")
                    if rest:
                        yield rest
                    else:
                        strip_leading = True
                elif len(buffer) > _MAX_THINK_CHARS:
                    # Model never closes the tag — stop swallowing output.
                    state = "answer"
                    if buffer:
                        yield buffer
                    buffer = ""

        # Stream ended with leftover buffer (unclosed tag or short response).
        if buffer:
            yield buffer

    return _gen(), holder
