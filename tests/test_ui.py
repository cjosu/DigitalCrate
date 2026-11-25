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
               DIGITALCRATE_CONFIG=str(root / "cfg.toml"), DIGITALCRATE_NO_SCOUT="1",
               DIGITALCRATE_NO_SLOT="1")  # the test library has its own jobs: no waiting on the real ones
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
            ("v3", "acapella test", "2000s hits [playlist]", 1.9, 0, 1, e(3)),
            ("v4", "acapella test", "Third (Acapella)", 1.0, 0, 1, e(4))]
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
    page.locator(".ygrp.inbox .ymoms .play").nth(1).click()  # listening doesn't move a find out of the inbox
    page.wait_for_timeout(600)
    page.evaluate("CRATE.setTab('Y')")
    page.wait_for_selector(".ygrp.inbox .yt", timeout=30000)
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


def test_hold_a_pad_on_its_sustain_loop(page):
    """∞ hold: a sustained sample with a seamless loop plays and holds until stopped; a sketchpad lane can hold too."""
    i = page.evaluate("+Object.keys(CRATE.LOOPS).find(k=>S[k]&&S[k][F.kind]!=='loop')")
    assert i == i, "the test library should have at least one loopable pad"  # not NaN
    page.evaluate(f"select({i},'list')")
    page.click("#holdit")
    page.wait_for_function("players.has('hold')")
    page.click("#holdit")
    page.wait_for_function("!players.has('hold')")
    page.evaluate(f"CRATE.skAdd({i})")
    page.wait_for_function("SK.lanes.length&&SK.lanes[SK.lanes.length-1].state==='ok'", timeout=60000)
    page.evaluate("(()=>{const l=SK.lanes[SK.lanes.length-1];l.more=true;CRATE.drawSK()})()")
    page.locator("[data-skhold]").last.click()
    assert page.evaluate("(()=>{const l=SK.lanes[SK.lanes.length-1];const h=CRATE.laneHold(l);return l.hold&&l.every>=2&&!!h&&h.b>h.a})()")


def test_drum_takes_alternate(site, page):
    """🔁 takes: other hits of the same drum from the same song; hits cycle main, take 2, take 3… deterministically."""
    found = None
    for i in page.evaluate("S.map((s,i)=>i).filter(i=>S[i][F.cat]==='Percussion'&&S[i][F.kind]==='oneshot')"):
        p = page.evaluate(f"S[{i}][F.path]")
        t = json.loads(urllib.request.urlopen(site["base"] + "api/drums/takes?path=" + urllib.parse.quote(p), timeout=30).read())
        if t["takes"]:
            found = i
            break
    assert found is not None, "the test library should have a drum hit with another take in its song"
    page.evaluate(f"CRATE.drumAdd({found},{{quiet:true}})")
    page.wait_for_function("SK.lanes.some(l=>l.type==='drums'&&l.state==='ok')", timeout=60000)
    page.locator("[data-dtakes]").first.click()
    page.wait_for_function("(()=>{const l=SK.lanes.find(l=>l.type==='drums');return l.pads[0].tk&&l.pads[0].tk.length>0})()", timeout=30000)
    seq = page.evaluate("""(()=>{const l=SK.lanes.find(l=>l.type==='drums'),p=l.pads[0];p.steps=new Array(32).fill(0);[0,4,8,12].forEach(k=>p.steps[k]=1);
      const out=[];for(let bar=0;bar<2;bar++)for(const k of [0,4,8,12]){const t=CRATE.drumTake(l,p,k,bar);out.push(t?t.path:'main')}return out})()""")
    n = page.evaluate("SK.lanes.find(l=>l.type==='drums').pads[0].tk.length") + 1
    assert seq[0] == "main" and len(set(seq)) == n and seq[n] == "main"  # cycles through every take, then repeats


