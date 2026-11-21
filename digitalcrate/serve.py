"""Local server for Browser.html: serves the library and handles favourites.

    python -m digitalcrate serve        ->  http://localhost:8765

Favourites are stored in SQLite and hardlinked into SampleLibrary/Favorites/<category>/ so they show up
in Ableton's browser straight away. Works for library samples and for variation-family files alike.
"""
import json
import os
import shutil
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
from urllib.parse import unquote

from . import config as C
from .db import connect

FAV_DIR = C.LIB_ROOT / "Favorites"
JOBS = {}  # id -> dict(target, proc, log)


def start_job(kind, args, target):
    import subprocess, sys, time
    jid = str(int(time.time() * 1000))
    logf = C.DATA_DIR / f"{kind}_{jid}.log"
    cmd = [sys.executable, "-u", "-m", "digitalcrate", kind] + args
    proc = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent.parent), stdout=open(logf, "w"),
                            stderr=subprocess.STDOUT)
    JOBS[jid] = dict(kind=kind, target=target, proc=proc, log=logf)
    return jid


def start_ingest(target, drums):
    return start_job("ingest", [target] + (["--drums"] if drums else []), target)


def job_status(kind=None):
    import re
    out = []
    for jid, j in sorted(JOBS.items()):
        if kind and j.get("kind", "ingest") != kind:
            continue
        txt = j["log"].read_text(errors="ignore") if j["log"].exists() else ""
        lines = [l for l in re.split(r"[\r\n]+", txt) if l.strip() and not re.search(r"Warning|warn|redirects|Loading weights", l)]
        rc = j["proc"].poll()
        m = re.search(r"INGEST TRACKS ([\d,]+)", txt)
        out.append(dict(id=jid, kind=j.get("kind"), target=j["target"], running=rc is None,
                        ok=rc == 0 and ("INGEST DONE" in txt or "SCOUT DONE" in txt),
                        tracks=m.group(1) if m else "", tail=[l for l in lines if not l.startswith("INGEST TRACKS")][-6:]))
    return out


def _db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS favorites (path TEXT PRIMARY KEY, sample_id TEXT,
                   label TEXT, added_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def _fav_target(rel):
    p = Path(rel)
    parts = p.parts
    if parts[0] == "Variations":           # Variations/<cat>/<family>/<NN name>.wav
        cat = parts[1] if len(parts) > 3 else "Variations"
        return FAV_DIR / cat / f"{parts[-2][:60]} — {p.name}"
    return FAV_DIR / (parts[0] if len(parts) > 1 else "Misc") / p.name


def set_fav(rel, on, sample_id=None, label=None):
    rel = rel.lstrip("/")
    src = (C.LIB_ROOT / rel).resolve()
    if C.LIB_ROOT.resolve() not in src.parents or not src.exists():
        raise ValueError("not a library file")
    con = _db()
    dst = _fav_target(rel)
    if on:
        con.execute("INSERT OR REPLACE INTO favorites(path, sample_id, label) VALUES (?,?,?)", (rel, sample_id, label))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
    else:
        con.execute("DELETE FROM favorites WHERE path=?", (rel,))
        dst.unlink(missing_ok=True)
        if dst.parent.exists() and not any(dst.parent.iterdir()):
            dst.parent.rmdir()
    con.commit()


def _sketch_db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS sketches (name TEXT PRIMARY KEY, state TEXT,
                   updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def bounce(req):
    """Audio rendered in the browser (chop-pad pattern, sketch mixdown) -> a new sample with provenance."""
    import base64, io
    import numpy as np
    import soundfile as sf
    from .edit import store
    y, sr = sf.read(io.BytesIO(base64.b64decode(req["wav"])), dtype="float32", always_2d=True)
    y = y.T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, 0)
    if sr != C.SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, C.SR, sr, axis=1).astype(np.float32)
    y *= 0.891 / (np.abs(y).max() + 1e-9)
    con = connect()
    parent = con.execute("SELECT s.*, t.artist, t.title FROM samples s JOIN tracks t ON t.id=s.track_id WHERE s.path=?",
                         (unquote(req["parent"]),)).fetchone()
    if parent is None:
        raise ValueError("bounces start from a library sample")
    p = dict(semis=float(req.get("semis") or 0))
    if req.get("key"):
        p["tune_key"] = req["key"]   # sketch/pads conformed to a project key: store that key
    ov = dict(kind=req.get("kind", "loop"), bpm=req.get("bpm"), bars=req.get("bars"), tag=req.get("tag", "bounce"),
              category=req.get("category"),
              ops=dict(bounce=req.get("ops") or {}))
    row = store(parent, parent["path"], y, p, req.get("name") or None, override=ov, prefix=req.get("prefix", "Bounce"))
    from .taste import log_event
    log_event(row["path"], "star", 1, row["id"])
    set_fav(row["path"], True, row["id"], f"{req.get('tag', 'bounce')} from {parent['artist']} — {parent['title']}")
    return row



