"""
Re-index ChromaDB collections after an embedding-model change.

Why: switching embedding models changes vector dimensionality (MiniLM 384 →
multilingual-e5-base 768). ChromaDB cannot mix dimensions in one collection,
so every collection must be rebuilt. Chunk TEXTS are stored in ChromaDB, so
this script re-embeds the existing documents — user knowledge bases survive.

Usage (run once after deploying the new embedding model config):

    python -m scripts.reindex                    # dry-run: shows what would happen
    python -m scripts.reindex --apply            # migrate old → new collections
    python -m scripts.reindex --apply --delete-old   # also drop old collections

Old collections are matched by --old-prefix (default: "researchrag").
New collections use the prefix from the CURRENT config (cfg.chroma_collection,
e.g. "researchrag_v2") and the CURRENT embedding model.
"""

from __future__ import annotations

import argparse

BATCH = 500  # stay far below Chroma's ~5461-embedding add limit


def migrate() -> None:
    parser = argparse.ArgumentParser(description="Re-embed ChromaDB collections")
    parser.add_argument("--old-prefix", default="researchrag",
                        help="collection-name prefix of the OLD index")
    parser.add_argument("--apply", action="store_true",
                        help="actually migrate (default: dry-run)")
    parser.add_argument("--delete-old", action="store_true",
                        help="drop old collections after successful migration")
    args = parser.parse_args()

    from app import database as db
    from app.config import get_settings

    cfg        = get_settings()
    new_prefix = cfg.chroma_collection
    if new_prefix == args.old_prefix:
        raise SystemExit(
            f"chroma_collection is still '{new_prefix}' — bump it (e.g. "
            f"'{args.old_prefix}_v2') in config/.env before re-indexing."
        )

    embed_docs = getattr(db, "embed_documents", db.embed_texts)
    client     = db._get_client()

    old_collections = [
        c for c in client.list_collections()
        if c.name.startswith(args.old_prefix)
        and not c.name.startswith(new_prefix)
    ]
    if not old_collections:
        print(f"No collections with prefix '{args.old_prefix}' found — nothing to do.")
        return

    print(f"Embedding model : {cfg.embedding_model}")
    print(f"Migration       : '{args.old_prefix}*' → '{new_prefix}*'")
    print(f"Mode            : {'APPLY' if args.apply else 'DRY-RUN'}\n")

    for old in old_collections:
        new_name = new_prefix + old.name[len(args.old_prefix):]
        count    = old.count()
        print(f"  {old.name}  ({count} chunks)  →  {new_name}")
        if not args.apply or count == 0:
            continue

        new_col = client.get_or_create_collection(
            name=new_name, metadata={"hnsw:space": "cosine"},
        )

        offset = 0
        while offset < count:
            batch = old.get(
                include=["documents", "metadatas"],
                limit=BATCH, offset=offset,
            )
            ids   = batch.get("ids", [])
            docs  = batch.get("documents", []) or []
            metas = batch.get("metadatas", []) or [{}] * len(ids)
            if not ids:
                break

            new_col.upsert(
                ids        = ids,
                documents  = docs,
                embeddings = embed_docs(docs),
                metadatas  = metas,
            )
            offset += len(ids)
            print(f"    … {min(offset, count)}/{count}")

        if new_col.count() < count:
            raise SystemExit(
                f"    MIGRATION INCOMPLETE for {old.name}: "
                f"{new_col.count()}/{count} — old collection kept."
            )

        if args.delete_old:
            client.delete_collection(old.name)
            print(f"    old collection '{old.name}' deleted")

    print("\nDone." if args.apply else "\nDry-run only — re-run with --apply to migrate.")


if __name__ == "__main__":
    migrate()
