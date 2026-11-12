"""Part 3 unit + integration tests: human approval, guardrails, arbitration,
real parallel branches and a full intake→generation→approval→document E2E.

Anchored to the TrackFlow BRIEFING: approvers (warehouse→Ana Whitfield,
reverse→Sofía Ramos), §7 triggers resolved by fixed arbiters (Miguel Torres),
thread namespacing ``rfp-{ticket}[:{dept}]`` and the final document format.
"""
from __future__ import annotations

import copy
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from data.pipelines.rfp_intake.approval import (
    ApprovalError,
    DECISION_APROBAR,
    DECISION_CAMBIOS,
    DECISION_RECHAZAR,
    STATUS_ESPERANDO_APROBACION,
    STATUS_TERMINADO,
    TRIGGER_CURRENCY_MISMATCH,
    TRIGGER_RETURNS_SLA_BREACH,
    TRIGGER_VOLUME_VS_CAPACITY,
    DecisionValidationError,
    department_thread_id,
    detect_conflicts,
    open_approval_env,
    thread_id,
    validate_decision,
)
from data.pipelines.rfp_intake.response import (
    STATUS_EN_EVALUACION,
    STATUS_NEEDS_HUMAN_REVIEW,
    build_part3_handoff,
    run_response_generation,
)
from services.rfp_graph import process_rfp_markdown
from tests.pipelines.test_rfp_response import HANDOFF

TICKET = HANDOFF["ticket_id"]
DEPTS = ("warehouse", "reverse")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_handoff(ticket_id: str) -> dict:
    handoff = copy.deepcopy(HANDOFF)
    handoff["ticket_id"] = ticket_id
    return handoff


def clean_generator(context: dict) -> str:
    """Borrador limpio: moneda del cliente (España → EUR), sin violaciones."""
    return (f"## {context['department_id']} — ModaViva\n"
            "Todo se factura en EUR conforme al ámbito de la RFP.")


def usd_generator(context: dict) -> str:
    """Generador defectuoso: cotiza en USD pese a client_country=Spain (§5)."""
    return (f"## {context['department_id']} — ModaViva\n"
            "Todo se factura en USD.")


def evaluate_draft(text: str, ctx: dict) -> dict:
    bad_currency = "USD" in text
    violations = ([{"rule_id": "currency-by-country",
                    "message": "moneda distinta de la del cliente"}]
                  if bad_currency else [])
    return {
        "overall_pass": not bad_currency,
        "score": 60 if bad_currency else 95,
        "feedback_for_generator": "Usa la moneda del cliente." if bad_currency else "",
        "compliance": {"violations": violations},
        "readability": {"pass": True},
        "relevance": {"pass": True},
    }


def approval_payload(department_id: str,
                     decision: str = DECISION_APROBAR,
                     comment: str = "Conforme con la sección.") -> dict:
    approver = {"warehouse": "Ana Whitfield",
                "reverse": "Sofía Ramos"}[department_id]
    return {"decision": decision, "approver": approver, "comment": comment}


def _pending_id(session, ticket_id: str, department: str) -> str:
    pending = session.pending_interrupts(ticket_id)[department]
    assert pending, f"{department} no tiene interrupt pendiente"
    return pending[0]["id"]


