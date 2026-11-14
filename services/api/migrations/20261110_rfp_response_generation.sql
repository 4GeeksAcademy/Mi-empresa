-- Parte 2 del flujo agéntico de RFP: borradores, evaluaciones y handoff a la Parte 3.
ALTER TABLE rfp_department_sections
    ADD COLUMN IF NOT EXISTS draft_content TEXT,
    ADD COLUMN IF NOT EXISTS evaluation_results JSONB,
    ADD COLUMN IF NOT EXISTS approval_status VARCHAR(32) NOT NULL DEFAULT 'pendiente',
    ADD COLUMN IF NOT EXISTS iteration_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

ALTER TABLE rfp_tickets
    ADD COLUMN IF NOT EXISTS response_handoff JSONB;

CREATE INDEX IF NOT EXISTS ix_rfp_department_sections_approval
    ON rfp_department_sections(approval_status);