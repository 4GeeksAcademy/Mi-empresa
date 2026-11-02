"""Evaluate exported traces without invoking LangGraph, retrieval or a model."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from services.support_agent.evaluation import (
    EXTERNAL_REQUIRED_CASES, REQUIRED_CASES, evaluate_trace,
)


def load_traces(paths: list[Path]) -> list[dict[str, Any]]:
    traces = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read trace export {path}: {type(exc).__name__}") from exc
        candidates = data if isinstance(data, list) else [data]
        if not all(isinstance(trace, dict) for trace in candidates):
            raise ValueError(f"Trace export {path} must contain JSON objects.")
        if any(trace.get("origin") == "synthetic_test_fixture" for trace in candidates):
            raise ValueError(f"Refusing synthetic test fixture as acceptance evidence: {path}")
        traces.extend(candidates)
    return traces


def evaluate_exports(paths: list[Path]) -> tuple[list[tuple[str, bool, str]], set[str]]:
    results = []
    seen_cases: set[str] = set()
    for trace in load_traces(paths):
        for case_name, passed, description in evaluate_trace(trace):
            results.append((case_name, passed, description))
            seen_cases.add(case_name)
    return results, seen_cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-external",
        action="store_true",
        help="Require both incident-tool and RAG routing acceptance cases.",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Require a trace for every acceptance case (flow, empty, no-context, grounding).",
    )
    parser.add_argument(
        "traces",
        nargs="+",
        type=Path,
        help="JSON trace exports from GET /agent/traces/{trace_id}",
    )
    args = parser.parse_args()
    try:
        results, seen_cases = evaluate_exports(args.traces)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    required = set()
    if args.require_all:
        required.update(REQUIRED_CASES)
    if args.require_external:
        required.update(EXTERNAL_REQUIRED_CASES)
    missing = required - seen_cases
    for name, passed, description in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}: {description}")
    if missing:
        print(f"FAIL missing required trace cases: {', '.join(sorted(missing))}")
    passed_count = sum(passed for _, passed, _ in results)
    print(f"{passed_count}/{len(results)} checks passed")
    return 0 if (
        results
        and all(passed for _, passed, _ in results)
        and not missing
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
