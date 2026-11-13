"""Part 2 unit tests: one generator, one evaluator, one failed evaluation and a
compliance failure anchored to a real rule of the TrackFlow BRIEFING §5."""
from __future__ import annotations

import data.pipelines.rfp_intake.response as response_module
from data.pipelines.rfp_intake.response import (
    build_generation_context,
    evaluate_compliance,
    evaluate_section,
    generate_section,
    run_section_cycle,
    run_response_generation,
)

HANDOFF = {
    "ticket_id": "11111111-1111-1111-1111-111111111111",
    "metadata": {
        "client_name": "ModaViva",
        "client_country": "Spain",
        "currency": "EUR",
        "services_requested": ["warehouse", "reverse"],
        "monthly_volume": 1200,
        "monthly_volume_unit": "orders/month",
        "deadline": "30 November 2026",
        "budget_range": None,
        "departments_needed": ["warehouse", "reverse"],
    },
    "department_workstreams": [
        {
            "department_id": "warehouse",
            "approver": "Ana Whitfield",
            "key_aspects": ["warehousing for our apparel SKUs"],
            "open_questions": [],
            "source_extract": "We need warehousing for our apparel SKUs in Spain.",
        },
        {
            "department_id": "reverse",
            "approver": "Sofía Ramos",
            "key_aspects": ["returns processing"],
            "open_questions": [],
            "source_extract": "Reverse logistics for returns processing.",
        },
    ],
}


def _workstream(department_id: str) -> dict:
    return next(ws for ws in HANDOFF["department_workstreams"]
                if ws["department_id"] == department_id)


# --- Generador ------------------------------------------------------------
def test_generator_drafts_only_its_department_from_the_handoff():
    context = build_generation_context(HANDOFF, _workstream("warehouse"))
    draft = generate_section(context)

    assert draft.startswith("## Warehouse Operations — ModaViva")
    assert "1,200" in draft  # usa el volumen declarado en la RFP, no lo inventa
    assert "EUR" in draft  # moneda coherente con client_country=Spain
    assert "### Descuentos por volumen" in draft
    assert "Reverse Logistics" not in draft  # no redacta la sección de otro depto


def test_generator_registers_open_question_when_volume_is_missing():
    handoff = {**HANDOFF, "metadata": {**HANDOFF["metadata"],
                                       "monthly_volume": None,
                                       "monthly_volume_unit": None}}
    context = build_generation_context(handoff, _workstream("warehouse"))
    draft = generate_section(context)

    assert "no declara el volumen mensual" in draft
    assert "¿Cuál es el volumen mensual esperado?" in draft


# --- Evaluadores ----------------------------------------------------------
def test_evaluators_only_receive_section_and_required_context(monkeypatch):
    seen: list[tuple[str, dict]] = []

    def spy(section_text: str, context: dict) -> dict:
        seen.append((section_text, context))
        return {"pass": True}

    monkeypatch.setitem(response_module.EVALUATORS, "relevance", spy)
    draft = generate_section(build_generation_context(HANDOFF, _workstream("warehouse")))
    result = evaluate_section(draft, {"key_aspects": ["warehousing for our apparel SKUs"],
                                      "client_country": "Spain", "department_id": "warehouse"})

    # el evaluador recibió SOLO su sección, nunca el documento completo
    assert len(seen) == 1
    section_text, context = seen[0]
    assert section_text == draft
    assert "modaviva-request.pdf" not in section_text
    assert set(context) == {"key_aspects", "client_country", "department_id"}
    assert result["overall_pass"] is True


def test_evaluator_reports_failing_draft_with_concrete_feedback():
    context = build_generation_context(HANDOFF, _workstream("warehouse"))
    draft = "## Warehouse Operations — ModaViva"
    result = evaluate_section(draft, {"key_aspects": context["key_aspects"],
                                      "client_country": "Spain",
                                      "department_id": "warehouse"})

    assert result["overall_pass"] is False
    assert result["readability"]["pass"] is False
    assert result["relevance"]["pass"] is False
    assert "warehousing for our apparel SKUs" in result["relevance"]["missing_aspects"]
    assert "aspectos clave" in result["feedback_for_generator"]


def test_compliance_fails_when_draft_promises_returns_under_48h():
    """Regla del BRIEFING §5: ninguna propuesta promete devoluciones < 48 h."""
    draft = (
        "## Reverse Logistics — ModaViva\n\n"
        "Procesamos cada devolución en 24 horas para tu tienda.\n\n"
        "### Costes\nEl SLA de entregas a tiempo es del 90% cada mes. "
        "Todo se factura en EUR.\n\n"
        "### Descuentos por volumen\n| Volumen | Descuento |\n| --- | --- |\n"
        "| Alto | 10% |\n"
    )
    result = evaluate_compliance(draft, {"client_country": "Spain"})

    assert result["pass"] is False
    assert "returns-window-48h" in result["rule_ids"]
    assert any("48" in v["message"] for v in result["violations"])


def test_compliance_requires_contractual_sla_not_discount_percentage():
    draft = (
        "### Costes\nEl cliente recibe un descuento del 10%. "
        "Todo se factura en EUR.\n\n"
        "### Descuentos por volumen\n| Volumen | Descuento |\n"
        "| --- | --- |\n| Alto | 10% |\n"
    )
    result = evaluate_compliance(draft, {"client_country": "Spain"})

    assert "on-time-sla-required" in result["rule_ids"]


