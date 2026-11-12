-- Hito 9 Parte 3: aprobación humana y cierre del documento.
-- Extiende las secciones/ticket con el estado de aprobación, el documento
-- final y una tabla de trazas por ejecución de nodo (agente, input, output,
-- timestamp) consultable por ticket.

ALTER TABLE rfp_department_sections
    ADD COLUMN IF NOT EXISTS rework_runs INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rfp_department_sections
    ADD COLUMN IF NOT EXISTS decision JSONB;
ALTER TABLE rfp_department_sections
    ADD COLUMN IF NOT EXISTS arbitration_blocked BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE rfp_tickets
    ADD COLUMN IF NOT EXISTS final_document JSONB;

CREATE TABLE IF NOT EXISTS rfp_node_traces (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES rfp_tickets(ticket_id) ON DELETE CASCADE,
    node TEXT NOT NULL,
    agent TEXT NOT NULL,
    department TEXT,
    input JSONB,
    output JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_rfp_node_traces_ticket
    ON rfp_node_traces (ticket_id, timestamp);