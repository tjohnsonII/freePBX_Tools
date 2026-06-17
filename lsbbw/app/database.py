import sqlite3
import os

DB_PATH = os.environ.get("LSBBW_DB", "/var/www/lsbbw/lsbbw.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT,
            category    TEXT    DEFAULT 'General',
            type        TEXT    NOT NULL CHECK(type IN ('embed','upload')),
            embed_url   TEXT,
            file_path   TEXT,
            thumbnail   TEXT,
            submitter   TEXT    DEFAULT 'Anonymous',
            status      TEXT    DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            views       INTEGER DEFAULT 0,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_videos_status    ON videos(status);
        CREATE INDEX IF NOT EXISTS idx_videos_created   ON videos(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_videos_category  ON videos(category);

        CREATE TABLE IF NOT EXISTS admin_sessions (
            token      TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
