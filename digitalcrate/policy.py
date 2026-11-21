"""Source policy: which records are fair game to sample.

  reference   — sample-based producers. Never enters the library; their extracted sounds live in
                SampleLibrary/_Reference and are used only as *style queries* ("find me things like this").
  vocals_only — the vocal performance is original but the beat is built from samples (most hip-hop).
  source      — everything else: original recordings, fair game.

Edit the lists below freely, then run `python -m digitalcrate policy` to apply.
"""
import re
import shutil

from . import config as C
from .db import connect

REFERENCE_ARTISTS = [
    "Burial", "Gas", "Wolfgang Voigt", "Voigt & Voigt", "Mike Ink", "Breakage",
    "Madvillain", "Madlib", "MF DOOM", "Viktor Vaughn", "King Geedorah", "J Dilla", "Pete Rock",
    "DJ Shadow", "DJ Screw", "Clams Casino", "Flying Lotus", "Four Tet", "James Blake", "Moodymann",
    "Theo Parrish", "DJ Rashad", "Traxman", "DJ Paypal", "DJ Spooky", "Massive Attack", "Huerco S",
    "Ricky Eat Acid", "The Avalanches", "DJ Koze", "Lil Ugly Mane", "SpaceGhostPurrp", "Gorillaz",
] + list(C._cfg.get("reference_artists", []))   # add your own in digitalcrate.toml (e.g. your releases)
REFERENCE_EXACT = list(C._cfg.get("reference_exact", []))  # exact artist-name matches
REFERENCE_GENRES = ["footwork", "juke"]
VOCALS_ONLY_GENRES = ["rap", "hip-hop", "hip hop"]
VOCALS_ONLY_ARTISTS = ["Ghostface", "Raekwon", "Nas", "Mos Def", "Gang Starr", "Outkast", "Fugees",
                       "Dr. Dre", "Kendrick Lamar", "Earl Sweatshirt", "ANTWON"]


def _has(name, words):
    return any(re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", name) for w in words)


def classify_track(artist, genre, path):
    a = (artist or "").lower()
    g = (genre or "").lower()
    rel = str(path).replace(str(C.MUSIC_ROOT), "").lower()
    top = rel.strip("/").split("/")[0] if rel else ""
    if a in [x.lower() for x in REFERENCE_EXACT] or top in [x.lower() for x in REFERENCE_EXACT]:
        return "reference"
    if _has(a, REFERENCE_ARTISTS) or _has(top, REFERENCE_ARTISTS) or _has(g, REFERENCE_GENRES):
        return "reference"
    if _has(a, VOCALS_ONLY_ARTISTS) or _has(g, VOCALS_ONLY_GENRES):
        return "vocals_only"
    return "source"


def sample_dir(policy):
    return C.LIB_ROOT / "_Reference" if policy == "reference" else C.LIB_ROOT


def apply():
    con = connect()
    rows = con.execute("SELECT id, artist, genre, path FROM tracks").fetchall()
    counts = {}
    for r in rows:
        p = classify_track(r["artist"], r["genre"], r["path"])
        counts[p] = counts.get(p, 0) + 1
        con.execute("UPDATE tracks SET policy=? WHERE id=?", (p, r["id"]))
    con.commit()
    # move existing samples to match their track's policy
    moved = dropped = 0
    for s in con.execute("""SELECT s.id, s.path, s.category, s.source, t.policy FROM samples s
                            JOIN tracks t ON t.id = s.track_id""").fetchall():
        if s["policy"] == "vocals_only" and s["category"] not in ("Vocals",):
            (C.LIB_ROOT / s["path"]).unlink(missing_ok=True)
            con.execute("DELETE FROM samples WHERE id=?", (s["id"],))
            dropped += 1
            continue
        is_ref = s["path"].startswith("_Reference/")
        want_ref = s["policy"] == "reference"
        if is_ref != want_ref:
            new = s["path"][len("_Reference/"):] if is_ref else "_Reference/" + s["path"]
            src, dst = C.LIB_ROOT / s["path"], C.LIB_ROOT / new
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
            con.execute("UPDATE samples SET path=? WHERE id=?", (new, s["id"]))
            moved += 1
    con.commit()
    print("tracks by policy:", counts)
    print(f"samples moved: {moved}, dropped (non-vocal from vocals-only tracks): {dropped}")
    return counts