def test_drum_takes_pin_shuffle_and_make_main(site, page):
    """Takes: ⇧-click pins a step to one take, "shuffled" is a seeded shuffle bag the export reproduces exactly, and ★
    makes a take the main hit."""
    from digitalcrate.drumexport import take_idx
    for n in (2, 3, 4):  # the page and the exporter pick the same take for every hit
        js = page.evaluate(f"[...Array(60).keys()].map(h=>CRATE.takeIdx({{order:'shuffle',seed:777}},h,0,{n}))")
        assert js == [take_idx(dict(order="shuffle", seed=777), h, 0, n) for h in range(60)]
        if n > 2:
            assert all(a != b for a, b in zip(js, js[1:])) and set(js) == set(range(n))
    found = None
    for i in page.evaluate("S.map((s,i)=>i).filter(i=>S[i][F.cat]==='Percussion'&&S[i][F.kind]==='oneshot')"):
        p = page.evaluate(f"S[{i}][F.path]")
        t = json.loads(urllib.request.urlopen(site["base"] + "api/drums/takes?path=" + urllib.parse.quote(p), timeout=30).read())
        if t["takes"]:
            found = i
            break
    assert found is not None
    page.evaluate(f"CRATE.drumAdd({found},{{quiet:true}})")
    page.wait_for_function("SK.lanes.some(l=>l.type==='drums'&&l.state==='ok')", timeout=60000)
    page.locator("[data-dtakes]").first.click()
    page.wait_for_function("(()=>{const l=SK.lanes.find(l=>l.type==='drums');return l.pads[0].tk&&l.pads[0].tk.length>0})()", timeout=30000)
    page.evaluate("(()=>{const p=SK.lanes.find(l=>l.type==='drums').pads[0];p.steps=new Array(32).fill(0);[0,4,8,12].forEach(k=>p.steps[k]=1);CRATE.drawSK()})()")
    st = page.locator('[data-dstep$=":0:4"]').first
    st.click(modifiers=["Shift"])
    st.click(modifiers=["Shift"])  # auto -> main -> take 2
    assert page.locator('[data-dstep$=":0:4"]').first.get_attribute("data-pin") == "2"
    seq = page.evaluate("""(()=>{const l=SK.lanes.find(l=>l.type==='drums'),p=l.pads[0];const out=[];for(let bar=0;bar<3;bar++){const t=CRATE.drumTake(l,p,4,bar);out.push(t?t.path:'main')}return out})()""")
    t2 = page.evaluate("SK.lanes.find(l=>l.type==='drums').pads[0].takes[0]")
    assert seq == [t2] * 3  # pinned: every pass
    # ★ make take 2 the main hit
    old = page.evaluate("SK.lanes.find(l=>l.type==='drums').pads[0].path")
    page.locator("[data-dtkmain]").first.click()  # the takes row shows under the pad once takes are on
    page.wait_for_function(f"(()=>{{const p=SK.lanes.find(l=>l.type==='drums').pads[0];return p.path==={json.dumps(t2)}&&p.buf}})()", timeout=30000)
    p = page.evaluate("(()=>{const p=SK.lanes.find(l=>l.type==='drums').pads[0];return {takes:p.takes,pin:p.pins[4]}})()")
    assert p["takes"][0] == old and p["pin"] == 1  # the pin follows its recording, now the main one
    # shuffled is in the saved state
    page.select_option("[data-dtkord]", "shuffle")
    assert page.evaluate("JSON.parse(CRATE.skSnap()).lanes.find(l=>l.type==='drums').pads[0].order") == "shuffle"
    # each pad row stays on one line (✕ doesn't wrap)
    tops = page.evaluate("[...document.querySelector('.drow').children].map(e=>Math.round(e.getBoundingClientRect().top+e.getBoundingClientRect().height/2))")
    assert max(tops) - min(tops) <= 4, tops


def test_pad_solo_hears_only_that_pad(page):
    """S on a drum pad: only that pad plays, and the other lanes go quiet too."""
    i = page.evaluate("S.findIndex(s=>s[F.cat]==='Percussion'&&s[F.kind]==='oneshot')")
    page.evaluate(f"CRATE.drumAdd({i},{{quiet:true}})")
    page.wait_for_function("SK.lanes.some(l=>l.type==='drums'&&l.state==='ok')", timeout=60000)
    page.locator("[data-dsolo]").first.click()
    assert page.evaluate("SK.lanes.find(l=>l.type==='drums').pads[0].solo") is True
    assert page.evaluate("CRATE.laneSolo(SK.lanes.find(l=>l.type==='drums'))") is True
    assert page.locator("[data-dsolo]").first.get_attribute("class").split().count("on") == 1
    page.locator("[data-dsolo]").first.click()
    assert page.evaluate("CRATE.laneSolo(SK.lanes.find(l=>l.type==='drums'))") is False


