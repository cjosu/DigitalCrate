"""Collections: named lists of samples for a project you have in mind (📁 on any sample; the Favorites tab's 📁 view).

A sample can be in any number of collections. Each collection is also a folder of hardlinks,
SampleLibrary/Collections/<name>/<category>/<file>, like Favorites/, so you can browse it in Ableton without exporting
(no extra disk space). The taste model counts adding a sample to a collection as a like, a bit less than a ★.
"""
import os
import re
import shutil
import time
from pathlib import Path

from . import config as C
from .db import connect

DIR = C.LIB_ROOT / "Collections"


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS collections (name TEXT PRIMARY KEY, created_at REAL, note TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS collection_items (collection TEXT, path TEXT, sample_id TEXT, added_at REAL,
                   PRIMARY KEY (collection, path))""")
    return con


def _clean(name):
    name = re.sub(r"[/\\:*?\"<>|]+", " ", (name or "").strip())[:60].strip()
    if not name:
        raise ValueError("give the collection a name")
    return name


def _link(name, rel):
    """Folder view: Collections/<name>/<category>/<file> (a hardlink, like Favorites/)."""
    p = Path(rel)
    return DIR / name / (p.parts[0] if len(p.parts) > 1 else "Misc") / p.name


def listing():
    con = _db()
    items = {}
    for r in con.execute("SELECT collection, path FROM collection_items ORDER BY added_at"):
        items.setdefault(r[0], []).append(r[1])
    out = []
    for r in con.execute("SELECT name, created_at FROM collections ORDER BY created_at DESC"):
        out.append(dict(name=r[0], paths=items.get(r[0], []), n=len(items.get(r[0], []))))
    return out


def create(name):
    name = _clean(name)
    con = _db()
    con.execute("INSERT OR IGNORE INTO collections VALUES (?,?,?)", (name, time.time(), None))
    con.commit()
    return dict(name=name)


def add(name, rel, sample_id=None):
    name = _clean(name)
    src = (C.LIB_ROOT / rel).resolve()
    if C.LIB_ROOT.resolve() not in src.parents or not src.exists():
        raise ValueError("not a library file")
    if rel.startswith("_Reference/"):
        raise ValueError("reference-only sounds (style references) aren't sampled, so they can't be collected")
    create(name)
    con = _db()
    con.execute("INSERT OR IGNORE INTO collection_items VALUES (?,?,?,?)", (name, rel, sample_id, time.time()))
    con.commit()
    dst = _link(name, rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    from .taste import log_event
    log_event(rel, "collect", 1, sample_id, dict(collection=name))
    return dict(ok=True)


def remove(name, rel):
    con = _db()
    con.execute("DELETE FROM collection_items WHERE collection=? AND path=?", (name, rel))
    con.commit()
    dst = _link(name, rel)
    dst.unlink(missing_ok=True)
    for d in (dst.parent, dst.parent.parent):
        if d.exists() and d != DIR and not any(d.iterdir()):
            d.rmdir()
    return dict(ok=True)


def delete(name):
    """The collection and its folder of links go; the samples themselves stay where they are."""
    con = _db()
    con.execute("DELETE FROM collection_items WHERE collection=?", (name,))
    con.execute("DELETE FROM collections WHERE name=?", (name,))
    con.commit()
    d = DIR / _clean(name)
    if d.exists() and DIR.resolve() in d.resolve().parents:
        shutil.rmtree(d)
    return dict(ok=True)


def rename(old, new):
    new = _clean(new)
    con = _db()
    if con.execute("SELECT 1 FROM collections WHERE name=?", (new,)).fetchone():
        raise ValueError(f"there's already a collection called {new}")
    con.execute("UPDATE collections SET name=? WHERE name=?", (new, old))
    con.execute("UPDATE collection_items SET collection=? WHERE collection=?", (new, old))
    con.commit()
    if (DIR / old).exists():
        (DIR / old).rename(DIR / new)
    return dict(name=new)


def members(con=None):
    """paths in any collection (the taste model's 'collected' likes)."""
    con = con or _db()
    try:
        return {r[0] for r in con.execute("SELECT DISTINCT path FROM collection_items")}
    except Exception:
        return set()
