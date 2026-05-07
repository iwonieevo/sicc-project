CREATE EXTENSION IF NOT EXISTS pgcrypto;

--====================================================================
CREATE TABLE IF NOT EXISTS users (
    id               BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    email            TEXT UNIQUE NOT NULL,
    hashed_password  TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted       BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS devices (
    id               BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name             TEXT UNIQUE NOT NULL,
    status           TEXT NOT NULL DEFAULT 'offline',
    last_seen        TIMESTAMPTZ,
    registered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted       BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS commands (
    id               BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name             TEXT UNIQUE NOT NULL,
    description      TEXT,
    python_code      TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted       BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS command_parameters (
    id               BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    command_id       BIGINT NOT NULL REFERENCES commands(id) ON DELETE RESTRICT,
    name             TEXT NOT NULL,
    param_type       TEXT NOT NULL DEFAULT 'text',
    is_required      BOOLEAN NOT NULL DEFAULT TRUE,
    default_value    TEXT,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted       BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (command_id, name)
);

CREATE TABLE IF NOT EXISTS command_queue (
    id               BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    device_id        BIGINT NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
    command_id       BIGINT NOT NULL REFERENCES commands(id) ON DELETE RESTRICT,
    parameters       JSONB,
    queued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS command_executions (
    queue_id         BIGINT PRIMARY KEY REFERENCES command_queue(id) ON DELETE RESTRICT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS command_results (
    queue_id         BIGINT PRIMARY KEY REFERENCES command_queue(id) ON DELETE RESTRICT,
    is_error         BOOLEAN NOT NULL,
    result           TEXT,
    finished_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW v_command_log AS
SELECT
    q.id               AS queue_id,
    q.device_id,
    q.command_id,
    q.parameters,
    q.queued_at,
    e.started_at,
    r.finished_at,
    r.is_error,
    r.result,
    CASE
        WHEN r.queue_id IS NOT NULL AND r.is_error = FALSE THEN 'done'
        WHEN r.queue_id IS NOT NULL AND r.is_error = TRUE  THEN 'error'
        WHEN e.queue_id IS NOT NULL                        THEN 'running'
        ELSE                                                    'queued'
    END                 AS status
FROM      command_queue      q
LEFT JOIN command_executions e ON e.queue_id = q.id
LEFT JOIN command_results    r ON r.queue_id = q.id;

--====================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id               BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    table_name       TEXT NOT NULL,
    operation        TEXT NOT NULL,
    row_id           BIGINT,
    old_data         JSONB,
    new_data         JSONB,
    changed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION fn_audit_log()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_log (table_name, operation, row_id, old_data, new_data)
    VALUES (
        TG_TABLE_NAME,
        TG_OP,
        CASE TG_OP WHEN 'DELETE' THEN OLD.id ELSE NEW.id END,
        CASE TG_OP WHEN 'INSERT' THEN NULL ELSE to_jsonb(OLD) END,
        CASE TG_OP WHEN 'DELETE' THEN NULL ELSE to_jsonb(NEW) END
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_audit_users
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_audit_log();

CREATE TRIGGER trg_audit_devices
    AFTER INSERT OR UPDATE OR DELETE ON devices
    FOR EACH ROW EXECUTE FUNCTION fn_audit_log();

CREATE TRIGGER trg_audit_commands
    AFTER INSERT OR UPDATE OR DELETE ON commands
    FOR EACH ROW EXECUTE FUNCTION fn_audit_log();

CREATE TRIGGER trg_audit_command_parameters
    AFTER INSERT OR UPDATE OR DELETE ON command_parameters
    FOR EACH ROW EXECUTE FUNCTION fn_audit_log();

CREATE TRIGGER trg_audit_command_queue
    AFTER INSERT OR UPDATE OR DELETE ON command_queue
    FOR EACH ROW EXECUTE FUNCTION fn_audit_log();

--====================================================================
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_updated_at_users
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_updated_at_devices
    BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_updated_at_commands
    BEFORE UPDATE ON commands
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_updated_at_command_parameters
    BEFORE UPDATE ON command_parameters
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();