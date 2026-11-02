"""Capture one real support-agent trace using the configured RAG providers."""

import argparse
import json
from pathlib import Path

from services.support_agent.execution import execute_agent
from services.support_agent.graph import open_agent_graph
from services.support_agent.traces import AgentTraceStore, agent_data_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True, help="Question to run through the live RAG")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("agent-trace.json"),
        help="Trace export destination (default: agent-trace.json)",
    )
    args = parser.parse_args()

    data_directory = agent_data_directory()
    database_path = data_directory / "agent.sqlite3"
    owner_id = "local-trace-capture"
    traces = AgentTraceStore(database_path)
    traces.setup()

    with open_agent_graph(database_path) as graph:
        execution = execute_agent(graph, traces, owner_id, args.question)
    if execution.error:
        print(f"Agent rejected the question; trace_id={execution.trace_id}")
        return 1

    trace = traces.get_for_owner(execution.trace_id, owner_id)
    if trace is None:
        raise RuntimeError(f"Trace {execution.trace_id} was not persisted.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    retrieval = next(
        (node for node in trace["nodes"] if node["node"] == "retrieve"), None
    )
    sources = sorted({
        item["source_document"]
        for item in retrieval["output"]["context"]
    }) if retrieval is not None else []
    print(f"Trace: {execution.trace_id}")
    print(f"Status: {trace['status']}")
    print(f"Sources: {', '.join(sources) if sources else '(none)'}")
    print(f"Nodes: {' -> '.join(node['node'] for node in trace['nodes'])}")
    print(f"Answer: {trace['answer']}")
    print(f"Export: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
