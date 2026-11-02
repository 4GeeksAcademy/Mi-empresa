"""Capture real incident routing and not-found traces without invoking a model."""

import argparse
import json
from pathlib import Path

from services.support_agent.execution import execute_agent
from services.support_agent.graph import open_agent_graph
from services.support_agent.incidents import IncidentQuery, query_incidents
from services.support_agent.traces import AgentTraceStore, agent_data_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=agent_data_directory() / "incident-evals.json",
    )
    args = parser.parse_args()
    listing = query_incidents(IncidentQuery())
    if not listing["ok"]:
        print(f"BLOCKED real incident listing: {listing['error_code']}")
        return 1
    has_ticket = bool(listing["incidents"])
    if not has_ticket:
        print("BLOCKED existing-ticket eval: backend is empty; capturing list/404 diagnostics only.")
    ticket_id = listing["incidents"][0]["id"] if has_ticket else None
    missing_id = max((int(row["id"]) for row in listing["incidents"]), default=0) + 1
    database = agent_data_directory() / "agent.sqlite3"
    traces = AgentTraceStore(database)
    traces.setup()
    exports = []
    with open_agent_graph(database) as graph:
        for question in (
            f"¿En qué estado está el ticket {ticket_id}?" if has_ticket else "Lista incidencias abiertas",
            f"¿En qué estado está el ticket {missing_id}?",
        ):
            execution = execute_agent(graph, traces, "local-incident-evals", question)
            trace = traces.get_for_owner(execution.trace_id, "local-incident-evals")
            if trace is None:
                raise RuntimeError("Incident evaluation trace was not persisted.")
            trace["expected_source"] = "incidents"
            exports.append(trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(exports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Captured {len(exports)} real backend traces: {args.output}")
    return 0 if has_ticket else 1


if __name__ == "__main__":
    raise SystemExit(main())
