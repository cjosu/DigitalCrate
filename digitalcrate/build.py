"""Library-wide build: mood tags, pairwise compatibility, kits, key/tempo views, HTML browser."""
import json
import os
import shutil
from pathlib import Path

import numpy as np

from . import config as C
from .db import connect
from .process import MOOD_PROMPTS

CATS = ["Vocals", "Vocal Atmospheres", "Pads & Atmospheres", "Chords & Keys",
        "Melodies & Leads", "Textures & Field", "Bass & Sub", "Percussion"]
_R = {  # how well two roles sit together in an arrangement (symmetric)
    ("Vocals", "Vocals"): .45, ("Vocals", "Vocal Atmospheres"): .5, ("Vocals", "Pads & Atmospheres"): 1.,
    ("Vocals", "Chords & Keys"): .9, ("Vocals", "Melodies & Leads"): .65, ("Vocals", "Textures & Field"): .95,
    ("Vocals", "Bass & Sub"): .8, ("Vocal Atmospheres", "Vocal Atmospheres"): .3,
    ("Vocal Atmospheres", "Pads & Atmospheres"): .6, ("Vocal Atmospheres", "Chords & Keys"): .6,
    ("Vocal Atmospheres", "Melodies & Leads"): .6, ("Vocal Atmospheres", "Textures & Field"): .9,
    ("Vocal Atmospheres", "Bass & Sub"): .85, ("Pads & Atmospheres", "Pads & Atmospheres"): .55,
    ("Pads & Atmospheres", "Chords & Keys"): .8, ("Pads & Atmospheres", "Melodies & Leads"): .9,
    ("Pads & Atmospheres", "Textures & Field"): 1., ("Pads & Atmospheres", "Bass & Sub"): .85,
    ("Chords & Keys", "Chords & Keys"): .4, ("Chords & Keys", "Melodies & Leads"): .85,
    ("Chords & Keys", "Textures & Field"): .9, ("Chords & Keys", "Bass & Sub"): .85,
    ("Melodies & Leads", "Melodies & Leads"): .4, ("Melodies & Leads", "Textures & Field"): .9,
    ("Melodies & Leads", "Bass & Sub"): .85, ("Textures & Field", "Textures & Field"): .6,
    ("Textures & Field", "Bass & Sub"): .8, ("Bass & Sub", "Bass & Sub"): .2,
}
for c, v in {"Vocals": .9, "Vocal Atmospheres": .85, "Pads & Atmospheres": .9, "Chords & Keys": .85,
             "Melodies & Leads": .8, "Textures & Field": .85, "Bass & Sub": .9, "Percussion": .6}.items():
    _R[(c, "Percussion")] = v
ROLE = np.ones((len(CATS), len(CATS)))
for (a, b), v in _R.items():
    ROLE[CATS.index(a), CATS.index(b)] = ROLE[CATS.index(b), CATS.index(a)] = v

KEY_NEUTRAL = 0.75
TOPK = 30


def load(con, reference=False):
    op = "LIKE" if reference else "NOT LIKE"
    rows = con.execute(f"""SELECT s.*, t.artist, t.title, t.album, t.genre, t.processed_at, t.path AS tpath FROM samples s
                          JOIN tracks t ON t.id = s.track_id WHERE s.path {op} '_Reference/%'
                          ORDER BY s.category, s.quality DESC""").fetchall()
    n = len(rows)
    d = dict(rows=rows, n=n)
    d["emb"] = np.stack([np.frombuffer(r["clap"], np.float16).astype(np.float32) for r in rows]) if n else None
    d["chroma"] = np.array([json.loads(r["chroma"]) for r in rows]) if n else None
    d["cat"] = np.array([CATS.index(r["category"]) for r in rows])
    d["num"] = np.array([int(r["camelot"][:-1]) for r in rows])
    d["minor"] = np.array([r["camelot"][-1] == "A" for r in rows])
    d["keyed"] = np.array([r["key_from"] != "none" for r in rows])
    d["bpm"] = np.array([r["bpm"] or 0.0 for r in rows])
    d["loop"] = np.array([r["kind"] == "loop" for r in rows])
    d["track"] = np.array([r["track_id"] for r in rows])
    d["quality"] = np.array([r["quality"] for r in rows])
    return d


