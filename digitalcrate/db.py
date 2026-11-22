import sqlite3
from .config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE,
    artist TEXT, album TEXT, title TEXT, genre TEXT, year TEXT,
    duration REAL, mtime REAL,
    status TEXT DEFAULT 'new', error TEXT,
    bpm REAL, bpm_conf REAL, tempo_ok INTEGER,
    key TEXT, scale TEXT, camelot TEXT, key_strength REAL,
    separated INTEGER, clean_frac REAL, vocal_frac REAL,
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    id TEXT PRIMARY KEY,
    track_id INTEGER REFERENCES tracks(id),
    source TEXT, rendered_from TEXT,
    category TEXT, subtype TEXT, kind TEXT,
    start REAL, dur REAL, bpm REAL, bars INTEGER,
    key TEXT, scale TEXT, camelot TEXT, key_strength REAL, key_from TEXT, note TEXT,
    chroma TEXT, centroid REAL, flatness REAL, pratio REAL, dominance REAL, drum_leak REAL,
    loudness REAL, quality REAL,
    clap BLOB, type_probs TEXT, mood_sims TEXT, instrument TEXT,
    path TEXT, env TEXT, tags TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS samples_track ON samples(track_id);
CREATE INDEX IF NOT EXISTS samples_cat ON samples(category);
-- side tables, created up front: other modules open their own connections, and a CREATE there while
-- the main connection holds a write transaction fails with "database is locked" on a fresh library
CREATE TABLE IF NOT EXISTS overrides (sample_id TEXT PRIMARY KEY, category TEXT, subtype TEXT,
    old_category TEXT, old_subtype TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS variants (sample_id TEXT, idx INTEGER, technique TEXT,
    chain TEXT, seed INTEGER, path TEXT, PRIMARY KEY(sample_id, idx));
CREATE TABLE IF NOT EXISTS favorites (path TEXT PRIMARY KEY, sample_id TEXT,
    label TEXT, added_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sketches (name TEXT PRIMARY KEY, state TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events (ts REAL, path TEXT, sample_id TEXT, type TEXT, value REAL, context TEXT);
CREATE INDEX IF NOT EXISTS events_path ON events(path);
CREATE TABLE IF NOT EXISTS embeddings (path TEXT PRIMARY KEY, clap BLOB);
CREATE TABLE IF NOT EXISTS shootout_votes (clip TEXT, sample TEXT, task TEXT, method TEXT,
    material TEXT, rating INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS yt_scout (id TEXT PRIMARY KEY, query TEXT, url TEXT, title TEXT,
    channel TEXT, duration REAL, views INTEGER, score REAL, vocal REAL, neg REAL, taste REAL,
    best_at REAL, snippet TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS pair_votes (trial TEXT PRIMARY KEY, rating INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS drum_labels (sample_id TEXT PRIMARY KEY, pieces TEXT, ts REAL);
"""


def _wal(con):
    """Write-ahead logging: the app reads while mining runs and analyses write, instead of waiting on their locks.
    It's a setting of the database file, so this switches it once; commits then only need synchronous=NORMAL."""
    try:
        if con.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:  # busy right now: try again on the next connection
        pass


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.row_factory = sqlite3.Row
    _wal(con)
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    for c in ("env", "tags", "parent_id", "root_id", "ops"):
        if c not in cols:
            con.execute(f"ALTER TABLE samples ADD COLUMN {c} TEXT")
    tcols = {r[1] for r in con.execute("PRAGMA table_info(tracks)")}
    for c, t in (("policy", "TEXT"), ("scout_vocal", "REAL"), ("scout_sparse", "REAL"),
                 ("scout_ref", "REAL"), ("scout_ref_match", "TEXT"), ("scout_done", "INTEGER"),
                 ("scout_pad", "REAL"), ("scout_score", "REAL")):
        if c not in tcols:
            con.execute(f"ALTER TABLE tracks ADD COLUMN {c} {t}")
    return con
