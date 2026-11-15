-- Establish server-managed tenant membership and an initially nullable RFP
-- tenant reference. Existing rows intentionally remain NULL (quarantined).

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
    user_id VARCHAR(64) PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    role VARCHAR(32) NOT NULL CHECK (role IN ('tenant_admin', 'tenant_member')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_tenant_memberships_tenant_id
    ON tenant_memberships (tenant_id);

ALTER TABLE rfp_tickets
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(tenant_id);

CREATE INDEX IF NOT EXISTS ix_rfp_tickets_tenant_created
    ON rfp_tickets (tenant_id, created_at);