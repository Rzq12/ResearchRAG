"""
Evaluation harness for the ResearchRAG retrieval pipeline.

Self-contained: ingests eval/corpus.json into a dedicated `_eval` user
collection (wiped each run), then runs the 30 golden queries from
eval/golden_set.json through the real `retrieve_chunks` pipeline.

Metrics
-------
- hit@1 / hit@5 : any expected doc among the first 1 / 5 unique retrieved docs
- MRR@10        : reciprocal rank of the first relevant doc
- latency       : p50 / p95 wall time of retrieve_chunks (warm)
- per-language breakdown (en / id / mixed)
- optional --with-llm: full ask() + ROUGE-L against expected answer points

Usage
-----
    python -m eval.run_eval --tag baseline
    python -m eval.run_eval --tag fase1 --compare eval/results/baseline.json
    python -m eval.run_eval --tag fase9 --with-llm
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR    = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
EVAL_USER   = "_eval"


# -- Ingestion ----------------------------------------------------------------

def _reset_eval_collections() -> None:
    """Drop the eval user's child + parent collections so each run starts clean."""
    from app import database as db

    client = db._get_client()
    for role in ("child", "parent"):
        name = db._collection_name(EVAL_USER, role)
        try:
            client.delete_collection(name)
        except Exception:
            pass  # did not exist yet
    # Invalidate the module-level collection cache
    normalized = db._normalize_user_id(EVAL_USER)
    db._collections.pop(normalized, None)
    db._collections.pop(f"{normalized}_parent", None)


def ingest_corpus(corpus: dict) -> int:
    """Ingest corpus abstracts as child chunks (same path as OpenAlex abstracts)."""
    from app.chunker import chunk_text
    from app.database import get_collection, make_doc_id
    from app import database as db

    # Phase 1 splits embed_texts into embed_documents/embed_query;
    # fall back to embed_texts on the pre-phase-1 codebase.
    embed_docs = getattr(db, "embed_documents", db.embed_texts)

    collection = get_collection(EVAL_USER)
    texts, ids, metadatas = [], [], []

    for doc in corpus["documents"]:
        chunks = chunk_text(doc["abstract"], source=f"eval:{doc['eval_doc_id']}")
        for chunk in chunks:
            texts.append(chunk["text"])
            ids.append(make_doc_id(chunk["source"], chunk["chunk_index"]))
            metadatas.append({
                "chunk_role":    "child",
                "source":        "eval",
                "eval_doc_id":   doc["eval_doc_id"],
                "title":         doc["title"],
                "authors":       doc["authors"],
                "published":     doc["published"],
                "language":      doc["language"],
                "url":           "",
                "chunk_index":   chunk["chunk_index"],
                "page_num":      1,
                "content_type":  "text",
                "section_path":  "",
                "section_title": "Abstract",
                "word_count":    len(chunk["text"].split()),
                "parent_id":     "",
            })

    collection.add(
        documents  = texts,
        embeddings = embed_docs(texts),
        ids        = ids,
        metadatas  = metadatas,
    )
    return len(texts)


# -- Metrics ------------------------------------------------------------------

def _retrieved_doc_order(metadatas: list[dict]) -> list[str]:
    """Unique eval_doc_ids in retrieval order."""
    seen: list[str] = []
    for m in metadatas:
        did = m.get("eval_doc_id", "")
        if did and did not in seen:
            seen.append(did)
    return seen


def evaluate_query(query: dict) -> dict:
    from app.rag import retrieve_chunks

    t0 = time.perf_counter()
    chunks, metadatas = retrieve_chunks(query["question"], user_id=EVAL_USER)
    latency_ms = (time.perf_counter() - t0) * 1000

    doc_order = _retrieved_doc_order(metadatas)
    expected  = set(query["expected_doc_ids"])

    hit1 = 1.0 if doc_order[:1] and doc_order[0] in expected else 0.0
    hit5 = 1.0 if any(d in expected for d in doc_order[:5]) else 0.0
    rr   = 0.0
    for rank, did in enumerate(doc_order[:10], start=1):
        if did in expected:
            rr = 1.0 / rank
            break

    return {
        "id":            query["id"],
        "language":      query["language"],
        "hit@1":         hit1,
        "hit@5":         hit5,
        "rr@10":         round(rr, 4),
        "latency_ms":    round(latency_ms, 1),
        "retrieved":     doc_order[:10],
        "expected":      sorted(expected),
        "n_chunks":      len(chunks),
    }


def run_llm_eval(query: dict, api_key: str, model: str) -> dict:
    """Full ask() + ROUGE-L against the reference answer points. Costs 1+ LLM call."""
    from app.rag import ask
    from rouge_score import rouge_scorer

    t0 = time.perf_counter()
    response = ask(query["question"], api_key=api_key, model=model, user_id=EVAL_USER)
    latency_ms = (time.perf_counter() - t0) * 1000

    reference = " ".join(query["expected_answer_points"])
    scorer    = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)
    rouge_l   = scorer.score(reference, response.answer)["rougeL"].fmeasure

    return {
        "rouge_l":         round(rouge_l, 4),
        "llm_latency_ms":  round(latency_ms, 1),
        "answer_preview":  response.answer[:200],
    }