def test_playable_pad_for_live(site, page):
    """🎹 playable: a Simpler preset tuned to the sample's chord, its loop in the WAV, and its chords as MIDI."""
    import gzip, re
    i = page.evaluate("S.findIndex(s=>['Pads & Atmospheres','Strings & Orchestral','Chords & Keys'].includes(s[F.cat])&&s[F.kind]!=='oneshot')")
    assert i >= 0
    page.evaluate(f"select({i},'list')")
    page.wait_for_selector("#playit")
    page.evaluate("window._t=[];const o=toast;toast=(m,...a)=>{_t.push(String(m));return o(m,...a)}")
    page.route("**/api/pad/playable", lambda route: route.continue_(post_data=json.dumps({**json.loads(route.request.post_data), "reveal": False})))
    page.click("#playit")
    page.wait_for_function("_t.some(m=>m.includes('Playable pads')||m.includes('failed'))", timeout=60000)
    msg = page.evaluate("_t.find(m=>m.includes('Playable pads')||m.includes('failed'))")
    assert "Playable pads" in msg, msg
    d = site["root"] / "ableton" / "Playable pads"
    mids, advs = list(d.glob("*chords.mid")), list(d.glob("*.adv"))
    assert list(d.glob("*.wav"))
    try:
        import madmom  # noqa: F401  (the chords clip needs the chord recognizer; without it the instrument still works)
        assert mids
    except ImportError:
        pass
    if advs:  # Live installed: the preset's root key is the chord's root
        x = gzip.open(advs[0]).read().decode()
        assert re.search(r'<RootKey Value="(\d+)"', x)


def test_tab_survives_refresh(page):
    page.click("#tabC")
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='C'", timeout=30000)
    assert "on" in page.locator("#tabC").get_attribute("class").split()
    page.click("#tabS")  # leave it where the other tests expect it


def test_playback_progress_shows(page):
    """While a sample plays: a thin bar on the now-playing strip and a playhead on its waveform."""
    page.evaluate("CRATE.setTab('S')")
    page.locator(".row [data-play]").first.click()
    page.wait_for_function("document.querySelector('#npbar')&&parseFloat(document.querySelector('#npbar').style.width)>0", timeout=20000)
    page.wait_for_function("document.querySelector('.row svg.wave .phl')", timeout=10000)
    page.evaluate("stopAll()")
    page.wait_for_function("!document.querySelector('svg.wave .phl')", timeout=10000)


def test_search_from_crate_and_by_id(page):
    """Typing in search on another tab shows the samples; an id finds its sample even if filters would hide it."""
    sid, cat = page.evaluate("[S[3][F.id],S[3][F.cat]]")
    other = page.evaluate(f"CATS.find(c=>c!=={json.dumps(cat)})")
    page.click("#tabC")
    page.fill("#search", sid)
    page.wait_for_function("st.tab==='S'", timeout=5000)
    page.evaluate(f"st.cats=new Set([{json.dumps(other)}]);render()")  # a category filter that would hide it
    page.wait_for_function(f"document.querySelectorAll('#list .row').length===1&&document.querySelector('#list .row').dataset.i==='3'", timeout=5000)
    page.fill("#search", "")
    page.evaluate("st.cats=new Set();render()")


def test_now_playing_does_not_move_the_page(page):
    """Starting and stopping playback never shifts the list (the now-playing strip floats over it)."""
    page.evaluate("CRATE.setTab('S')")
    row = page.locator("#list .row").nth(1)
    y0 = row.bounding_box()["y"]
    page.locator("#list .row [data-play]").first.click()
    page.wait_for_function("!document.querySelector('#np').hidden", timeout=10000)
    y1 = row.bounding_box()["y"]
    page.evaluate("stopAll()")
    page.wait_for_function("document.querySelector('#np').hidden", timeout=10000)
    y2 = row.bounding_box()["y"]
    assert abs(y1 - y0) < 1 and abs(y2 - y0) < 1, (y0, y1, y2)


def test_recommendations_updated_only_when_the_list_changes(page):
    """Fresh taste scores that don't change the top of the list don't show "recommendations updated"."""
    page.evaluate("CRATE.setTab('S')")
    page.wait_for_function("TASTE.loaded", timeout=30000)
    page.evaluate("$('refresh').hidden=true")
    page.evaluate("loadTaste()")
    page.wait_for_timeout(1500)
    assert page.evaluate("$('refresh').hidden") is True


