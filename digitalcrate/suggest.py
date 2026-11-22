"""Edit suggestions for a sample, judged by your taste model: ✨ suggest in the editor.

How it works
  1. Moves. Each is plain editor settings (stretch, pitch, tape, Tune to, Tone, reverse, a plugin), drawn from families
     that suit the material, built only from engines and treatments you rated well in blind tests
     (memory: formant-kept or tape pitch-UP on voices, natural tuning, never pitch-down/wobble/hard snaps on a voice;
     octave-down, darkening and wash on sustained sounds).
  2. Critic. Each move is rendered (a ~8 s window), embedded with CLAP and scored by the same model that ranks "for
     you": how much more it sounds like what you star than the original does, minus a cost for drifting from the
     original. On your blind shootout ratings, the taste model alone could NOT hear render quality (72% vs 77% for
     simple closeness to the original), so quality comes from the curated moves and the closeness term, and the taste
     score only chooses between good options.
  3. Picks. The best move from each of three different families, plus one random wildcard from the rest. Your
     reactions (apply, save, ✕) are logged with which slot they came from, so it can be measured whether the critic's
     picks beat the random one, and they tilt future picks per family (a Beta prior per material).
"""
import json
import random
import time

import numpy as np

from . import config as C
from .db import connect

SR = C.SR
LAMBDA = 3.0       # cost of drifting from the original: cosine 0.9 costs 0.3 (in taste-score units)
WINDOW = 8.0       # seconds rendered for scoring

MATERIAL = {"Vocals": "vocal", "Vocal Atmospheres": "vocal", "Pads & Atmospheres": "sustained",
            "Textures & Field": "sustained", "Chords & Keys": "melodic", "Melodies & Leads": "melodic",
            "Bass & Sub": "melodic", "Percussion": "perc"}


def _sm(params_by_key, mix=0.3, mode="Gemini", decay=None):
    """Valhalla Supermassive settings by fraction of each control's range (installed plugins only)."""
    from .plugins import find, params
    path = find("Supermassive")
    if not path:
        return None
    ps = {p["key"]: p for p in params(path)}
    out = {}
    if "mix" in ps:
        out["mix"] = ps["mix"]["min"] + mix * (ps["mix"]["max"] - ps["mix"]["min"])
    if "mode" in ps and mode in ps["mode"].get("choices", []):
        out["mode"] = mode
    if decay is not None and "feedback" in ps:
        out["feedback"] = ps["feedback"]["min"] + decay * (ps["feedback"]["max"] - ps["feedback"]["min"])
    return dict(plugins=[dict(path=path, params=out)], tail=4.0 if mix < 0.4 else 7.0)


