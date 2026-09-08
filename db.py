"""
SQLite persistence for the ME Dashboard app.
DB file lives on the Render Persistent Disk (mounted at /var/data in prod;
falls back to a local ./instance/ dir for local dev).
"""

import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "instance", "dashboard.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_type TEXT NOT NULL,     -- 'me' or 'sales'
                month_label TEXT NOT NULL,      -- e.g. 'September 2026'
                month_sort  TEXT NOT NULL,      -- e.g. '2026-09' for ordering
                data_json   TEXT NOT NULL,       -- full parsed clinics/employees data
                goals_json  TEXT,                -- goals used for this report (me only)
                synopses_json TEXT,               -- AI synopses, if generated
                pace REAL,
                days_into INTEGER,
                days_in_month INTEGER,
                end_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (report_type, month_label)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals_history (
                report_type TEXT NOT NULL,
                month_label TEXT NOT NULL,
                goals_json TEXT NOT NULL,
                PRIMARY KEY (report_type, month_label)
            )
        """)


def save_report(report_type, month_label, month_sort, data, goals=None,
                 synopses=None, pace=None, days_into=None, days_in_month=None, end_date=None):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO reports (report_type, month_label, month_sort, data_json, goals_json,
                                  synopses_json, pace, days_into, days_in_month, end_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_type, month_label) DO UPDATE SET
                data_json=excluded.data_json,
                goals_json=excluded.goals_json,
                synopses_json=excluded.synopses_json,
                pace=excluded.pace,
                days_into=excluded.days_into,
                days_in_month=excluded.days_in_month,
                end_date=excluded.end_date,
                updated_at=CURRENT_TIMESTAMP
        """, (report_type, month_label, month_sort, json.dumps(data),
              json.dumps(goals) if goals is not None else None,
              json.dumps(synopses) if synopses is not None else None,
              pace, days_into, days_in_month, end_date))


def get_report(report_type, month_label):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE report_type=? AND month_label=?",
            (report_type, month_label)
        ).fetchone()
        return _row_to_dict(row)


def get_latest_report(report_type):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE report_type=? ORDER BY month_sort DESC LIMIT 1",
            (report_type,)
        ).fetchone()
        return _row_to_dict(row)


def get_previous_report(report_type, before_month_sort):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE report_type=? AND month_sort < ? ORDER BY month_sort DESC LIMIT 1",
            (report_type, before_month_sort)
        ).fetchone()
        return _row_to_dict(row)


def list_months(report_type):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT month_label, month_sort FROM reports WHERE report_type=? ORDER BY month_sort DESC",
            (report_type,)
        ).fetchall()
        return [dict(r) for r in rows]


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    d["data"] = json.loads(d.pop("data_json"))
    d["goals"] = json.loads(d.pop("goals_json")) if d.get("goals_json") else None
    d["synopses"] = json.loads(d.pop("synopses_json")) if d.get("synopses_json") else None
    return d