def test_plays_record_where_they_came_from(site, page):
    """A play from the crate's wildcards is logged with that source (for "where your stars come from")."""
    import sqlite3
    page.click("#tabC")
    page.wait_for_selector("#list .kit")
    b = page.locator("#list .kit").nth(1).locator("[data-play]").first
    if not b.count():
        b = page.locator("#list .kit").first.locator("[data-play]").first
    want = "crate · wildcards" if page.locator("#list .kit").nth(1).locator("[data-play]").count() else "crate · for you"
    b.click()
    page.wait_for_timeout(600)
    page.evaluate("stopAll()")
    db = sqlite3.connect(site["lib"] / "_data" / "samples.sqlite")
    for _ in range(20):  # the event is sent in the background
        ctx = [r[0] for r in db.execute("SELECT context FROM events WHERE type='listen' AND context IS NOT NULL")]
        if any(json.loads(c).get("src") == want for c in ctx):
            break
        page.wait_for_timeout(250)
    page.click("#tabS")
    assert any(json.loads(c).get("src") == want for c in ctx), ctx


def test_alternate_takes_play_through(page):
    """🔁 takes: a tag on the row, the list in the sample panel, play all, and T for the next take."""
    page.evaluate("CRATE.setTab('S')")
    i = page.evaluate("S.findIndex((s,i)=>CRATE.takesOf(i).length>1)")
    assert i >= 0, "the test library's drum hits (three of each kind in one song) should group as takes"
    g = page.evaluate(f"CRATE.takesOf({i})")
    page.fill("#search", page.evaluate(f"S[{i}][F.id]"))
    page.wait_for_selector(f'#list .row[data-i="{i}"] [data-takes]')
    page.click(f'#list .row[data-i="{i}"] [data-takes]')   # plays through the takes, the first one first
    page.wait_for_function(f"players.has({g[0]})", timeout=10000)
    page.wait_for_function(f"players.has({g[1]})", timeout=20000)   # ... then the next, on its own
    page.evaluate("stopAll()")
    page.evaluate(f"select({i},'list')")
    page.wait_for_selector("#tkbox")
    assert page.locator("#tkbox .prow").count() == len(g)
    page.keyboard.press("t")
    nxt = g[(g.index(i) + 1) % len(g)]
    page.wait_for_function(f"st.sel==={nxt}", timeout=5000)
    page.evaluate("stopAll()")
    page.fill("#search", "")


def test_editor_selection_sticks_to_bars_and_knobs_need_a_real_grab(page):
    """Dragging a selection in the editor: its length sticks at whole bars; a click near (not on) a fade knob selects."""
    page.evaluate("CRATE.setTab('S')")
    i = page.evaluate("S.findIndex(s=>s[F.kind]==='loop'&&s[F.bpm]>0&&s[F.dur]>240/s[F.bpm]*1.6)")
    if i < 0:  # no loop long enough: a free sample against the project tempo
        i = page.evaluate("S.findIndex(s=>s[F.dur]>5)")
        page.evaluate("PROJ.bpm=120")
    page.evaluate(f"select({i},'list')")
    page.evaluate(f"openEditor({i})")
    page.wait_for_function("ED&&ED.buf&&document.querySelector('#edc')", timeout=30000)
    box = page.locator("#edc").bounding_box()
    bar, dur = page.evaluate("edBar()"), page.evaluate("ED.buf.duration")
    assert bar > 0 and dur > bar * 1.5
    x = lambda t: box["x"] + t / dur * box["width"]
    fi0 = page.evaluate("+$('edfi').value")
    # near the left edge, below the knob: starts a selection, the fade stays as it was
    page.evaluate("$('edsnap').checked=false")
    t0 = 0.15 * dur   # well clear of the edges (within 7 px of one, a drag moves that edge instead)
    page.mouse.move(x(t0), box["y"] + 60)
    page.mouse.down()
    page.mouse.move(x(t0 + bar) + 5, box["y"] + 60, steps=8)   # 5 px past one bar: sticks to exactly one
    page.mouse.up()
    a, b = page.evaluate("ED.sel")
    assert abs((b - a) - bar) < 0.002, (a, b, bar)
    assert "1 bar" in page.inner_text("#edsel")
    assert page.evaluate("+$('edfi').value") == fi0
    # a click 20 px down, right by the fade-in knob, is not a knob grab
    page.mouse.move(x(a) + 6, box["y"] + 22)
    page.mouse.down()
    page.mouse.move(x(a) + 80, box["y"] + 22, steps=4)
    page.mouse.up()
    assert page.evaluate("+$('edfi').value") <= max(fi0, 10)
    page.keyboard.press("Escape")


