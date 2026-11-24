"""Discogs styles from the audio itself (Essentia's Discogs-EffNet, 400 styles such as "Funk / Soul---Neo Soul" or
"Jazz---Spiritual Jazz"), for every song in the collection, mined or not.

    digitalcrate styles [--limit N]

Per song: three 10-second windows (at 20%, 50% and 80% of the way through) are decoded with ffmpeg, cut into the
model's ~2-second mel patches, and the patches' style probabilities and 1280-d embeddings averaged. Stored in the
`styles` table: the top styles, and the embedding (float16), which is what "related music" uses: songs whose
embeddings are close sound alike in style, whatever their tags say.

The model (models/discogs/, from essentia.upf.edu, CC BY-NC-SA 4.0) runs on onnxruntime, so no TensorFlow needed.
"""
import json
import subprocess
import time

import numpy as np

from . import config as C
from .db import connect

DIR = C.MODELS_DIR / "discogs"
MODEL = DIR / "discogs-effnet-bsdynamic-1.onnx"
BASE = "https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bsdynamic-1"
SR, FRAME, HOP, PATCH, PATCH_HOP = 16000, 512, 256, 128, 62
_sess = None
_classes = None


def _ensure():
    if not MODEL.exists():
        DIR.mkdir(parents=True, exist_ok=True)
        for ext in (".onnx", ".json"):
            subprocess.run(["curl", "-sfL", "--retry", "5", "--retry-all-errors", "-o", str(DIR / (MODEL.stem + ext)),
                            BASE + ext], check=True)


def classes():
    global _classes
    if _classes is None:
        _ensure()
        _classes = json.loads((DIR / (MODEL.stem + ".json")).read_text())["classes"]
    return _classes


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        _ensure()
        import os
        so = ort.SessionOptions()
        if os.environ.get("DC_THREADS"):
            so.intra_op_num_threads = int(os.environ["DC_THREADS"])
        _sess = ort.InferenceSession(str(MODEL), so, providers=["CPUExecutionProvider"])
    return _sess


def _window(path, at, dur=10.0):
    out = subprocess.run(["ffmpeg", "-v", "quiet", "-ss", f"{max(0.0, at):.2f}", "-t", f"{dur}", "-i", str(path),
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(out, np.float32)


def melspec(y):
    import essentia.standard as es
    mel = es.TensorflowInputMusiCNN()
    fr = [mel(f) for f in es.FrameGenerator(np.ascontiguousarray(y, dtype=np.float32), frameSize=FRAME, hopSize=HOP,
                                             startFromZero=True)]
    return np.array(fr, np.float32) if fr else np.zeros((0, 96), np.float32)


def predict(windows):
    """[mono 16 kHz arrays] -> (style probabilities (400,), embedding (1280,)), or None if too short."""
    patches = []
    for y in windows:
        m = melspec(y)
        for a in range(0, len(m) - PATCH + 1, PATCH_HOP):
            patches.append(m[a:a + PATCH])
    if not patches:
        return None
    s = _session()
    p, e = s.run(["activations", "embeddings"], {"melspectrogram": np.stack(patches)})
    return p.mean(0), e.mean(0)


def analyse(path, duration):
    d = duration or 0
    ats = [d * f - 5 for f in (0.2, 0.5, 0.8)] if d > 40 else [0.0]
    return predict([w for w in (_window(path, a, 10.0 if d > 40 else 30.0) for a in ats) if len(w) > SR * 3])


def _db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS styles (track_id INTEGER PRIMARY KEY, top TEXT, probs BLOB, emb BLOB,
                   created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def run(limit=None, con=None):
    from tqdm import tqdm
    con = _db(con or connect())
    rows = con.execute("""SELECT t.id, t.path, t.duration FROM tracks t LEFT JOIN styles s ON s.track_id=t.id
                          WHERE s.track_id IS NULL AND t.status != 'duplicate'
                          ORDER BY (t.status='done') DESC, t.id""").fetchall()[:limit]
    names, t0, n = classes(), time.time(), 0
    from .memguard import breathe
    seen_ = 0
    for r in tqdm(rows, desc="styles", mininterval=5):
        seen_ += 1
        if seen_ % 25 == 1:  # every 25: wait while memory is low or a job you started runs
            breathe()
        f = r["path"]
        try:
            res = analyse(f, r["duration"])
        except Exception as e:
            print(f"  {r['path']}: {e}")
            res = None
        if res is None:
            con.execute("INSERT OR REPLACE INTO styles (track_id, top) VALUES (?, '[]')", (r["id"],))
            con.commit()
            continue
        p, e = res
        top = [[names[i], round(float(p[i]), 3)] for i in np.argsort(-p)[:8]]
        con.execute("INSERT OR REPLACE INTO styles (track_id, top, probs, emb) VALUES (?,?,?,?)",
                    (r["id"], json.dumps(top), p.astype(np.float16).tobytes(), e.astype(np.float16).tobytes()))
        n += 1
        con.commit()  # right away: holding the write lock across songs blocks the app and other jobs
    con.commit()
    print(f"styled {n} songs in {time.time() - t0:.0f}s")
    return n


# ---- using them -----------------------------------------------------------------------------------------------------

def family_of(top, min_p=0.15):
    """A genre family from the top styles: the family with the most probability among the styles above min_p."""
    from .genre import from_tag
    votes = {}
    for name, p in top:
        if p < min_p:
            continue
        parent, style = name.split("---", 1)
        f = from_tag(style)
        if not f or f == "Other":
            f = PARENT.get(parent)
        if f:
            votes[f] = votes.get(f, 0) + p
    return max(votes, key=votes.get) if votes else None


PARENT = {"Blues": "Folk", "Classical": "Classical", "Electronic": "Electronic", "Folk, World, & Country": "Folk",
          "Funk / Soul": "Soul & R&B", "Hip Hop": "Hip-Hop", "Jazz": "Jazz", "Latin": "World", "Pop": "Pop",
          "Reggae": "World", "Rock": "Rock & Indie", "Stage & Screen": "Soundtrack", "Children's": "Pop",
          "Brass & Military": "Classical", "Non-Music": None}


def families(con=None):
    """track_id -> family from audio styles, for tracks whose tags and artist say nothing: the artist's most common
    family across all their songs (one song can sound off-genre), else the song's own."""
    import collections
    con = con or connect()
    try:
        rows = con.execute("""SELECT s.track_id, s.top, t.artist FROM styles s JOIN tracks t ON t.id=s.track_id
                              WHERE s.top != '[]'""").fetchall()
    except Exception:
        return {}
    own, by_artist = {}, collections.defaultdict(collections.Counter)
    for r in rows:
        f = family_of(json.loads(r["top"]))
        if f:
            own[r["track_id"]] = f
            a = " ".join((r["artist"] or "").lower().split())
            if a and a not in ("various artists", "unknown artist"):
                by_artist[a][f] += 1
    art = {r["track_id"]: " ".join((r["artist"] or "").lower().split()) for r in rows}
    return {t: (by_artist[art[t]].most_common(1)[0][0] if art[t] in by_artist else f) for t, f in own.items()}


def embeddings(con=None):
    """(track_ids, (n, 1280) unit-normalised float32 embeddings, top styles)"""
    con = con or connect()
    rows = con.execute("SELECT track_id, emb, top FROM styles WHERE emb IS NOT NULL").fetchall()
    if not rows:
        return [], np.zeros((0, 1280), np.float32), []
    E = np.stack([np.frombuffer(r["emb"], np.float16).astype(np.float32) for r in rows])
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    return [r["track_id"] for r in rows], E, [json.loads(r["top"]) for r in rows]