def camelot_score(num_a, minor_a, num_b, minor_b):
    diff = np.abs(num_a - num_b) % 12
    diff = np.minimum(diff, 12 - diff)
    same = minor_a == minor_b
    s = np.where(same, np.select([diff == 0, diff == 1, diff == 2], [1.0, .85, .45], .12),
                 np.select([diff == 0, diff == 1], [.9, .5], .12))
    return s


def compat_block(d, idx, cols=None):
    """Compatibility of samples idx (rows) vs cols (default: all). Returns dict of component matrices."""
    cols = np.arange(d["n"]) if cols is None else cols
    i, j = idx[:, None], cols[None, :]
    cam = camelot_score(d["num"][i], d["minor"][i], d["num"][j], d["minor"][j])
    ch = d["chroma"][idx] @ d["chroma"][cols].T
    nrm = np.linalg.norm(d["chroma"][idx], axis=1)[:, None] * np.linalg.norm(d["chroma"][cols], axis=1)[None, :]
    ch = ch / (nrm + 1e-9)
    harm = 0.65 * cam + 0.35 * ch
    keyed = d["keyed"][i] & d["keyed"][j]
    harm = np.where(keyed, harm, KEY_NEUTRAL)
    # tempo: only matters when both are tempo-synced loops
    bi, bj = d["bpm"][i], d["bpm"][j]
    both = d["loop"][i] & d["loop"][j] & (bi > 0) & (bj > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.abs(np.log2(np.where(both, bi / np.where(bj > 0, bj, 1), 1.0)))
    r = np.minimum.reduce([r, np.abs(r - 1), np.abs(r + 1)])
    tempo = np.where(both, np.clip(1 - (r - 0.02) / 0.2, 0.4, 1.0), 1.0)
    role = ROLE[d["cat"][i], d["cat"][j]]
    vibe = np.clip((d["emb"][idx] @ d["emb"][cols].T - 0.25) / 0.55, 0, 1)
    score = harm * tempo * (0.4 * role + 0.6 * vibe)
    return dict(score=score, harm=harm, tempo=tempo, role=role, vibe=vibe)


def mood_tags(con, d):
    if not d["n"]:
        return [[] for _ in range(0)]
    M = np.array([[json.loads(r["mood_sims"])[k] for k in MOOD_PROMPTS] for r in d["rows"]])
    z = (M - M.mean(0)) / (M.std(0) + 1e-9)
    names = list(MOOD_PROMPTS)
    tags = []
    for r, zr in zip(d["rows"], z):
        top = [names[k] for k in np.argsort(-zr)[:3] if zr[k] > 0.6]
        tags.append(top)
        con.execute("UPDATE samples SET tags=? WHERE id=?", (json.dumps(top), r["id"]))
    con.commit()
    return tags


def partners(d):
    out = []
    for s in range(0, d["n"], 256):
        idx = np.arange(s, min(s + 256, d["n"]))
        comp = compat_block(d, idx)
        sc = comp["score"].copy()
        sc[np.arange(len(idx)), idx] = -1
        for row_i, gi in enumerate(idx):
            order = np.argsort(-sc[row_i])
            picks, same_track = [], 0
            for j in order:
                if d["track"][j] == d["track"][gi]:
                    if same_track >= 3:
                        continue
                    same_track += 1
                picks.append([int(j), round(float(sc[row_i, j]), 3),
                              round(float(comp["harm"][row_i, j]), 2), round(float(comp["vibe"][row_i, j]), 2)])
                if len(picks) >= TOPK:
                    break
            out.append(picks)
    return out


KIT_ROLES = [("Pads & Atmospheres",), ("Chords & Keys", "Melodies & Leads"), ("Textures & Field",),
             ("Vocals",), ("Pads & Atmospheres", "Melodies & Leads", "Bass & Sub")]


def make_kits(d, tags, n_kits):
    rows = d["rows"]
    seeds = [i for i in range(d["n"]) if rows[i]["category"] in ("Vocals", "Vocal Atmospheres")
             and rows[i]["subtype"] != "Chops"]
    seeds.sort(key=lambda i: -d["quality"][i])
    used_tracks, kits = set(), []
    for s in seeds:
        if len(kits) >= n_kits:
            break
        if d["track"][s] in used_tracks:
            continue
        chosen, tracks = [s], {d["track"][s]}
        for roles in KIT_ROLES:
            pool = np.array([j for j in range(d["n"]) if rows[j]["category"] in roles
                             and d["track"][j] not in tracks and j not in chosen])
            if s in chosen and roles == ("Vocals",):
                pool = np.array([j for j in pool if rows[j]["subtype"] == "Chops"]) if len(pool) else pool
            if not len(pool):
                continue
            sc = np.mean([compat_block(d, np.array([c]), pool)["score"][0] for c in chosen], axis=0)
            sc = sc * (0.6 + 0.4 * d["quality"][pool])
            best = int(np.argmax(sc))
            if sc[best] < 0.35:
                continue
            chosen.append(int(pool[best]))
            tracks.add(d["track"][pool[best]])
        if len(chosen) < 4:
            continue
        used_tracks.add(d["track"][s])
        mood = (tags[s] or ["mixed"])[0]
        r = rows[s]
        bpm = next((d["bpm"][c] for c in chosen if d["loop"][c]), d["bpm"][s])
        name = (f"Kit{len(kits) + 1:03d}_{int(r['camelot'][:-1]):02d}{r['camelot'][-1]}-{r['key']}"
                f"{'m' if r['scale'] == 'minor' else ''}_{f'{bpm:.0f}bpm' if bpm else 'free'}_{mood}")
        kits.append(dict(name=name, members=chosen))
    return kits


def _link(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except FileExistsError:
        pass
    except OSError:
        shutil.copy2(src, dst)


def build_views(d, kits):
    root = C.LIB_ROOT
    for v in ("_By Key", "_By Tempo", "Kits"):
        if (root / v).exists():
            shutil.rmtree(root / v)
    from .audio import PITCHES
    for r in d["rows"]:
        src = root / r["path"]
        if not src.exists():
            continue
        cam = r["camelot"]
        kdir = "No Key" if r["key_from"] == "none" else \
            f"{int(cam[:-1]):02d}{cam[-1]} {r['key']}{'m' if r['scale'] == 'minor' else ''}"
        _link(src, root / "_By Key" / kdir / r["category"] / src.name)
        if r["bpm"] and r["kind"] == "loop":
            lo = int(r["bpm"] // 5 * 5)
            _link(src, root / "_By Tempo" / f"{lo:03d}-{lo + 4:03d} bpm" / r["category"] / src.name)
    for k in kits:
        lines = []
        for m in k["members"]:
            r = d["rows"][m]
            src = root / r["path"]
            _link(src, root / "Kits" / k["name"] / src.name)
            lines.append(f"{r['category']:20s} {r['camelot']:4s} {src.name}")
        (root / "Kits" / k["name"] / "kit.txt").write_text("\n".join(lines) + "\n")


def build(n_kits=60):
    con = connect()
    d = load(con)
    if not d["n"]:
        print("no samples yet — run `process` first")
        return
    print(f"{d['n']} samples")
    tags = mood_tags(con, d)
    from .genre import assign
    d["genre"] = assign(d["rows"], d["emb"])
    ref = load(con, reference=True)
    d["ref_sim"], d["ref_match"] = np.zeros(d["n"]), [""] * d["n"]
    if ref["n"]:
        keep = np.array([r["kind"] != "oneshot" for r in ref["rows"]])
        R = ref["emb"][keep]
        names = [f"{r['artist']} – {r['title']}" for r, k in zip(ref["rows"], keep) if k]
        sims = d["emb"] @ R.T
        d["ref_sim"] = sims.max(1)
        d["ref_match"] = [names[j] for j in sims.argmax(1)]
        print(f"reference set: {len(names)} sounds")
    print("computing compatibility…")
    parts = partners(d)
    kits = make_kits(d, tags, n_kits)
    print(f"{len(kits)} kits")
    build_views(d, kits)
    from .browser import write_browser
    write_browser(d, tags, parts, kits)
    print(f"open {C.LIB_ROOT / 'Browser.html'}")