def test_lane_trim_sticks_to_bars(page):
    """Dragging a part of a sketchpad lane: its length sticks at whole bars of the project."""
    i = page.evaluate("S.findIndex(s=>s[F.cat]!=='Percussion'&&s[F.dur]>6)")
    assert i >= 0
    n0 = page.evaluate("SK.lanes.length")
    page.evaluate(f"CRATE.skAdd({i})")
    page.wait_for_function(f"SK.lanes.length>{n0}&&SK.lanes[SK.lanes.length-1].state==='ok'", timeout=60000)
    k = page.evaluate("SK.lanes.length-1")
    c = page.locator(f'[data-skw="{k}"]')
    c.scroll_into_view_if_needed()
    box = c.bounding_box()
    dur, bar = page.evaluate(f"SK.lanes[{k}].buf.duration"), page.evaluate("CRATE.barLen()")
    assert dur > bar * 1.2
    x = lambda t: box["x"] + t / dur * box["width"]
    t0 = 0.15 * dur   # well clear of the edges
    page.mouse.move(x(t0), box["y"] + 15)
    page.mouse.down()
    page.mouse.move(x(t0 + bar) + 4, box["y"] + 15, steps=8)   # 4 px past one bar
    page.mouse.up()
    a, b = page.evaluate(f"SK.lanes[{k}].trim")
    assert abs((b - a) * dur - bar) < 0.003, ((b - a) * dur, bar)
    assert "1 bar" in page.locator(".lane .meta").last.inner_text()


STEM_SONGS = r'''
import json, numpy as np, soundfile as sf
from digitalcrate import stems, config as C
SR = C.SR
for tid, bpm, pc in ((901, 100, 0), (902, 110, 2), (903, 92, 7)):
    d = stems.DIR / f"t{tid}"; d.mkdir(parents=True, exist_ok=True)
    bar, nb = 240.0 / bpm, 16
    t = np.arange(int(nb * bar * SR)) / SR
    tone = lambda f: (0.25 * np.sin(2 * np.pi * f * t)).astype(np.float32)
    click = (0.5 * (np.modf(t / (bar / 4))[0] < 0.02) * np.sin(2 * np.pi * 90 * t)).astype(np.float32)
    root = 220 * 2 ** ((pc - 9) / 12)
    parts = dict(drums=click, bass=tone(root / 2), vocals=tone(root * 2), other=tone(root) + tone(root * 1.26) + tone(root * 1.5))
    for k, y in parts.items():
        sf.write(str(d / f"{k}.flac"), np.stack([y, y]).T, SR, format="FLAC", subtype="PCM_16")
    ch = np.zeros(12); ch[[pc, (pc + 4) % 12, (pc + 7) % 12]] = 1; ch /= np.linalg.norm(ch)
    e = np.zeros((4, 512), np.float16); e[:, tid % 512] = 1; np.save(d / "emb.npy", e)
    (d / "meta.json").write_text(json.dumps(dict(track=tid, artist=f"Stem Artist {tid}", title="Song", bpm=bpm, pc=pc,
        scale="major", camelot="8B", bars=[round(b * bar, 4) for b in range(nb + 1)], act={k: [1.0] * nb for k in stems.STEMS},
        chroma=[ch.round(3).tolist()] * nb, stems=list(stems.STEMS), separated=False)))
print("STEMS OK")
'''