# ---------------------------------------------------------------------------
# (1) interrupt + resume exitoso, con validación de la respuesta humana
# ---------------------------------------------------------------------------
def test_interrupt_then_resume_validates_human_decision(tmp_path):
    traces: list[dict] = []
    with open_approval_env(
            tmp_path / "approval.db",
            trace_sink=lambda ticket, entry: traces.append(entry),
            generate=clean_generator, evaluate=evaluate_draft) as session:
        result = session.start_approvals(TICKET, make_handoff(TICKET))

        # Punto A: checkpoint persistido ANTES de la interrupción.
        assert sorted(result["pending"]) == sorted(DEPTS)
        for department in DEPTS:
            items = session.pending_interrupts(TICKET)[department]
            assert len(items) == 1
            value = items[0]["value"]
            assert value["department_id"] == department
            assert value["approver"] == approval_payload(department)["approver"]

        # Validación previa a reinsertar la respuesta en el grafo.
        with pytest.raises(DecisionValidationError):
            validate_decision(
                {"decision": "quizas", "approver": "Ana Whitfield",
                 "comment": "x"}, "warehouse")
        with pytest.raises(DecisionValidationError):
            validate_decision(
                {"decision": DECISION_APROBAR, "approver": "Carlos Vega",
                 "comment": ""}, "warehouse")   # aprobador no es el del depto
        with pytest.raises(DecisionValidationError):
            validate_decision(
                {"decision": DECISION_CAMBIOS, "approver": "Sofía Ramos",
                 "comment": "   "}, "reverse")  # cambios sin razón

        # Resume explícito: solo avanza la rama elegida, nunca reinicio total.
        interrupt_id = _pending_id(session, TICKET, "warehouse")
        out = session.resume(TICKET, "warehouse", interrupt_id,
                             approval_payload("warehouse"))
        state = session.approval_state(TICKET)
        assert state["warehouse"]["approval_status"] == "aprobado"
        assert state["reverse"]["approval_status"] == "pendiente"
        assert state["reverse"]["pending_interrupt"] is True
        assert out["complete"] is False
        # El id consumido ya no está pendiente; el de la otra rama sigue.
        assert "warehouse" not in session.pending_interrupts(TICKET)
        assert session.pending_interrupts(TICKET)["reverse"]

        interrupt_id = _pending_id(session, TICKET, "reverse")
        out = session.resume(TICKET, "reverse", interrupt_id,
                             approval_payload("reverse"))
        assert out["complete"] is True
        assert session.is_complete(TICKET)

        # Rechazo → vuelve al generador dentro del MISMO ticket y thread.
        threads = {t["node"] for t in traces}
        assert {"start_approvals", "resume", "review_department",
                "human_decision"} <= threads
        assert all(t["timestamp"] for t in traces)


def test_pending_approvals_survive_checkpoint_reopen(tmp_path):
    checkpoint = tmp_path / "approval.db"
    ticket_id = str(uuid.uuid4())

    # Simula el fin del proceso tras persistir ambos interrupts, antes de que
    # llegue cualquier decisión humana.
    with open_approval_env(checkpoint, generate=clean_generator,
                           evaluate=evaluate_draft) as session:
        session.start_approvals(ticket_id, make_handoff(ticket_id))
        pending_before = session.pending_interrupts(ticket_id)
        ids_before = {
            department: _pending_id(session, ticket_id, department)
            for department in DEPTS
        }
        assert sorted(pending_before) == sorted(DEPTS)

    # Un nuevo saver/ApprovalSession sobre el mismo archivo debe recuperar
    # los estados pausados e IDs, sin volver a llamar start_approvals.
    with open_approval_env(checkpoint, generate=clean_generator,
                           evaluate=evaluate_draft) as recovered:
        pending_after = recovered.pending_interrupts(ticket_id)
        assert {
            department: _pending_id(recovered, ticket_id, department)
            for department in DEPTS
        } == ids_before
        assert recovered.approval_state(ticket_id)["warehouse"][
            "pending_interrupt"] is True
        assert recovered.approval_state(ticket_id)["reverse"][
            "pending_interrupt"] is True

        for department in DEPTS:
            assert pending_after[department][0]["value"] == \
                pending_before[department][0]["value"]

        # Cada interrupt se consume desde la sesión recuperada; al cerrar la
        # segunda rama queda persistido el documento final.
        for department in DEPTS:
            recovered.resume(ticket_id, department, ids_before[department],
                             approval_payload(department))
        assert recovered.is_complete(ticket_id) is True

    # La finalización también sobrevive a otra apertura del checkpoint.
    with open_approval_env(checkpoint) as reopened:
        assert reopened.is_complete(ticket_id) is True
        assert reopened.pending_interrupts(ticket_id) == {}