def moves(material, key=None, project_key=None, k=None):
    """[(id, family, label, params)] for this kind of sample. k: {family: strength multiplier} learned from your
    "too much" / "too subtle" ratings (1 = as designed)."""
    M = []
    k = k or {}
    add = lambda i, f, l, p: M.append((i, f, l, p)) if p is not None else None
    mix = lambda f, m: min(0.9, max(0.05, m * k.get(f, 1)))
    tone = lambda f, hz: int(min(16000, max(400, hz / k.get(f, 1))))
    slow = lambda f, s: round(1 + (s - 1) * k.get(f, 1), 2)
    kh = lambda hz: f"{hz / 1000:.1f} kHz"
    if material == "vocal":
        add("tape_up2", "lift", "tape up 2 (pitch and speed)", dict(tape=True, semis=2))
        add("clean_up3", "lift", "pitch up 3", dict(semis=3))
        add("clean_up5", "lift", "pitch up 5 (a fourth: still in key)", dict(semis=5))
        if key:
            add("tune_own", "tune", f"tuned to its own key ({key}), natural", dict(tune_key=key, tune_strength=0.8, tune_speed=60))
        if project_key and project_key != key:
            add("tune_proj", "tune", f"tuned to your project ({project_key}), natural",
                dict(tune_key=project_key, tune_strength=0.8, tune_speed=60))
        add("space_light", "space", f"a little space (Supermassive {mix('space', .22):.0%})", _sm({}, mix=mix("space", 0.22)))
        add("slow125", "slow", f"slower ×{slow('slow', 1.25)}, same pitch", dict(stretch=slow("slow", 1.25)))
        add("warm", "tone", f"softer top (Tone {kh(tone('tone', 7000))})", dict(tone=tone("tone", 7000)))
    elif material == "sustained":
        add("oct_down", "octave", "an octave down (tape)", dict(tape=True, semis=-12))
        add("fifth_down", "octave", "a fourth down (tape)", dict(tape=True, semis=-5))
        add("dark", "tone", f"darker (Tone {kh(tone('tone', 2500))})", dict(tone=tone("tone", 2500)))
        add("darker", "tone", f"much darker (Tone {kh(tone('tone', 1200))})", dict(tone=tone("tone", 1200)))
        add("wash", "space", f"washed out (Supermassive {mix('space', .5):.0%})", _sm({}, mix=mix("space", 0.5), decay=0.6))
        add("slow2", "slow", f"slower ×{slow('slow', 2.0)}, same pitch", dict(stretch=slow("slow", 2.0)))
        add("slow15", "slow", f"slower ×{slow('slow', 1.5)}, same pitch", dict(stretch=slow("slow", 1.5)))
        add("reverse", "reverse", "reversed", dict(reverse=True))
    elif material == "melodic":
        add("tape_up2", "transpose", "tape up 2", dict(tape=True, semis=2))
        add("tape_down2", "transpose", "tape down 2", dict(tape=True, semis=-2))
        add("fifth_up", "transpose", "up 7 (a fifth)", dict(semis=7))
        add("space_light", "space", f"some space (Supermassive {mix('space', .3):.0%})", _sm({}, mix=mix("space", 0.3)))
        add("dark", "tone", f"darker (Tone {kh(tone('tone', 3000))})", dict(tone=tone("tone", 3000)))
        add("slow15", "slow", f"slower ×{slow('slow', 1.5)}, same pitch", dict(stretch=slow("slow", 1.5)))
        add("reverse", "reverse", "reversed", dict(reverse=True))
    else:  # percussion
        add("tape_down2", "pitch", "tape down 2 (heavier)", dict(tape=True, semis=-2))
        add("tape_up2", "pitch", "tape up 2 (tighter)", dict(tape=True, semis=2))
        add("dark", "tone", f"darker (Tone {kh(tone('tone', 3500))})", dict(tone=tone("tone", 3500)))
        add("reverse", "reverse", "reversed", dict(reverse=True))
    if project_key and key and material != "vocal":
        from .conform import parse_key
        try:  # the smallest move from its tonic to the project's (−6..+5 semitones)
            s = (parse_key(project_key)[0] - parse_key(key)[0] + 6) % 12 - 6
        except Exception:
            s = None
        if s:
            add("to_project", "project", f"in your project key ({project_key}): {s:+d} st", dict(semis=s))
    return M


PAIRS = {"vocal": [("lift", "space"), ("tune", "space"), ("slow", "space")],
         "sustained": [("octave", "space"), ("slow", "tone"), ("octave", "tone"), ("reverse", "space")],
         "melodic": [("transpose", "space"), ("slow", "tone")], "perc": [("pitch", "tone")]}


# ---------------------------------------------------------------- the critic

def _clap_of(ys):
    from scipy.signal import resample_poly
    from .models import clap
    clips = []
    for y in ys:
        m = y.mean(0)
        if len(m) > SR * 10:
            mid = len(m) // 2
            m = m[mid - SR * 5: mid + SR * 5]
        clips.append(resample_poly(m, 48000, SR).astype(np.float32))
    return clap().embed_audio(clips)


