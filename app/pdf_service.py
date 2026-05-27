from app.chunker import extract_pdf_chunks
from app.database import get_collection, embed_texts, make_doc_id


def ingest_pdf(pdf_bytes: bytes, filename: str) -> dict:
    """
    Ingest a user-uploaded PDF into ChromaDB.
    Returns summary of what was stored.
    """
    collection = get_collection()

    chunks = extract_pdf_chunks(pdf_bytes, filename=filename)
    if not chunks:
        return {"filename": filename, "chunks_added": 0, "message": "No text extracted"}

    texts, ids, metadatas = [], [], []

    for chunk in chunks:
        doc_id = make_doc_id(chunk["source"], chunk["chunk_index"])
        existing = collection.get(ids=[doc_id])
        if existing["ids"]:
            continue

        texts.append(chunk["text"])
        ids.append(doc_id)
        metadatas.append({
            "source": "upload",
            "filename": filename,
            "chunk_index": chunk["chunk_index"],
            "title": filename.replace(".pdf", ""),
            "authors": "Uploaded by user",
            "published": "N/A",
            "url": "",
        })

    if texts:
        embeddings = embed_texts(texts)
        collection.add(documents=texts, embeddings=embeddings,
                       ids=ids, metadatas=metadatas)

    return {
        "filename": filename,
        "total_chunks": len(chunks),
        "chunks_added": len(texts),
        "chunks_skipped": len(chunks) - len(texts),
    }


def list_uploaded_docs() -> list[dict]:
    """List all documents in ChromaDB with their metadata."""
    collection = get_collection()
    results = collection.get(include=["metadatas"])
    
    seen = set()
    docs = []
    for meta in results["metadatas"]:
        key = meta.get("arxiv_id") or meta.get("filename") or meta.get("title", "unknown")
        if key not in seen:
            seen.add(key)
            docs.append({
                "title": meta.get("title", key),
                "source": meta.get("source", "unknown"),
                "authors": meta.get("authors", ""),
                "published": meta.get("published", ""),
                "url": meta.get("url", ""),
            })
    return docs


def delete_document(title: str) -> int:
    """Delete all chunks for a given document title."""
    collection = get_collection()
    results = collection.get(include=["metadatas"])
    
    ids_to_delete = [
        results["ids"][i]
        for i, meta in enumerate(results["metadatas"])
        if meta.get("title") == title or meta.get("filename") == title
    ]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)

    return len(ids_to_delete)
