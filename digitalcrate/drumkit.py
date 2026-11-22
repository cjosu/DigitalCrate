"""Complete the kit: drum hits for the kinds your drum lane is missing, that sound like they were recorded with the
pads you have (🔎 on the drum lane; 🥁 build a kit around this, on any drum hit).

"Goes well with" compares whole sounds, so a kick's best matches are other kicks. Here each hit's sound (its CLAP
embedding) has the average of its kind subtracted: what's left is the recording's character (room, tape, era,
brightness) rather than "it's a kick". Candidates are ranked by how close their character is to the kit's.
Checked on the library's own songs: given one song's hits, it ranks that song's other drums above every other
drum of that kind with AUC 0.83 over 3,120 kit pairs (comparing whole sounds: 0.80).
"""
import numpy as np

from .db import connect

# single hits only: layered hits ("Kick + Snare") already hold two drums
KIND = {"Kick": "kick", "Snare": "snare", "Rim & Clap": "clap", "Hat Open": "hat", "Hat Closed": "hat",
        "Perc + Hat": "hat", "Ride": "cymbal", "Crash": "cymbal", "Shaker & Tamb": "shaker", "Tom": "tom",
        "Hand Drum": "perc", "Wood & Metal": "perc", "Orchestral": "perc"}
ORDER = [("kick", "Kick"), ("snare", "Snare"), ("clap", "Rim / clap"), ("hat", "Hats"), ("cymbal", "Ride / crash"),
         ("shaker", "Shaker / tambourine"), ("tom", "Tom"), ("perc", "Hand drums / percussion")]
_C = {}


def _hits(con):
    key = tuple(con.execute("SELECT COUNT(*), MAX(rowid) FROM samples").fetchone())
    if _C.get("key") != key:
        rows = [r for r in con.execute("""SELECT s.path, s.subtype, s.track_id, s.clap, s.quality FROM samples s
                   WHERE s.category='Percussion' AND s.kind='oneshot' AND s.path NOT LIKE '_Reference/%'
                   AND s.parent_id IS NULL""") if r["subtype"] in KIND]
        E = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rows])
        E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
        kind = np.array([KIND[r["subtype"]] for r in rows])
        cent = {k: E[kind == k].mean(0) for k in set(kind)}
        R = E - np.stack([cent[k] for k in kind])
        R /= np.linalg.norm(R, axis=1, keepdims=True) + 1e-9
        _C.update(key=key, paths=[r["path"] for r in rows], pos={r["path"]: k for k, r in enumerate(rows)}, R=R,
                  kind=kind, track=np.array([r["track_id"] for r in rows]),
                  q=np.array([r["quality"] or 0.5 for r in rows]), sub=[r["subtype"] for r in rows])
    return _C


def kind_of(subtype):
    return KIND.get(subtype)


def complete(paths, per=3, kinds=None):
    """For each kind the kit lacks (or `kinds`), the `per` best-fitting hits, one per song."""
    con = connect()
    H = _hits(con)
    have = [H["pos"][p] for p in paths if p in H["pos"]]
    if not have:
        return dict(error="add a drum hit (kick, snare, hats…) first: the kit is built around what it sounds like")
    style = H["R"][have].mean(0)
    style /= np.linalg.norm(style) + 1e-9
    fit = H["R"] @ style
    try:
        from .taste import scores_payload
        t = scores_payload(None).get("score", {})
        taste = np.array([t.get(p, 0.0) for p in H["paths"]])
    except Exception:
        taste = np.zeros(len(H["paths"]))
    disliked = {r[0] for r in con.execute("SELECT path FROM events WHERE type='dislike' AND value>0")}
    kit_tracks = set(H["track"][have])
    covered = {H["kind"][k] for k in have}
    score = fit + 0.05 * (H["q"] - 0.5) + 0.03 * np.clip(taste, -2, 3) + 0.02 * np.isin(H["track"], list(kit_tracks))
    out = []
    for k, label in ORDER:
        if (kinds and k not in kinds) or (not kinds and k in covered):
            continue
        idx = [i for i in np.argsort(-score) if H["kind"][i] == k and H["paths"][i] not in disliked and i not in have]
        picks, songs = [], set()
        for i in idx:
            if H["track"][i] in songs:
                continue
            songs.add(H["track"][i])
            picks.append(dict(path=H["paths"][i], fit=round(float(fit[i]), 3), sub=H["sub"][i],
                              same_song=bool(H["track"][i] in kit_tracks)))
            if len(picks) >= per:
                break
        if picks:
            out.append(dict(kind=k, label=label, picks=picks))
    return dict(missing=out, covered=sorted(covered))
