-- VoiceMode Telemetry D1 Database Schema
--
-- This schema stores telemetry events with privacy protections:
-- - IP addresses are hashed before storage
-- - Event data is stored as JSON for flexibility
-- - Automatic cleanup of old events via scheduled worker

-- Main events table
CREATE TABLE IF NOT EXISTS events (
    -- Event identification
    event_id TEXT PRIMARY KEY,              -- SHA-256 hash from client (telemetry_id + timestamp)
    telemetry_id TEXT NOT NULL,             -- Anonymous UUID from client device

    -- Timestamps
    timestamp TEXT NOT NULL,                -- Event timestamp (ISO 8601 from client)
    created_at TEXT NOT NULL,               -- Server receipt time (ISO 8601)

    -- Event data (stored as JSON for flexibility)
    environment TEXT NOT NULL,              -- JSON: {os, version, installation_method, mcp_host, execution_source}
    usage TEXT NOT NULL,                    -- JSON: {total_sessions, duration_distribution, provider_usage, etc.}

    -- Privacy-preserving metadata
    client_ip_hash TEXT NOT NULL           -- SHA-256 hash of client IP (for rate limiting only)
);

-- Indexes for efficient queries

-- Index for querying events by telemetry_id (user retention analysis)
CREATE INDEX IF NOT EXISTS idx_events_telemetry_id
ON events(telemetry_id);

-- Index for querying events by timestamp (DAU, time-series analysis)
CREATE INDEX IF NOT EXISTS idx_events_timestamp
ON events(timestamp);

-- Index for cleanup queries (finding old events)
CREATE INDEX IF NOT EXISTS idx_events_created_at
ON events(created_at);

-- Composite index for user activity over time
CREATE INDEX IF NOT EXISTS idx_events_telemetry_timestamp
ON events(telemetry_id, timestamp);

-- Notes on schema design:
--
-- 1. Event ID is the primary key to enforce idempotency - duplicate
--    submissions with the same event_id will be rejected by the database.
--
-- 2. We store environment and usage as JSON TEXT rather than normalized
--    tables because:
--    - The schema may evolve over time
--    - D1 supports JSON functions for querying (json_extract)
--    - Simplifies inserts and reduces table complexity
--    - VoiceMode is early stage - premature optimization avoided
--
-- 3. IP addresses are hashed before storage and only used for rate limiting.
--    We cannot reverse the hash to identify users.
--
-- 4. The timestamp column uses the client-provided timestamp (privacy: no
--    server timezone leak), while created_at uses server time for ordering
--    and cleanup.
--
-- 5. No foreign keys or complex constraints - keep it simple for MVP.
--
-- Example queries:
--
-- Daily Active Users (DAU):
--   SELECT COUNT(DISTINCT telemetry_id) as dau
--   FROM events
--   WHERE DATE(timestamp) = DATE('now');
--
-- Sessions by OS:
--   SELECT json_extract(environment, '$.os') as os,
--          SUM(json_extract(usage, '$.total_sessions')) as sessions
--   FROM events
--   GROUP BY os;
--
-- Provider usage over time:
--   SELECT DATE(timestamp) as date,
--          json_extract(usage, '$.provider_usage.tts') as tts_providers
--   FROM events
--   ORDER BY date DESC;
--
-- Retention (7-day):
--   WITH first_seen AS (
--     SELECT telemetry_id, MIN(DATE(timestamp)) as first_date
--     FROM events
--     GROUP BY telemetry_id
--   )
--   SELECT
--     COUNT(DISTINCT e.telemetry_id) as retained_users
--   FROM events e
--   JOIN first_seen f ON e.telemetry_id = f.telemetry_id
--   WHERE DATE(e.timestamp) = DATE(f.first_date, '+7 days');
