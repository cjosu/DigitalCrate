"""New samples into the open page without `digitalcrate build` (the page asks every minute while it's served).

Rows come back in exactly the page's format (browser.write_browser), with mood tags scaled against the whole
library, the genre family, and their "goes well with" picks scored like a full build (the library is loaded once per
batch, not per sample). What only a full build makes (kits, folder views, the galaxy map, reference matches) still
waits for the next build; the Processing page's runs do that at the end anyway.
"""
import json
from datetime import datetime, timezone

import numpy as np

from .db import connect

_MOOD = {}


def _mood_stats(con, keys):
    """Mean and spread of each mood score across the library, for tags scaled like build.mood_tags."""
    n = con.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    if _MOOD.get("n") != n:
        M = np.array([[json.loads(r[0] or "{}").get(k, 0.0) for k in keys]
                      for r in con.execute("SELECT mood_sims FROM samples WHERE mood_sims IS NOT NULL")])
        _MOOD.update(n=n, mu=M.mean(0) if len(M) else 0, sd=(M.std(0) + 1e-9) if len(M) else 1)
    return _MOOD["mu"], _MOOD["sd"]


def new_rows(since_min, known=()):
    """Samples created at or after `since_min` (minutes since the epoch, UTC) that the page doesn't have yet."""
    from .browser import _pack_env, _ops_label
    from .process import MOOD_PROMPTS
    con = connect()
    t0 = datetime.fromtimestamp(max(0, int(since_min) - 1) * 60, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    known = set(known)
    rows = [r for r in con.execute("""SELECT s.*, t.artist, t.title, t.album, t.genre, t.processed_at, t.path AS tpath
                     FROM samples s JOIN tracks t ON t.id = s.track_id
                     WHERE s.created_at >= ? AND s.path NOT LIKE '_Reference/%' ORDER BY s.rowid LIMIT 2000""", (t0,))
            if r["id"] not in known]
    if not rows:
        return dict(samples=[], partners=[], tracks={}, born=[])
    keys = list(MOOD_PROMPTS)
    mu, sd = _mood_stats(con, keys)
    from .genre import assign
    emb = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rows])
    fams = assign(rows, emb)
    S, born, tracks = [], [], {}
    for r, fam in zip(rows, fams):
        z = (np.array([json.loads(r["mood_sims"] or "{}").get(k, 0.0) for k in keys]) - mu) / sd
        tags = [keys[k] for k in np.argsort(-z)[:3] if z[k] > 0.6]
        keyed = r["key_from"] != "none"
        S.append([r["id"], r["path"], r["category"], r["subtype"], r["kind"],
                  r["camelot"] if keyed else "", (r["key"] + ("m" if r["scale"] == "minor" else "")) if keyed else "",
                  round(r["bpm"]) if r["bpm"] else 0, round(r["dur"], 1), r["artist"] or "", r["title"] or "",
                  round(r["quality"] or 0, 2), tags, _pack_env(json.loads(r["env"] or "[]")), r["note"] or "",
                  r["instrument"] or "", r["bars"] or 0, round(r["start"] or 0), 0.0, "", fam, r["track_id"],
                  r["parent_id"] or "", r["root_id"] or "", _ops_label(r["ops"])])
        ts = r["created_at"]
        born.append(int(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() // 60) if ts else 0)
        if r["track_id"] not in tracks:
            pt = r["processed_at"]
            ep = int(datetime.strptime(pt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()) if pt else 0
            tracks[r["track_id"]] = [ep, r["artist"] or "", r["title"] or "", "", r["album"] or ""]
    return dict(samples=S, partners=_partners([r["id"] for r in rows]), tracks=tracks, born=born)


def _partners(ids):
    """'Goes well with' for each new sample, scored against the whole library like a build (one load for all)."""
    try:
        from .build import load, compat_block, _picks
        d = load(connect())
        pos = {r["id"]: k for k, r in enumerate(d["rows"])}
        out = []
        for sid in ids:
            gi = pos.get(sid)
            if gi is None:
                out.append([])
                continue
            comp = compat_block(d, np.array([gi]))
            sc = comp["score"].copy()
            sc[0, gi] = -1
            out.append([[d["rows"][j]["id"], s, h, v] for j, s, h, v in _picks(d, gi, comp, sc, 0)])
        return out
    except Exception as e:  # the samples still show; their picks come with the next build
        print("live partners failed:", e)
        return [[] for _ in ids]
