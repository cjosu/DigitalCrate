"""The app in a real browser (Playwright), on a throwaway library built once per run:

  two synthetic songs mined by the real pipeline (pads, keys, melodies), plus a synthetic drum kit (kick, snare, hats,
  clap, tom, shaker one-shots, each with ~25 ms before the hit, as real drum hits have) written into the library with
  real CLAP embeddings, then `build`, then a server on a spare port. Everything the tests do (stars, deletes, sketches,
  collections) happens in that library; nothing touches yours.

    pip install playwright && playwright install chromium
    pytest --ui tests/test_ui.py          (first run downloads the separation and CLAP models)
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from conftest import SR, tone

pytestmark = pytest.mark.ui

DRUMS = r'''
import json, numpy as np, soundfile as sf
from digitalcrate import config as C
from digitalcrate.db import connect
from digitalcrate import models
SR = 44100
rng = np.random.default_rng(0)
def hit(kind, k):
    n = int(0.6 * SR); t = np.arange(n) / SR; pre = int(0.025 * SR)  # 25 ms before the hit
    if kind == "Kick":
        f = 55 + 70 * np.exp(-t * 30) + 4 * k; y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    elif kind == "Tom":
        f = 110 + 40 * np.exp(-t * 20) + 15 * k; y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    else:
        noise = rng.standard_normal(n)
        if kind == "Hat Closed": noise = np.diff(np.r_[0, noise]); y = noise * np.exp(-t * 60)
        elif kind == "Shaker & Tamb": y = np.diff(np.r_[0, noise]) * np.exp(-((t - 0.05) / 0.04) ** 2)
        elif kind == "Rim & Clap": y = noise * (np.exp(-t * 40) + 0.6 * np.exp(-np.abs(t - 0.012) * 300))
        else: y = 0.6 * noise * np.exp(-t * 18) + 0.4 * np.sin(2 * np.pi * (180 + 10 * k) * t) * np.exp(-t * 14)  # snare
    y = np.r_[np.zeros(pre), y][:n] * (0.5 + 0.1 * k)
    return np.stack([y, y]).astype(np.float32)
con = connect()
con.execute("INSERT INTO tracks (path, artist, album, title, genre, duration, status) VALUES (?,?,?,?,?,?,?)",
            ("synthetic/drums.wav", "Drum Machine", "Kits", "Beat", "Jazz", 30.0, "done"))  # not Electronic: hidden by default
tid = con.execute("SELECT id FROM tracks WHERE path='synthetic/drums.wav'").fetchone()[0]
cl = models.clap()
from scipy.signal import resample_poly
from digitalcrate.process import MOOD_PROMPTS
T = cl.embed_text(tuple(MOOD_PROMPTS.values()))  # mood scores as mining computes them: the sound against each mood
for kind in ["Kick", "Snare", "Hat Closed", "Rim & Clap", "Tom", "Shaker & Tamb"]:
    for k in range(3):
        y = hit(kind, k); sid = f"drm{kind[:2].lower()}{k}"
        rel = f"Percussion/{kind.replace(' & ', ' ')}/{kind.replace(' ', '')}_{sid}.wav"
        (C.LIB_ROOT / rel).parent.mkdir(parents=True, exist_ok=True); sf.write(C.LIB_ROOT / rel, y.T, SR)
        e = cl.embed_audio([resample_poly(y.mean(0), 48000, SR).astype(np.float32)])[0]
        moods = json.dumps(dict(zip(MOOD_PROMPTS, np.round((T @ e) / (np.linalg.norm(T, axis=1) * np.linalg.norm(e) + 1e-9), 4).tolist())))
        a = np.abs(y).max(0); env = [float(x.max()) for x in np.array_split(a, 64)]
        env = (np.array(env) / (max(env) + 1e-9) * 99).astype(int).tolist()
        con.execute("""INSERT INTO samples (id, track_id, source, rendered_from, category, subtype, kind, start, dur, bpm,
            key, scale, camelot, key_strength, key_from, chroma, centroid, flatness, pratio, quality, clap, type_probs,
            mood_sims, instrument, path, env) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, tid, "drums", "mix", "Percussion", kind, "oneshot", 1.0 + k, 0.6, 0, "C", "major", "8B", 0, "none",
             json.dumps([0.0] * 12), 3000, 0.3, 0.8, 0.8, e.astype(np.float16).tobytes(), "{}", moods, "drums", rel,
             json.dumps(env)))