def _aggregate(rows: list[dict]) -> dict:
    def mean(key: str, subset: list[dict]) -> float:
        vals = [r[key] for r in subset]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    latencies = sorted(r["latency_ms"] for r in rows)

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(int(len(latencies) * p), len(latencies) - 1)
        return round(latencies[idx], 1)

    out = {
        "n_queries":      len(rows),
        "hit@1":          mean("hit@1", rows),
        "hit@5":          mean("hit@5", rows),
        "mrr@10":         mean("rr@10", rows),
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
        "latency_p95_ms": pct(0.95),
        "by_language":    {},
    }
    for lang in ("en", "id", "mixed"):
        subset = [r for r in rows if r["language"] == lang]
        if subset:
            out["by_language"][lang] = {
                "n":      len(subset),
                "hit@1":  mean("hit@1", subset),
                "hit@5":  mean("hit@5", subset),
                "mrr@10": mean("rr@10", subset),
            }
    if rows and "rouge_l" in rows[0]:
        out["rouge_l"] = mean("rouge_l", rows)
    return out


def _config_snapshot() -> dict:
    """Relevant settings, tolerant of fields that don't exist yet in earlier phases."""
    from app.config import get_settings
    cfg  = get_settings()
    keys = [
        "embedding_model", "enable_reranker", "reranker_model", "reranker_top_k",
        "top_k_retrieval", "similarity_threshold",
        "enable_bm25", "bm25_weight", "vector_weight",
        "enable_hyde", "hyde_num_hypotheticals",
        "relevance_threshold", "enable_web_fallback", "enable_reasoning",
    ]
    return {k: getattr(cfg, k, None) for k in keys}


# -- Comparison --------------------------------------------------------------

def print_comparison(current: dict, baseline_path: str) -> None:
    base = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    print(f"\n-- Comparison vs {base['tag']} ------------------------")
    for key in ("hit@1", "hit@5", "mrr@10", "latency_p50_ms", "latency_p95_ms"):
        old = base["metrics"].get(key, 0)
        new = current["metrics"].get(key, 0)
        delta = new - old
        sign  = "+" if delta >= 0 else ""
        print(f"  {key:<16} {old:>8}  ->  {new:>8}   ({sign}{round(delta, 4)})")
    for lang, vals in current["metrics"].get("by_language", {}).items():
        old_lang = base["metrics"].get("by_language", {}).get(lang, {})
        old_h5   = old_lang.get("hit@5", 0)
        delta    = vals["hit@5"] - old_h5
        sign     = "+" if delta >= 0 else ""
        print(f"  hit@5 [{lang:<5}]    {old_h5:>8}  ->  {vals['hit@5']:>8}   ({sign}{round(delta, 4)})")


# -- Main --------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ResearchRAG retrieval evaluation")
    parser.add_argument("--tag", required=True, help="run label, e.g. 'baseline'")
    parser.add_argument("--with-llm", action="store_true",
                        help="also run full ask() + ROUGE-L (costs LLM quota)")
    parser.add_argument("--compare", default=None,
                        help="path to a previous results JSON to diff against")
    parser.add_argument("--keep", action="store_true",
                        help="keep the eval collection after the run")
    args = parser.parse_args()

    corpus = json.loads((EVAL_DIR / "corpus.json").read_text(encoding="utf-8"))
    golden = json.loads((EVAL_DIR / "golden_set.json").read_text(encoding="utf-8"))

    print(f"[eval] resetting '{EVAL_USER}' collections …")
    _reset_eval_collections()

    print(f"[eval] ingesting {len(corpus['documents'])} corpus documents …")
    n_chunks = ingest_corpus(corpus)
    print(f"[eval] {n_chunks} chunks indexed")

    # Warm-up so model load time doesn't pollute latency numbers
    from app.rag import retrieve_chunks
    retrieve_chunks("warm up query", user_id=EVAL_USER)

    llm_key = llm_model = None
    if args.with_llm:
        from app.config import get_settings
        cfg       = get_settings()
        llm_key   = cfg.groq_api_key or cfg.gemini_api_key
        llm_model = getattr(cfg, "default_model", None) or getattr(cfg, "groq_model", None)
        if not llm_key:
            raise SystemExit("--with-llm requires GROQ_API_KEY or GEMINI_API_KEY in .env")

    rows = []
    for query in golden["queries"]:
        row = evaluate_query(query)
        if args.with_llm:
            row.update(run_llm_eval(query, llm_key, llm_model))
        status = "OK" if row["hit@5"] else "--"
        print(f"  {status} {row['id']} [{row['language']:<5}] "
              f"rr={row['rr@10']:<6} {row['latency_ms']:>7.1f} ms  "
              f"got={row['retrieved'][:3]}")
        rows.append(row)

    metrics = _aggregate(rows)
    result  = {
        "tag":       args.tag,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config":    _config_snapshot(),
        "metrics":   metrics,
        "queries":   rows,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.tag}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n-- Results [{args.tag}] --------------------------------")
    print(f"  hit@1  = {metrics['hit@1']}   hit@5 = {metrics['hit@5']}   MRR@10 = {metrics['mrr@10']}")
    print(f"  latency p50 = {metrics['latency_p50_ms']} ms   p95 = {metrics['latency_p95_ms']} ms")
    for lang, vals in metrics["by_language"].items():
        print(f"  [{lang:<5}] n={vals['n']:<3} hit@5={vals['hit@5']}  mrr={vals['mrr@10']}")
    if "rouge_l" in metrics:
        print(f"  ROUGE-L = {metrics['rouge_l']}")
    print(f"  saved -> {out_path}")

    if args.compare:
        print_comparison(result, args.compare)

    if not args.keep:
        _reset_eval_collections()
        print("[eval] eval collections cleaned up")


if __name__ == "__main__":
    main()
