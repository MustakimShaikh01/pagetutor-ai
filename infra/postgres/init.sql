-- ============================================================
-- PageTutor AI - PostgreSQL Initialization Script
-- Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
--
-- Creates:
--   - Extensions (uuid-ossp, pg_trgm for text search)
--   - Read replica user (for Kubernetes read scaling)
--   - Initial database setup
-- ============================================================

-- UUID generation extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigram index for fast text search (ILIKE queries)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- B-tree index on timestamps (for range queries)
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create read-only user for analytics / replicas
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'pagetutor_readonly') THEN
        CREATE ROLE pagetutor_readonly WITH LOGIN PASSWORD 'readonly_secret';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE pagetutor_db TO pagetutor_readonly;
GRANT USAGE ON SCHEMA public TO pagetutor_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pagetutor_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO pagetutor_readonly;

-- Settings for better performance
ALTER DATABASE pagetutor_db SET log_min_duration_statement = 1000;
ALTER DATABASE pagetutor_db SET idle_in_transaction_session_timeout = '5min';
