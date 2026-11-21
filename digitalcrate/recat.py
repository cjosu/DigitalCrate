"""Manual recategorisation: move/rename the file, update DB + favourites, and remember the override
so reprocessing / reclassify never undo it. Overrides are keyed by sample id, which is a stable hash of
(track, source, start, kind)."""
import os
import shutil
from pathlib import Path

from . import config as C
from .db import connect

SUBTYPES = {
    "Vocals": ["Phrases", "Chops", "Choir & Group", "Spoken"],
    "Vocal Atmospheres": ["Loops", "Free", "One-Shots"],
    "Pads & Atmospheres": ["Loops", "Free", "One-Shots"],
    "Chords & Keys": ["Loops", "Free", "One-Shots"],
    "Melodies & Leads": ["Loops", "Free", "One-Shots"],
    "Textures & Field": ["Loops", "Free", "One-Shots"],
    "Bass & Sub": ["Loops", "Free", "One-Shots"],
}
from .percussion import SUBTYPES as _PS
SUBTYPES["Percussion"] = _PS


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS overrides (sample_id TEXT PRIMARY KEY, category TEXT, subtype TEXT,
                   old_category TEXT, old_subtype TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def overrides():
    return {r["sample_id"]: (r["category"], r["subtype"]) for r in _db().execute("SELECT * FROM overrides")}


def new_path(row, cat, sub):
    from .process import SUBTYPE_PREFIX
    old = Path(row["path"])
    if old.parts[0] == "Edits":
        return Path("Edits") / cat / old.name
    if cat == "Percussion":
        from .percussion import PREFIX
        base = Path("_Reference") if old.parts[0] == "_Reference" else Path()
        pref = PREFIX[sub] + (f"-Loop{row['bars']}" if row["kind"] == "loop" and row["bars"] else "")
        return base / cat / sub / (pref + "_" + old.name.split("_", 1)[1])
    if old.parts[0] == "Edits":
        return Path("Edits") / cat / old.name
    base = Path("_Reference") if old.parts[0] == "_Reference" else Path()
    pref = SUBTYPE_PREFIX.get((cat, sub), SUBTYPE_PREFIX.get(cat, "Smp"))
    if row["kind"] == "loop" and row["bars"]:
        pref += f"-Loop{row['bars']}"
    return base / cat / sub / (pref + "_" + old.name.split("_", 1)[1])


def move_sample(con, row, cat, sub):
    """Move one sample's file + references. Returns new relative path."""
    old_rel, new_rel = row["path"], str(new_path(row, cat, sub))
    if new_rel != old_rel:
        src, dst = C.LIB_ROOT / old_rel, C.LIB_ROOT / new_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.move(str(src), str(dst))
        # favourites: DB row + hardlink folder
        has = lambda t: con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()
        if has("favorites"):
            fav = con.execute("SELECT * FROM favorites WHERE path=?", (old_rel,)).fetchone()
            if fav:
                from .serve import _fav_target
                _fav_target(old_rel).unlink(missing_ok=True)   # old hardlink in Favorites/<old cat>/
                link = _fav_target(new_rel)
                link.parent.mkdir(parents=True, exist_ok=True)
                if not link.exists():
                    try:
                        os.link(dst, link)
                    except OSError:
                        shutil.copy2(dst, link)
                con.execute("UPDATE favorites SET path=? WHERE path=?", (new_rel, old_rel))
        if has("events"):
            con.execute("UPDATE events SET path=? WHERE path=?", (new_rel, old_rel))
    con.execute("UPDATE samples SET category=?, subtype=?, path=? WHERE id=?", (cat, sub, new_rel, row["id"]))
    return new_rel


def recategorise(sample_id, cat, sub):
    if cat not in SUBTYPES or sub not in SUBTYPES[cat]:
        raise ValueError(f"unknown category/subtype {cat} / {sub}")
    con = _db()
    row = con.execute("SELECT * FROM samples WHERE id=?", (sample_id,)).fetchone()
    if row is None:
        raise ValueError("no such sample")
    con.execute("""INSERT INTO overrides(sample_id, category, subtype, old_category, old_subtype) VALUES (?,?,?,?,?)
                   ON CONFLICT(sample_id) DO UPDATE SET category=excluded.category, subtype=excluded.subtype""",
                (sample_id, cat, sub, row["category"], row["subtype"]))
    new_rel = move_sample(con, row, cat, sub)
    con.commit()
    return dict(id=sample_id, category=cat, subtype=sub, path=new_rel)
