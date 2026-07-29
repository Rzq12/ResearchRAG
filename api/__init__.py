"""
Thin FastAPI wrapper around the existing ResearchRAG backend.

This package does NOT reimplement any RAG / retrieval / inference logic. It
imports the exact same modules that ``streamlit_app.py`` uses (``app.rag``,
``app.openalex_service``, ``app.pdf_service``, ``app.semantic_search``,
``app.auth`` …) and exposes them over HTTP so the React frontend can call them.

The Streamlit application is left completely untouched.
"""
