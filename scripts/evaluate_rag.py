"""Measure live Qdrant retrieval Recall@3 for the curated RAG query set."""

import json
from pathlib import Path

from services.knowledge.pipeline import retrieve

ROOT = Path(__file__).resolve().parents[1]
TEST_QUERIES = ROOT / "data/eval/test-queries.json"


def evaluate() -> dict:
    cases = json.loads(TEST_QUERIES.read_text(encoding="utf-8"))
    hits = 0
    details = []
    for case in cases:
        results = retrieve(case["question"], k=3)
        retrieved = {
            (item["source_document"], item["section"])
            for item in results
        }
        expected = {
            (item["source_document"], item["section"])
            for item in case["expected"]
        }
        hit = bool(retrieved & expected)
        hits += int(hit)
        details.append({"question": case["question"], "hit": hit})
    score = hits / len(cases) if cases else 0.0
    return {"metric": "Recall@3", "hits": hits, "total": len(cases), "recall_at_3": score, "target": 0.8, "passed": score >= 0.8, "results": details}


def main() -> None:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