class Critic:
    """The live taste model, applied to audio that isn't in the library."""

    def __init__(self, sample_path):
        from . import taste
        taste.scores_payload(None)  # fit (or reuse the cached fit)
        self.r = taste._FIT.get(None) or {}
        self.L = taste._library(taste._db())
        self.c = self.r.get("critic")
        self.i = self.L["pos"].get(sample_path)
        self.meta = self.L["meta"].get(sample_path, {})

    def ok(self):
        return self.c is not None and self.i is not None

    def score(self, E):
        """taste score (z units, like 'for you') of each embedding, as if it were this sample."""
        from . import taste
        fz, c = self.L["fz"], self.c
        X = np.stack([np.r_[fz(e, self.meta), self.L["extra"][self.i]] for e in E])
        p, _ = taste.predict(X, self.r["beta"], self.r["cov"])
        z = (p - c["prob"][0]) / c["prob"][1]
        if c["trees"] is not None:
            t = c["trees"].predict_proba(X)[:, 1]
            z = (z + (t - c["tree"][0]) / c["tree"][1] - c["sum"][0]) / c["sum"][1]
        k = ((E @ c["pos_E"].T).max(1) - c["knn"][0]) / c["knn"][1]
        return 0.7 * z + 0.3 * k


# ---------------------------------------------------------------- your ratings of edits

REASONS = ("too much", "too subtle", "sounds processed", "wrong mood")
FAMILIES = ("lift", "transpose", "pitch", "octave", "tune", "space", "slow", "tone", "reverse", "project")
MATERIALS = ("vocal", "sustained", "melodic", "perc")
_LAST = {}  # (sample path, move) -> what the last suggestion rendered: embeddings for rating it without re-rendering


def _rdb(con):
    con.execute("""CREATE TABLE IF NOT EXISTS edit_ratings (ts REAL, path TEXT, sample_id TEXT, source TEXT, move TEXT,
                   family TEXT, material TEXT, arm TEXT, params TEXT, delta BLOB, close REAL, rating INTEGER,
                   reason TEXT)""")
    return con


def param_families(p):
    """Which kinds of edit a set of editor settings contains (also for your own edits, which have no move id)."""
    f = set()
    if abs(p.get("semis") or 0) > 1e-3:
        f.add("octave" if abs(p["semis"]) >= 5 and p.get("tape") and p["semis"] < 0 else "pitch")
    if abs((p.get("stretch") or 1) - 1) > 1e-3:
        f.add("slow")
    if (p.get("tone") or 20000) < 19000:
        f.add("tone")
    if p.get("plugins"):
        f.add("space")
    if p.get("reverse"):
        f.add("reverse")
    if p.get("tune_key"):
        f.add("tune")
    return f


def _param_feats(p):
    """How strong an edit is, in a few numbers the edit model can weigh."""
    sm = p.get("semis") or 0
    mixes = [v for pl in (p.get("plugins") or []) for k, v in (pl.get("params") or {}).items() if k == "mix"]
    return [abs(sm) / 12, float(sm > 0), float(bool(p.get("tape"))), np.log(p.get("stretch") or 1),
            np.log(20000 / min(20000, p.get("tone") or 20000)) / np.log(66), float(bool(p.get("reverse"))),
            float(bool(p.get("tune_key"))), (mixes[0] / 100 if mixes and mixes[0] > 1 else (mixes[0] if mixes else 0))]