def test_stem_mixer_deals_plays_and_learns(site, page):
    """🎛 Stems: prepared songs, 🎲 all fills the slots with parts rendered to the tempo, they loop in sync, and a
    rating is logged."""
    # three prepared songs written straight into the test library (the beat tracker doesn't take the synthetic songs)
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    n = json.load(urllib.request.urlopen(urllib.request.Request(site["base"] + "api/stems/library", data=b"{}", method="POST")))["n"]
    assert n == 3
    page.click("#tabM")
    page.wait_for_selector("#mxall")
    page.fill("#mxbpm", "100")
    page.dispatch_event("#mxbpm", "change")
    page.click("#mxall")
    page.wait_for_function("CRATE.MX.on&&Object.values(CRATE.MX.slots).some(p=>p&&p.buf)", timeout=90000)
    slots = page.evaluate("Object.fromEntries(Object.entries(CRATE.MX.slots).map(([k,p])=>[k,{n:p.n,dur:p.buf?p.buf.duration:0,track:p.track}]))")
    for k, p in slots.items():
        if p["dur"]:
            assert abs(p["dur"] - p["n"] * 2.4) < 0.01, (k, p)   # n bars at 100 bpm, whatever the song's tempo
    stem = next(k for k, p in slots.items() if p["dur"])
    page.select_option(f'[data-mxlen="{stem}"]', "2")
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].buf&&Math.abs(CRATE.MX.slots['{stem}'].buf.duration-4.8)<0.01", timeout=60000)
    page.click("#mxup")
    page.wait_for_function("CRATE.MX.rated>0", timeout=10000)
    # the waveform and its play line
    page.wait_for_function(f"(()=>{{const b=document.querySelector('[data-mxwave=\"{stem}\"]');return b&&b.querySelector('canvas').width>50&&getComputedStyle(b.querySelector('i')).display==='block'}})()", timeout=10000)
    # ↶ goes back to the part a slot held before a 🎲, ↷ forward again
    before = page.evaluate(f"[CRATE.MX.slots['{stem}'].track,CRATE.MX.slots['{stem}'].bar0]")
    page.click(f'[data-mxroll="{stem}"]')
    page.wait_for_function(f"(()=>{{const p=CRATE.MX.slots['{stem}'];return p&&p.buf&&!p._loading&&(p.track!=={before[0]}||p.bar0!=={before[1]})}})()", timeout=60000)
    after = page.evaluate(f"[CRATE.MX.slots['{stem}'].track,CRATE.MX.slots['{stem}'].bar0]")
    page.click(f'[data-mxhist="{stem}:-1"]')
    page.wait_for_function(f"(()=>{{const p=CRATE.MX.slots['{stem}'];return p.track==={before[0]}&&p.bar0==={before[1]}&&p.buf&&!p._loading}})()", timeout=60000)
    page.click(f'[data-mxhist="{stem}:1"]')
    page.wait_for_function(f"(()=>{{const p=CRATE.MX.slots['{stem}'];return p.track==={after[0]}&&p.bar0==={after[1]}&&p.buf&&!p._loading}})()", timeout=60000)
    # a part that is all sub-bass gets harmonics by itself (small speakers can't play it), and says so
    b = next((k for k in page.evaluate("CRATE.MX.order") if page.evaluate(f"CRATE.MX.roles['{{}}']".format(k)) == "bass" and page.evaluate(f"!!CRATE.MX.slots['{{}}']".format(k))), None)
    if b:
        page.wait_for_function(f"CRATE.MX.slots['{b}'].sub>=0.85&&CRATE.MX.slots['{b}'].harm===true", timeout=30000)
        assert "sub-bass" in page.locator(f'[data-mxrow="{b}"] .mxsrc').inner_text()
    # the list of prepared songs, and a stem button that puts a song straight into a slot of that kind
    page.click("#mxsongs summary")
    page.wait_for_function("document.querySelectorAll('#mxsongs .mxsong').length===3", timeout=10000)
    page.click('[data-mxput="drums:903"]')
    page.wait_for_function("Object.entries(CRATE.MX.slots).some(([id,p])=>CRATE.MX.roles[id]==='drums'&&p&&p.track===903&&p.buf)", timeout=60000)
    # ⇄ steps to another stretch of the same stem in the same song
    b0, tr = page.evaluate(f"[CRATE.MX.slots['{stem}'].bar0,CRATE.MX.slots['{stem}'].track]")
    page.click(f'[data-mxalt="{stem}"]')
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].bar0!=={b0}&&CRATE.MX.slots['{stem}'].buf&&!CRATE.MX.slots['{stem}']._loading", timeout=60000)
    assert page.evaluate(f"CRATE.MX.slots['{stem}'].track") == tr and page.evaluate(f"CRATE.MX.slots['{stem}'].alt[1]") >= 2
    # ✕ takes a part out; 🔍 puts a chosen song in
    page.click(f'[data-mxdel="{stem}"]')
    page.wait_for_function(f"!CRATE.MX.slots['{stem}']", timeout=10000)
    page.click(f'[data-mxfind="{stem}"]')
    page.fill("#mxq", "Stem Artist 902")
    page.wait_for_selector(f'[data-mxsong="{stem}:902"]')
    page.keyboard.press("Enter")
    page.wait_for_function(f"CRATE.MX.slots['{stem}']&&CRATE.MX.slots['{stem}'].track===902&&CRATE.MX.slots['{stem}'].buf", timeout=60000)
    # save, clear all, open it again
    assert "dirty" in page.locator("#mxsave").get_attribute("class")      # unsaved changes: the button says so
    page.fill("#mxname", "ui mix")
    page.click("#mxsave")
    page.wait_for_selector("#mxload")
    page.wait_for_function("!document.querySelector('#mxsave').classList.contains('dirty')", timeout=10000)
    page.evaluate(f"(()=>{{const e=document.querySelector('[data-mxdb=\"{stem}\"]');e.value=-9;e.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")
    assert "dirty" in page.locator("#mxsave").get_attribute("class")      # a volume change is a change
    page.click("#mxsave")
    page.wait_for_function("!document.querySelector('#mxsave').classList.contains('dirty')", timeout=10000)
    page.click("#mxclear")
    assert page.evaluate("Object.keys(CRATE.MX.slots).length") == 0
    page.select_option("#mxload", "ui mix")
    page.wait_for_function(f"CRATE.MX.slots['{stem}']&&CRATE.MX.slots['{stem}'].track===902&&CRATE.MX.slots['{stem}'].buf", timeout=60000)
    page.select_option(f'[data-mxlen="{stem}"]', "2")
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].buf&&Math.abs(CRATE.MX.slots['{stem}'].buf.duration-4.8)<0.01", timeout=60000)
    # another slot (a second "other"), then its role changed to vocals: a part of the new kind comes in
    page.select_option("#mxaddrole", "other")
    page.click("#mxadd")
    page.wait_for_function("CRATE.MX.order.length===5&&CRATE.MX.slots[CRATE.MX.order[4]]&&CRATE.MX.slots[CRATE.MX.order[4]].buf", timeout=60000)
    new = page.evaluate("CRATE.MX.order[4]")
    assert page.evaluate(f"CRATE.MX.slots['{new}'].stem") == "other"
    page.select_option(f'[data-mxrole="{new}"]', "vocals")
    page.wait_for_function(f"CRATE.MX.roles['{new}']==='vocals'&&CRATE.MX.slots['{new}']&&CRATE.MX.slots['{new}'].stem==='vocals'&&CRATE.MX.slots['{new}'].buf", timeout=60000)
    page.click("#mxplay")
    assert page.evaluate("CRATE.MX.on") is False
    page.reload()                                   # the tab and the combination come back
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'", timeout=30000)
    page.wait_for_function(f"CRATE.MX.slots['{stem}']&&CRATE.MX.slots['{stem}'].n===2", timeout=10000)
    assert page.evaluate("CRATE.MX.order.length") == 5 and page.evaluate(f"CRATE.MX.roles['{new}']") == "vocals"
    page.evaluate("localStorage.removeItem('dcStems')")   # the next tests start with the default four slots
    page.click("#tabS")