def test_compliance_accepts_contractual_90_percent_on_time_sla():
    draft = (
        "### Costes\nEl SLA de entregas a tiempo es del 90% cada mes. "
        "Todo se factura en EUR.\n\n"
        "### Descuentos por volumen\n| Volumen | Descuento |\n"
        "| --- | --- |\n| Alto | 10% |\n"
    )
    result = evaluate_compliance(draft, {"client_country": "Spain"})

    assert "on-time-sla-required" not in result["rule_ids"]


def test_compliance_detects_carrier_rates_case_insensitively():
    draft = (
        "### Costes\nEl SLA de entregas a tiempo es del 90% cada mes. "
        "La tarifa de MRW es confidencial. Todo se factura en EUR.\n\n"
        "### Descuentos por volumen\n| Volumen | Descuento |\n"
        "| --- | --- |\n| Alto | 10% |\n"
    )
    result = evaluate_compliance(draft, {"client_country": "Spain"})

    assert "carrier-rates-confidential" in result["rule_ids"]


def test_relevance_requires_key_aspect_exact_text():
    from data.pipelines.rfp_intake.response import evaluate_relevance

    result = evaluate_relevance(
        "We provide WAREHOUSING for our apparel SKUs.",
        {"key_aspects": ["warehousing for our apparel SKUs"]},
    )

    assert result["pass"] is False
    assert result["missing_aspects"] == ["warehousing for our apparel SKUs"]


def test_48_hour_return_rule_applies_in_lastmile_sections():
    draft = (
        "## Last Mile\nReturns are processed in 24 hours.\n"
        "The SLA of on-time deliveries is 90% monthly.\n\n"
        "### Volume discount table\n| Volume | Discount |\n| --- | --- |\n| High | 10% |\n"
    )
    result = evaluate_compliance(draft, {"department_id": "lastmile"})

    assert "returns-window-48h" in result["rule_ids"]


def test_compliance_fails_on_currency_mismatch_with_client_country():
    draft = (
        "### Costes\nTodo se factura en USD con un SLA de entregas a tiempo del "
        "90% mensual.\n\n### Descuentos por volumen\n| Volumen | Descuento |\n"
        "| --- | --- |\n| Alto | 10% |\n"
    )
    result = evaluate_compliance(draft, {"client_country": "Spain"})

    assert result["pass"] is False
    assert "currency-by-country" in result["rule_ids"]


# --- Ciclo generador-evaluador -------------------------------------------
def test_failed_section_returns_to_generator_then_passes():
    attempts: list[str] = []

    def flaky_generator(context: dict) -> str:
        attempts.append(context.get("feedback") or "")
        if len(attempts) == 1:
            return "## Warehouse Operations — ModaViva"  # borrador inservible
        context["feedback"] = ""  # el generador ya incorporó el feedback
        return generate_section(context)

    result = run_section_cycle(HANDOFF, _workstream("warehouse"),
                               max_iterations=3, generate=flaky_generator)

    assert len(attempts) == 2
    assert "aspectos clave" in attempts[1]  # feedback concreto del evaluador
    assert result["needs_human_review"] is False
    assert result["iteration_count"] == 2
    assert result["evaluation_results"]["overall_pass"] is True


def test_iteration_limit_keeps_last_draft_and_flags_needs_human_review():
    def never_passing(context: dict) -> str:
        return "## Warehouse Operations — ModaViva"

    result = run_section_cycle(HANDOFF, _workstream("warehouse"),
                               max_iterations=2, generate=never_passing)

    assert result["iteration_count"] == 2  # el límite se respeta
    assert result["needs_human_review"] is True
    assert result["status"] == "needs_human_review"
    assert result["draft_content"].startswith("## Warehouse Operations")
    assert result["evaluation_results"]["overall_pass"] is False


def test_progress_callback_reports_live_phases_in_order():
    """El llamante ve generacion → evaluacion en tiempo real (ticket en vivo)."""
    phases: list[tuple[str, str]] = []

    def on_progress(phase: str, payload: dict) -> None:
        phases.append((phase, payload["department_id"]))

    run_response_generation(HANDOFF, max_iterations=1, on_progress=on_progress)

    assert phases[0] == ("generacion", "warehouse")
    assert {"generacion", "evaluacion"} == {phase for phase, _ in phases}
    # una fase por intento y departamento, sin colapsar en el estado final
    assert len(phases) == 2 * len(HANDOFF["department_workstreams"])


def test_part3_handoff_contains_content_and_evaluation_per_department():
    output = run_response_generation(HANDOFF, max_iterations=3)

    assert output["ticket_status"] in {"en_evaluación", "needs_human_review"}
    handoff = output["part3_handoff"]
    assert handoff["ticket_id"] == HANDOFF["ticket_id"]
    departments = [section["department_id"] for section in handoff["sections"]]
    assert departments == ["warehouse", "reverse"]  # orden original del handoff
    for section in handoff["sections"]:
        assert section["draft_content"]
        evaluation = section["evaluation_results"]
        assert set(evaluation) >= {"readability", "relevance", "compliance",
                                   "overall_pass", "feedback_for_generator"}
        assert section["approver"] in {"Ana Whitfield", "Sofía Ramos"}