def rate(rel, rating, reason=None, params=None, move=None, family=None, material=None, arm=None, source="suggestion"):
    """👍 (+1) / 👎 (−1) on an edit, with an optional reason. A reason sent shortly after a 👎 completes that rating."""
    con = _rdb(connect())
    s = con.execute("SELECT id, category FROM samples WHERE path=?", (rel,)).fetchone()
    if s is None:
        raise ValueError("not a library sample")
    material = material or MATERIAL.get(s["category"], "melodic")
    move = move or "own"
    if reason and rating < 0:
        last = con.execute("""SELECT rowid FROM edit_ratings WHERE path=? AND move=? AND rating<0 AND reason IS NULL
                              AND ts > ? ORDER BY ts DESC LIMIT 1""", (rel, move, time.time() - 900)).fetchone()
        if last:
            con.execute("UPDATE edit_ratings SET reason=? WHERE rowid=?", (reason, last[0]))
            con.commit()
            return dict(ok=True, updated=True)
    hit = _LAST.get((rel, move))
    if hit and source == "suggestion":
        e, E0, close, params = hit["e"], hit["E0"], hit["close"], hit["params"]
    else:  # your own edit (or a server restart since the suggestion): render the same window and listen again
        from .edit import render
        params = dict(params or {})
        a0 = float(params.get("start") or 0)
        win = dict(start=a0, end=min(float(params.get("end") or 1e9), a0 + WINDOW))
        y0, _ = render(rel, win)
        y1, _ = render(rel, dict(params, **win))
        E0, e = _clap_of([y0, y1])
        close = float(e @ E0 / (np.linalg.norm(e) * np.linalg.norm(E0) + 1e-9))
    d = e / np.linalg.norm(e) - E0 / np.linalg.norm(E0)
    clean = {k: v for k, v in (params or {}).items() if k not in ("start", "end")}
    con.execute("INSERT INTO edit_ratings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), rel, s["id"], source, move, family or "+".join(sorted(param_families(clean))) or "none",
                 material, arm, json.dumps(clean), d.astype(np.float16).tobytes(), close, int(np.sign(rating)), reason))
    con.commit()
    _EM.clear()
    return dict(ok=True)


def _ratings(con):
    return _rdb(con).execute("SELECT * FROM edit_ratings ORDER BY ts").fetchall()


def _learned(con, material):
    """From your ratings and reactions: a preference per move and per family, and a strength per family.
    Moves: Beta(1 + 👍, 1 + 👎) with "sounds processed" counting double (only you can hear artifacts).
    Families: also from use / save / ✕ on suggestion cards. Strength: ×1.25 per "too subtle", ×0.8 per "too much"."""
    mv, fam, much = {}, {}, {}
    bump = lambda d, k, i, v: d.setdefault(k, [0.0, 0.0]).__setitem__(i, d[k][i] + v)
    for r in _ratings(con):
        if r["material"] != material:
            continue
        good = r["rating"] > 0
        w = 2.0 if r["reason"] == "sounds processed" else 1.0
        bump(mv, r["move"], 0 if good else 1, w)
        fams = (set((r["family"] or "").split("+")) | param_families(json.loads(r["params"] or "{}"))) - {"", "none"}
        for f in fams:
            bump(fam, f, 0 if good else 1, 1.0)
            if r["reason"] in ("too much", "too subtle"):  # on a combination, the blame is shared between its moves
                much[f] = much.get(f, 0) + (1 if r["reason"] == "too subtle" else -1) / len(fams)
    for r in con.execute("SELECT value, context FROM events WHERE type='suggest' AND value != 0 AND value != 0.5"):
        try:
            ctx = json.loads(r["context"] or "{}")
        except Exception:
            continue
        if ctx.get("material") == material:
            for f in (ctx.get("family") or "").split("+"):
                bump(fam, f, 0 if r["value"] > 0 else 1, 0.5 * (2 if r["value"] >= 2 else 1))
    beta = lambda d, k: (1 + d.get(k, [0, 0])[0]) / (2 + sum(d.get(k, [0, 0]))) - 0.5
    strength = {f: float(min(2.0, max(0.5, 1.25 ** n))) for f, n in much.items()}
    return (lambda m: beta(mv, m)), (lambda f: beta(fam, f)), strength


_EM = {}


def _edit_X(rows_or_items, P):
    """Edit-model features: how the sound moved (CLAP difference, 16 principal directions of your library), how strong
    the edit is, and the material."""
    X = []
    for d, p, mat in rows_or_items:
        X.append(np.r_[d @ P, _param_feats(p), [float(mat == m) for m in MATERIALS]])
    return np.array(X)


