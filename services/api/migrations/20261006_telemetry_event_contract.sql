BEGIN;

LOCK TABLE telemetry_events IN ACCESS EXCLUSIVE MODE;

DO $migration$
BEGIN
    IF EXISTS (
        SELECT event_id
        FROM telemetry_events
        GROUP BY event_id
        HAVING COUNT(DISTINCT jsonb_build_object(
            'timestamp', timestamp,
            'session_id', session_id,
            'user_id', user_id,
            'event_type', event_type,
            'schema_version', schema_version,
            'request_id', request_id,
            'service', service,
            'tags', tags
        )) > 1
    ) THEN
        RAISE EXCEPTION 'Divergent telemetry event_id duplicates; resolve them before migration';
    END IF;
END
$migration$;

WITH ranked_events AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY id) AS duplicate_rank
    FROM telemetry_events
)
DELETE FROM telemetry_events AS discarded
USING ranked_events
WHERE discarded.id = ranked_events.id
  AND ranked_events.duplicate_rank > 1;

ALTER TABLE telemetry_events ADD COLUMN migrated_id UUID;
UPDATE telemetry_events SET migrated_id = event_id::UUID;
ALTER TABLE telemetry_events ALTER COLUMN migrated_id SET NOT NULL;
ALTER TABLE telemetry_events ALTER COLUMN migrated_id SET DEFAULT gen_random_uuid();
ALTER TABLE telemetry_events ADD COLUMN level VARCHAR(16) NOT NULL DEFAULT 'info';
ALTER TABLE telemetry_events ADD COLUMN value DOUBLE PRECISION;
ALTER TABLE telemetry_events ADD COLUMN message TEXT;

UPDATE telemetry_events
SET tags = tags || jsonb_build_object(
    'sessionId', session_id,
    'userId', user_id,
    'schemaVersion', schema_version,
    'requestId', request_id
);

UPDATE telemetry_events
SET service = CASE service
    WHEN 'frontend' THEN 'backoffice'
    WHEN 'backend' THEN 'api'
    ELSE service
END;

ALTER TABLE telemetry_events DROP CONSTRAINT telemetry_events_pkey;
ALTER TABLE telemetry_events
    DROP COLUMN id,
    DROP COLUMN event_id,
    DROP COLUMN session_id,
    DROP COLUMN user_id,
    DROP COLUMN schema_version,
    DROP COLUMN request_id;
ALTER TABLE telemetry_events RENAME COLUMN migrated_id TO id;
ALTER TABLE telemetry_events ADD CONSTRAINT telemetry_events_pkey PRIMARY KEY (id);
ALTER TABLE telemetry_events ALTER COLUMN tags SET DEFAULT '{}'::JSONB;

COMMIT;