"""Words in vocal samples (Whisper large-v3-turbo, on Apple's MLX): what's sung, so you can search by lyric and tell
a chop of a word from a wordless "ooh".

    digitalcrate lyrics [--limit N]     transcribe vocal samples that haven't been yet

Tested on 80 random samples: lyrics in sung phrases come out close to right; on pads (which have no words) Whisper
still "hears" "Thank you." or "you" in 19 of 20, the classic Whisper hallucination, so those, near-silent segments,
low-confidence segments and stutters ("ba-a-a-a…") are dropped. That left 2 false hits in 20 pads. Only vocal
categories are transcribed, in whatever language is sung (detected). About 2 s per sample.

Chops shorter than 0.8 s are too short to transcribe on their own; they get the word the longer phrase from the same
spot in the song was heard singing there, when there is one.
"""
import json
import re
import time

import numpy as np

from . import config as C
from .db import connect

MODEL = "mlx-community/whisper-large-v3-turbo"
CATS = ("Vocals", "Vocal Atmospheres")
MIN_DUR = 0.8
BAD = {"thank you", "you", "thank you for watching", "thanks for watching", "so", "the", "oh", "bye", "music", ""}


def _db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS words (sample_id TEXT PRIMARY KEY, text TEXT, words TEXT,
                   how TEXT, model TEXT, lang TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def _clean(r):
    """Whisper's result -> (text, [[word, start, end], ...]) keeping only what's likely really sung."""
    keep = []
    for sg in r.get("segments", []):
        raw = sg.get("text", "")
        t = re.sub(r"[^\w\s']", "", raw.lower()).strip()
        if (t in BAD or sg.get("no_speech_prob", 1) >= 0.6 or sg.get("avg_logprob", -9) <= -1.0
                or sg.get("compression_ratio", 9) >= 2.4 or re.search(r"\b(\w+)\b(?:[\s-]+\1\b){5,}", t)
                or re.search(r"(\w)(-\1){5,}", raw.lower())):
            continue
        keep += [[w["word"].strip(), round(w["start"], 2), round(w["end"], 2)] for w in sg.get("words", [])
                 if w.get("probability", 0) > 0.4 and w["word"].strip()]
    return " ".join(w[0] for w in keep), keep, r.get("language")


def transcribe(y16):
    import mlx_whisper
    r = mlx_whisper.transcribe(y16, path_or_hf_repo=MODEL, temperature=0.0,
                               condition_on_previous_text=False, word_timestamps=True, verbose=None)
    return _clean(r)


def _load16(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(1)
    return resample_poly(y, 16000, sr).astype(np.float32) if sr != 16000 else y


def run(limit=None, con=None, quiet=False):
    from tqdm import tqdm
    con = _db(con or connect())
    done = {r[0] for r in con.execute("SELECT sample_id FROM words")}
    rows = [r for r in con.execute(f"""SELECT id, path, track_id, start, dur, kind FROM samples
              WHERE category IN ({",".join("?" * len(CATS))}) AND path NOT LIKE '_Reference/%'
              ORDER BY created_at DESC""", CATS) if r["id"] not in done]
    long_ = [r for r in rows if r["dur"] >= MIN_DUR][:limit]
    t0, n = time.time(), 0
    for r in tqdm(long_, desc="words", disable=quiet, mininterval=5):
        f = C.LIB_ROOT / r["path"]
        if not f.exists():
            continue
        try:
            text, ws, lang = transcribe(_load16(f))
        except Exception as e:  # one bad file shouldn't stop the run
            print(f"  {r['id']}: {e}")
            continue
        con.execute("INSERT OR REPLACE INTO words (sample_id, text, words, how, model, lang) VALUES (?,?,?,?,?,?)",
                    (r["id"], text, json.dumps(ws), "heard", MODEL, lang))
        n += 1
        con.commit()  # right away: holding the write lock across songs blocks the app and other jobs
    con.commit()
    m = inherit(con)
    if not quiet:
        print(f"transcribed {n} vocal samples in {time.time() - t0:.0f}s; {m} short chops got a word from their phrase")
    return n


def inherit(con):
    """Short chops: the word a transcribed phrase from the same track was singing at that moment."""
    heard = collections_by_track(con)
    rows = con.execute(f"""SELECT s.id, s.track_id, s.start, s.dur FROM samples s LEFT JOIN words w ON w.sample_id=s.id
                          WHERE w.sample_id IS NULL AND s.dur < ? AND s.category IN ({",".join("?" * len(CATS))})
                          AND s.path NOT LIKE '_Reference/%'""", (MIN_DUR, *CATS)).fetchall()
    n = 0
    for r in rows:
        a, b = r["start"], r["start"] + r["dur"]
        best = None
        for start, dur, ws in heard.get(r["track_id"], ()):
            if start <= a and b <= start + dur + 0.05:  # the phrase covers the chop
                hit = [w for w in ws if w[1] + start < b and w[2] + start > a]
                best = " ".join(w[0] for w in hit)
                break
        if best is not None:
            con.execute("INSERT OR REPLACE INTO words (sample_id, text, words, how, model) VALUES (?,?,?,?,?)",
                        (r["id"], best, "[]", "from phrase", MODEL))
            n += 1
    con.commit()
    return n


def collections_by_track(con):
    out = {}
    for r in con.execute("""SELECT s.track_id, s.start, s.dur, w.words FROM words w JOIN samples s ON s.id=w.sample_id
                            WHERE w.how='heard' AND s.kind != 'oneshot'"""):
        out.setdefault(r["track_id"], []).append((r["start"], r["dur"], json.loads(r["words"] or "[]")))
    return out


def for_browser(con, ids):
    """index-aligned: text if words were heard, '' if transcribed and wordless, None if not transcribed."""
    try:
        m = {r[0]: r[1] for r in con.execute("SELECT sample_id, text FROM words")}
    except Exception:
        return [None] * len(ids)
    return [m.get(i) for i in ids]
