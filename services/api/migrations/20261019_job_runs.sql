BEGIN;
CREATE TABLE IF NOT EXISTS job_runs (
    id VARCHAR(36) PRIMARY KEY,
    job_name VARCHAR(120) NOT NULL,
    target_date DATE NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_job_runs_job_date ON job_runs (job_name, target_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_runs_processing ON job_runs (job_name)
    WHERE status = 'processing';
COMMIT;