# ---------------------------------------------------------------------------
# (2) Límite de iteraciones (guardrail de ciclos restantes)
# ---------------------------------------------------------------------------
def test_iteration_limit_stops_generator_and_keeps_last_draft(tmp_path):
    """Guardrail de ciclos restantes: el generador no se invoca más allá del
    límite, se conserva el último borrador y el juicio humano sigue abierto."""
    generate_calls = {"warehouse": 0, "reverse": 0}

    def counting_generator(context: dict) -> str:
        generate_calls[context["department_id"]] += 1
        return clean_generator(context)   # sin violaciones §7 (no es arbitraje)

    def never_passing_evaluator(text: str, ctx: dict) -> dict:
        return {
            "overall_pass": False,
            "score": 40,
            "feedback_for_generator": "Falta detalle operativo.",
            "compliance": {"violations": []},   # ningún trigger §7
            "readability": {"pass": True},
            "relevance": {"pass": True},
        }

    with open_approval_env(tmp_path / "approval.db",
                           generate=counting_generator,
                           evaluate=never_passing_evaluator,
                           max_iterations=1) as session:
        session.start_approvals(TICKET, make_handoff(TICKET))

        # El ciclo inicial agota el límite (1 permitido): el interrupt ya
        # muestra la bandera y la sección sigue "pendiente" de juicio humano.
        assert generate_calls["warehouse"] == 1
        pending = session.pending_interrupts(TICKET)
        assert pending["warehouse"][0]["value"]["iteration_limit_reached"] is True
        assert pending["warehouse"][0]["value"]["needs_human_review"] is True
        state = session.approval_state(TICKET)["warehouse"]
        assert state["rework_runs"] == 1
        assert state["approval_status"] == "pendiente"

        # request_changes humano → re-entrada al ciclo restante: NO se invoca
        # al generador (límite respetado) y la decisión humana se reofrece.
        session.resume(TICKET, "warehouse",
                       pending["warehouse"][0]["id"],
                       approval_payload("warehouse", DECISION_CAMBIOS,
                                        "La sección no cumple."))
        assert generate_calls["warehouse"] == 1          # nunca pasa del límite
        pending = session.pending_interrupts(TICKET)
        assert "warehouse" in pending
        assert pending["warehouse"][0]["value"]["iteration_limit_reached"] is True
        assert session.approval_state(TICKET)["warehouse"][
            "approval_status"] == "cambios_solicitados"

        # Pese al límite, el aprobador puede cerrar con el borrador conservado.
        session.resume(TICKET, "warehouse",
                       pending["warehouse"][0]["id"],
                       approval_payload("warehouse"))
        assert session.approval_state(TICKET)["warehouse"][
            "approval_status"] == "aprobado"
        assert generate_calls["warehouse"] == 1


def test_arbitration_exhaustion_blocks_approval(tmp_path):
    """§7 currency-mismatch: si el límite se agota, no se admite aprobación."""
    with open_approval_env(tmp_path / "approval.db",
                           generate=usd_generator,  # nunca corrige la moneda
                           evaluate=evaluate_draft,
                           max_iterations=1) as session:
        session.start_approvals(TICKET, make_handoff(TICKET))
        interrupt_id = _pending_id(session, TICKET, "warehouse")
        session.resume(TICKET, "warehouse", interrupt_id,
                       approval_payload("warehouse", DECISION_CAMBIOS,
                                        "La moneda no es la del cliente."))

        state = session.approval_state(TICKET)["warehouse"]
        assert state["arbitration_blocked"] is True
        assert state["approval_status"] == "rechazado"
        # Rechazo terminal: no se ofrece un nuevo interrupt de aprobación.
        assert "warehouse" not in session.pending_interrupts(TICKET)

        # Aun forzando un resume con un id antiguo, la aprobación queda bloqueada.
        with pytest.raises(ApprovalError):
            session.resume(TICKET, "warehouse", interrupt_id,
                           approval_payload("warehouse"))


