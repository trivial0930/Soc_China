-- Management-app backend store (SQLite). Matches app/API_SPEC.md v1.
-- All timestamps that originate on the robot stay as-is (ISO string or unix float);
-- received_at is the backend's own ISO8601 ingest time.

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    timestamp       TEXT,                 -- ISO8601 with tz (robot event time)
    received_at     TEXT,                 -- ISO8601 (backend ingest time)
    station_id      TEXT,
    source          TEXT,
    event_type      TEXT,
    severity        TEXT,                 -- info|warning|critical
    confidence      REAL,
    summary         TEXT,
    image           TEXT DEFAULT '',      -- evidence image filename ('' if none)
    robot_task      TEXT DEFAULT '',
    voice_prompt    TEXT DEFAULT '',
    reported_to_admin INTEGER DEFAULT 0,
    handled         INTEGER DEFAULT 0,
    handled_at      TEXT,
    handled_note    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_station  ON events(station_id);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_time     ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_handled  ON events(handled);

-- L2 brief, 1:1 with an event (event_id may arrive before/after the event).
CREATE TABLE IF NOT EXISTS briefs (
    event_id           TEXT PRIMARY KEY,
    explanation        TEXT,
    confirmed_severity TEXT,
    actions            TEXT,              -- JSON array
    escalate_to_cloud  INTEGER DEFAULT 0,
    received_at        TEXT
);

CREATE TABLE IF NOT EXISTS workstation_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id   TEXT,
    entered_at   REAL,                    -- unix seconds
    left_at      REAL,
    snapshots    TEXT,                    -- JSON array of image filenames
    note         TEXT DEFAULT '',
    acceptance_hint TEXT DEFAULT '',
    received_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_rec_station ON workstation_records(station_id, entered_at);

CREATE TABLE IF NOT EXISTS acceptance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id  TEXT,
    verdict     TEXT,                     -- 合格|需整理|存在安全隐患
    severity    TEXT,
    problems    TEXT,                     -- JSON array
    report_id   INTEGER,
    received_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_acc_station ON acceptance(station_id);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT,
    report_type   TEXT,
    verdict       TEXT,
    severity      TEXT,
    event_ids     TEXT,                   -- JSON array
    body_markdown TEXT,
    created_at    TEXT,
    received_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type);

-- App -> robot command queue (downlink). Robot polls pending, acks, posts result.
CREATE TABLE IF NOT EXISTS commands (
    command_id   TEXT PRIMARY KEY,        -- cmd-YYYYMMDD-HHMMSS-NNNN
    type         TEXT NOT NULL,           -- see app/API_SPEC.md command types
    params       TEXT,                    -- JSON object
    status       TEXT NOT NULL,           -- queued|sent|done|failed|canceled
    issued_by    TEXT DEFAULT 'app',
    result       TEXT DEFAULT '',         -- robot receipt (JSON/text), '' until reported
    created_at   TEXT,                    -- ISO8601 with tz
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
CREATE INDEX IF NOT EXISTS idx_commands_type   ON commands(type);

CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    category    TEXT,                     -- large|small
    station_id  TEXT DEFAULT '',
    area        TEXT DEFAULT '',
    cabinet     TEXT DEFAULT '',
    drawer      TEXT DEFAULT '',
    box         TEXT DEFAULT '',
    quantity    INTEGER DEFAULT 0,
    note        TEXT DEFAULT '',
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name);
CREATE INDEX IF NOT EXISTS idx_assets_cat  ON assets(category);
