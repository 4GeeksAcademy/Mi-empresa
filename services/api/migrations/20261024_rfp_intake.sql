CREATE TABLE IF NOT EXISTS rfp_tickets (
    ticket_id UUID PRIMARY KEY,
    rfp_id UUID NOT NULL UNIQUE,
    owner_id VARCHAR(64) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    raw_pdf_path TEXT NOT NULL,
    markdown_path TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'analizando',
    classification_result BOOLEAN,
    classification_reason TEXT,
    processing_error TEXT,
    synthesizer_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_rfp_tickets_owner_created ON rfp_tickets(owner_id, created_at);
CREATE INDEX IF NOT EXISTS ix_rfp_tickets_owner_id ON rfp_tickets(owner_id);
CREATE INDEX IF NOT EXISTS ix_rfp_tickets_status ON rfp_tickets(status);

CREATE TABLE IF NOT EXISTS rfp_metadata (
    ticket_id UUID PRIMARY KEY REFERENCES rfp_tickets(ticket_id) ON DELETE CASCADE,
    client_name VARCHAR(255),
    client_country VARCHAR(80),
    services_requested JSONB NOT NULL DEFAULT '[]'::jsonb,
    unknown_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    monthly_volume INTEGER,
    monthly_volume_unit VARCHAR(80),
    deadline VARCHAR(120),
    budget_range VARCHAR(255),
    departments_needed JSONB NOT NULL DEFAULT '[]'::jsonb,
    currency VARCHAR(3),
    readability_metrics JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS rfp_department_sections (
    id BIGSERIAL PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES rfp_tickets(ticket_id) ON DELETE CASCADE,
    department_id VARCHAR(32) NOT NULL,
    key_aspects JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_extract TEXT NOT NULL DEFAULT '',
    approver VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rfp_ticket_department UNIQUE(ticket_id, department_id)
);
CREATE INDEX IF NOT EXISTS ix_rfp_department_sections_ticket_id ON rfp_department_sections(ticket_id);