# ---------------------------------------------------------------------------
# (3) Arbitraje ante desacuerdo (estado estructurado, árbitro fijo)
# ---------------------------------------------------------------------------
def test_arbitration_resolves_structured_currency_conflict(tmp_path):
    """Un conflicto §7 detectado en campos tipados se resuelve con la regla
    determinista del árbitro fijo (nunca vota un LLM)."""
    handoff = make_handoff(TICKET)
    generation = run_response_generation(handoff, max_iterations=3,
                                         generate=clean_generator,
                                         evaluate=evaluate_draft)
    part3 = generation["part3_handoff"]
    # Estado estructurado de conflicto: reverse cotiza en USD, España → EUR.
    reverse = next(s for s in part3["sections"]
                   if s["department_id"] == "reverse")
    reverse["draft_content"] = (
        "## Reverse Logistics — ModaViva\nTodo se factura en USD.")
    reverse["evaluation_results"] = evaluate_draft(reverse["draft_content"], {})

    conflicts = detect_conflicts(part3)
    assert conflicts and conflicts[0]["trigger"] == TRIGGER_CURRENCY_MISMATCH
    assert set(conflicts[0]["departments"]) == {"reverse"}
    assert conflicts[0]["detail"]["expected"] == "EUR"
    # Los agentes solo señalan: no se decide aquí la resolución.
    assert "arbiter" not in conflicts[0]
    assert "action" not in conflicts[0]

    with open_approval_env(tmp_path / "approval.db",
                           generate=clean_generator,
                           evaluate=evaluate_draft) as session:
        result = session.start_approvals(TICKET, part3)
        # El arbitraje corrió ANTES de ofrecer la decisión humana: el
        # interrupt de reverse ya trae la moneda corregida por la regla.
        reverse_value = session.pending_interrupts(TICKET)["reverse"][0]["value"]
        assert "USD" not in reverse_value["draft_content"]
        assert "EUR" in reverse_value["draft_content"]

        for department in DEPTS:
            session.resume(TICKET, department,
                           _pending_id(session, TICKET, department),
                           approval_payload(department))
        document = session.final_document(TICKET)
        assert document["currency"] == "EUR"
        assert "USD" not in document["content"]
        assert result["complete"] is False  # se completa al cerrar el último
        assert session.is_complete(TICKET) is True


def test_detect_conflicts_covers_returns_and_volume_triggers():
    handoff = {
        "metadata": {"client_country": "Spain", "monthly_volume": 1200},
        "sections": [
            {
                "department_id": "warehouse",
                "capacity_shortfall": True,
            },
            {
                "department_id": "lastmile",
                "volume_assumption": True,
                "draft_content": "La RFP declara 1,200 pedidos al mes.",
            },
            {
                "department_id": "reverse",
                "evaluation_results": {
                    "compliance": {
                        "violations": [{"rule_id": "returns-window-48h"}],
                    },
                },
            },
        ],
    }

    conflicts = detect_conflicts(handoff)
    by_trigger = {conflict["trigger"]: conflict for conflict in conflicts}
    assert by_trigger[TRIGGER_VOLUME_VS_CAPACITY]["departments"] == [
        "lastmile", "warehouse"]
    assert by_trigger[TRIGGER_VOLUME_VS_CAPACITY]["detail"][
        "monthly_volume"] == 1200
    assert by_trigger[TRIGGER_RETURNS_SLA_BREACH]["departments"] == [
        "reverse"]
    assert by_trigger[TRIGGER_RETURNS_SLA_BREACH]["detail"][
        "offenders"] == ["reverse"]


def test_arbitration_rewrites_returns_sla_before_human_interrupt(tmp_path):
    ticket_id = str(uuid.uuid4())
    handoff = run_response_generation(
        make_handoff(ticket_id), max_iterations=3,
        generate=clean_generator, evaluate=evaluate_draft)["part3_handoff"]
    reverse = next(section for section in handoff["sections"]
                   if section["department_id"] == "reverse")
    reverse["draft_content"] = (
        "## Reverse Logistics — ModaViva\nDevoluciones en 24 horas.")
    reverse["evaluation_results"] = {
        "overall_pass": False,
        "compliance": {"violations": [{"rule_id": "returns-window-48h"}]},
    }

    def sla_generator(context: dict) -> str:
        if context["department_id"] == "reverse":
            return "## Reverse Logistics — ModaViva\nDevoluciones en 24 horas."
        return clean_generator(context)

    with open_approval_env(tmp_path / "approval.db",
                           generate=sla_generator,
                           evaluate=evaluate_draft) as session:
        result = session.start_approvals(ticket_id, handoff)
        assert TRIGGER_RETURNS_SLA_BREACH in {
            conflict["trigger"] for conflict in result["conflicts"]}
        pending_reverse = session.pending_interrupts(ticket_id)["reverse"][0]
        assert "24 horas" not in pending_reverse["value"]["draft_content"]
        assert "48 horas" in pending_reverse["value"]["draft_content"]