def _with_partners(row):
    """Attach fresh 'goes well with' picks to a newly saved sample. If scoring fails, the browser
    falls back to the source clip's picks, so the save itself still succeeds."""
    try:
        from .build import partners_for
        row["partners"] = partners_for(row["id"])
    except Exception as e:
        print("partners for new sample failed:", e)
    return row

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        if self.path.endswith(".html") or self.path in ("/", "/Browser.html") or self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, f, ctype, headers=None):
        data = Path(f).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self.path = "/Browser.html"
        if self.path == "/Browser.html" and not (C.LIB_ROOT / "Browser.html").exists():
            msg = (f"<body style='font:16px system-ui;background:#0e1013;color:#e6e6e6;padding:40px'><h2>No library yet</h2>"
                   f"<p>{C.LIB_ROOT} has no Browser.html. Mine some music first:</p><pre>python -m digitalcrate scan\n"
                   f"python -m digitalcrate process --top 50\npython -m digitalcrate build</pre><p>then reload this page.</p></body>")
            body = msg.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] in ("/pairtest", "/drumlabel"):
            return self._file(Path(__file__).resolve().parent / "static" / (self.path.split("?")[0][1:] + ".html"),
                              "text/html", {"Cache-Control": "no-store"})
        if self.path.split("?")[0] == "/shootout":
            return self._file(Path(__file__).resolve().parent / "static" / "shootout.html", "text/html",
                              {"Cache-Control": "no-store"})
        if self.path.startswith("/studio/"):
            name = Path(unquote(self.path.split("?")[0])).name
            f = Path(__file__).resolve().parent / "static" / name
            if f.exists():
                return self._file(f, "text/css" if name.endswith(".css") else "application/javascript",
                                  {"Cache-Control": "no-store"})
        if self.path.startswith("/api/taste"):
            from .taste import scores_payload
            recent = 3 if "recent=1" in self.path else None
            return self._json(scores_payload(recent))
        if self.path.startswith("/api/onsets?"):
            from urllib.parse import parse_qs, urlparse
            from .edit import onsets
            return self._json(onsets(parse_qs(urlparse(self.path).query)["path"][0]))
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/search":
                from .search import text_search
                return self._json(text_search(q["q"], int(q.get("k", 400))))
            if u.path == "/api/galaxy":
                from .search import galaxy
                return self._json(galaxy())
            if u.path == "/api/conform":
                from .conform import render
                f, info = render(q["path"], q.get("key") or None, float(q["bpm"]) if q.get("bpm") else None,
                                 float(q["src"]) if q.get("src") else None)
                return self._file(f, "audio/wav", {"X-Conform": json.dumps(info)})
            if u.path == "/api/chords":
                from .harmony import suggest
                return self._json(suggest(q["path"], float(q["bpm"]) if q.get("bpm") else None, int(q.get("bpc", 1))))
            if u.path == "/api/pulse":
                from .conform import pulse
                return self._json(pulse(q["path"]))
            if u.path == "/api/conform/info":
                from .conform import lookup, plan
                row, shift = lookup(q["path"])
                se, ti, info = plan(row, shift, q.get("key") or None, float(q["bpm"]) if q.get("bpm") else None)
                return self._json(dict(info, semis=se, time=ti))
            if u.path == "/api/midi":
                from .midi import transcribe
                return self._json(transcribe(q["path"], float(q["bpm"]) if q.get("bpm") else None))
            if u.path == "/api/tune/report":
                from .edit import _load
                from .retune import report
                return self._json(report(_load(q["path"]), q["key"]))
            if u.path == "/api/link":
                from .link import status
                return self._json(status())
            if u.path == "/api/ytscout":
                from .ytscout import results, PRESETS
                return self._json(dict(presets=PRESETS, results=results(q.get("q") or None)))
            if u.path == "/api/shootout":
                from .shootout import manifest, votes, results
                return self._json(dict(manifest(q.get("round")), votes=votes(), results=results()))
            if u.path == "/api/pairtest":
                from .listening import pair_manifest, _db as listen_db
                m = pair_manifest([g for g in q.get("excl", "").split("|") if g], new=q.get("new") == "1")
                v = {r["trial"]: r["rating"] for r in listen_db().execute("SELECT * FROM pair_votes")}
                return self._json(dict(m, votes=v))
            if u.path == "/api/pairtest/results":
                from .listening import pair_results
                return self._json(pair_results())
            if u.path == "/api/drumlabel":
                from .listening import drum_manifest, drum_labels
                return self._json(dict(drum_manifest(new=q.get("new") == "1"), labels=drum_labels()))
            if u.path == "/api/sketches":
                return self._json([dict(r) for r in _sketch_db().execute("SELECT * FROM sketches ORDER BY updated_at DESC")])
        except Exception as e:
            return self._json({"error": str(e)}, 400)
        if u.path == "/api/jobs":
            return self._json(job_status(q.get("kind")))
        if self.path == "/api/favs":
            rows = _db().execute("SELECT path, sample_id, label, added_at FROM favorites ORDER BY added_at DESC")
            return self._json([dict(r) for r in rows])
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            from .taste import log_event
            path = unquote(req.get("path", ""))
            if self.path == "/api/fav":
                on = bool(req.get("on", True))
                set_fav(path, on, req.get("id"), req.get("label"))
                log_event(path, "star" if on else "unstar", 1, req.get("id"))
            elif self.path == "/api/edit/preview":
                from .edit import preview
                return self._json({"url": preview(path, req.get("params", {}))})
            elif self.path == "/api/edit/save":
                from .edit import save
                row = save(path, req.get("params", {}), req.get("name") or None)
                log_event(row["path"], "star", 1, row["id"])  # you made it: counts as a like
                set_fav(row["path"], True, row["id"], f"edit of {req.get('label', path)}")
                return self._json({"row": _with_partners(row)})
            elif self.path == "/api/recat":
                from .recat import recategorise
                res = recategorise(req["id"], req["category"], req["subtype"])
                log_event(res["path"], "recat", None, req["id"], {"category": req["category"], "subtype": req["subtype"]})
                return self._json(res)
            elif self.path == "/api/refsearch":
                from .search import reference_search
                return self._json(reference_search(req["target"]))
            elif self.path == "/api/ytscout":
                mode = "pads" if req.get("mode") == "pads" else "voice"
                return self._json({"job": start_job("ytscout", [req["query"], "--n", str(int(req.get("n", 15))), "--mode", mode],
                                                    req["query"])})
            elif self.path == "/api/ytscout/mark":
                from .ytscout import mark
                mark(req["id"], req["status"])
            elif self.path == "/api/link/tempo":
                from .link import set_tempo
                set_tempo(req["bpm"])
            elif self.path == "/api/bounce":
                return self._json({"row": _with_partners(bounce(req))})
            elif self.path == "/api/sketch/save":
                con = _sketch_db()
                con.execute("""INSERT INTO sketches(name, state, updated_at) VALUES (?,?,CURRENT_TIMESTAMP)
                               ON CONFLICT(name) DO UPDATE SET state=excluded.state, updated_at=CURRENT_TIMESTAMP""",
                            (req["name"], json.dumps(req["state"])))
                con.commit()
            elif self.path == "/api/chords/midi":
                from .harmony import write_midi
                return self._json(write_midi(req["name"], req["chords"], float(req["step"]), float(req["tempo"])))
            elif self.path == "/api/pair/save":
                from .combos import save_pair
                return self._json(save_pair(unquote(req["src"]), unquote(req["partner"]), req.get("name") or None))
            elif self.path == "/api/stems":
                from .combos import write_stems
                return self._json(write_stems(req["name"], req["stems"], req.get("key"), req.get("bpm")))
            elif self.path == "/api/pairtest/vote":
                from .listening import pair_vote
                return self._json({"ok": pair_vote(req["trial"], req.get("rating"))})
            elif self.path == "/api/drumlabel/vote":
                from .listening import drum_vote
                return self._json({"ok": drum_vote(req["id"], req.get("pieces"))})
            elif self.path == "/api/shootout/vote":
                from .shootout import vote
                return self._json({"ok": vote(req["clip"], req.get("rating"))})
            elif self.path == "/api/sketch/delete":
                con = _sketch_db(); con.execute("DELETE FROM sketches WHERE name=?", (req["name"],)); con.commit()
            elif self.path == "/api/ingest":
                return self._json({"job": start_ingest(req["target"], bool(req.get("drums")))})
            elif self.path == "/api/export":
                from .export import export, favorites_paths, kit_paths
                scope = req.get("scope")
                paths = favorites_paths() if scope == "favorites" else kit_paths(req["kit"]) if scope == "kit" \
                    else [unquote(p) for p in req.get("paths", [])]
                return self._json(export(paths, req.get("name"), reveal=req.get("reveal", True), rack=bool(req.get("rack")),
                                         key=req.get("key") or None, bpm=float(req["bpm"]) if req.get("bpm") else None,
                                         midi=bool(req.get("midi")), chop=bool(req.get("chop"))))
            elif self.path == "/api/event":
                log_event(path, req["type"], req.get("value"), req.get("id"), req.get("context"))
            else:
                return self._json({"error": "not found"}, 404)
            return self._json({"ok": True})
        except Exception as e:
            return self._json({"error": str(e)}, 400)


def serve(port=8765, open_browser=True):
    _db()
    from .edit import clear_previews
    clear_previews()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(C.LIB_ROOT)))
    url = f"http://localhost:{port}/"
    print(f"DigitalCrate at {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
