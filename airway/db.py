from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS participants(
 id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('unassigned','provisional','confirmed','disputed')),
 created_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS videos(
 id TEXT PRIMARY KEY, source_path TEXT NOT NULL UNIQUE, relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
 bytes INTEGER NOT NULL, decode_status TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments(
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id), participant_id TEXT REFERENCES participants(id),
 status TEXT NOT NULL CHECK(status IN ('unassigned','provisional','confirmed','disputed')),
 camera_view TEXT NOT NULL DEFAULT 'unknown', maneuver TEXT NOT NULL DEFAULT 'unknown', side TEXT,
 source TEXT, reviewer TEXT, created_at TEXT NOT NULL, supersedes_id TEXT REFERENCES assignments(id), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS cases(
 id TEXT PRIMARY KEY, participant_id TEXT REFERENCES participants(id), label TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
 created_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS segments(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, video_id TEXT NOT NULL REFERENCES videos(id), start_ms REAL, end_ms REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS evidence_frames(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, video_id TEXT NOT NULL REFERENCES videos(id), timestamp_ms REAL NOT NULL, path TEXT, sha256 TEXT, coordinate_space TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_runs(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, video_id TEXT NOT NULL REFERENCES videos(id), config_json TEXT NOT NULL, model_hash TEXT, state TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS analysis_artifacts(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE, kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_intervals(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE, reviewer TEXT NOT NULL, neutral_start_ms REAL, neutral_end_ms REAL, maneuver_start_ms REAL, maneuver_end_ms REAL, exclusions_json TEXT NOT NULL DEFAULT '[]', camera_fixed TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id), metric_id TEXT NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_revisions(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, proposal_id TEXT REFERENCES proposals(id), reviewer TEXT NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, supersedes_id TEXT REFERENCES review_revisions(id));
CREATE TABLE IF NOT EXISTS calibrations(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, reference_cm REAL, reference_px REAL, geometry_json TEXT NOT NULL, verified_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements(
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, video_id TEXT REFERENCES videos(id), run_id TEXT REFERENCES analysis_runs(id),
 metric_id TEXT NOT NULL, metric_version TEXT NOT NULL, protocol_id TEXT, source_hash TEXT, timestamp_ms REAL, interval_json TEXT,
 neutral_frame_id TEXT, reference_frame_id TEXT, value REAL, unit TEXT, coordinate_space TEXT, method TEXT NOT NULL,
 endpoints_json TEXT NOT NULL DEFAULT '{}', calibration_id TEXT REFERENCES calibrations(id), quality_json TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL CHECK(state IN ('available','needs_review','unavailable','not_applicable')), reason_codes_json TEXT NOT NULL DEFAULT '[]',
 proposal_id TEXT REFERENCES proposals(id), review_revision_id TEXT REFERENCES review_revisions(id), reviewer TEXT, revised_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS report_snapshots(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, review_revision_id TEXT, snapshot_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, invalidated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_assign_video_active ON assignments(video_id,active);
CREATE INDEX IF NOT EXISTS idx_measure_case_active ON measurements(case_id,active);
"""

def connect(path: str | Path = "data/airway.sqlite3") -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def initialize(path: str | Path = "data/airway.sqlite3") -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)

@contextmanager
def transaction(path: str | Path = "data/airway.sqlite3"):
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