# ---------------------------------------------------------------------------
# (4) Ramas paralelas REALES: B se aprueba mientras A sigue interrumpida
# ---------------------------------------------------------------------------
def test_parallel_branches_approve_b_while_a_still_interrupted(tmp_path):
    traces: list[dict] = []
    with open_approval_env(
            tmp_path / "approval.db",
            trace_sink=lambda ticket, entry: traces.append(entry),
            generate=clean_generator, evaluate=evaluate_draft) as session:
        session.start_approvals(TICKET, make_handoff(TICKET))
        state = session.approval_state(TICKET)

        # Ambas ramas pausadas en paralelo, cada una con su propio thread.
        assert state["warehouse"]["pending_interrupt"] is True
        assert state["reverse"]["pending_interrupt"] is True
        assert state["warehouse"]["thread_id"] == department_thread_id(
            TICKET, "warehouse")
        assert state["reverse"]["thread_id"] == department_thread_id(
            TICKET, "reverse")
        assert state["warehouse"]["thread_id"] != state["reverse"]["thread_id"]

        pending_before = session.pending_interrupts(TICKET)
        warehouse_id = pending_before["warehouse"][0]["id"]
        reverse_id = pending_before["reverse"][0]["id"]
        assert warehouse_id != reverse_id

        # Se aprueba "reverse" (B): "warehouse" (A) sigue interrumpido.
        session.resume(TICKET, "reverse", reverse_id,
                       approval_payload("reverse"))
        state = session.approval_state(TICKET)
        assert state["reverse"]["approval_status"] == "aprobado"
        assert state["warehouse"]["approval_status"] == "pendiente"
        assert state["warehouse"]["pending_interrupt"] is True
        assert session.pending_interrupts(TICKET) == {
            "warehouse": pending_before["warehouse"]}  # id estable y sin cambiar

        # Nada del ticket cerrado: el consolidador espera a TODOS.
        assert session.is_complete(TICKET) is False

        # La traza prueba que cada ejecución de nodo quedó registrada.
        by_dept = {department: [t for t in traces if t["department"] == department]
                   for department in DEPTS}
        assert by_dept["warehouse"], "sin trazas de la rama warehouse"
        assert by_dept["reverse"], "sin trazas de la rama reverse"
        human_decisions = [t for t in traces
                           if t["node"] == "human_decision"]
        assert {(t["department"], t["output"]["decision"])
                for t in human_decisions} == {("reverse", DECISION_APROBAR)}
        assert all(t["timestamp"] and t["agent"] for t in traces)

        # Aún así, "warehouse" puede decidir en su propio hilo.
        session.resume(TICKET, "warehouse", warehouse_id,
                       approval_payload("warehouse"))
        assert session.is_complete(TICKET) is True


def test_concurrent_department_resumes_preserve_both_approvals(tmp_path):
    ticket_id = str(uuid.uuid4())
    with open_approval_env(tmp_path / "approval.db",
                           generate=clean_generator,
                           evaluate=evaluate_draft) as session:
        session.start_approvals(ticket_id, make_handoff(ticket_id))
        interrupt_ids = {
            department: _pending_id(session, ticket_id, department)
            for department in DEPTS
        }

    checkpoint = tmp_path / "approval.db"

    def approve(department: str) -> dict:
        # Cada worker crea su propia conexión/saver, como tareas Celery
        # concurrentes en procesos distintos.
        with open_approval_env(checkpoint, generate=clean_generator,
                               evaluate=evaluate_draft) as worker_session:
            return worker_session.resume(ticket_id, department,
                                         interrupt_ids[department],
                                         approval_payload(department))

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(approve, DEPTS))

    with open_approval_env(checkpoint) as session:
        assert all(outcome["approval_status"] == "aprobado"
                   for outcome in outcomes)
        state = session.approval_state(ticket_id)
        assert {department: state[department]["approval_status"]
                for department in DEPTS} == {
                    "warehouse": "aprobado", "reverse": "aprobado"}
        assert session.is_complete(ticket_id) is True


