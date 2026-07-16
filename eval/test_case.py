"""
Mandatory test case (Fase 9) — the academic analogue of the legal notebook's
"uang lembur" test. Makes REAL LLM calls using the key configured in .env.

    python -m eval.test_case

Verifies, for an English and an Indonesian version of the same question:
1. reasoning is present (the <think> block was produced and parsed out),
2. the final answer cites >= 2 distinct references [n],
3. every cited [n] exists in the returned reference list (no hallucinated
   citation indices),
4. the Indonesian answer is actually in Indonesian even though the source
   papers are English (the multilingual claim, tested explicitly).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from eval.run_eval import _reset_eval_collections, ingest_corpus, EVAL_USER

# The question spans TWO corpus papers (LoRA + QLoRA) so the >=2-citations
# check is genuinely satisfiable — a question answerable from one paper would
# punish the model for honest single-source citing.
TEST_CASES = [
    {
        "lang": "en",
        "question": ("Which parameter-efficient fine-tuning methods in my library "
                     "allow adapting very large language models on limited GPU "
                     "memory, and how do they differ?"),
    },
    {
        "lang": "id",
        "question": ("Metode fine-tuning hemat parameter apa saja di library saya "
                     "yang memungkinkan adaptasi model bahasa sangat besar dengan "
                     "memori GPU terbatas, dan apa bedanya?"),
    },
]

_ID_MARKERS = re.compile(
    r"\b(yang|adalah|dengan|tidak|dapat|keterbatasan|jawaban|dokumen|utama|memungkinkan|perbedaan)\b",
    re.IGNORECASE,
)

_EN_MARKERS = re.compile(
    r"\b(the|which|allows?|memory|difference|fine-tuning|weights|while|both)\b",
    re.IGNORECASE,
)


def check_answer(response, lang: str) -> list[tuple[str, bool, str]]:
    """Run the mandatory checks; returns (name, passed, detail) rows."""
    cited  = sorted({int(n) for n in re.findall(r"\[(\d+)\]", response.answer)})
    n_refs = len(response.references)

    checks = [
        ("reasoning <think> present", bool(response.reasoning.strip()),
         f"{len(response.reasoning)} chars"),
        (">= 2 distinct citations", len(cited) >= 2, f"cited: {cited}"),
        ("no hallucinated citation index",
         all(1 <= n <= n_refs for n in cited) and bool(cited),
         f"refs available: {n_refs}"),
        ("answer from local KB", response.source == "kb", f"source: {response.source}"),
    ]
    if lang == "id":
        checks.append((
            "answer in Indonesian",
            len(_ID_MARKERS.findall(response.answer)) >= 3,
            response.answer[:80].replace("\n", " "),
        ))
    if lang == "en":
        checks.append((
            "answer in English",
            len(_EN_MARKERS.findall(response.answer))
            > len(_ID_MARKERS.findall(response.answer)),
            response.answer[:80].replace("\n", " "),
        ))
    return checks


def main() -> None:
    from app.config import get_settings
    from app.rag import ask

    cfg   = get_settings()
    key   = cfg.groq_api_key or cfg.gemini_api_key
    model = cfg.default_model
    if not key:
        raise SystemExit("Requires GROQ_API_KEY or GEMINI_API_KEY in .env")

    corpus = json.loads(
        (Path(__file__).parent / "corpus.json").read_text(encoding="utf-8")
    )
    print("[test-case] ingesting eval corpus ...")
    _reset_eval_collections()
    ingest_corpus(corpus)

    all_ok = True
    for case in TEST_CASES:
        print(f"\n=== [{case['lang']}] {case['question']}")
        response = ask(case["question"], api_key=key, model=model, user_id=EVAL_USER)

        print(f"--- reasoning ({len(response.reasoning)} chars):")
        print("   " + response.reasoning[:300].replace("\n", "\n   "))
        print("--- answer:")
        print("   " + response.answer[:600].replace("\n", "\n   "))

        for name, passed, detail in check_answer(response, case["lang"]):
            mark = "PASS" if passed else "FAIL"
            all_ok &= passed
            print(f"  [{mark}] {name}  ({detail})")

    _reset_eval_collections()
    print("\n" + ("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED"))
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