def edit_model(con=None):
    """A small Bayesian logistic regression on your 👍/👎, once there are enough of them (8+, with 3+ of each).
    Returns (predict(d, params, material) -> logit, info)."""
    if "m" in _EM:
        return _EM["m"]
    from . import taste
    con = con or connect()
    rows = _ratings(con)
    P = taste._library(taste._db())["fz"].P[:, :16]
    y = np.array([r["rating"] > 0 for r in rows], float)
    info = dict(n=len(rows), likes=int(y.sum()), on=False, auc=None)
    if len(rows) < 8 or y.sum() < 3 or (1 - y).sum() < 3:
        _EM["m"] = (None, info)
        return _EM["m"]
    items = [(np.frombuffer(r["delta"], np.float16).astype(np.float32), json.loads(r["params"] or "{}"), r["material"])
             for r in rows]
    X = _edit_X(items, P)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    beta, cov = taste.fit_blr(Z, y, np.ones(len(y)), prior_var=0.5)
    if len(rows) >= 12:  # leave-one-out: does it predict a rating it hasn't seen?
        from .taste_report import _auc
        s = np.array([(Z[i] @ taste.fit_blr(np.delete(Z, i, 0), np.delete(y, i), np.ones(len(y) - 1), prior_var=0.5)[0])
                      for i in range(len(y))])
        info["auc"] = _auc(y.astype(bool), s)
    info["on"] = True

    def predict(d, p, mat):
        return float(((_edit_X([(d, p, mat)], P)[0] - mu) / sd) @ beta)
    _EM["m"] = (predict, info)
    return _EM["m"]


# ---------------------------------------------------------------- suggest

