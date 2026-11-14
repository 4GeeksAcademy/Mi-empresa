# Parte 2 — Generación y evaluación de respuestas a RFP (TrackFlow)

> Hito 9 · Flujo agéntico de RFPs — Parte 2 de 3.
> Parte 1 (intake/synthesizer) → **Parte 2 (este documento)** → Parte 3 (envío).

## Alcance

Parte 2 **no re-ingiere el PDF crudo**: parte únicamente del handoff que entrega
el synthesizer de la Parte 1 (`ticket_id` + `synthesizer_payload` con
`metadata` y `department_workstreams`, cada uno con `key_aspects`,
`source_extract`, `open_questions`).

## Módulo

`data/pipelines/rfp_intake/response.py`

- **Generador por departamento** (`warehouse` → Ana Whitfield, `lastmile` →
  Carlos Vega, `reverse` → Sofía Ramos). Cada generador recibe solo su
  `workstream` + metadatos; nunca redacta la sección de otro departamento.
- **Evaluadores en paralelo** (`ThreadPoolExecutor`, sin escrituras
  compartidas) — cada uno recibe **solo su sección** y el contexto mínimo:
  - `readability` — `py-readability-metrics` Flesch Reading Ease (umbral
    `READABILITY_MIN_SCORE = 45`, fallback a longitud media de frase y
    mínimo 50 palabras; tablas markdown se excluyen del cálculo).
  - `relevance` — `key_aspects` del workstream presentes en el borrador.
  - `compliance` — reglas reales del BRIEFING §5:
    | rule_id | Regla |
    | --- | --- |
    | `currency-by-country` | moneda según `client_country` (US→USD, Spain→EUR) |
    | `on-time-sla-required` | debe declarar el SLA de entregas a tiempo (%) |
    | `returns-window-48h` | **nunca** prometer devoluciones en menos de 48 h |
    | `volume-discount-table` | debe incluir la tabla de descuentos por volumen |
    | `carrier-rates-confidential` | no revelar tarifas negociadas con transportistas |
- **Bucle generador ↔ evaluador** con límite `RFP_MAX_ITERATIONS` (por
  defecto 3). Si se agota, se conserva **el último borrador + su evaluación**
  → `needs_human_review` → queda encolado en el handoff a la Parte 3;
  **nunca se descarta el ticket**.
- Feedback concreto y etiquetado por `rule_ids` para que el generador pueda
  corregir en la siguiente iteración.

## Estados persistidos (PostgreSQL)

`rfp_tickets.status`:

```
analisis_completo → generando_borrador → en_evaluación → needs_human_review
                                    ↘ (todas las secciones aprueban) en_evaluación
```

`rfp_department_sections` (nuevas columnas, migración
`services/api/migrations/20261110_rfp_response_generation.sql`):
`draft_content`, `evaluation_results` (JSONB), `approval_status`
(`pendiente`), `iteration_count`, `needs_human_review`, `evaluated_at`,
`approved_at`. `rfp_tickets.response_handoff` (JSONB) guarda el handoff
completo a la Parte 3.

## API

- `POST /api/rfps/{ticket_id}/response` → 202; solo desde
  `analisis_completo` con `synthesizer_payload` (409 en otro estado);
  persiste `generando_borrador` y encola la tarea Celery
  `services.response_tasks.generate_rfp_response_task`.
- `GET /api/rfps/{ticket_id}/response` → estado del ticket, `handoff`
  (Parte 3) y las secciones con borrador, evaluación, iteraciones y
  flag de revisión humana.

## Handoff a la Parte 3 (`part3_handoff`)

```jsonc
{
  "contract_version": "2.0",
  "ticket_id": "…",
  "generated_at": "…",
  "ticket_status": "en_evaluación | needs_human_review",
  "metadata": { "client_name": "…", "client_country": "Spain", "currency": "EUR", "…": "…" },
  "sections": [
    {
      "department_id": "warehouse",
      "section_id": "…",
      "approver": "Ana Whitfield",
      "draft_content": "## Warehouse Operations — …",
      "evaluation_results": {
        "section_id": "…",
        "department_id": "warehouse",
        "readability":  { "pass": true, "score": 9.4, "details": "…" },
        "relevance":    { "pass": true, "missing_aspects": [], "details": "…" },
        "compliance":   { "pass": true, "rule_ids": [], "violations": [] },
        "overall_pass": true,
        "feedback_for_generator": "",
        "evaluated_at": "…",
        "schema_version": "1.0"
      },
      "approval_status": "pendiente",
      "iteration_count": 1,
      "needs_human_review": false,
      "open_questions": ["…"],
      "provisional": false      // true si needs_human_review (borrador NO validado)
    }
  ],
  "pending_approvals": ["warehouse", "reverse"],
  "human_review_queue": []      // department_ids con needs_human_review=true
}
```

La Parte 3 debe tratar `provisional: true` / `human_review_queue` como
bloqueante de envío automático: requiere aprobación humana previa.

## Pruebas

```bash
python -m pytest tests/pipelines/test_rfp_response.py -q   # 9 tests
cd services/api && .venv/bin/python -m pytest tests/test_rfp.py -q   # 5 tests
```