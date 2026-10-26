"""Explicit live-provider smoke test: python -m app.embedding_smoke (one small request)."""

from app.embeddings import embed_texts

if __name__ == "__main__":
    vectors = embed_texts(["Embedding connectivity check. בדיקת חיבור."])
    print(f"Provider smoke test passed: {len(vectors)} vector, {len(vectors[0])} dimensions.")
