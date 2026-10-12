"""CV vector store (Chroma) for semantic job matching and RAG excerpts.

Embeddings come from the all-MiniLM-L6-v2 sentence-transformer (ONNX runtime,
bundled with chromadb). FITSCREEN_FAKE_EMBEDDINGS=1 switches to a token-hash
vector so the test suite runs offline without downloading the model.
"""

from __future__ import annotations

import hashlib
import math
import os
import re

HASH_DIM = 96
MODEL_NAME = "all-MiniLM-L6-v2"

_model = None


def _use_fake() -> bool:
    return os.getenv("FITSCREEN_FAKE_EMBEDDINGS", "").lower() in {"1", "true", "yes"}


def embedding_mode() -> dict:
    if _use_fake():
        return {"model": "token-hash", "dim": HASH_DIM, "purpose": "tests only"}
    return {"model": MODEL_NAME, "dim": 384, "runtime": "onnx"}


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * HASH_DIM
    tokens = [t for t in re.split(r"[\s,/|;]+", (text or "").lower()) if t]
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        vec[int.from_bytes(digest[:2], "little") % HASH_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _embed(texts: list[str]) -> list[list[float]]:
    if _use_fake():
        return [_hash_embed(t) for t in texts]
    global _model
    if _model is None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        _model = DefaultEmbeddingFunction()
    return [list(map(float, v)) for v in _model(texts)]


def chroma_path() -> str:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            return current_app.config["CHROMA_PATH"]
    except Exception:
        pass
    return os.getenv("CHROMA_PATH", "chroma_data")


def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=chroma_path())
    # Separate collections per embedding space: vectors of different models are not comparable.
    name = "cv_embeddings_hash" if _use_fake() else "cv_embeddings_minilm"
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def _chunks(text: str, size: int = 700) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text or "") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if current and len(current) + len(p) > size:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks or [(text or "")[:size]]


def embed_application(application_id: str, job_id: str, cv_text: str) -> None:
    col = _collection()
    document = (cv_text or "")[:12000]
    chunks = _chunks(document)
    ids = [application_id] + [f"{application_id}#c{i}" for i in range(len(chunks))]
    docs = [document] + chunks
    metas = [{"job_id": job_id, "application_id": application_id, "kind": "full"}] + [
        {"job_id": job_id, "application_id": application_id, "kind": "chunk"} for _ in chunks
    ]
    col.upsert(ids=ids, documents=docs, embeddings=_embed(docs), metadatas=metas)


def _job_text(job: dict) -> str:
    return (
        f"{job.get('title','')}. {job.get('description','')}. "
        f"Required skills: {job.get('must_have_skills','')}"
    )


def similar_for_job(job: dict, limit: int = 8) -> list[dict]:
    col = _collection()
    if col.count() == 0:
        return []
    try:
        result = col.query(
            query_embeddings=_embed([_job_text(job)]),
            n_results=min(limit, col.count()),
            where={"$and": [{"job_id": job["id"]}, {"kind": "full"}]},
            include=["distances", "metadatas", "documents"],
        )
    except Exception:
        return []
    matches = []
    ids = (result.get("ids") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    for i, app_id in enumerate(ids):
        distance = dists[i] if i < len(dists) else 1.0
        matches.append(
            {
                "application_id": app_id,
                "score": max(0.0, 1.0 - float(distance)),
                "excerpt": (docs[i] if i < len(docs) else "")[:240],
            }
        )
    return matches


def excerpts_for_application(application_id: str, job_text: str, n: int = 3) -> list[str]:
    col = _collection()
    if col.count() == 0:
        return []
    try:
        result = col.query(
            query_embeddings=_embed([job_text]),
            n_results=n,
            where={"$and": [{"application_id": application_id}, {"kind": "chunk"}]},
            include=["documents"],
        )
    except Exception:
        return []
    return [d for d in (result.get("documents") or [[]])[0] if d]
