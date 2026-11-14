ALTER TABLE rfp_tickets
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_rfp_tickets_owner_accepted_at
    ON rfp_tickets(owner_id, accepted_at);
