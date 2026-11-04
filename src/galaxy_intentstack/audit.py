"""Atomic SQLite storage; audit records contain commitments, never raw message text."""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sanitize(text):
    # Evidence is content storage, separate from operational audit. Reject common secret shapes.
    if re.search(
        r"(?i)(bearer\s+\S+|sk-(?:proj-)?[a-z0-9_-]{12,}|"
        r"(?:password|api[_-]?key|secret|token)\s*[:=]\s*\S+)",
        text,
    ):
        raise ValueError("Secret-like content must be removed before ingestion")
    return text


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                previous TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, source TEXT NOT NULL,
                type TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL,
                valid INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS claims(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS beliefs(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, subject TEXT NOT NULL,
                value TEXT NOT NULL, claim_id TEXT, status TEXT NOT NULL,
                revision INTEGER NOT NULL, source TEXT NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS belief_subject ON beliefs(session,subject);
            CREATE TABLE IF NOT EXISTS edges(
                parent TEXT NOT NULL REFERENCES beliefs(id),
                child TEXT NOT NULL REFERENCES beliefs(id), PRIMARY KEY(parent,child));
            CREATE TABLE IF NOT EXISTS requests(
                session TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                decision TEXT NOT NULL, PRIMARY KEY(session,id));
            CREATE TABLE IF NOT EXISTS principals(
                id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, capabilities TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sources(
                id TEXT PRIMARY KEY, authority INTEGER NOT NULL, trusted INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS grants(
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, kind TEXT NOT NULL,
                resource TEXT NOT NULL, scope TEXT NOT NULL, session TEXT NOT NULL,
                starts REAL NOT NULL, expires REAL NOT NULL, approval INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0, binding TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS approvals(
                grant_id TEXT PRIMARY KEY REFERENCES grants(id),
                approver TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS policy(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), enabled INTEGER NOT NULL);
            INSERT OR IGNORE INTO policy VALUES(1,1);
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
              BEGIN SELECT RAISE(ABORT,'append-only events'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
              BEGIN SELECT RAISE(ABORT,'append-only events'); END;
            """)

            columns = {row[1] for row in c.execute("PRAGMA table_info(grants)")}
            if "binding" not in columns:
                c.execute("ALTER TABLE grants ADD COLUMN binding TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA synchronous=FULL")
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def event(self, c, kind, payload):
        previous = c.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        encoded = canonical(payload)
        hashed = digest([kind, encoded, previous])
        return c.execute(
            "INSERT INTO events(kind,payload,previous,hash) VALUES(?,?,?,?)",
            (kind, encoded, previous, hashed),
        ).lastrowid

    def verify_audit(self):
        with self.connection() as c:
            previous = "0" * 64
            for row in c.execute("SELECT * FROM events ORDER BY id"):
                if row["previous"] != previous or row["hash"] != digest(
                    [row["kind"], row["payload"], previous]
                ):
                    return False
                previous = row["hash"]
        return True