def test_sliders_look_off_at_their_minimum(page):
    """Every slider's fill starts at its minimum (or at zero for ranges that span it): nothing shows when it's off."""
    page.evaluate("""(()=>{const d=document.createElement('div');d.id='sltest';d.innerHTML='<input type="range" id="sl1" min="0" max="10" value="0"><input type="range" id="sl2" min="-12" max="12" value="0"><input type="range" id="sl3" min="0" max="10" value="5">';document.body.appendChild(d)})()""")
    page.wait_for_function("getComputedStyle(document.querySelector('#sl3')).getPropertyValue('--b').trim()!==''", timeout=5000)
    v = lambda i, k: float(page.evaluate(f"getComputedStyle(document.querySelector('#{i}')).getPropertyValue('--{k}')"))
    assert v("sl1", "a") == 0 and v("sl1", "b") == 0            # at the minimum: no fill
    assert v("sl2", "a") == 0.5 and v("sl2", "b") == 0.5        # at zero in a ± range: no fill
    assert v("sl3", "a") == 0 and v("sl3", "b") == 0.5
    page.evaluate("(()=>{const e=document.querySelector('#sl2');e.value=-6;e.dispatchEvent(new Event('input',{bubbles:true}))})()")
    assert v("sl2", "a") == 0.25 and v("sl2", "b") == 0.5       # below zero: the fill runs from the value up to zero
    page.evaluate("document.querySelector('#sltest').remove()")
