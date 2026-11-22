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


def moves(material, key=None, project_key=None):
    """[(id, family, label, params)] for this kind of sample."""
    M = []
    add = lambda i, f, l, p: M.append((i, f, l, p)) if p is not None else None
    if material == "vocal":
        add("tape_up2", "lift", "tape up 2 (pitch and speed)", dict(tape=True, semis=2))
        add("clean_up3", "lift", "pitch up 3", dict(semis=3))
        add("clean_up5", "lift", "pitch up 5 (a fourth: still in key)", dict(semis=5))
        if key:
            add("tune_own", "tune", f"tuned to its own key ({key}), natural", dict(tune_key=key, tune_strength=0.8, tune_speed=60))
        if project_key and project_key != key:
            add("tune_proj", "tune", f"tuned to your project ({project_key}), natural",
                dict(tune_key=project_key, tune_strength=0.8, tune_speed=60))
        add("space_light", "space", "a little space (Supermassive)", _sm({}, mix=0.22))
        add("slow125", "slow", "slower ×1.25, same pitch", dict(stretch=1.25))
        add("warm", "tone", "softer top (Tone 7 kHz)", dict(tone=7000))
    elif material == "sustained":
        add("oct_down", "octave", "an octave down (tape)", dict(tape=True, semis=-12))
        add("fifth_down", "octave", "a fourth down (tape)", dict(tape=True, semis=-5))
        add("dark", "tone", "darker (Tone 2.5 kHz)", dict(tone=2500))
        add("darker", "tone", "much darker (Tone 1.2 kHz)", dict(tone=1200))
        add("wash", "space", "washed out (Supermassive)", _sm({}, mix=0.5, decay=0.6))
        add("slow2", "slow", "twice as slow, same pitch", dict(stretch=2.0))
        add("slow15", "slow", "slower ×1.5, same pitch", dict(stretch=1.5))
        add("reverse", "reverse", "reversed", dict(reverse=True))
    elif material == "melodic":
        add("tape_up2", "transpose", "tape up 2", dict(tape=True, semis=2))
        add("tape_down2", "transpose", "tape down 2", dict(tape=True, semis=-2))
        add("fifth_up", "transpose", "up 7 (a fifth)", dict(semis=7))
        add("space_light", "space", "some space (Supermassive)", _sm({}, mix=0.3))
        add("dark", "tone", "darker (Tone 3 kHz)", dict(tone=3000))
        add("slow15", "slow", "slower ×1.5, same pitch", dict(stretch=1.5))
        add("reverse", "reverse", "reversed", dict(reverse=True))
    else:  # percussion
        add("tape_down2", "pitch", "tape down 2 (heavier)", dict(tape=True, semis=-2))
        add("tape_up2", "pitch", "tape up 2 (tighter)", dict(tape=True, semis=2))
        add("dark", "tone", "darker (Tone 3.5 kHz)", dict(tone=3500))
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


# ---------------------------------------------------------------- learned preferences per family

def _prior(con, material):
    """Beta(1+kept, 1+dismissed) per family, from your reactions to past suggestions."""
    a, b = {}, {}
    for r in con.execute("SELECT value, context FROM events WHERE type='suggest' AND value != 0"):
        try:
            ctx = json.loads(r["context"] or "{}")
        except Exception:
            continue
        if ctx.get("material") != material:
            continue
        f = ctx.get("family")
        if r["value"] > 0:
            a[f] = a.get(f, 0) + (2 if r["value"] >= 2 else 1)  # saved counts double
        else:
            b[f] = b.get(f, 0) + 1
    return lambda f: (1 + a.get(f, 0)) / (2 + a.get(f, 0) + b.get(f, 0)) - 0.5


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

    cands = [(i, f, l, p) for i, f, l, p in moves(material, key, project_key)]
    renders = {}

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
    prior = _prior(con, material)
    for (i, f, l, p), e, t in zip(cands, E, T):
        close = float(e @ E0 / (np.linalg.norm(e) * np.linalg.norm(E0) + 1e-9))
        renders[i] = dict(id=i, family=f, label=l, params=p, taste=float(t), delta=float(t - t0), close=close,
                          score=float(t - t0 + LAMBDA * (close - 1) + 0.6 * prior(f)), e=e)
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
            close = float(e @ E0 / (np.linalg.norm(e) * np.linalg.norm(E0) + 1e-9))
            pr = (prior(f.split("+")[0]) + prior(f.split("+")[1])) / 2
            renders[i] = dict(id=i, family=f, label=l, params=p, taste=float(t), delta=float(t - t0), close=close,
                              score=float(t - t0 + LAMBDA * (close - 1) + 0.6 * pr), e=e)

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
                        close=round(r["close"], 2), material=material))
    from .taste import log_event
    for r in (out if log else []):  # shown (value 0): the denominator for "did the critic's picks beat the wildcard?"
        log_event(rel, "suggest", 0, s["id"], dict(move=r["id"], family=r["family"], arm=r["arm"], material=material,
                                                   action="shown"))
    return dict(original=round(t0, 2), material=material, suggestions=out,
                tried=len(renders), note="judged by your taste model; quality comes from the moves themselves")


def feedback(rel, sample_id, move, family, arm, material, action):
    """action: play | apply | save | dismiss. Stored as 'suggest' events (value: apply 1, save 2, dismiss -1)."""
    from .taste import log_event
    v = {"play": 0.5, "apply": 1, "save": 2, "dismiss": -1}.get(action)
    if v is None:
        raise ValueError(action)
    log_event(rel, "suggest", v, sample_id, dict(move=move, family=family, arm=arm, material=material, action=action))


def stats():
    """How each slot does: share of shown suggestions applied or saved, critic picks vs the wildcard."""
    con = connect()
    shown, good = {}, {}
    for r in con.execute("SELECT value, context FROM events WHERE type='suggest'"):
        ctx = json.loads(r["context"] or "{}")
        arm = ctx.get("arm", "?")
        if ctx.get("action") == "shown":
            shown[arm] = shown.get(arm, 0) + 1
        elif ctx.get("action") in ("apply", "save"):
            good[arm] = good.get(arm, 0) + 1
    return {a: dict(shown=shown[a], kept=good.get(a, 0), rate=round(good.get(a, 0) / shown[a], 3)) for a in shown}
