"""Unit tests for app/reasoning.py — think-tag parsing and stream splitting."""

from app.reasoning import parse_think, split_think_stream


def _consume(tokens):
    gen, holder = split_think_stream(iter(tokens))
    return "".join(gen), holder


# ─── parse_think ──────────────────────────────────────────────────────────────

def test_parse_think_with_block_returns_reasoning_and_answer():
    reasoning, answer = parse_think("<think>step 1\nstep 2</think>\n\nFinal answer [1].")
    assert reasoning == "step 1\nstep 2"
    assert answer == "Final answer [1]."


def test_parse_think_without_block_returns_full_text():
    reasoning, answer = parse_think("Just a plain answer.")
    assert reasoning == ""
    assert answer == "Just a plain answer."


def test_parse_think_unclosed_tag_treated_as_answer():
    reasoning, answer = parse_think("<think>never closed and then text")
    assert reasoning == ""
    assert "never closed" in answer


def test_parse_think_empty_input():
    assert parse_think("") == ("", "")


# ─── split_think_stream ───────────────────────────────────────────────────────

def test_stream_with_think_block_swallows_reasoning():
    answer, holder = _consume(["<think>", "reasoning here", "</think>", "\n\n", "The answer."])
    assert holder["think"] == "reasoning here"
    assert answer == "The answer."
    assert "<think>" not in answer


def test_stream_tag_split_across_tokens():
    answer, holder = _consume(["<th", "ink>rea", "soning</th", "ink>ans", "wer"])
    assert holder["think"] == "reasoning"
    assert answer == "answer"


def test_stream_without_think_passes_through():
    answer, holder = _consume(["Hello ", "world, ", "no tags here."])
    assert holder["think"] == ""
    assert answer == "Hello world, no tags here."


def test_stream_first_token_rules_out_think_immediately():
    # "T" is not a prefix of "<think>" → flushed on the first token.
    gen, holder = split_think_stream(iter(["T", "he answer."]))
    first = next(gen)
    assert first == "T"


def test_stream_unclosed_think_flushes_at_end():
    answer, holder = _consume(["<think>", "this never closes"])
    assert holder["think"] == ""
    assert "this never closes" in answer


def test_stream_never_closed_think_flushes_after_cap():
    big_chunk = "x" * 9000
    answer, holder = _consume(["<think>", big_chunk, " more text"])
    assert holder["think"] == ""
    assert "more text" in answer


def test_stream_leading_whitespace_before_think():
    answer, holder = _consume(["\n\n", "<think>r</think>", "answer"])
    assert holder["think"] == "r"
    assert answer == "answer"


def test_stream_empty_input():
    answer, holder = _consume([])
    assert answer == ""
    assert holder["think"] == ""
