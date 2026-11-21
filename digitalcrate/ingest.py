"""Add new sources from anywhere: a YouTube (or other yt-dlp-supported) URL, a single audio file, or a folder.

    python -m digitalcrate ingest "https://www.youtube.com/watch?v=..."   [--drums] [--vocals demucs|roformer]
    python -m digitalcrate ingest "/path/to/song.mp3"
    python -m digitalcrate ingest "/path/to/folder"

Downloads go to <found_sounds>/YouTube (see digitalcrate.toml). Files/folders are catalogued in place (not copied).
Everything then runs through the normal pipeline (vocals/pads, optional percussion) and the library is rebuilt.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from . import config as C
from .db import connect

FOUND = C.FOUND_DIR


def log(msg):
    print(msg, flush=True)


def is_url(s):
    return bool(re.match(r"^https?://", s.strip()))


def download(url):
    out_dir = FOUND / "YouTube"
    out_dir.mkdir(parents=True, exist_ok=True)
    ytdlp = str(Path(sys.executable).parent / "yt-dlp")
    log(f"downloading audio: {url}")
    info = json.loads(subprocess.run([ytdlp, "--no-playlist", "-J", url], capture_output=True, text=True,
                                     check=True).stdout)
    tmpl = str(out_dir / "%(title).80s [%(id)s].%(ext)s")
    subprocess.run([ytdlp, "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
                    "--audio-quality", "0", "--embed-metadata", "-o", tmpl, url], check=True,
                   capture_output=True, text=True)
    files = sorted(out_dir.glob(f"*[[]{info['id']}[]].m4a"))
    if not files:
        raise RuntimeError("download finished but no audio file found")
    meta = dict(artist=info.get("artist") or info.get("uploader") or info.get("channel"),
                title=info.get("track") or info.get("title"), album=info.get("album") or "YouTube",
                genre=None, year=(info.get("upload_date") or "")[:4], url=url)
    log(f"downloaded: {files[0].name}")
    return files[0], meta


def catalogue(paths, meta=None):
    """Insert/refresh specific files in the tracks table; returns their track ids."""
    from mutagen import File as MFile
    from .policy import classify_track
    con = connect()
    ids = []
    for p in paths:
        p = Path(p)
        artist = album = title = genre = year = None
        dur = None
        try:
            mf = MFile(str(p), easy=True)
            if mf is not None:
                dur = mf.info.length
                t = mf.tags or {}
                g = lambda k: (t.get(k) or [None])[0] if t else None
                artist, album, title, genre, year = g("albumartist") or g("artist"), g("album"), g("title"), g("genre"), g("date")
        except Exception:
            pass
        if meta:
            artist, title = meta.get("artist") or artist, meta.get("title") or title
            album, genre, year = meta.get("album") or album, meta.get("genre") or genre, meta.get("year") or year
        artist = artist or p.parent.name
        title = title or p.stem
        con.execute("""INSERT INTO tracks(path, artist, album, title, genre, year, duration, mtime, status)
                       VALUES(?,?,?,?,?,?,?,?,'new')
                       ON CONFLICT(path) DO UPDATE SET artist=excluded.artist, album=excluded.album,
                       title=excluded.title, genre=excluded.genre, duration=excluded.duration, mtime=excluded.mtime""",
                    (str(p), artist, album, title, genre, year, dur, p.stat().st_mtime))
        tid = con.execute("SELECT id FROM tracks WHERE path=?", (str(p),)).fetchone()[0]
        con.execute("UPDATE tracks SET policy=? WHERE id=?", (classify_track(artist, genre, str(p)), tid))
        ids.append(tid)
    con.commit()
    return ids


def ingest(target, drums=False, vocals="roformer", separate="always", rebuild=True, reprocess=False):
    target = target.strip().strip('"').strip("'")
    if is_url(target):
        f, meta = download(target)
        ids = catalogue([f], meta)
    else:
        p = Path(target).expanduser()
        if not p.exists():
            raise FileNotFoundError(target)
        if p.is_dir():
            files = [q for q in p.rglob("*") if q.suffix.lower() in C.AUDIO_EXTS and not q.name.startswith("._")]
            log(f"found {len(files)} audio files in {p}")
        else:
            files = [p]
        ids = catalogue(files)
    if not ids:
        log("nothing to process"); return
    con = connect()
    pol = {r["id"]: r["policy"] for r in con.execute(f"SELECT id, policy FROM tracks WHERE id IN ({','.join('?' * len(ids))})", ids)}
    refs = [i for i in ids if pol[i] == "reference"]
    if refs:
        log(f"{len(refs)} track(s) match your reference-only list and are skipped (edit digitalcrate/policy.py to change)")
    ids = [i for i in ids if pol[i] != "reference"]
    if not ids:
        return
    where = f"id IN ({','.join(str(i) for i in ids)})"
    from .process import run as prun
    log(f"mining vocals / pads / textures from {len(ids)} track(s)…")
    prun(where, (), separate, None, True, verbose=True, vocals=vocals)
    if drums:
        from .percussion import run as drun
        log("mining percussion…")
        drun(where, (), None, None, redo=True)
    n = con.execute(f"SELECT COUNT(*) FROM samples WHERE track_id IN ({','.join(str(i) for i in ids)})").fetchone()[0]
    log(f"{n} samples from the new source(s)")
    if rebuild:
        log("rebuilding library views and browser…")
        from .build import build
        build()
    log("INGEST TRACKS " + ",".join(str(i) for i in ids))
    log("INGEST DONE")