# ---------------------------------------------------------------------------
# (5) E2E: recepción → generación → aprobación → documento final
# ---------------------------------------------------------------------------
def test_e2e_intake_generation_approval_final_document(tmp_path):
    # --- Parte 1: recepción y enrutado -------------------------------
    markdown = """Request for Proposal
Client: ModaViva
Spain
We need warehousing and reverse logistics for our returns.
We use our own carrier for last mile.
Deadline: 30 November 2026
"""
    source = tmp_path / "source.md"
    source.write_text(markdown, encoding="utf-8")
    intake = process_rfp_markdown(markdown, str(source))
    assert intake["accepted"] is True
    assert [w["department_id"] for w in intake["department_sections"]] == list(DEPTS)

    handoff = intake["handoff"]
    ticket_id = str(uuid.uuid4())
    handoff["ticket_id"] = ticket_id

    # --- Parte 2: generación + evaluación de secciones ----------------
    output = run_response_generation(handoff, max_iterations=3)
    assert output["ticket_status"] in {STATUS_EN_EVALUACION,
                                       STATUS_NEEDS_HUMAN_REVIEW}
    part3 = output["part3_handoff"]
    assert part3["ticket_id"] == ticket_id
    assert [s["department_id"] for s in part3["sections"]] == list(DEPTS)
    for section in part3["sections"]:
        assert section["draft_content"]
        assert section["approver"] in {"Ana Whitfield", "Sofía Ramos"}
        assert section["approval_status"] == "pendiente"

    # --- Parte 3: aprobación humana y cierre --------------------------
    traces: list[dict] = []
    with open_approval_env(
            tmp_path / "approval.db",
            trace_sink=lambda ticket, entry: traces.append(entry),
            generate=clean_generator, evaluate=evaluate_draft) as session:
        started = session.start_approvals(ticket_id, part3)
        assert sorted(started["pending"]) == sorted(DEPTS)

        for department in DEPTS:
            session.resume(ticket_id, department,
                           _pending_id(session, ticket_id, department),
                           approval_payload(department))

        # Solo con sign-off de TODOS los departamentos activos.
        assert session.is_complete(ticket_id) is True
        document = session.final_document(ticket_id)

        # Formato BRIEFING + moneda por client_country (España → EUR).
        assert document["ticket_id"] == ticket_id
        assert document["content"].startswith("# Propuesta TrackFlow para ModaViva")
        assert document["currency"] == "EUR"
        assert document["provisional"] is False
        positions = [document["content"].find("Warehouse Operations"),
                     document["content"].find("Reverse Logistics")]
        assert all(p >= 0 for p in positions)
        assert positions[0] < positions[1]  # orden fijo DEPT_ORDER
        # Estados de ticket sin inventar: terminado solo con doc final.
        assert STATUS_ESPERANDO_APROBACION and STATUS_TERMINADO

        nodes = [t["node"] for t in traces]
        for expected in ("detect_conflicts", "start_approvals", "resume",
                         "review_department", "human_decision", "coordinator"):
            assert expected in nodes

def test_trace_sink_failure_propagates(tmp_path):
    def failing_trace_sink(ticket_id, entry):
        raise RuntimeError("trace persistence failed")

    with open_approval_env(
            tmp_path / "approval.db",
            trace_sink=failing_trace_sink) as session:
        with pytest.raises(RuntimeError, match="trace persistence failed"):
            session._trace(TICKET, {"node": "test"})