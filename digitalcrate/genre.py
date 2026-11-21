"""Clean genre families for tracks.

Order of evidence, per track:
  1. your overrides: [genres] in digitalcrate.toml, artist = family (file tags are often just wrong);
  2. the file's genre tag, mapped by keyword; Ambient and Electronic win in compound tags ("Disco/Deep House/Funk");
  3. the artist's consensus: the most common family among their tagged tracks anywhere in the collection;
  4. CLAP on the average embedding of the track's samples (weak: samples are stems and fragments).
"""
from collections import Counter

import numpy as np

FAMILIES = {  # family: (tag keywords, CLAP prompt)
    "Choral & Sacred": (["choral", "sacred", "chant", "gospel", "mass", "requiem"], "choral sacred music, a choir singing in a church"),
    "Classical": (["classical", "baroque", "opera", "symphon", "romantic", "chamber", "orchestr", "concerto"], "classical orchestral or chamber music"),
    "Jazz": (["jazz", "bebop", "bebob", "swing", "fusion", "bossa"], "jazz music"),
    "Soul & R&B": (["r&b", "rnb", "soul", "funk", "motown", "neo soul", "quiet storm"], "soul and r&b music"),
    "Hip-Hop": (["hip-hop", "hip hop", "rap"], "hip hop music with rapping"),
    "Folk": (["folk", "singer-songwriter", "americana", "country", "bluegrass", "blues"], "acoustic folk music"),
    "World": (["world", "african", "ethnic", "latin", "brazil", "mpb", "reggae", "chinese", "japanese", "indian", "afro"], "traditional world music"),
    "Soundtrack": (["soundtrack", "score", "film", "game", "library", "exotica", "mall"], "film soundtrack music"),
    "Ambient": (["ambient", "new age", "drone", "meditat", "kankyo", "chillout"], "ambient music"),
    "Electronic": (["electronic", "electronica", "techno", "house", "idm", "dub", "minimal", "dance", "trance",
                    "footwork", "juke", "bass", "garage", "electro", "trip hop", "trip-hop", "disco", "edits",
                    "downtempo", "breaks", "breakbeat", "jungle", "drum and bass", "drum & bass", "dnb", "synth",
                    "leftfield", "glitch", "broken beat", "acid", "balearic", "krautrock", "kosmische"],
                   "electronic dance music"),
    "Experimental": (["experimental", "noise", "avant", "musique concrete"], "experimental avant-garde music"),
    "Rock & Indie": (["rock", "indie", "alternative", "punk", "psych", "shoegaze", "alt."], "indie rock music with guitars"),
    "Pop": (["pop"], "pop music"),
}
ORDER = list(FAMILIES) + ["Other"]
PRIORITY = ["Ambient", "Electronic"] + [f for f in FAMILIES if f not in ("Ambient", "Electronic")]


def from_tag(tag):
    t = (tag or "").lower().strip()
    if not t or t in ("other", "unknown", "general", "misc"):
        return None
    for fam in PRIORITY:
        if any(k in t for k in FAMILIES[fam][0]):
            return fam
    return "Other"


def _norm(a):
    return " ".join((a or "").lower().split())


def overrides():
    """[genres] in digitalcrate.toml: artist = family. Matching ignores case and extra spaces."""
    from . import config as C
    out = {}
    for a, f in (C._cfg.get("genres") or {}).items():
        if f in FAMILIES or f == "Other":
            out[_norm(a)] = f
        else:
            print(f"digitalcrate.toml [genres]: unknown family {f!r} for {a!r} (use one of: {', '.join(ORDER)})")
    return out


def artist_consensus():
    """Most common tag family per artist across the whole collection (not just mined tracks)."""
    from .db import connect
    votes = {}
    for r in connect().execute("SELECT artist, genre, count(*) n FROM tracks GROUP BY artist, genre"):
        f = from_tag(r["genre"])
        if f and f != "Other":
            votes.setdefault(_norm(r["artist"]), Counter())[f] += r["n"]
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}


def family(artist, tag, ov=None, cons=None):
    """Family for one track, or None when only the audio can tell."""
    ov = overrides() if ov is None else ov
    a = _norm(artist)
    if a in ov:
        return ov[a]
    f = from_tag(tag)
    if f and f != "Other":
        return f
    cons = artist_consensus() if cons is None else cons
    return cons.get(a) or f


def assign(rows, emb):
    """rows: sample rows with track_id + genre tag; emb: (n, d) CLAP. Returns family per row."""
    by_track = {}
    for i, r in enumerate(rows):
        by_track.setdefault(r["track_id"], []).append(i)
    fam_track = {}
    need = []
    ov, cons = overrides(), artist_consensus()
    for tid, idx in by_track.items():
        f = family(rows[idx[0]]["artist"], rows[idx[0]]["genre"], ov, cons)
        if f:
            fam_track[tid] = f
        else:
            need.append(tid)
    if need:
        from . import models
        T = models.clap().embed_text(tuple(p for _, p in FAMILIES.values()))
        names = list(FAMILIES)
        for tid in need:
            m = emb[by_track[tid]].mean(0)
            fam_track[tid] = names[int(np.argmax(T @ (m / (np.linalg.norm(m) + 1e-9))))]
    return [fam_track[r["track_id"]] for r in rows]
