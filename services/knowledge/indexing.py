"""Semantic corpus preparation and idempotent Qdrant indexing."""

import argparse
import json
import math
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

COLLECTION = "trackflow_knowledge"
CORPUS = Path(__file__).resolve().parents[2] / "docs/company-knowledge-base"
DOCUMENTS = ("sla-delivery", "returns-policy", "carrier-coverage", "storage-pricing")


def prepare_chunks(corpus: Path = CORPUS) -> list[dict]:
    from markdown_it import MarkdownIt

    parser = MarkdownIt("commonmark")
    chunks = []
    for source in DOCUMENTS:
        path = corpus / f"trackflow-{source}.es.md"
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        tokens = [
            token for token in parser.parse(text)
            if token.level == 0 and token.map is not None
        ]
        headings = []
        pending = []
        document_chunks = []

        def append_chunk() -> None:
            if pending:
                document_chunks.append({
                    "company": "trackflow",
                    "source_document": source,
                    "section": " / ".join(title for _, title in headings),
                    "language": "es",
                    "chunk_index": len(document_chunks),
                    "text": "\n\n".join(pending),
                })
                pending.clear()

        for position, token in enumerate(tokens):
            start, end = token.map
            block = "".join(lines[start:end]).strip()
            if token.type == "heading_open":
                append_chunk()
                level = int(token.tag[1:])
                title = block.lstrip("#").strip().rstrip("#").strip()
                headings = [(depth, name) for depth, name in headings if depth < level]
                headings.append((level, title))
                continue
            if token.type == "hr":
                append_chunk()
                continue
            pending.append(block)
            next_type = tokens[position + 1].type if position + 1 < len(tokens) else None
            if next_type in {"bullet_list_open", "ordered_list_open"}:
                continue
            if block.endswith(":") and next_type == "paragraph_open":
                continue
            append_chunk()
        append_chunk()
        if len(document_chunks) < 3:
            raise ValueError(f"{path.name} must provide at least 3 semantic chunks")
        if any(not chunk["section"] for chunk in document_chunks):
            raise ValueError(f"{path.name} contains content without a section heading")
        chunks.extend(document_chunks)
    return chunks


def required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Configure {name} with the value provided by 4Geeks")
    return value


def embed(text: str) -> list[float]:
    from openai import OpenAI

    if not text.strip():
        raise ValueError("Embedding text must not be empty")
    model = required_setting("RAG_EMBEDDING_MODEL")
    generation_model = required_setting("RAG_GENERATION_MODEL")
    if model == generation_model:
        raise ValueError("Embedding and generation models must be distinct")
    client = OpenAI(
        base_url=required_setting("RAG_EMBEDDING_BASE_URL"),
        api_key=required_setting("RAG_EMBEDDING_API_KEY"),
        timeout=30.0,
        max_retries=1,
    )
    result = client.embeddings.create(model=model, input=text)
    vector = [float(value) for value in result.data[0].embedding]
    if not vector or not all(math.isfinite(value) for value in vector):
        raise ValueError("Embedding service returned an invalid vector")
    if not any(vector):
        raise ValueError("Embedding service returned a zero vector")
    return vector


def chunk_id(payload: dict) -> str:
    identity = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return str(uuid5(NAMESPACE_URL, f"{COLLECTION}:{identity}"))


def setup() -> dict:
    from qdrant_client import QdrantClient, models

    chunks = prepare_chunks()
    vectors = [embed(chunk["text"]) for chunk in chunks]
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise ValueError("Embedding dimensions changed during indexing")
    client = QdrantClient(
        url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        api_key=os.environ.get("QDRANT_API_KEY") or None,
        timeout=30,
    )
    try:
        if client.collection_exists(COLLECTION):
            configuration = client.get_collection(COLLECTION).config.params.vectors
            if not isinstance(configuration, models.VectorParams):
                raise ValueError("Expected a single unnamed vector configuration")
            if configuration.size != dimension or configuration.distance != models.Distance.COSINE:
                raise ValueError("Existing collection dimension or distance is incompatible")
        else:
            client.create_collection(
                COLLECTION,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
            )
        previous_ids = set()
        offset = None
        while True:
            points, offset = client.scroll(
                COLLECTION, limit=256, offset=offset,
                with_payload=False, with_vectors=False,
            )
            previous_ids.update(str(point.id) for point in points)
            if offset is None:
                break
        current_ids = {chunk_id(chunk) for chunk in chunks}
        client.upsert(
            COLLECTION,
            points=[
                models.PointStruct(id=chunk_id(chunk), vector=vector, payload=chunk)
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
            wait=True,
        )
        stale_ids = sorted(previous_ids - current_ids)
        if stale_ids:
            client.delete(
                COLLECTION, points_selector=models.PointIdsList(points=stale_ids), wait=True,
            )
        return {"collection": COLLECTION, "chunks": len(chunks), "dimension": dimension}
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Inspect chunks without external calls")
    arguments = parser.parse_args()
    if arguments.preview:
        chunks = prepare_chunks()
        output = {
            "collection": COLLECTION,
            "documents": {
                source: {
                    "chunks": sum(chunk["source_document"] == source for chunk in chunks),
                    "characters": [
                        len(chunk["text"]) for chunk in chunks if chunk["source_document"] == source
                    ],
                }
                for source in DOCUMENTS
            },
        }
    else:
        output = setup()
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()