-- =============================================================================
-- TAMS — complete PostgreSQL schema (Railway / local)
-- Matches app/models/entities.py
--
-- Usage (Railway Query / psql):
--   \i scripts/schema.sql
-- Or paste into Railway Postgres → Query
--
-- Note: On Railway the database "railway" already exists — skip CREATE DATABASE.
-- =============================================================================

-- CREATE DATABASE tams_db
--   WITH OWNER = postgres
--        ENCODING = 'UTF8'
--        TEMPLATE = template0;
-- \c tams_db

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Optional (not required — geometry is JSONB):
-- CREATE EXTENSION IF NOT EXISTS "postgis";

-- ---------------------------------------------------------------------------
-- Lookup / catalog
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS asset_types (
    asset_type_id      SERIAL PRIMARY KEY,
    type_code          VARCHAR(50)  NOT NULL UNIQUE,
    type_name          VARCHAR(200) NOT NULL,
    category           VARCHAR(50)  NOT NULL,
    description        VARCHAR(500),
    default_parameters JSONB,
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS substations (
    substation_id   SERIAL PRIMARY KEY,
    substation_code VARCHAR(50)  NOT NULL UNIQUE,
    substation_name VARCHAR(200) NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    voltage_level   VARCHAR(20),
    region          VARCHAR(100),
    status          VARCHAR(20)  NOT NULL DEFAULT 'InService'
);

CREATE TABLE IF NOT EXISTS roles (
    role_id     SERIAL PRIMARY KEY,
    role_code   VARCHAR(50)  NOT NULL UNIQUE,
    role_name   VARCHAR(100) NOT NULL,
    description VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS users (
    user_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    department   VARCHAR(100),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_role_id SERIAL PRIMARY KEY,
    user_id      UUID    NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    role_id      INTEGER NOT NULL REFERENCES roles (role_id) ON DELETE CASCADE,
    CONSTRAINT uq_user_roles_user_role UNIQUE (user_id, role_id)
);

-- ---------------------------------------------------------------------------
-- Core assets
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assets (
    asset_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_code           VARCHAR(50)  NOT NULL UNIQUE,
    name                 VARCHAR(255) NOT NULL,
    asset_type_id        INTEGER      NOT NULL REFERENCES asset_types (asset_type_id),
    parent_asset_id      UUID         REFERENCES assets (asset_id),
    substation_id        INTEGER      REFERENCES substations (substation_id),
    manufacturer         VARCHAR(200),
    serial_number        VARCHAR(100),
    installation_date    DATE,
    warranty_expiry_date DATE,
    voltage_level_kv     DOUBLE PRECISION,
    capacity_rating      DOUBLE PRECISION,
    capacity_unit        VARCHAR(20),
    latitude             DOUBLE PRECISION,
    longitude            DOUBLE PRECISION,
    elevation_m          DOUBLE PRECISION,
    status               VARCHAR(20)  NOT NULL DEFAULT 'InService',
    criticality          VARCHAR(20)  NOT NULL DEFAULT 'Medium',
    qr_code_url          VARCHAR(500),
    tags                 JSONB,
    metadata             JSONB,
    geometry             JSONB,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_assets_status_criticality ON assets (status, criticality);
CREATE INDEX IF NOT EXISTS ix_assets_substation ON assets (substation_id);
CREATE INDEX IF NOT EXISTS ix_assets_parent ON assets (parent_asset_id);
CREATE INDEX IF NOT EXISTS ix_assets_type ON assets (asset_type_id);
CREATE INDEX IF NOT EXISTS ix_assets_lat_lon ON assets (latitude, longitude);

-- ---------------------------------------------------------------------------
-- Sensors / alarms / health / maintenance / inspections
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sensors (
    sensor_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id             UUID         NOT NULL REFERENCES assets (asset_id) ON DELETE CASCADE,
    sensor_code          VARCHAR(50)  NOT NULL UNIQUE,
    sensor_type          VARCHAR(50)  NOT NULL,
    parameter            VARCHAR(100) NOT NULL,
    unit                 VARCHAR(20)  NOT NULL,
    min_value            DOUBLE PRECISION,
    max_value            DOUBLE PRECISION,
    alarm_high_threshold DOUBLE PRECISION,
    alarm_low_threshold  DOUBLE PRECISION,
    protocol             VARCHAR(20),
    iot_device_id        VARCHAR(200),
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alarms (
    alarm_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id         UUID         NOT NULL REFERENCES assets (asset_id) ON DELETE CASCADE,
    sensor_id        UUID         REFERENCES sensors (sensor_id),
    alarm_code       VARCHAR(50)  NOT NULL,
    title            VARCHAR(200) NOT NULL,
    description      VARCHAR(1000),
    severity         VARCHAR(20)  NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'Active',
    trigger_value    DOUBLE PRECISION,
    threshold_value  DOUBLE PRECISION,
    generated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    acknowledged_at  TIMESTAMPTZ,
    acknowledged_by  UUID,
    closed_at        TIMESTAMPTZ,
    closed_by        UUID,
    closure_notes    VARCHAR(1000),
    escalation_level INTEGER      NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_alarms_status_severity
    ON alarms (status, severity, generated_at);

CREATE TABLE IF NOT EXISTS health_scores (
    health_score_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id               UUID             NOT NULL REFERENCES assets (asset_id) ON DELETE CASCADE,
    health_score           DOUBLE PRECISION NOT NULL,
    condition_score        INTEGER          NOT NULL,
    risk_score             DOUBLE PRECISION NOT NULL,
    rul_months             DOUBLE PRECISION,
    age_factor              DOUBLE PRECISION,
    loading_factor          DOUBLE PRECISION,
    inspection_factor       DOUBLE PRECISION,
    failure_history_factor  DOUBLE PRECISION,
    sensor_health_factor    DOUBLE PRECISION,
    criticality_factor      DOUBLE PRECISION,
    computed_at            TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    model_version          VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS ix_health_scores_asset ON health_scores (asset_id, computed_at DESC);

CREATE TABLE IF NOT EXISTS work_orders (
    work_order_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_order_number VARCHAR(20)  NOT NULL UNIQUE,
    asset_id          UUID         NOT NULL REFERENCES assets (asset_id) ON DELETE CASCADE,
    maintenance_type  VARCHAR(10)  NOT NULL,
    priority          VARCHAR(20)  NOT NULL DEFAULT 'Medium',
    status            VARCHAR(20)  NOT NULL DEFAULT 'Draft',
    description       TEXT,
    assigned_crew     VARCHAR(200),
    scheduled_start   TIMESTAMPTZ,
    scheduled_end     TIMESTAMPTZ,
    actual_start      TIMESTAMPTZ,
    actual_end        TIMESTAMPTZ,
    estimated_cost    DOUBLE PRECISION,
    actual_cost       DOUBLE PRECISION,
    labor_hours       DOUBLE PRECISION,
    root_cause        VARCHAR(500),
    completion_notes  TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inspections (
    inspection_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID        NOT NULL REFERENCES assets (asset_id) ON DELETE CASCADE,
    inspection_type VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
    inspector_name  VARCHAR(200),
    scheduled_date  TIMESTAMPTZ,
    completed_date  TIMESTAMPTZ,
    overall_score   DOUBLE PRECISION,
    summary         TEXT,
    report_pdf_url  VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID,
    action       VARCHAR(50) NOT NULL,
    entity_type  VARCHAR(50) NOT NULL,
    entity_id    UUID,
    old_values   JSONB,
    new_values   JSONB,
    ip_address   VARCHAR(45),
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_timestamp ON audit_logs (timestamp);

-- ---------------------------------------------------------------------------
-- Seed reference data (safe to re-run)
-- ---------------------------------------------------------------------------

INSERT INTO asset_types (type_code, type_name, category) VALUES
    ('TOWER', 'Transmission Tower', 'Tower'),
    ('LINE', 'Transmission Line', 'Line'),
    ('SUBSTATION', 'Substation', 'Substation'),
    ('TRANSFORMER', 'Power Transformer', 'Transformer'),
    ('BREAKER', 'Circuit Breaker', 'Breaker'),
    ('RELAY', 'Protection Relay', 'Relay')
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO roles (role_code, role_name, description) VALUES
    ('ADMIN', 'Administrator', 'Full system access'),
    ('OPS_ENGINEER', 'Operations Engineer', 'Monitoring and alarms'),
    ('MAINT_ENGINEER', 'Maintenance Engineer', 'Work orders and maintenance'),
    ('ASSET_ENGINEER', 'Asset Engineer', 'Asset registry and health'),
    ('FIELD_TECH', 'Field Technician', 'Inspections and field work'),
    ('EXECUTIVE', 'Executive Management', 'Dashboards and reports'),
    ('AUDITOR', 'Auditor', 'Read-only audit access')
ON CONFLICT (role_code) DO NOTHING;

INSERT INTO users (email, display_name, department)
VALUES ('admin@tams.local', 'TAMS Administrator', 'IT')
ON CONFLICT (email) DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.user_id, r.role_id
FROM users u
CROSS JOIN roles r
WHERE u.email = 'admin@tams.local'
  AND r.role_code = 'ADMIN'
ON CONFLICT ON CONSTRAINT uq_user_roles_user_role DO NOTHING;