# a one-bar drum loop at 120 bpm: kick 0/8, snare 4/12, hats on the off-8ths (for slicing into pads)
st = int(SR * 60 / 120 / 4); loop = np.zeros((2, 16 * st), np.float32)
for s, kind in [(0, "Kick"), (4, "Snare"), (8, "Kick"), (12, "Snare"), (2, "Hat Closed"), (6, "Hat Closed"), (10, "Hat Closed"), (14, "Hat Closed")]:
    h = hit(kind, 0)[:, int(0.025 * SR):][:, :st * 2]; loop[:, s * st:s * st + h.shape[1]] += h[:, :16 * st - s * st]
rel = "Percussion/Full Kit/FullKit_drmloop.wav"; (C.LIB_ROOT / rel).parent.mkdir(parents=True, exist_ok=True); sf.write(C.LIB_ROOT / rel, loop.T, SR)
e = cl.embed_audio([resample_poly(loop.mean(0), 48000, SR).astype(np.float32)])[0]
moods = json.dumps(dict(zip(MOOD_PROMPTS, np.round((T @ e) / (np.linalg.norm(T, axis=1) * np.linalg.norm(e) + 1e-9), 4).tolist())))
con.execute("""INSERT INTO samples (id, track_id, source, rendered_from, category, subtype, kind, start, dur, bpm, bars,
    key, scale, camelot, key_strength, key_from, chroma, centroid, flatness, pratio, quality, clap, type_probs,
    mood_sims, instrument, path, env) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("drmloop", tid, "drums", "mix", "Percussion", "Full Kit", "loop", 10.0, 2.0, 120, 1, "C", "major", "8B", 0, "none",
     json.dumps([0.0] * 12), 3000, 0.3, 0.8, 0.8, e.astype(np.float16).tobytes(), "{}", moods, "drums", rel, json.dumps([50] * 64)))
con.commit()
print("DRUMS OK")
'''


def _has_live():
    try:
        from digitalcrate.ableton import _template
        _template()
        return True
    except Exception:
        return False


# Drum Racks are built from an installed Live's own factory rack: without Live (as on CI) there's nothing to build from
needs_live = pytest.mark.skipif(not _has_live(), reason="needs Ableton Live installed (its Drum Rack is the template)")


def _song(chords, mel_hz, secs=5.0):
    pad = np.concatenate([tone(c, secs) for c in chords], axis=1)
    t = np.arange(pad.shape[1]) / SR
    f = mel_hz * 2 ** (np.round(4 * np.sin(2 * np.pi * t / 7)) / 12)
    mel = 0.15 * np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 2.5) ** 2)
    return (pad + mel[None]).astype(np.float32)


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("playwright")
    root = tmp_path_factory.mktemp("uilib")
    music, lib = root / "music", root / "lib"
    for artist, title, chords, mel in (
            ("Test Artist", "Night", [(220, 261.6, 329.6), (174.6, 220, 261.6), (196, 246.9, 293.7), (164.8, 207.7, 246.9)] * 2, 440),
            ("Other Artist", "Morning", [(261.6, 329.6, 392), (220, 261.6, 329.6), (174.6, 220, 261.6), (196, 246.9, 293.7)] * 2, 523)):
        d = music / artist / "Album"
        d.mkdir(parents=True)
        sf.write(d / f"01 {title}.wav", _song(chords, mel).T, SR)
    env = dict(os.environ, DIGITALCRATE_MUSIC=str(music), DIGITALCRATE_LIBRARY=str(lib),
               DIGITALCRATE_FOUND=str(root / "found"), DIGITALCRATE_ABLETON_SAMPLES=str(root / "ableton"),
               DIGITALCRATE_CONFIG=str(root / "cfg.toml"), DIGITALCRATE_NO_SCOUT="1")
    (root / "cfg.toml").write_text(f'music = "{music}"\nlibrary = "{lib}"\n')
    def run(*a):
        r = subprocess.run([sys.executable, *a], env=env, capture_output=True, text=True)
        assert r.returncode == 0, f"{a}: {r.stderr[-3000:]}"
        return r.stdout
    run("-m", "digitalcrate", "scan")
    run("-m", "digitalcrate", "policy")
    run("-m", "digitalcrate", "process", "--all", "--separate", "never")
    assert "DRUMS OK" in run("-c", DRUMS)
    run("-m", "digitalcrate", "build")
    port = _port()
    srv = subprocess.Popen([sys.executable, "-m", "digitalcrate", "serve", "--port", str(port), "--no-browser"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://localhost:{port}/"
    for _ in range(90):
        try:
            urllib.request.urlopen(base + "api/ping", timeout=1)
            break
        except OSError:
            time.sleep(1)
    else:
        srv.terminate()
        pytest.fail("server did not start")
    yield dict(base=base, lib=lib, env=env, root=root)
    srv.terminate()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        yield b
        b.close()


@pytest.fixture
def page(site, browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(site["base"])
    pg.wait_for_function("typeof S!=='undefined'&&document.querySelectorAll('#list .row').length>=3", timeout=60000)
    pg.evaluate("localStorage.removeItem('atlasSketchDraft')")
    yield pg
    ctx.close()
    assert not errors, errors  # every test also fails on a page error


def idx(pg, cond):
    return pg.evaluate(f"S.findIndex(s=>{cond})")


# ---------------------------------------------------------------------------------------------------- browsing

def test_library_loads_with_every_kind(page):
    cats = set(page.evaluate("S.map(s=>s[F.cat])"))
    assert "Percussion" in cats and len(cats) >= 2


def test_play_shows_and_stop_hides_the_now_playing_bar(page):
    page.locator("#list .row [data-play]").first.click()
    page.wait_for_timeout(300)
    assert page.is_visible("#np")
    page.click("#npstop")
    page.wait_for_timeout(200)
    assert not page.is_visible("#np")


def test_select_and_unselect(page):
    row = page.locator("#list .row .meta").first
    row.click()
    assert page.evaluate("st.sel") is not None
    row.click()
    assert page.evaluate("st.sel") is None
    row.click()
    page.keyboard.press("Escape")
    assert page.evaluate("st.sel") is None
    row.click()
    page.click("#dclose")
    assert page.evaluate("st.sel") is None


def test_favourite_appears_in_the_favorites_tab(page):
    b = page.locator("#list .row [data-fav]").first
    b.click()
    page.wait_for_timeout(300)
    page.click("#tabF")
    page.click("[data-favview='list']")
    assert page.locator("#list .row").count() >= 1
    page.locator("#list .row [data-fav]").first.click()  # unstar again


def test_delete_and_undo(page):
    n0 = page.evaluate("filtered().length")
    page.locator("#list .row .meta").first.click()
    page.click("#detail [data-del]")
    page.wait_for_timeout(500)
    assert page.evaluate("filtered().length") == n0 - 1
    page.click("#undel")
    page.wait_for_timeout(800)
    assert page.evaluate("filtered().length") == n0


def test_collections(page):
    page.locator("#list .row [data-col]").first.click()
    page.fill("#colnew", "UI test set")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    page.mouse.click(5, 5)
    page.click("#tabF")
    page.click("[data-favview='cols']")
    page.wait_for_selector("[data-colplay]")
    assert page.locator(".kit .row").count() == 1
    page.click("[data-coldel]")
    page.click("[data-coldel]")
    page.wait_for_timeout(500)
    assert page.locator("[data-colplay]").count() == 0


# ---------------------------------------------------------------------------------------------------- sketchpad

def _drums(page, kinds=("Kick", "Snare")):
    for k in kinds:
        i = idx(page, "s[F.cat]==='Percussion'&&s[F.sub]===" + json.dumps(k))
        page.evaluate(f"CRATE.drumAdd({i})")
    page.wait_for_function(f"SK.lanes[0]&&SK.lanes[0].state==='ok'&&SK.lanes[0].pads.length==={len(kinds)}", timeout=30000)


def test_drum_hits_go_to_the_drum_lane_with_a_starter_and_start_on_the_hit(page):
    _drums(page)
    lane = page.evaluate("SK.lanes.map(l=>l.type||'sample')")
    assert lane == ["drums"]
    assert page.evaluate("SK.lanes[0].pads.every(p=>p.steps.some(Boolean))")
    starts = page.evaluate("SK.lanes[0].pads.map(p=>p.start)")
    assert all(0.015 < s < 0.035 for s in starts), starts  # the synthetic hits have 25 ms before them


def test_step_edits_are_scheduled_at_once(page):
    _drums(page)
    page.evaluate("CRATE.PROJ.bpm=90;SK.lanes[0].pads[0].steps.fill(0);CRATE.drawSK()")
    page.evaluate("document.getElementById('skplay').click()")
    page.wait_for_timeout(1000)
    res = page.evaluate("""(async()=>{const l=SK.lanes[0],st=CRATE.barLen()/16,ac=l.g.context,j=(Math.floor((ac.currentTime-SK.start)/st)+4)%16;
        document.querySelector(`[data-dstep="0:0:${j}"]`).click();const t0=ac.currentTime;await new Promise(r=>setTimeout(r,(5*st)*1000));
        const q=l.live.get('0:'+j);return q?q.t-t0:null})()""")
    page.evaluate("document.getElementById('skplay').click()")
    assert res is not None and res < 1.0, res  # within the same pass, not after the bar


def test_pad_editor_and_volume(page):
    _drums(page)
    page.click("[data-dedit='0:0']")
    assert "▾" in page.inner_text("[data-dedit='0:0']") and page.locator(".dped").count() == 1
    page.fill("[data-dpv='0:0']", "-6")
    page.dispatch_event("[data-dpv='0:0']", "input")
    assert page.evaluate("SK.lanes[0].pads[0].db") == -6
    page.click("[data-dedit='0:0']")
    assert page.locator(".dped").count() == 0


def test_complete_the_kit(page):
    _drums(page, ("Kick",))
    page.click("[data-dfind='0']")
    page.wait_for_selector(".dfrow", timeout=60000)
    kinds = [x.split("\n")[0] for x in page.locator(".dfrow .dlab").all_inner_texts()]
    assert "Snare" in kinds and "Kick" not in kinds
    page.locator(".dfrow").first.locator("[data-dfadd]").first.click()
    page.wait_for_function("SK.lanes[0].pads.length===2", timeout=30000)


def test_unsaved_save_undo_and_the_kept_draft(page):
    _drums(page)
    page.wait_for_timeout(800)
    assert "dirty" in page.get_attribute("#sksave", "class")
    page.fill("#skname", "UI test beat")
    page.keyboard.press("Meta+s")
    page.wait_for_timeout(800)
    assert "dirty" not in (page.get_attribute("#sksave", "class") or "")
    s0 = page.evaluate("SK.lanes[0].pads[0].steps.join('')")
    page.click("[data-dstep='0:0:2']")
    page.wait_for_timeout(800)
    assert "dirty" in page.get_attribute("#sksave", "class")
    page.keyboard.press("Meta+z")
    page.wait_for_timeout(800)
    assert page.evaluate("SK.lanes[0].pads[0].steps.join('')") == s0
    page.click("#skclear")
    page.wait_for_timeout(800)
    page.click("#skundo")
    page.wait_for_function("SK.lanes.length===1", timeout=10000)
    page.wait_for_timeout(800)
    page.reload()
    page.wait_for_function("typeof S!=='undefined'&&SK.lanes.length===1", timeout=30000)


def test_hidden_sketch_shows_its_bar(page):
    _drums(page)
    page.evaluate("document.getElementById('skplay').click()")
    page.click("#skhide")
    assert page.is_visible(".skminibar")
    page.click(".skminibar #skplay")
    assert not page.evaluate("SK.playing")


# ---------------------------------------------------------------------------------------------------- editor, pages

def test_editor_reset(page):
    page.locator("#list .row .meta").first.click()
    page.click("#edopen")
    page.wait_for_selector("#edreset", timeout=30000)
    page.wait_for_function("ED&&ED.buf&&ED.sel", timeout=30000)  # the editor has loaded the audio
    page.fill("#edst", "2")
    page.dispatch_event("#edst", "input")
    page.click("#edreset")
    assert page.evaluate("edParams().stretch") == 1


def test_drum_editor_has_the_drum_panel(page):
    i = idx(page, "s[F.cat]==='Percussion'")
    page.evaluate(f"select({i},'list')")
    page.click("#edopen")
    page.wait_for_selector("#eddrum", timeout=30000)
    assert page.is_checked("#edtape")


def test_taste_and_activity_pages_render(site, browser):
    pg = browser.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    for path in ("taste", "activity", "setup"):
        pg.goto(site["base"] + path)
        pg.wait_for_timeout(1500)
    pg.close()
    assert not errors, errors


def test_api_answers(site):
    get = lambda p: json.load(urllib.request.urlopen(site["base"] + p, timeout=120))
    assert "sets" in get("api/sets")
    assert isinstance(get("api/collections"), list)
    assert get("api/ping")["ok"]


def test_new_samples_appear_without_a_rebuild(site, page):
    """A sample mined after the page was built shows up in the open page (live.py), with its goes-with picks."""
    import shutil
    import sqlite3
    db = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite")
    db.row_factory = sqlite3.Row
    r = dict(db.execute("SELECT * FROM samples WHERE category != 'Percussion' LIMIT 1").fetchone())
    new = r["path"].replace(".wav", "_live.wav")
    shutil.copy(site["lib"] / r["path"], site["lib"] / new)
    r.update(id="live01", path=new)
    r.pop("created_at", None)
    cols = ",".join(r)
    db.execute(f"INSERT INTO samples ({cols}) VALUES ({','.join('?' * len(r))})", list(r.values()))
    db.commit()
    n0 = page.evaluate("S.length")
    added = page.evaluate("window.liveCheck(true)")
    assert added == 1 and page.evaluate("S.length") == n0 + 1
    assert page.evaluate("BYID.has('live01')")


def test_rows_drag_out_as_files(page):
    """A dragged row carries a file promise (Finder, the desktop) and the file's own path (apps that take a path)."""
    page.wait_for_function("document.querySelector('#list .row[data-i][draggable]')", timeout=10000)
    got = page.evaluate("""(()=>{const row=document.querySelector('#list .row[data-i]'),dt=new DataTransfer();
        row.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:dt}));
        return {promise:dt.getData('DownloadURL'),uri:dt.getData('text/uri-list')}})()""")
    assert got["promise"].startswith("audio/wav:") and "/" in got["promise"]
    assert got["uri"].startswith("file://") and got["uri"].endswith(".wav")


@needs_live
def test_drum_rack_export_starts_on_the_hit(site):
    """⇩ Ableton / Drum Rack: drum one-shots are written starting on the hit, edited pads as edited."""
    import sqlite3
    db = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite")
    paths = [r[0] for r in db.execute("SELECT path FROM samples WHERE category='Percussion' LIMIT 3")]
    body = dict(scope="paths", paths=paths, name="UI rack", rack=True, reveal=False,
                pad_edits={paths[0]: dict(start=0.0, end=0.2, tune=-2, decay=0.1)})
    req = urllib.request.Request(site["base"] + "api/export", method="POST", data=json.dumps(body).encode())
    r = json.load(urllib.request.urlopen(req, timeout=120))
    dest = site["root"] / "ableton" / "UI rack"
    assert r["count"] == 3 and (dest / "UI rack.adg").exists()
    wavs = {p.name: sf.read(str(p), always_2d=True)[0] for p in dest.rglob("*.wav")}
    for name, y in wavs.items():
        m = np.abs(y).max(1)
        first = int(np.argmax(m >= 0.25 * m.max())) / SR
        if paths[0].endswith(name):  # the edited pad keeps its start at 0 (as the drum lane played it) and is short
            assert len(y) / SR < 0.25
        else:
            assert first < 0.005, (name, first)  # the 25 ms before the hit is gone


def test_recent_actions_undo(page):
    """★, ✕ and collection changes land in 🕘 recent actions; ⌘Z (sketchpad closed) and the list undo them."""
    path = page.evaluate("S[+document.querySelector('#list .row[data-i]').dataset.i][F.path]")
    page.locator("#list .row [data-fav]").first.click()
    page.wait_for_timeout(300)
    assert page.evaluate(f"FAV.has({json.dumps(path)})")
    page.keyboard.press("Meta+z")
    page.wait_for_timeout(500)
    assert not page.evaluate(f"FAV.has({json.dumps(path)})")
    page.locator("#list .row [data-nope]").first.click()
    assert page.evaluate(f"TASTE.disliked.has({json.dumps(path)})")
    page.click("#actbtn")
    page.locator("#actpop [data-actu]").first.click()
    page.wait_for_timeout(300)
    assert not page.evaluate(f"TASTE.disliked.has({json.dumps(path)})")


def test_recategorize_and_undo_moves_the_file_back(site, page):
    i = page.evaluate("+document.querySelector('#list .row[data-i]').dataset.i")
    cat0, path0 = page.evaluate(f"[S[{i}][F.cat],S[{i}][F.path]]")
    page.evaluate(f"select({i},'list')")
    target = "Textures & Field" if cat0 != "Textures & Field" else "Pads & Atmospheres"
    page.select_option("#rcat", target)
    page.dispatch_event("#rcat", "change")
    page.click("#rsave")
    page.wait_for_function(f"S[{i}][F.cat]==={json.dumps(target)}", timeout=20000)
    moved = page.evaluate(f"S[{i}][F.path]")
    assert moved != path0 and (site["lib"] / moved).exists() and not (site["lib"] / path0).exists()
    page.keyboard.press("Escape")
    page.keyboard.press("Meta+z")
    page.wait_for_function(f"S[{i}][F.cat]==={json.dumps(cat0)}", timeout=20000)
    back = page.evaluate(f"S[{i}][F.path]")
    assert (site["lib"] / back).exists() and not (site["lib"] / moved).exists()


def test_keyboard_browsing(page):
    page.mouse.click(700, 5)  # focus the page, not a field
    page.keyboard.press("ArrowDown")
    first = page.evaluate("st.sel")
    assert first is not None and page.evaluate(f"players.has({first})")  # moving previews
    page.keyboard.press("j")
    second = page.evaluate("st.sel")
    assert second != first
    page.keyboard.press("k")
    assert page.evaluate("st.sel") == first
    path = page.evaluate(f"S[{first}][F.path]")
    page.keyboard.press("f")
    page.wait_for_timeout(300)
    assert page.evaluate(f"FAV.has({json.dumps(path)})")
    page.keyboard.press("f")  # and off again
    page.keyboard.press("x")
    assert page.evaluate(f"TASTE.disliked.has({json.dumps(path)})")
    page.keyboard.press("x")
    page.keyboard.press("Shift+?")
    assert page.is_visible("#khelp")
    page.keyboard.press("Shift+?")
    page.keyboard.press("Enter")
    page.wait_for_selector("#edprev", timeout=20000)


def test_velocity_flam_and_choke(page):
    _drums(page, ("Tom", "Hat Closed"))
    page.evaluate("SK.lanes[0].pads.forEach(p=>p.steps.fill(0));SK.lanes[0].pads[0].steps[0]=1;CRATE.drawSK()")
    step = "[data-dstep='0:0:0']"
    page.dispatch_event(step, "wheel", {"deltaY": 120})
    assert abs(page.evaluate("SK.lanes[0].pads[0].steps[0]") - 0.9) < 1e-6  # scroll down: 10% softer
    page.click("[data-dstep='0:1:2']", modifiers=["Alt"])
    assert page.evaluate("SK.lanes[0].pads[1].flams[2]") == 1 and page.evaluate("SK.lanes[0].pads[1].steps[2]") > 0
    # choke: the tom rings from step 0; the hat on step 2 in the same group cuts it off
    level = """(async(choke)=>{const l=SK.lanes[0];l.pads.forEach(p=>{p.choke=choke;p.flams=[]});l.pads[1].steps.fill(0);l.pads[1].steps[2]=1;l._choke=null;
        const L=CRATE.barLen(),ctx=new OfflineAudioContext(1,Math.ceil(L*44100),44100);CRATE.skBar(ctx,ctx.destination,l,0,0,L,null);
        const d=(await ctx.startRendering()).getChannelData(0),a=Math.floor(L/16*4*44100),b=Math.floor(L/16*8*44100);let s=0;for(let k=a;k<b;k++)s+=d[k]*d[k];return s})"""
    ringing = page.evaluate(level + "(0)")
    choked = page.evaluate(level + "(1)")
    assert choked < 0.2 * ringing, (choked, ringing)


@needs_live
def test_drum_midi_and_rack_export(site):
    import gzip
    import sqlite3
    import pretty_midi
    db = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite")
    paths = [r[0] for r in db.execute("SELECT path FROM samples WHERE category='Percussion' AND subtype IN ('Kick','Snare','Hat Closed') LIMIT 3")]
    steps = lambda *on: [1 if j in on else 0 for j in range(16)]
    pads = [dict(path=paths[0], steps=steps(0, 8), choke=0), dict(path=paths[1], steps=steps(4, 12), flams=steps(12)),
            dict(path=paths[2], steps=steps(*range(0, 16, 2)), choke=1)]
    body = dict(name="UI drums", bpm=100, bars=1, swing=0.2, pads=pads, reveal=False)
    req = urllib.request.Request(site["base"] + "api/drums/export", method="POST", data=json.dumps(body).encode())
    r = json.load(urllib.request.urlopen(req, timeout=120))
    dest = site["root"] / "ableton" / "UI drums"
    pm = pretty_midi.PrettyMIDI(str(dest / r["midi"]))
    notes = pm.instruments[0].notes
    assert len(notes) == 2 + 3 + 8  # kick 2, snare 2 + a flam, hats 8
    assert {n.pitch for n in notes} == {36, 37, 38}
    adg = gzip.open(dest / "UI drums.adg").read().decode()
    assert '<ChokeGroup Value="1"' in adg


def test_slice_a_drum_loop_into_pads(page):
    i = idx(page, "s[F.id]==='drmloop'")
    page.evaluate(f"select({i},'list')")
    page.click("#sliceit")
    page.wait_for_function("SK.lanes[0]&&SK.lanes[0].type==='drums'&&SK.lanes[0].pads.length>=6&&SK.lanes[0].pads.every(p=>p.buf)", timeout=30000)
    on = page.evaluate("SK.lanes[0].pads.map(p=>p.steps.findIndex(v=>v>0))")
    assert set(on) <= set(range(16)) and {0, 2, 4, 6, 8, 10, 12, 14} <= set(on), on  # each hit on its own step
    assert page.evaluate("SK.lanes[0].pads.every(p=>p.label&&p.end>p.start)")


def test_arrangement_sections(page):
    """AB × 1 bar: a lane ticked only for B is silent in bar 1 and plays in bar 2; the bounce offers the whole song."""
    _drums(page, ("Kick",))
    page.evaluate("SK.lanes[0].pads[0].steps.fill(0);SK.lanes[0].pads[0].steps[0]=1;CRATE.drawSK()")
    page.fill("#skarr", "ab")
    page.dispatch_event("#skarr", "change")
    page.select_option("#sksec", "1")
    assert page.evaluate("SK.arr") == "AB"
    page.click("[data-sksec='0:A']")  # untick A: the drums play in B only
    assert page.evaluate("SK.lanes[0].secs") == "B"
    assert page.input_value("#skbars") == "2"
    energy = """(async()=>{const l=SK.lanes[0],L=CRATE.barLen(),ctx=new OfflineAudioContext(1,Math.ceil(2*L*44100),44100);
        for(let b=0;b<2;b++)CRATE.skBar(ctx,ctx.destination,l,b,b*L,L,null);const d=(await ctx.startRendering()).getChannelData(0),h=Math.floor(L*44100);
        let a=0,b=0;for(let k=0;k<h;k++){a+=d[k]*d[k];b+=d[h+k]*d[h+k]}return [a,b]})()"""
    a, b = page.evaluate(energy)
    assert a < 1e-6 and b > 0.01, (a, b)
    snap = json.loads(page.evaluate("JSON.stringify(JSON.parse(CRATE.skSnap()))"))
    assert snap["arr"] == "AB" and snap["sec"] == 1 and snap["lanes"][0]["secs"] == "B"


def test_fits_my_track(site, page, tmp_path):
    """🎚 fits my track: a bounce's key and tempo are detected, results carry their reasons, and the track's key and
    tempo can become the project's. The file is only analysed (nothing is added to the library)."""
    import sqlite3
    A, D, E, Fs, Cs = 220.0, 293.66, 329.63, 369.99, 277.18
    bounce = _song([[A, Cs, E], [D, Fs, A], [E, A * 2 ** (8 / 12), 493.88 / 2], [A, Cs, E]], 440.0)
    f = tmp_path / "my bounce.wav"
    sf.write(f, bounce.T, SR)
    n0 = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite").execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    page.click("#mybtn")
    page.fill("#myIn", str(f))
    page.click("#myGo")
    page.wait_for_selector("#sbanner #myproj", timeout=120000)
    label = page.inner_text("#sbanner")
    assert "fits my bounce.wav" in label and "bpm" in label
    assert page.locator("#list .row[data-i] .meta span").first.inner_text().count("sounds like") == 1
    page.click("#myproj")
    key = page.evaluate("CRATE.PROJ.key")
    assert key and key in label
    n1 = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite").execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert n1 == n0


def test_why_this(site, page):
    """💡 why this? explains a sample's rank: where it stands, and the liked samples it sounds closest to."""
    paths = page.evaluate("[...document.querySelectorAll('#list .row[data-i]')].slice(0,4).map(r=>S[+r.dataset.i][F.path])")
    for p in paths[:3]:
        req = urllib.request.Request(site["base"] + "api/fav", method="POST", data=json.dumps(dict(path=p, on=True)).encode())
        urllib.request.urlopen(req, timeout=30)
    page.reload()
    page.wait_for_function("TASTE.loaded", timeout=60000)
    i = page.evaluate(f"byPath.get({json.dumps(paths[3])})")
    page.evaluate(f"select({i},'list')")
    page.click("#whybtn")
    page.wait_for_function("document.querySelector('#whybox b')", timeout=60000)
    txt = page.inner_text("#whybox")
    assert "In your" in txt and "sounds closest to what you liked" in txt
    page.locator("#whybox [data-go2]").first.click()  # a liked sample opens; the explanation follows it
    page.wait_for_function(f"st.sel!=={i}")
    page.wait_for_function("document.querySelector('#whybox b')", timeout=60000)


def test_build_a_kit_around_a_hit(page):
    """🥁 build a kit around this: the hit goes into the drum lane and the finder offers the rest of a kit."""
    i = idx(page, "s[F.cat]==='Percussion'&&s[F.sub]==='Kick'")
    page.evaluate(f"select({i},'list')")
    page.click("#kitaround")
    page.wait_for_function("SK.lanes[0]&&SK.lanes[0].type==='drums'&&SK.lanes[0].pads.length===1", timeout=30000)
    page.wait_for_selector(".dfrow [data-dfadd]", timeout=60000)
    page.locator(".dfrow").filter(has_text="Snare").first.locator("[data-dfadd]").first.click()
    page.wait_for_function("SK.lanes[0].pads.length===2", timeout=30000)


def test_scout_groups_inbox_and_filters(site, page):
    """🔭 Scout: full width, finds grouped by search, the daily inbox on top, playlists filtered, ✕ remembered."""
    import sqlite3
    urllib.request.urlopen(site["base"] + "api/ytscout", timeout=60).read()  # creates the table
    db = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite")
    e = lambda k: (np.eye(512)[k] + 0.1).astype(np.float16).tobytes()
    rows = [("v1", "acapella test", "Singer - Song (Acapella)", 1.5, 1, 0, e(1)),
            ("v2", "acapella test", "Another (A Cappella)", 1.2, 0, 1, e(2)),
            ("v3", "acapella test", "2000s hits [playlist]", 1.9, 0, 1, e(3))]
    for vid, q, t, sc, auto, seen, emb in rows:
        db.execute("""INSERT OR REPLACE INTO yt_scout(id, query, queries, url, title, channel, duration, views, score,
                      vocal, neg, taste, best_at, snippet, status, mode, emb, moments, auto, seen)
                      VALUES (?,?,?,?,?,'ch',200,10,?,0.5,0.1,0.2,30,'x.wav','scored','voice',?,?,?,?)""",
                   (vid, q, q, f"https://www.youtube.com/watch?v={vid}", t, sc, emb,
                    json.dumps([[30, "x.wav"], [50, "y.wav"]]), auto, seen))
    db.commit()
    page.evaluate("CRATE.setTab('Y')")
    page.wait_for_selector(".ygrp .yghead", timeout=30000)
    assert not page.locator("aside").is_visible()
    assert page.locator(".ygrp.inbox .yt").count() == 1
    grp = page.locator(".ygrp:not(.inbox)").filter(has_text="acapella test")
    assert grp.locator(".yt").count() == 2  # the playlist is filtered out
    assert grp.locator(".yt").first.locator(".ymoms .play").count() == 2
    assert "dismissed or filtered" in page.inner_text("#ytcount")
    grp.locator(".yt").filter(has_text="Another").locator("[data-ytskip]").click()
    page.wait_for_function("document.querySelectorAll('.ygrp:not(.inbox) .yt').length===1")
    assert db.execute("SELECT status FROM yt_scout WHERE id='v2'").fetchone()[0] == "skipped"
    assert db.execute("SELECT status FROM yt_scout WHERE id='v3'").fetchone()[0] == "filtered"
    page.click("[data-ytseen]")
    page.wait_for_function("!document.querySelector('.ygrp.inbox')")
    page.evaluate("CRATE.setTab('S')")
    assert page.locator("aside").is_visible()
