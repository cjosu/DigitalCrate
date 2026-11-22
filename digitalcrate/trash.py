"""Deleting samples you don't want, with undo.

A deleted sample leaves the library and the page, but nothing is lost yet: its file (and its variations' files) move to
_data/trash/, and its database rows are kept in the `trash` table, so `restore` puts everything back as it was.
`digitalcrate trash --empty` deletes the trashed files for good.

What's removed with a sample: its favourite (and the Favorites/ link), variations, category correction, lyrics and
drum labels. Your listening history is kept (it's only a log). Edits you made from it are separate samples and stay. Songs aren't re-mined unless you ask
for --reprocess, so deleted cuts don't come back on their own.
"""
import json
import shutil
import time

from . import config as C
from .db import connect

TRASH = C.DATA_DIR / "trash"
# tables holding per-sample rows, and the column that points at the sample
SIDE = [("favorites", "path"), ("collection_items", "path"), ("variants", "sample_id"), ("overrides", "sample_id"), ("words", "sample_id"),
        ("drum_labels", "sample_id"), ("embeddings", "path")]


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS trash (sample_id TEXT PRIMARY KEY, path TEXT, track_id INTEGER,
                   rows TEXT, files TEXT, deleted_at REAL)""")
    return con


def _has(con, t):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def _move(rel, to_trash):
    a, b = (C.LIB_ROOT / rel, TRASH / rel) if to_trash else (TRASH / rel, C.LIB_ROOT / rel)
    if a.exists():
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(a), str(b))
        return True
    return False


def delete(ids):
    """Move samples to the trash. Returns {deleted: [ids], paths: [paths]}."""
    from .serve import _fav_target
    from .taste import log_event
    con = _db()
    done, paths = [], []
    for sid in ids:
        s = con.execute("SELECT * FROM samples WHERE id=?", (sid,)).fetchone()
        if s is None:
            continue
        rows = {"samples": [dict(s)]}
        for t, col in SIDE:
            if _has(con, t):
                key = s["path"] if col == "path" else sid
                rows[t] = [dict(r) for r in con.execute(f"SELECT * FROM {t} WHERE {col}=?", (key,))]
                con.execute(f"DELETE FROM {t} WHERE {col}=?", (key,))
        files = [s["path"]] + [v["path"] for v in rows.get("variants", []) if v.get("path")]
        files = [f for f in files if _move(f, True)]
        if rows.get("favorites"):
            _fav_target(s["path"]).unlink(missing_ok=True)
        from .collections_ import _link
        for c in rows.get("collection_items", []):  # its links in Collections/ (a hardlink would keep it audible there)
            _link(c["collection"], s["path"]).unlink(missing_ok=True)
        con.execute("DELETE FROM samples WHERE id=?", (sid,))
        con.execute("INSERT OR REPLACE INTO trash VALUES (?,?,?,?,?,?)",
                    (sid, s["path"], s["track_id"], json.dumps(rows, default=_blob), json.dumps(files), time.time()))
        con.commit()
        log_event(s["path"], "delete", 1, sid)
        done.append(sid); paths.append(s["path"])
    return dict(deleted=done, paths=paths)


def _blob(x):
    if isinstance(x, (bytes, memoryview)):
        return {"__hex__": bytes(x).hex()}
    raise TypeError(type(x))


def _unblob(d):
    return {k: bytes.fromhex(v["__hex__"]) if isinstance(v, dict) and "__hex__" in v else v for k, v in d.items()}


def restore(ids):
    """Put trashed samples back: files, rows, favourites."""
    from .serve import set_fav
    con = _db()
    back = []
    for sid in ids:
        t = con.execute("SELECT * FROM trash WHERE sample_id=?", (sid,)).fetchone()
        if t is None:
            continue
        for f in json.loads(t["files"]):
            _move(f, False)
        rows = json.loads(t["rows"])
        for table, rs in rows.items():
            for r in map(_unblob, rs):
                cols = ",".join(r)
                con.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({','.join('?' * len(r))})", list(r.values()))
        con.execute("DELETE FROM trash WHERE sample_id=?", (sid,))
        con.commit()
        for fav in rows.get("favorites", []):  # re-make the Favorites/ link
            set_fav(fav["path"], True, fav.get("sample_id"), fav.get("label"))
        from .collections_ import add as collect
        for c in rows.get("collection_items", []):  # and the Collections/ links
            collect(c["collection"], c["path"], c.get("sample_id"))
        con.execute("UPDATE events SET value=0 WHERE sample_id=? AND type='delete'", (sid,))
        con.commit()
        back.append(sid)
    return dict(restored=back)


def summary():
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM trash").fetchone()[0]
    size = sum(f.stat().st_size for f in TRASH.rglob("*") if f.is_file()) if TRASH.exists() else 0
    return dict(n=n, mb=round(size / 1e6, 1))


def empty():
    """Delete trashed samples for good: their files, and the saved rows that made undo possible."""
    s = summary()
    if TRASH.exists():
        shutil.rmtree(TRASH)
    con = _db()
    con.execute("DELETE FROM trash")
    con.commit()
    return s