def suggest(rel, project_key=None, start=None, end=None, n=3, seed=None, log=True):
    from .edit import render, preview
    con = connect()
    s = con.execute("SELECT * FROM samples WHERE path=?", (rel,)).fetchone()
    if s is None:
        raise ValueError("not a library sample")
    material = MATERIAL.get(s["category"], "melodic")
    key = (s["key"] + ("m" if s["scale"] == "minor" and not s["key"].endswith("m") else "")) if s["key"] else None
    critic = Critic(rel)
    if not critic.ok():
        return dict(error="the taste model needs a few more ★ before it can judge edits")
    a0 = float(start or 0)
    full_end = float(end) if end else None
    win_end = min(full_end or 1e9, a0 + WINDOW)
    base = dict(start=a0, end=win_end)

    mprior, fprior, strength = _learned(con, material)
    em, em_info = edit_model(con)
    w_em = 0.5 * min(1.0, em_info["n"] / 30) if em else 0.0  # the edit model earns its say as your ratings grow
    cands = [(i, f, l, p) for i, f, l, p in moves(material, key, project_key, k=strength)]
    renders = {}

    def judge(i, f, l, p, e, t):
        close = float(e @ E0 / (np.linalg.norm(e) * np.linalg.norm(E0) + 1e-9))
        fams = f.split("+")
        learned = 0.6 * float(np.mean([fprior(x) for x in fams])) + 0.8 * mprior(i)
        d = e / np.linalg.norm(e) - E0 / np.linalg.norm(E0)
        lm = em(d, p, material) if em else 0.0
        _LAST[(rel, i)] = dict(e=e, E0=E0, close=close, params=dict(p))
        return dict(id=i, family=f, label=l, params=p, taste=float(t), delta=float(t - t0), close=close,
                    learned=round(learned + w_em * lm, 2),
                    score=float(t - t0 + LAMBDA * (close - 1) + learned + w_em * lm), e=e)

    def run(items):
        ys = []
        for i, f, l, p in items:
            y, _ = render(rel, dict(base, **p))
            ys.append(y)
        return ys

    y0, _ = render(rel, base)
    E0 = _clap_of([y0])[0]
    t0 = float(critic.score(E0[None])[0])
    ys = run(cands)
    E = _clap_of(ys)
    T = critic.score(E)
    if len(_LAST) > 2000:
        _LAST.clear()
    for (i, f, l, p), e, t in zip(cands, E, T):
        renders[i] = judge(i, f, l, p, e, t)
    # pairs: the best of two complementary families, together
    best = {}
    for r in renders.values():
        if r["family"] not in best or r["score"] > best[r["family"]]["score"]:
            best[r["family"]] = r
    pairs = []
    for fa, fb in PAIRS.get(material, []):
        if fa in best and fb in best:
            ra, rb = best[fa], best[fb]
            pairs.append((f"{ra['id']}+{rb['id']}", f"{fa}+{fb}", f"{ra['label']}, {rb['label']}",
                          {**ra["params"], **rb["params"]}))
    if pairs:
        Ep = _clap_of(run(pairs))
        for (i, f, l, p), e, t in zip(pairs, Ep, critic.score(Ep)):
            renders[i] = judge(i, f, l, p, e, t)

    # picks: best per family group (a pair counts as both its families), three different ones
    ranked = sorted(renders.values(), key=lambda r: -r["score"])
    picks, used = [], set()
    for r in ranked:
        fams = set(r["family"].split("+"))
        if fams & used:
            continue
        picks.append(dict(r, arm="critic"))
        used |= fams
        if len(picks) >= n:
            break
    rest = [r for r in renders.values() if not set(r["family"].split("+")) & used]
    if rest:
        picks.append(dict(random.Random(seed).choice(rest), arm="wildcard"))
    out = []
    for r in picks:
        params = dict(r["params"], start=a0, end=full_end)
        out.append(dict(id=r["id"], family=r["family"], label=r["label"], arm=r["arm"], params=params,
                        url=preview(rel, params), score=round(r["score"], 2), delta=round(r["delta"], 2),
                        close=round(r["close"], 2), learned=r["learned"], material=material))
    from .taste import log_event
    for r in (out if log else []):  # shown (value 0): the denominator for "did the critic's picks beat the wildcard?"
        log_event(rel, "suggest", 0, s["id"], dict(move=r["id"], family=r["family"], arm=r["arm"], material=material,
                                                   action="shown"))
    return dict(original=round(t0, 2), material=material, suggestions=out, tried=len(renders),
                learning=dict(ratings=em_info["n"], model_on=bool(em), model_auc=em_info["auc"],
                              strengths={f: round(v, 2) for f, v in strength.items() if abs(v - 1) > 0.01}),
                note="judged by your taste model; quality comes from the moves themselves")


def feedback(rel, sample_id, move, family, arm, material, action):
    """action: play | apply | save | dismiss. Stored as 'suggest' events (value: apply 1, save 2, dismiss -1)."""
    from .taste import log_event
    v = {"play": 0.5, "apply": 1, "save": 2, "dismiss": -1}.get(action)
    if v is None:
        raise ValueError(action)
    log_event(rel, "suggest", v, sample_id, dict(move=move, family=family, arm=arm, material=material, action=action))


def stats():
    """How each slot does (share of shown suggestions applied or saved, critic picks vs the wildcard), your 👍/👎 per
    slot, and the edit model's state."""
    con = connect()
    rated = {}
    for r in _ratings(con):
        a = r["arm"] or ("your edits" if r["source"] == "editor" else "?")
        x = rated.setdefault(a, dict(up=0, down=0))
        x["up" if r["rating"] > 0 else "down"] += 1
    _, info = edit_model(con)
    shown, good = {}, {}
    for r in con.execute("SELECT value, context FROM events WHERE type='suggest'"):
        ctx = json.loads(r["context"] or "{}")
        arm = ctx.get("arm", "?")
        if ctx.get("action") == "shown":
            shown[arm] = shown.get(arm, 0) + 1
        elif ctx.get("action") in ("apply", "save"):
            good[arm] = good.get(arm, 0) + 1
    return dict(slots={a: dict(shown=shown[a], kept=good.get(a, 0), rate=round(good.get(a, 0) / shown[a], 3)) for a in shown},
                ratings=rated, model=info)
