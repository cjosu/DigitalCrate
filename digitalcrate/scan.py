"""Catalogue the music library into SQLite (tags only, fast)."""
import os
from pathlib import Path
from mutagen import File as MFile
from tqdm import tqdm

from .config import MUSIC_ROOT, AUDIO_EXTS
from .db import connect


def _tag(tags, key):
    v = tags.get(key) if tags else None
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v) if v is not None else None


def scan(root=MUSIC_ROOT):
    con = connect()
    known = {r["path"]: r["mtime"] for r in con.execute("SELECT path, mtime FROM tracks")}
    files = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".")]
        for f in fn:
            if f.startswith("._"):
                continue
            p = Path(dp) / f
            if p.suffix.lower() in AUDIO_EXTS:
                files.append(p)
    added = 0
    for p in tqdm(files, desc="scan"):
        sp = str(p)
        mt = p.stat().st_mtime
        if sp in known and known[sp] == mt:
            continue
        artist = album = title = genre = year = None
        dur = None
        try:
            mf = MFile(sp, easy=True)
            if mf is not None:
                dur = mf.info.length
                t = mf.tags
                artist = _tag(t, "albumartist") or _tag(t, "artist")
                album, title = _tag(t, "album"), _tag(t, "title")
                genre, year = _tag(t, "genre"), _tag(t, "date")
        except Exception:
            pass
        rel = p.relative_to(root).parts
        artist = artist or (rel[0] if len(rel) > 1 else None)
        title = title or p.stem
        con.execute(
            """INSERT INTO tracks(path, artist, album, title, genre, year, duration, mtime)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET artist=excluded.artist, album=excluded.album,
               title=excluded.title, genre=excluded.genre, year=excluded.year,
               duration=excluded.duration, mtime=excluded.mtime""",
            (sp, artist, album, title, genre, year, dur, mt))
        added += 1
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    print(f"catalogued {added} new/changed files; {n} tracks total")
