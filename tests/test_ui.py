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
    pg.wait_for_function("typeof S!=='undefined'&&document.querySelectorAll('#list .row').length>=3", timeout=120000)
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
    page.wait_for_selector(".dfrow", timeout=120000)
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
    page.wait_for_function("TASTE.loaded", timeout=120000)
    i = page.evaluate(f"byPath.get({json.dumps(paths[3])})")
    page.evaluate(f"select({i},'list')")
    page.click("#whybtn")
    page.wait_for_function("document.querySelector('#whybox b')", timeout=120000)
    txt = page.inner_text("#whybox")
    assert "In your" in txt and "sounds closest to what you liked" in txt
    page.locator("#whybox [data-go2]").first.click()  # a liked sample opens; the explanation follows it
    page.wait_for_function(f"st.sel!=={i}")
    page.wait_for_function("document.querySelector('#whybox b')", timeout=120000)


def test_build_a_kit_around_a_hit(page):
    """🥁 build a kit around this: the hit goes into the drum lane and the finder offers the rest of a kit."""
    i = idx(page, "s[F.cat]==='Percussion'&&s[F.sub]==='Kick'")
    page.evaluate(f"select({i},'list')")
    page.click("#kitaround")
    page.wait_for_function("SK.lanes[0]&&SK.lanes[0].type==='drums'&&SK.lanes[0].pads.length===1", timeout=30000)
    page.wait_for_selector(".dfrow [data-dfadd]", timeout=120000)
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
    page.wait_for_function("SK.lanes.length&&SK.lanes[SK.lanes.length-1].state==='ok'", timeout=120000)
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
    page.wait_for_function("SK.lanes.some(l=>l.type==='drums'&&l.state==='ok')", timeout=120000)
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
    page.wait_for_function("SK.lanes.some(l=>l.type==='drums'&&l.state==='ok')", timeout=120000)
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
    page.wait_for_function("SK.lanes.some(l=>l.type==='drums'&&l.state==='ok')", timeout=120000)
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
    page.wait_for_function("_t.some(m=>m.includes('Playable pads')||m.includes('failed'))", timeout=120000)
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
    # let the list settle first (takes tags and fresh scores arrive just after the page loads and redraw it)
    y0, same = row.bounding_box()["y"], 0
    for _ in range(40):
        page.wait_for_timeout(250)
        y = row.bounding_box()["y"]
        same = same + 1 if abs(y - y0) < 0.5 else 0
        y0 = y
        if same >= 6:
            break
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
    page.wait_for_function(f"SK.lanes.length>{n0}&&SK.lanes[SK.lanes.length-1].state==='ok'", timeout=120000)
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
    """🎛 Mashup: prepared songs, 🎲 all fills the slots with parts rendered to the tempo, they loop in sync, and a
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
    page.evaluate(f"CRATE.TR.setLoop('{stem}',CRATE.MX.slots['{stem}'].bar0,2)")
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].buf&&Math.abs(CRATE.MX.slots['{stem}'].buf.duration-4.8)<0.01", timeout=120000)
    page.click("#mxup")
    page.wait_for_function("CRATE.MX.rated>0", timeout=10000)
    # the waveform and its play line
    page.wait_for_function(f"(()=>{{const b=document.querySelector('[data-mxwave=\"{stem}\"]');return b&&b.querySelector('canvas').width>50&&getComputedStyle(b.querySelector('i')).display==='block'}})()", timeout=10000)
    # ↶ goes back to the part a slot held before a 🎲, ↷ forward again
    before = page.evaluate(f"[CRATE.MX.slots['{stem}'].track,CRATE.MX.slots['{stem}'].bar0]")
    page.click(f'[data-mxroll="{stem}"]')
    page.wait_for_function(f"(()=>{{const p=CRATE.MX.slots['{stem}'];return p&&p.buf&&!p._loading&&(p.track!=={before[0]}||p.bar0!=={before[1]})}})()", timeout=120000)
    after = page.evaluate(f"[CRATE.MX.slots['{stem}'].track,CRATE.MX.slots['{stem}'].bar0]")
    page.click(f'[data-mxhist="{stem}:-1"]')
    page.wait_for_function(f"(()=>{{const p=CRATE.MX.slots['{stem}'];return p.track==={before[0]}&&p.bar0==={before[1]}&&p.buf&&!p._loading}})()", timeout=120000)
    page.click(f'[data-mxhist="{stem}:1"]')
    page.wait_for_function(f"(()=>{{const p=CRATE.MX.slots['{stem}'];return p.track==={after[0]}&&p.bar0==={after[1]}&&p.buf&&!p._loading}})()", timeout=120000)
    # a part that is all sub-bass gets harmonics by itself (small speakers can't play it), and says so
    b = next((k for k in page.evaluate("CRATE.MX.order") if page.evaluate(f"CRATE.MX.roles['{{}}']".format(k)) == "bass" and page.evaluate(f"!!CRATE.MX.slots['{{}}']".format(k))), None)
    if b:
        page.wait_for_function(f"CRATE.MX.slots['{b}'].sub>=0.85&&CRATE.MX.slots['{b}'].harm===1", timeout=30000)
        assert "sub-bass" in page.locator(f'[data-mxrow="{b}"] .mxsrc').inner_text()
    # the list of prepared songs, and a stem button that puts a song straight into a slot of that kind
    page.click("#mxsongs summary")
    page.wait_for_function("document.querySelectorAll('#mxsongs .mxsong').length===3", timeout=10000)
    page.click('[data-mxput="drums:903"]')
    page.wait_for_function("Object.entries(CRATE.MX.slots).some(([id,p])=>CRATE.MX.roles[id]==='drums'&&p&&p.track===903&&p.buf)", timeout=120000)
    # ⇄ steps to another stretch of the same stem in the same song
    b0, tr = page.evaluate(f"[CRATE.MX.slots['{stem}'].bar0,CRATE.MX.slots['{stem}'].track]")
    _more(page, stem)
    page.click(f'[data-mxalt="{stem}"]')
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].bar0!=={b0}&&CRATE.MX.slots['{stem}'].buf&&!CRATE.MX.slots['{stem}']._loading", timeout=120000)
    assert page.evaluate(f"CRATE.MX.slots['{stem}'].track") == tr and page.evaluate(f"CRATE.MX.slots['{stem}'].alt[1]") >= 2
    # ✕ takes a part out; 🔍 puts a chosen song in
    _more(page, stem)
    page.click(f'[data-mxdel="{stem}"]')
    page.wait_for_function(f"!CRATE.MX.slots['{stem}']", timeout=10000)
    _more(page, stem)
    page.click(f'[data-mxfind="{stem}"]')
    page.fill("#mxq", "Stem Artist 902")
    page.wait_for_selector(f'[data-mxsong="{stem}:902"]')
    page.keyboard.press("Enter")
    page.wait_for_function(f"CRATE.MX.slots['{stem}']&&CRATE.MX.slots['{stem}'].track===902&&CRATE.MX.slots['{stem}'].buf", timeout=120000)
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
    page.wait_for_function(f"CRATE.MX.slots['{stem}']&&CRATE.MX.slots['{stem}'].track===902&&CRATE.MX.slots['{stem}'].buf", timeout=120000)
    page.evaluate(f"CRATE.TR.setLoop('{stem}',CRATE.MX.slots['{stem}'].bar0,2)")
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].buf&&Math.abs(CRATE.MX.slots['{stem}'].buf.duration-4.8)<0.01", timeout=120000)
    # ↺ revert: changes made to an open saved combination are dropped, and it's back as saved
    saved_track = page.evaluate(f"CRATE.MX.slots['{stem}'].track")
    _more(page, stem)
    page.click(f'[data-mxdel="{stem}"]')
    page.wait_for_function(f"!CRATE.MX.slots['{stem}']", timeout=10000)
    page.click("#mxrevert")
    page.wait_for_function(f"CRATE.MX.slots['{stem}']&&CRATE.MX.slots['{stem}'].track==={saved_track}&&CRATE.MX.slots['{stem}'].buf", timeout=120000)
    page.wait_for_function("!document.querySelector('#mxsave').classList.contains('dirty')", timeout=10000)
    page.evaluate(f"CRATE.TR.setLoop('{stem}',CRATE.MX.slots['{stem}'].bar0,2)")   # (the saved one had 4 bars: 2 again, for the reload check below)
    page.wait_for_function(f"CRATE.MX.slots['{stem}'].buf&&Math.abs(CRATE.MX.slots['{stem}'].buf.duration-4.8)<0.01", timeout=120000)
    # another slot (a second "other"), then its role changed to vocals: a part of the new kind comes in
    page.select_option("#mxaddrole", "other")
    page.click("#mxadd")
    page.wait_for_function("CRATE.MX.order.length===5&&CRATE.MX.slots[CRATE.MX.order[4]]&&CRATE.MX.slots[CRATE.MX.order[4]].buf", timeout=120000)
    new = page.evaluate("CRATE.MX.order[4]")
    assert page.evaluate(f"CRATE.MX.slots['{new}'].stem") == "other"
    _more(page, new)
    page.select_option(f'[data-mxrole="{new}"]', "vocals")
    page.wait_for_function(f"CRATE.MX.roles['{new}']==='vocals'&&CRATE.MX.slots['{new}']&&CRATE.MX.slots['{new}'].stem==='vocals'&&CRATE.MX.slots['{new}'].buf", timeout=120000)
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


# ---------------------------------------------------------------------------------------------------- stem blends
def _mixer(site, page, bpm=100):
    """🎛 Mashup on the three prepared test songs, with a part dealt into each of the four slots and playing."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.click("#tabM")
    page.wait_for_selector("#mxall")
    page.fill("#mxbpm", str(bpm))
    page.dispatch_event("#mxbpm", "change")
    page.click("#mxall")
    page.wait_for_function("CRATE.MX.on&&['drums','bass','vocals','other'].every(s=>CRATE.MX.slots[s]&&CRATE.MX.slots[s].buf)", timeout=90000)


def _set(page, sel, value, events=("input",)):
    """Set a slider or a number field the way a hand does: the value, then the events the app listens for."""
    page.evaluate("([sel,v,evs])=>{const e=document.querySelector(sel);e.value=v;evs.forEach(n=>e.dispatchEvent(new Event(n,{bubbles:true})))}",
                  [sel, str(value), list(events)])


BLEND_AUDIO = r"""async () => {
  const BL = window.BLEND, SR = 44100, N = 4 * SR, out = {};
  const db = x => 20 * Math.log10(Math.max(x, 1e-12));
  const rms = (d, a, b) => { let s = 0; for (let i = a; i < b; i++) s += d[i] * d[i]; return Math.sqrt(s / (b - a)); };
  const play = (ctx, buf) => { const s = ctx.createBufferSource(); s.buffer = buf; s.start(0); return s; };
  const noise = (ctx, secs, seed) => { const b = ctx.createBuffer(1, secs * SR, SR), d = b.getChannelData(0); let s = seed;
    for (let i = 0; i < d.length; i++) { s = (s * 16807) % 2147483647; d[i] = (s / 2147483647) * 2 - 1; } return b; };
  // the level of one band of a signal: three bandpasses in a row, rendered offline
  const band = async (data, f0, q) => { const c = new OfflineAudioContext(1, data.length, SR), b = c.createBuffer(1, data.length, SR);
    b.copyToChannel(data, 0); let n = play(c, b);
    for (let i = 0; i < 3; i++) { const f = c.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = f0; f.Q.value = q; n.connect(f); n = f; }
    n.connect(c.destination); return (await c.startRendering()).getChannelData(0); };

  // 1. a parked blend filter passes everything, to the sample
  { const c = new OfflineAudioContext(1, SR, SR), nb = noise(c, 1, 7), x = BL.mkXf(c); play(c, nb).connect(x.in); x.out.connect(c.destination);
    const y = (await c.startRendering()).getChannelData(0), d = nb.getChannelData(0); let mx = 0;
    for (let i = 0; i < d.length; i++) mx = Math.max(mx, Math.abs(y[i] - d[i])); out.parked_max_diff = mx; }

  // 2. halfway through a filter handoff (cutoff 632 Hz): what is left of each side two octaves the wrong way, in dB
  out.handoff = {};
  for (const side of ['a', 'b']) { const c = new OfflineAudioContext(1, 2 * SR, SR), nb = noise(c, 2, side === 'a' ? 11 : 13), x = BL.mkXf(c), o = BL.blendAt('filter', 0.5, SR / 2);
    BL.setXf(x, side === 'a' ? { gain: o.ga, hp: o.hp, lp: SR / 2 } : { gain: o.gb, hp: 0, lp: o.lp }, 0);
    play(c, nb).connect(x.in); x.out.connect(c.destination); const y = (await c.startRendering()).getChannelData(0), d = nb.getChannelData(0);
    for (const f of [158, 2528]) out.handoff[side + '_' + f] = db(rms(await band(y, f, 4), SR, 2 * SR)) - db(rms(await band(d, f, 4), SR, 2 * SR)); }

  // 3. the duck: a kick on every beat at 120 bpm, at the loudness the server gives every part (RMS 0.08), over a bass of 55 Hz + 440 Hz
  const kick = ctx => { const b = ctx.createBuffer(1, N, SR), d = b.getChannelData(0);
    for (let beat = 0; beat < 8; beat++) { let ph = 0; const i0 = Math.round(beat * 0.5 * SR);
      for (let i = 0; i < 0.4 * SR; i++) { const t = i / SR; ph += 2 * Math.PI * (50 + 100 * Math.exp(-t / 0.03)) / SR; d[i0 + i] += Math.sin(ph) * Math.exp(-t / 0.12); } }
    const g = Math.min(0.08 / rms(d, 0, N), 0.9 / d.reduce((m, v) => Math.max(m, Math.abs(v)), 0)); for (let i = 0; i < N; i++) d[i] *= g; return b; };
  const bass = ctx => { const b = ctx.createBuffer(1, N, SR), d = b.getChannelData(0);
    for (let i = 0; i < N; i++) d[i] = 0.2 * Math.sin(2 * Math.PI * 55 * i / SR) + 0.1 * Math.sin(2 * Math.PI * 440 * i / SR); return b; };
  const O = { fx: true, bar: 2, DT: { '1/8': 1 / 8 } };
  const run = async (duck, drumsOn) => { const c = new OfflineAudioContext(2, N, SR), merge = c.createChannelMerger(2); merge.connect(c.destination);
    const MX = {}; BL.out(MX, c); MX.master.disconnect();                       // the bus without the speakers: each chain to its own channel
    const outB = c.createGain(), outK = c.createGain(); outB.connect(merge, 0, 0); outK.connect(merge, 0, 1);
    const cb = BL.mkChain(c, outB, MX.bus), ck = BL.mkChain(c, outK, MX.bus);
    BL.applyChain(cb, BL.mixOf({ db: 0 }, 'bass', { ...O, on: true, duck }), 0);
    BL.applyChain(ck, BL.mixOf({ db: 0 }, 'drums', { ...O, on: drumsOn }), 0);
    play(c, bass(c)).connect(cb.in); play(c, kick(c)).connect(ck.in); return (await c.startRendering()).getChannelData(0); };
  const ref = await run({ on: false }, true), lo0 = await band(ref, 55, 3), hi0 = await band(ref, 440, 6);
  const dip = async (duck, drumsOn) => { const y = await run(duck, drumsOn), lo = await band(y, 55, 3), hi = await band(y, 440, 6), w = Math.round(0.02 * SR), dips = [];
    for (let k = 0; k < 25; k++) { const a = 2 * SR + k * w; dips.push(db(rms(lo, a, a + w)) - db(rms(lo0, a, a + w))); }   // one beat, in 20 ms steps
    return { deepest: Math.min(...dips), shallowest: Math.max(...dips), high: db(rms(hi, 2 * SR, 3 * SR)) - db(rms(hi0, 2 * SR, 3 * SR)) }; };
  out.duck3 = await dip(undefined, true);            // no setting yet: on, 3 dB
  out.duck12 = await dip({ on: true, db: 12 }, true);
  out.muted = await dip({ on: true, db: 12 }, false); // muted drums duck nothing
  out.off = await dip({ on: false, db: 12 }, true);
  return out;
}"""


def test_blend_audio_core(page):
    """The stem blends audio graph, measured offline: a parked blend filter changes nothing, a filter handoff splits the
    spectrum between the two parts, and the duck takes a few dB off the bass's low end only, only under the kick."""
    o = page.evaluate(BLEND_AUDIO)
    assert o["parked_max_diff"] < 1e-6
    h = o["handoff"]
    assert h["a_158"] < -40 and h["b_2528"] < -40            # the outgoing part has no lows left, the incoming one no highs yet
    assert abs(h["a_2528"]) < 0.5 and abs(h["b_158"]) < 0.5  # and each keeps its own side whole
    assert -3.5 < o["duck3"]["deepest"] < -2.0 and o["duck3"]["shallowest"] > -0.5   # down under the kick, back between kicks
    assert abs(o["duck3"]["high"]) < 0.2                     # 440 Hz is left alone
    assert -13.0 < o["duck12"]["deepest"] < -9.0
    assert o["muted"]["deepest"] > -0.1 and o["off"]["deepest"] > -0.1


def test_duck_is_on_for_bass_and_remembered(site, page):
    """DUCK: on by default at 3 dB, on bass rows only; the switch and the amount are kept across a reload."""
    _mixer(site, page)
    assert page.locator("[data-mxduckon]").count() == 1 and page.locator('[data-mxduckon="bass"]').count() == 1
    assert page.evaluate("CRATE.MX.duck.bass?.db ?? BLEND.DUCK.db") == 3
    page.wait_for_function("CRATE.MX.slots.bass._c&&CRATE.MX.slots.bass._c.ducked===true&&CRATE.MX.slots.drums._c.ducked===false")
    page.evaluate("CRATE.TR.set('bass','duck',6)")
    assert page.evaluate("CRATE.MX.duck.bass.db") == 6
    page.click('[data-mxduckon="bass"]')
    page.wait_for_function("CRATE.MX.slots.bass._c.ducked===false&&CRATE.MX.duck.bass.on===false")
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).duck.bass") == {"on": False, "db": 6}
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX.duck.bass&&CRATE.MX.duck.bass.on===false", timeout=30000)


def test_state_saved_before_blends_still_opens(site, page):
    """A mixer saved before snapshots and the duck existed (no duck, snaps or trans keys) opens with their defaults."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.evaluate("""localStorage.setItem('dcStems',JSON.stringify({bpm:100,key:'',name:'',fx:true,order:['drums','bass','vocals','other'],
      roles:{drums:'drums',bass:'bass',vocals:'vocals',other:'other'},slots:{bass:{stem:'bass',track:901,bar0:0,n:4,k:1,off:0,bars:16,
      artist:'Stem Artist 901',title:'Song',db:-2,mute:false,lock:false,eq:[0,0,0],dly:0,dt:'1/8',eqOn:true,dlyOn:true}}}));localStorage.setItem('dcTab','M')""")
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX.slots.bass&&CRATE.MX.slots.bass.buf", timeout=120000)
    assert page.evaluate("[CRATE.MX.snaps.length,CRATE.MX.trans.length,Object.keys(CRATE.MX.duck).length]") == [0, 0, 0]
    assert page.evaluate("CRATE.MX.duck.bass?.db ?? BLEND.DUCK.db") == 3


def _roll(page, slot, track):
    """Put this prepared song's best-fitting bars into a slot, and wait until they are loaded."""
    page.evaluate(f"CRATE.mxRoll('{slot}', true, {track})")
    page.wait_for_function(f"CRATE.MX.slots['{slot}']&&CRATE.MX.slots['{slot}'].track==={track}&&CRATE.MX.slots['{slot}'].buf&&!CRATE.MX.slots['{slot}']._loading", timeout=120000)


def test_snapshots_capture_recall_replace_delete(site, page):
    """📸 keeps the mixer as it is; a snapshot comes back with a click, can be replaced and deleted, survives a reload,
    freezes an auto key, and teaches the recommendations."""
    _mixer(site, page)
    assert page.evaluate("CRATE.MX.snaps.length") == 0 and page.is_disabled("#snplay")
    _roll(page, "drums", 901)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===1&&CRATE.MX.snapSel===0")
    assert page.evaluate("CRATE.MX.key") != ""                                   # an auto key is frozen by the first snapshot
    page.wait_for_function("CRATE.MX.rated>=4", timeout=10000)                   # four slots, four weak yeses
    _roll(page, "drums", 902)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===2&&CRATE.MX.snapSel===1")
    label = page.inner_text('[data-sn="1"]')
    assert "B" in label and "drums" in label and "bass" not in label             # what changed since A
    assert "start" in page.inner_text('[data-sn="0"]')
    assert page.evaluate("CRATE.MX.trans.length") == 1 and page.is_enabled("#snplay")
    page.click('[data-sn="0"]')                                                  # A comes back
    page.wait_for_function("CRATE.MX.snapSel===0&&CRATE.MX.slots.drums.track===901&&CRATE.MX.slots.drums.buf", timeout=120000)
    bass = page.evaluate("CRATE.MX.slots.bass.track")
    _roll(page, "bass", 903 if bass != 903 else 901)
    page.click("#snrep")                                                         # ... and is replaced by what is playing now
    page.wait_for_function(f"CRATE.MX.snaps[0].slots.bass.track!=={bass}")
    assert page.evaluate("CRATE.MX.snaps.length") == 2
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX.snaps.length===2", timeout=30000)
    assert page.evaluate("[CRATE.MX.snaps[0].slots.drums.track,CRATE.MX.snaps[1].slots.drums.track,CRATE.MX.trans.length]") == [901, 902, 1]
    page.click('[data-sn="1"]')
    page.wait_for_function("CRATE.MX.snapSel===1")
    page.click("#sndel")
    page.wait_for_function("CRATE.MX.snaps.length===1&&CRATE.MX.trans.length===0&&CRATE.MX.snapSel===null")
    assert page.is_disabled("#snplay")


def test_blend_model(page):
    """The pure half of the stem blends block: which layers differ between two snapshots, each transition's settings (kept from
    the transition before), where a layer is for a master position, and the mix of a layer that stays."""
    r = page.evaluate("""() => { const B = BLEND, P = (stem, track, o) => Object.assign({stem, track, bar0: 0, n: 4, k: 1, off: 0, db: 0, eq: [0, 0, 0], dly: 0, dt: '1/8'}, o);
      const A = {order: ['drums', 'bass', 'vocals', 'other'], roles: {drums: 'drums', bass: 'bass', vocals: 'vocals', other: 'other'}, duck: {},
                 slots: {drums: P('drums', 1), bass: P('bass', 2, {db: -2}), vocals: P('vocals', 3, {mute: true})}};
      const Z = {order: ['drums', 'bass', 'vocals', 'other', 's1'], roles: {drums: 'drums', bass: 'bass', vocals: 'vocals', other: 'vocals', s1: 'other'}, duck: {},
                 slots: {drums: P('drums', 1, {bar0: 4}), bass: P('bass', 2, {db: -4}), other: P('vocals', 5), s1: P('other', 6)}};
      const rows = B.diffSnaps(A, Z), MX = {snaps: [A, Z, A], trans: [{bars: 4, layers: {drums: {style: 'xfade', win: 'second'}}}, {bars: 16, layers: {}}]};
      const T = B.transFor(MX, 0);
      return {rows: rows.map(x => [x.id, x.stem, x.kind]), back: B.diffSnaps(Z, A).map(x => [x.id, x.kind]), t0: T, t1: B.transFor(MX, 1),
        pos: [B.rowPos(rows[0], 0.75, T, {}), B.rowPos(rows[1], 0.75, T, {}), B.rowPos(rows[0], 0.75, T, {drums: 0.1})],
        mix: B.lerpMix(P('bass', 2, {db: -2, eq: [2, 0, 0], dly: 0.4, dt: '1/4'}), P('bass', 2, {db: -4, eq: [6, 0, 0], eqOn: false, dly: 0, dt: '1/16'}), 0.25),
        lp: [B.layerPos(0.25, 'all'), B.layerPos(0.25, 'first'), B.layerPos(0.25, 'second'), B.layerPos(0.75, 'second'), B.layerPos(0.49, 'cut'), B.layerPos(0.5, 'cut')],
        b: [B.blendAt('filter', 0, 22050), B.blendAt('filter', 0.5, 22050), B.blendAt('xfade', 0.5, 22050), B.blendAt('filter', 1, 22050), B.blendAt('filter', 0.025, 22050)]}; }""")
    # a moved loop is a changed layer; a volume change alone is not; a muted part counts as absent; a slot's stem is the side that sounds
    assert r["rows"] == [["drums", "drums", "change"], ["bass", "bass", "same"], ["vocals", "vocals", "empty"], ["other", "vocals", "enter"], ["s1", "other", "enter"]]
    assert r["back"] == [["drums", "change"], ["bass", "same"], ["vocals", "empty"], ["other", "exit"], ["s1", "exit"]]
    new = {"style": "filter", "win": "all"}
    assert r["t0"] == {"bars": 4, "layers": {"drums": {"style": "xfade", "win": "second"}, "other": new, "s1": new}}
    assert r["t1"] == {"bars": 16, "layers": {"drums": {"style": "xfade", "win": "second"}, "other": new, "s1": new}}   # drums: from the transition before
    assert r["pos"] == [0.5, 0.75, 0.1]
    m = r["mix"]
    assert m["db"] == -2.5 and m["eq"] == [1.5, 0, 0] and abs(m["dly"] - 0.3) < 1e-9 and m["dt"] == "1/4" and m["eqOn"] is True and m["dlyOn"] is True
    assert r["lp"] == [0.25, 0.5, 0, 0.5, 0, 1]
    b = r["b"]
    assert b[0] == {"ga": 1, "gb": 0, "hp": 0, "lp": 22050} and b[3] == {"ga": 0, "gb": 1, "hp": 0, "lp": 22050}
    assert b[1]["ga"] == 1 and b[1]["gb"] == 1 and abs(b[1]["hp"] - 632.4555) < 0.001 and b[1]["lp"] == b[1]["hp"]
    assert abs(b[2]["ga"] - 0.70711) < 1e-4 and abs(b[2]["gb"] - 0.70711) < 1e-4 and b[2]["hp"] == 0 and b[2]["lp"] == 22050
    assert b[4]["ga"] == 1 and abs(b[4]["gb"] - 0.5) < 1e-9


def _strip(site, page, bpm=100, three=False):
    """A strip on the test songs: A (drums from song 901), B (drums from 902, "other" taken out) and, with three=True,
    C (bass from another song)."""
    _mixer(site, page, bpm)
    _roll(page, "drums", 901)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===1")
    _roll(page, "drums", 902)
    _more(page, 'other')
    page.click('[data-mxdel="other"]')
    page.wait_for_function("!CRATE.MX.slots.other")
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===2")
    if three:
        bass = page.evaluate("CRATE.MX.slots.bass.track")
        _roll(page, "bass", 903 if bass != 903 else 901)
        page.click("#sncap")
        page.wait_for_function("CRATE.MX.snaps.length===3")


def _voice(page, slot, side):
    """What a playback voice was last told: its gain, highpass and lowpass, and how long its loop is. None if there is none."""
    return page.evaluate(f"(()=>{{const v=CRATE.PB.voice('{slot}','{side}');return v?{{...v.set,dur:v.buf.duration}}:null}})()")


def test_playback_shows_both_sets_and_blends_by_hand(site, page):
    """▶ play strip: both snapshots' four slots side by side, the transition controls between them, and a master and a
    slider per layer that move the sound from the left snapshot to the right one."""
    _strip(site, page)
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    assert page.evaluate("CRATE.MX.on") is False and page.is_visible("#pb")
    assert page.locator('#pb [data-pbside="a"]').count() == 4 and page.locator('#pb [data-pbside="b"]').count() == 4   # all eight slots
    assert page.evaluate("CRATE.PB.rows.map(r=>[r.id,r.kind])") == [["drums", "change"], ["bass", "same"], ["vocals", "same"], ["other", "exit"]]
    a, b = _voice(page, "drums", "a"), _voice(page, "drums", "b")
    assert a["gain"] == 1 and b["gain"] == 0 and abs(b["dur"] - 9.6) < 0.01                 # 4 bars at 100 bpm, loaded but silent
    assert page.evaluate("CRATE.PB.voice('bass','a')===CRATE.PB.voice('bass','b')")          # a layer that stays is one voice
    assert "same in both" in page.inner_text('[data-pbrow="bass"]')
    # every slot shows its waveform with a play line, as the mixer's rows do
    page.wait_for_function("(()=>{const b=document.querySelector('[data-pbwave=\"b:drums\"]');return b&&b.querySelector('canvas').width>50&&getComputedStyle(b.querySelector('i')).display==='block'})()", timeout=10000)
    _set(page, "#pbm", 50)                                                                   # the master, halfway
    assert page.evaluate("CRATE.PB.m") == 0.5 and page.input_value('[data-pbpos="drums"]') == "50"
    a, b = _voice(page, "drums", "a"), _voice(page, "drums", "b")
    assert a["gain"] == 1 and b["gain"] == 1 and abs(a["hp"] - 632.46) < 0.1 and abs(b["lp"] - 632.46) < 0.1 and b["hp"] == 0
    assert abs(_voice(page, "other", "a")["hp"] - 632.46) < 0.1 and _voice(page, "other", "b") is None   # leaves alone
    page.select_option('[data-pbstyle="drums"]', "xfade")
    a, b = _voice(page, "drums", "a"), _voice(page, "drums", "b")
    assert abs(a["gain"] - 0.7071) < 0.001 and abs(b["gain"] - 0.7071) < 0.001 and a["hp"] == 0
    page.select_option('[data-pbwin="drums"]', "second")                                     # changes over the second half only
    assert page.evaluate("CRATE.PB.pos('drums')") == 0 and _voice(page, "drums", "b")["gain"] == 0
    _set(page, "#pbm", 75)
    assert page.evaluate("CRATE.PB.pos('drums')") == 0.5
    _set(page, '[data-pbpos="other"]', 100, ("input", "change"))                            # one layer by hand
    assert page.evaluate("[CRATE.PB.pos('other'),CRATE.PB.m]") == [1, 0.75]
    assert page.locator('[data-pbrow="other"] .tag.hot').count() == 1 and page.locator('[data-pbwin="other"]').count() == 0
    _set(page, "#pbm", 100)
    assert page.evaluate("CRATE.PB.atEnd(1)") is True and page.is_disabled("#pbnext")        # B is the last snapshot
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).trans[0].layers.drums") == {"style": "xfade", "win": "second"}
    page.click("#pbback")
    page.wait_for_selector("#mxall")
    assert page.evaluate("CRATE.PB.on") is False
    _set(page, "#mxbpm", 120, ("change",))                                                   # the strip plays at the mixer's tempo
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    assert abs(_voice(page, "drums", "a")["dur"] - 8.0) < 0.01


def test_playback_arrows_walk_the_strip(site, page):
    """Fully on the right snapshot, ▶ moves the view on: B to the left without a gap in its sound, C on the right.
    ◀ goes back. A part whose song is no longer prepared shows as missing and the rest plays on."""
    _strip(site, page, three=True)
    page.evaluate("CRATE.MX.snaps[2].slots.vocals.track=999999")
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing&&CRATE.PB.nextReady", timeout=90000)
    assert page.is_disabled("#pbnext") and page.is_disabled("#pbprev")
    _set(page, "#pbm", 100)
    page.wait_for_function("!document.querySelector('#pbnext').disabled")
    key, t = page.evaluate("[CRATE.PB.voice('drums','b').key,CRATE.PB.voice('drums','b').t]")
    page.click("#pbnext")
    page.wait_for_function("CRATE.PB.i===1&&CRATE.PB.ready", timeout=120000)
    assert page.evaluate("[CRATE.PB.m,[...document.querySelectorAll('#pb .pbletter')].map(e=>e.textContent)]") == [0, ["B", "C"]]
    assert page.evaluate("[CRATE.PB.voice('drums','a').key,CRATE.PB.voice('drums','a').t]") == [key, t]     # B's drums never stopped
    assert "missing" in page.inner_text('[data-pbrow="vocals"] [data-pbside="b"]')
    assert page.evaluate("CRATE.PB.rows.find(r=>r.id==='vocals').kind") == "exit"
    assert page.is_disabled("#pbnext")                                                                    # C is the last one
    page.click("#pbprev")
    page.wait_for_function("CRATE.PB.i===0&&CRATE.PB.ready", timeout=120000)
    assert page.evaluate("CRATE.PB.m") == 1


def test_playback_waits_for_the_next_snapshot(site, page):
    """The arrow stays off until the next snapshot's parts are loaded, however long that takes."""
    _strip(site, page, three=True)
    page.evaluate("""(()=>{const api=CRATE.api,slow=CRATE.MX.snaps[2].slots.bass.track;
      CRATE.api=(p,b)=>p==='api/stems/render'&&b.stem==='bass'&&b.track===slow?new Promise(r=>setTimeout(r,4000)).then(()=>api(p,b)):api(p,b)})()""")
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    _set(page, "#pbm", 100)
    assert page.evaluate("CRATE.PB.nextReady") is False and page.is_disabled("#pbnext")
    page.wait_for_function("CRATE.PB.nextReady&&!document.querySelector('#pbnext').disabled", timeout=20000)


def test_auto_walks_the_strip_and_hands_back_control(site, page):
    """auto: hold a snapshot, move the master across over the transition's bars, move the view on, and stop on the last
    snapshot. A hand on a slider switches it off where it stands."""
    _strip(site, page, bpm=200, three=True)                  # 200 bpm: a bar lasts 1.2 s
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing&&CRATE.PB.nextReady", timeout=90000)
    page.select_option("#pbbars", "2")
    page.evaluate("CRATE.PB.setHold(1)")                     # the menu offers 4, 8 and 16 bars: one keeps the test short
    page.click("#pbauto")
    assert page.evaluate("CRATE.PB.auto") is True
    page.wait_for_function("CRATE.PB.i===0&&CRATE.PB.m>0.2&&CRATE.PB.m<1", timeout=15000)   # moving, after the hold
    assert "bar" in page.inner_text("#pbstat")
    page.wait_for_function("CRATE.PB.i===1", timeout=15000)                                # on B: the view moved on by itself
    _set(page, "#pbm", 30)                                                                  # a hand on the master
    assert page.evaluate("[CRATE.PB.auto,CRATE.PB.m]") == [False, 0.3]
    page.click("#pbauto")                                                                   # on again from where it stands
    page.wait_for_function("CRATE.PB.i===1&&CRATE.PB.m===1&&CRATE.PB.auto===false", timeout=30000)   # the last snapshot: it stays


def test_auto_holds_after_a_slow_next_snapshot(site, page):
    """auto waits on a snapshot that loads slowly, and once it is in, holds it before moving on: it never skips the
    hold or cuts through the transition because the wait was long."""
    _strip(site, page, bpm=200, three=True)                  # a bar lasts 1.2 s
    page.evaluate("""(()=>{const api=CRATE.api,slow=CRATE.MX.snaps[2].slots.bass.track;
      CRATE.api=(p,b)=>p==='api/stems/render'&&b.stem==='bass'&&b.track===slow?new Promise(r=>setTimeout(r,12000)).then(()=>api(p,b)):api(p,b)})()""")
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    page.select_option("#pbbars", "2")
    page.evaluate("CRATE.PB.setHold(1)")
    page.click("#pbauto")
    page.wait_for_function("CRATE.PB.i===1&&CRATE.PB.ready", timeout=40000)
    page.wait_for_timeout(300)
    assert page.evaluate("[CRATE.PB.auto,CRATE.PB.m,CRATE.PB.ph&&CRATE.PB.ph.kind]") == [True, 0, "hold"]


def test_a_failed_info_call_keeps_the_pair_playing(site, page):
    """When the server cannot answer for the next pair, ▶ leaves the view where it is and the sound playing; nothing
    is marked missing."""
    _strip(site, page, three=True)
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing&&CRATE.PB.nextReady", timeout=90000)
    _set(page, "#pbm", 100)
    page.wait_for_function("!document.querySelector('#pbnext').disabled")
    page.evaluate("""(()=>{const api=CRATE.api;CRATE.api=(p,b)=>p==='api/stems/info'?Promise.reject(new Error('down')):api(p,b)})()""")
    page.click("#pbnext")
    page.wait_for_timeout(1500)
    assert page.evaluate("[CRATE.PB.i,CRATE.PB.ready,!!(CRATE.PB.voice('drums','b')&&CRATE.PB.voice('drums','b').src)]") == [0, True, True]
    assert "missing" not in page.inner_text("#pb")


def test_changing_the_length_during_auto_does_not_jump(site, page):
    """A new transition length while auto is moving changes its speed from where the master is, not its position."""
    _strip(site, page, bpm=200, three=True)
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing&&CRATE.PB.nextReady", timeout=90000)
    page.evaluate("CRATE.PB.setHold(1)")
    page.click("#pbauto")                                    # over 8 bars: 9.6 s
    page.wait_for_function("CRATE.PB.m>0.3", timeout=20000)
    page.select_option("#pbbars", "2")
    page.wait_for_timeout(150)
    assert page.evaluate("CRATE.PB.m") < 0.6 and page.evaluate("CRATE.PB.i") == 0


def test_snapshot_says_when_the_mixer_has_moved_on(site, page):
    """Edits change the mixer, not the snapshot it came from: the strip says so and points at ↻ replace."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.evaluate("localStorage.removeItem('dcStems')")
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&window.CRATE&&CRATE.MX", timeout=30000)
    page.click("#tabM")
    page.wait_for_selector("#mxall")
    page.click("#mxall")
    page.wait_for_function("Object.values(CRATE.MX.slots).some(p=>p&&p.buf)", timeout=90000)
    page.click("#sncap")
    page.wait_for_selector("#snrep")
    assert "dirty" not in (page.locator("#snrep").get_attribute("class") or "")
    sid = page.evaluate("CRATE.MX.order.find(id=>CRATE.MX.slots[id]&&CRATE.MX.slots[id].buf)")
    page.click(f'[data-mxmute="{sid}"]')
    page.wait_for_function("document.querySelector('#snrep').classList.contains('dirty')", timeout=5000)
    assert "has changed since A" in page.inner_text("#snnote")
    assert page.evaluate(f"CRATE.MX.snaps[0].slots['{sid}'].mute") is False      # the snapshot itself is untouched
    page.click("#snrep")
    page.wait_for_function("!document.querySelector('#snrep').classList.contains('dirty')", timeout=5000)
    assert page.evaluate(f"CRATE.MX.snaps[0].slots['{sid}'].mute") is True       # ↻ wrote the change into it
    # a snapshot click replaces the mixer: when what was there isn't in any snapshot, it can be undone
    _more(page, sid)
    page.click(f'[data-mxdel="{sid}"]')
    page.wait_for_function(f"!CRATE.MX.slots['{sid}']", timeout=10000)
    page.click('[data-sn="0"]')
    page.wait_for_function(f"CRATE.MX.snapSel===0&&CRATE.MX.slots['{sid}']&&CRATE.MX.slots['{sid}'].buf", timeout=120000)
    page.wait_for_selector("#snundo")
    page.click("#snundo")
    page.wait_for_function(f"!CRATE.MX.slots['{sid}']&&CRATE.MX.snapSel===null", timeout=30000)
    # clear all is a clean slate: the strip goes too (asked once more first), so it can't tag along into the next one
    page.click("#mxclear")
    assert page.evaluate("CRATE.MX.snaps.length") == 1 and "click again" in page.inner_text("#mxclear")
    page.click("#mxclear")
    assert page.evaluate("CRATE.MX.snaps.length") == 0 and page.evaluate("Object.keys(CRATE.MX.slots).length") == 0
    page.evaluate("CRATE.mxPlay(false)")
    page.evaluate("localStorage.removeItem('dcStems')")
    page.click("#tabS")


def test_reverb_has_a_tail_that_decays_and_is_stereo(page):
    """The mixer's reverb, measured offline: a short burst rings on, dies away at about the decay time, and left and
    right differ (it is wide). A longer decay rings longer."""
    r = page.evaluate("""async()=>{
      const run=async(type,decay)=>{const sr=44100,c=new OfflineAudioContext(2,sr*4,sr),out=c.createGain();out.connect(c.destination);
        const rv=BLEND.reverb(c,out,{type,decay}),b=c.createBuffer(1,Math.floor(0.03*sr),sr),d=b.getChannelData(0);
        for(let i=0;i<d.length;i++)d[i]=Math.sin(i*0.9)*Math.sin(i*0.31)*0.8;            // a 30 ms burst with highs and mids
        const s=c.createBufferSource();s.buffer=b;s.connect(rv.in);s.start(0);
        const o=await c.startRendering(),L=o.getChannelData(0),R=o.getChannelData(1);
        const rms=(x,a,z)=>{let e=0;const i0=Math.floor(a*sr),i1=Math.floor(z*sr);for(let i=i0;i<i1;i++)e+=x[i]*x[i];return Math.sqrt(e/(i1-i0))};
        let num=0,dl=0,dr=0;for(let i=Math.floor(0.1*sr);i<sr;i++){num+=L[i]*R[i];dl+=L[i]*L[i];dr+=R[i]*R[i]}
        return {early:rms(L,0.1,0.3),late:rms(L,decay-0.1,decay+0.1),end:rms(L,3.5,3.9),corr:num/Math.sqrt(dl*dr+1e-20)}};
      return {plate:await run('plate',1.5),hall:await run('hall',3.0)}}""")
    import math
    p, h = r["plate"], r["hall"]
    assert p["early"] > 1e-4                                            # it rings on after the 30 ms burst
    drop = 20 * math.log10(p["late"] / p["early"])                      # by the decay time it is far down
    assert -70 < drop < -30, drop
    assert abs(p["corr"]) < 0.4                                         # left and right are different: wide, not mono
    assert h["end"] > 5 * p["end"]                                      # the hall is still ringing when the plate is gone


def test_mashup_reverb_send_and_bar_axis(site, page):
    """A slot's REVERB send reaches the shared reverb; its type is set at the top; the waveform stays visible."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.evaluate("localStorage.removeItem('dcStems')")
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&window.CRATE&&CRATE.MX", timeout=30000)
    page.click("#tabM")
    page.wait_for_selector("#mxall")
    page.click("#mxall")
    page.wait_for_function("Object.values(CRATE.MX.slots).some(p=>p&&p.buf)", timeout=90000)
    page.wait_for_function("CRATE.MX.on&&CRATE.MX.order.some(id=>CRATE.MX.slots[id]&&CRATE.MX.slots[id]._c)", timeout=90000)
    sid = page.evaluate("CRATE.MX.order.find(id=>CRATE.MX.slots[id]&&CRATE.MX.slots[id]._c)")   # (a slot's chain exists once it plays)
    page.evaluate("id=>CRATE.TR.set(id,'rev',50)", sid)
    page.wait_for_function(f"Math.abs(CRATE.MX.slots['{sid}']._c.rsend.gain.value-0.5)<0.02", timeout=5000)
    page.click(f'[data-mxrevon="{sid}"]')                                # off: nothing is sent, the setting is kept
    page.wait_for_function(f"CRATE.MX.slots['{sid}']._c.rsend.gain.value<0.02", timeout=5000)
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].rev") == 0.5
    page.select_option("#mxrvtype", "hall")
    page.wait_for_function("CRATE.MX.reverb.type==='hall'&&CRATE.MX.bus.rev.type==='hall'", timeout=5000)
    assert page.evaluate(f"document.querySelector('[data-mxwave=\"{sid}\"] canvas').height") > 40
    page.evaluate("CRATE.mxPlay(false)")
    page.evaluate("localStorage.removeItem('dcStems')")
    page.click("#tabS")


def test_mashup_one_shot_slot(site, page):
    """✦ one-shot: a library sample in a slot, placed on steps of a cycle of bars, played on the mixer's clock."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.evaluate("localStorage.removeItem('dcStems')")
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&!!(window.CRATE&&CRATE.MX&&CRATE.mxAddOneShot)", timeout=30000)
    i = page.evaluate("S.findIndex(s=>s[F.kind]==='oneshot'&&s[F.dur]<2)")
    assert i >= 0
    page.evaluate(f"CRATE.mxAddOneShot({i})")                       # as ✦ Mashup in the sample panel does
    page.wait_for_function("CRATE.MX.order.some(id=>CRATE.MX.roles[id]==='oneshot'&&CRATE.MX.slots[id]&&CRATE.MX.slots[id].buf)", timeout=120000)
    sid = page.evaluate("CRATE.MX.order.find(id=>CRATE.MX.roles[id]==='oneshot')")
    page.click("#tabM")
    page.wait_for_selector(f'[data-mxstep="{sid}:0"]')
    assert page.locator(f'[data-mxrow="{sid}"] .mxst').count() == 16 and page.evaluate(f"CRATE.MX.slots['{sid}'].steps") == [0]
    page.evaluate("""id=>{
      const create = AC.createBufferSource.bind(AC);
      AC.createBufferSource = () => {
        const source = create(), start = source.start.bind(source);
        source.start = (...args) => { window.auditionRate = source.playbackRate.value; return start(...args); };
        return source;
      };
      CRATE.TR.set(id, 'st', 5);
      CRATE.TR.set(id, 'ct', 25);
    }""", sid)
    page.click(f'[data-mxaud="{sid}"]')
    assert page.evaluate("auditionRate") == pytest.approx(2 ** (5.25 / 12))
    page.click(f'[data-mxstep="{sid}:10"]')                          # a hit in the middle of the bar
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].steps") == [0, 10]
    page.select_option(f'[data-mxlen="{sid}"]', "2")                 # a two-bar cycle: 32 steps, the hits stay
    assert page.locator(f'[data-mxrow="{sid}"] .mxst').count() == 32
    page.click(f'[data-mxstep="{sid}:30"]')                          # ... and one at the end of bar 2
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].steps") == [0, 10, 30]
    # trim: drag across the small waveform to choose the piece that plays; double-click for the whole sample
    tb = page.locator(f'canvas[data-mxtrim="{sid}"]').bounding_box()
    page.mouse.move(tb["x"] + tb["width"] * 0.25, tb["y"] + 10)
    page.mouse.down()
    page.mouse.move(tb["x"] + tb["width"] * 0.75, tb["y"] + 10, steps=5)
    page.mouse.up()
    tr = page.evaluate(f"CRATE.MX.slots['{sid}'].trim")
    assert abs(tr[0] - 0.25) < 0.03 and abs(tr[1] - 0.75) < 0.03
    page.dblclick(f'canvas[data-mxtrim="{sid}"]')
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].trim") is None
    # ⧉ duplicate: the same sample, placement and settings in a new slot right below
    _more(page, sid)
    page.click(f'[data-mxdup="{sid}"]')
    dup = page.evaluate(f"CRATE.MX.order[CRATE.MX.order.indexOf('{sid}')+1]")
    assert page.evaluate(f"CRATE.MX.roles['{dup}']") == "oneshot" and page.evaluate(f"CRATE.MX.slots['{dup}'].steps") == [0, 10, 30]
    assert page.evaluate(f"CRATE.MX.slots['{dup}'].sample===CRATE.MX.slots['{sid}'].sample&&!!CRATE.MX.slots['{dup}'].buf")
    page.click(f'[data-mxstep="{dup}:4"]')                           # the copy is its own: changing it leaves the original
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].steps") == [0, 10, 30]
    _more(page, dup)
    page.click(f'[data-mxdel="{dup}"]')
    _more(page, dup)
    page.click(f'[data-mxrm="{dup}"]')
    page.wait_for_function(f"!CRATE.MX.order.includes('{dup}')", timeout=10000)
    page.click("#mxplay")                                            # it plays on the bar clock, through its own chain
    page.wait_for_function(f"CRATE.MX.on&&CRATE.MX.slots['{sid}']._c&&CRATE.MX.slots['{sid}']._next>0", timeout=20000)
    page.click(f'[data-mxstep="{sid}:10"]')
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].steps") == [0, 30]
    page.click("#mxplay")
    # 🎲 on a one-shot slot asks the server for one (no sample named): it answers, even when the library has none to offer
    r = json.load(urllib.request.urlopen(urllib.request.Request(site["base"] + "api/stems/oneshot", data=json.dumps(
        {"state": {"bpm": 100, "key": None, "slots": {}}, "n": 1, "path": None}).encode(), method="POST")))
    assert "part" in r and "error" not in r
    page.reload()                                                    # it comes back with its placement
    page.wait_for_function(f"window.CRATE&&CRATE.MX&&CRATE.MX.slots['{sid}']&&CRATE.MX.slots['{sid}'].n===2", timeout=30000)
    assert page.evaluate(f"CRATE.MX.slots['{sid}'].steps") == [0, 30]
    page.evaluate("localStorage.removeItem('dcStems')")
    page.click("#tabS")


def test_saving_under_a_new_name_asks_about_another_ones_snapshots(site, page):
    """A strip that came with one saved combination doesn't silently become part of another."""
    _mixer(site, page)
    page.click("#sncap")
    page.wait_for_selector("#snrep")
    page.fill("#mxname", "first one")
    page.click("#mxsave")
    page.wait_for_function("!document.querySelector('#mxsave').classList.contains('dirty')", timeout=10000)
    page.fill("#mxname", "second one")
    page.click("#mxsave")
    page.wait_for_selector(".mxask")                                 # asked, not saved yet
    page.click("#mxdropsn")
    page.wait_for_function("CRATE.MX.name==='second one'&&CRATE.MX.snaps.length===0", timeout=10000)
    page.wait_for_function("!document.querySelector('#mxsave').classList.contains('dirty')", timeout=10000)   # saved
    saved = json.load(urllib.request.urlopen(urllib.request.Request(site["base"] + "api/stems/saved", data=b"{}", method="POST")))["mixes"]
    by = {m["name"]: m["state"] for m in saved}
    assert len(by["first one"]["snaps"]) == 1 and len(by["second one"].get("snaps") or []) == 0
    page.evaluate("CRATE.mxPlay(false)")
    page.evaluate("localStorage.removeItem('dcStems')")
    page.click("#tabS")


TRACKS_MATHS = [
    ("TR.resizeEnd({bar0:104,n:8,k:1},114,177)", {"bar0": 104, "n": 10}),
    ("TR.resizeEnd({bar0:104,n:8,k:1},100,177)", {"bar0": 104, "n": 1}),
    ("TR.resizeEnd({bar0:104,n:8,k:1},130,177)", {"bar0": 104, "n": 16}),
    ("TR.resizeEnd({bar0:170,n:4,k:1},190,177)", {"bar0": 170, "n": 7}),      # stops at the song's last bar line
    ("TR.resizeEnd({bar0:10,n:4,k:2},21,100)", {"bar0": 10, "n": 6}),         # half-time: every second line
    ("TR.resizeEnd({bar0:10,n:4,k:0.5},13,100)", {"bar0": 10, "n": 6}),       # double-time: two mixer bars a line
    ("TR.resizeEnd({bar0:10,n:4,k:0.5},30,100)", {"bar0": 10, "n": 16}),
    ("TR.resizeStart({bar0:104,n:8,k:1},108,177)", {"bar0": 108, "n": 4}),
    ("TR.resizeStart({bar0:104,n:8,k:1},120,177)", {"bar0": 111, "n": 1}),
    ("TR.resizeStart({bar0:4,n:8,k:1},-3,177)", {"bar0": 0, "n": 12}),
    ("TR.moveTo({bar0:104,n:8,k:1},175,177)", {"bar0": 169, "n": 8}),
    ("TR.moveTo({bar0:104,n:8,k:1},-5,177)", {"bar0": 0, "n": 8}),
    ("TR.nudge({bar0:104,n:8,k:1},1,177)", {"bar0": 105, "n": 8}),
    ("TR.grow({bar0:104,n:8,k:1},-1,177)", {"bar0": 104, "n": 7}),
    ("TR.grow({bar0:104,n:1,k:1},-1,177)", {"bar0": 104, "n": 1}),
    ("[3.9,-1,99].map(t=>TR.floorBar([0,2,4,6,8],t))", [1, 0, 3]),
    ("[2.9,3.1,99,-1].map(t=>TR.nearLine([0,2,4,6,8],t))", [1, 2, 4, 0]),
    ("[[100,160,158],[100,160,104],[100,160,130],[100,160,50],[100,106,104],[100,106,101]].map(a=>TR.hit(...a))",
     ["end", "start", "move", "out", "end", "start"]),
    ("TR.zoom(0,300,0.5,0.5,300,4)", [75, 225]), ("TR.zoom(0,300,0.5,4,300,4)", [0, 300]), ("TR.zoom(100,104,0,0.1,300,4)", [100, 104]),
    ("TR.pan(100,200,150,300)", [200, 300]), ("TR.pan(100,200,-500,300)", [0, 100]),
    ("TR.loopView(100,116,2,300)", [84, 132]), ("TR.loopView(2,6,2,300)", [0, 10]),
    ("[{bar0:104,n:8,k:1},{bar0:43,n:1,k:1},{bar0:10,n:4,k:2}].map(TR.barsText)",
     ["bars 105–112 · 8 bars", "bar 44 · 1 bar", "bars 11–18 · 4 bars"]),
    ("[TR.semis(4,{ct:25}),TR.semis(0,{}),TR.srcBars(4,2),TR.srcBars(1,0.5),TR.MAXN]", [4.25, 0, 8, 1, 16]),
]

def test_tracks_maths(page):
    for js, want in TRACKS_MATHS:
        assert page.evaluate(f"(()=>{{const TR=CRATE.TR;return {js}}})()") == want, js


def _calls(page):
    """Record every api call the page makes from now on, as [path, body]."""
    page.evaluate("(()=>{if(window.__calls)return;window.__calls=[];const a=CRATE.api;CRATE.api=(p,b)=>{__calls.push([p,b]);return a(p,b)}})()")

def test_pitch_is_two_numbers_you_drag(site, page):
    _mixer(site, page)
    for slot in ("drums", "bass", "vocals", "other"):
        assert page.locator(f'[data-v="{slot}:st"]').count() == 1 and page.locator(f'[data-v="{slot}:ct"]').count() == 1
    _calls(page)
    box = page.locator('[data-v="bass:ct"]').bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x, y - 20); page.mouse.move(x, y - 40)
    assert page.evaluate("__calls.filter(c=>c[0]==='api/stems/render').length") == 0     # nothing is asked while dragging
    page.mouse.up()
    page.wait_for_function("CRATE.MX.slots.bass.ct===25&&CRATE.MX.slots.bass.buf&&!CRATE.MX.slots.bass._loading")
    key = page.evaluate("CRATE.MX.info.slots.bass.semis")
    assert page.evaluate("__calls.filter(c=>c[0]==='api/stems/render'&&c[1].stem==='bass').pop()[1].semis") == key + 0.25
    page.evaluate("CRATE.TR.set('drums','st',2)")
    page.wait_for_function("__calls.some(c=>c[0]==='api/stems/render'&&c[1].stem==='drums'&&c[1].semis===2)")
    page.focus('[data-v="bass:st"]'); page.keyboard.press("ArrowUp")
    page.wait_for_function("CRATE.MX.slots.bass.off===1")
    page.dblclick('[data-v="bass:ct"]')
    page.wait_for_function("(CRATE.MX.slots.bass.ct||0)===0")
    assert "+1 st" in page.inner_text('[data-v="bass:st"]')
    page.evaluate("CRATE.TR.set('vocals','ct',-30)")
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).slots.vocals.ct") == -30
    # the strip: the same part at other cents is a change, not the same audio
    assert page.evaluate("(()=>{const a=CRATE.MX.slots.vocals;return BLEND.sameAudio(a,{...a,ct:0})})()") is False


def _box(page, sel):
    return page.evaluate("s=>{const r=document.querySelector(s).getBoundingClientRect();return {l:r.left,t:r.top,r:r.right,b:r.bottom}}", sel)

def _one_shot(page):
    """Put a short library one-shot in a new slot, as ✦ Mashup in the sample panel does. -> its slot id"""
    i = page.evaluate("S.findIndex(s=>s[F.kind]==='oneshot'&&s[F.dur]<2)")
    assert i >= 0
    page.evaluate(f"CRATE.mxAddOneShot({i})")
    page.wait_for_function("CRATE.MX.order.some(id=>CRATE.MX.roles[id]==='oneshot'&&CRATE.MX.slots[id]&&CRATE.MX.slots[id].buf)", timeout=120000)
    page.click("#tabM")
    return page.evaluate("CRATE.MX.order.find(id=>CRATE.MX.roles[id]==='oneshot')")

def test_effects_are_numbers_under_every_track(site, page):
    _mixer(site, page)
    devs = lambda s: page.evaluate(f"[...document.querySelectorAll('[data-mxrow=\"{s}\"] .trfx .trdev')].map(d=>d.dataset.dev)")
    for s in ("drums", "vocals", "other"):
        assert devs(s) == ["eq", "dly", "rev", "harm"], s
    assert devs("bass") == ["eq", "dly", "rev", "harm", "duck"]
    page.evaluate("CRATE.TR.set('bass','fb',60)")
    page.wait_for_function("Math.abs(CRATE.MX.slots.bass._c.fb.gain.value-0.6)<0.02")
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).slots.bass.fb") == 0.6
    assert page.evaluate("CRATE.MX.slots.drums._c.fb.gain.value") == pytest.approx(0.35, abs=0.01)   # untouched: as it was fixed
    box = page.locator('[data-v="vocals:g0"]').bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x, y - 40)
    page.wait_for_function("CRATE.MX.slots.vocals._c.lo.gain.value>2")                 # heard while dragging
    page.mouse.up()
    assert page.evaluate("CRATE.MX.slots.vocals.eq[0]") == 6                            # 40 px of 160 for 24 dB
    page.click('[data-mxrow="vocals"] [data-mxeqon]')
    page.wait_for_function("Math.abs(CRATE.MX.slots.vocals._c.lo.gain.value)<0.1")
    assert page.evaluate("CRATE.MX.slots.vocals.eq[0]") == 6 and page.locator('[data-mxrow="vocals"] .trdev[data-dev="eq"].mxoff').count() == 1
    page.evaluate("CRATE.TR.set('bass','dly',50)")
    assert page.evaluate("CRATE.MX.slots.bass.dly") == pytest.approx(0.4)
    assert page.locator('[data-mxrow] input[data-mxeq], [data-mxrow] input[data-mxdly], [data-mxrow] select[data-mxdt], [data-mxrow] input[data-mxrev], [data-mxrow] input[data-mxduck]').count() == 0
    page.set_viewport_size({"width": 1280, "height": 800})
    for s in ("drums", "bass", "vocals", "other"):                  # every row's effects are inside it, without clicking them
        r = _box(page, f'[data-mxrow="{s}"]')
        assert page.evaluate(f"[...document.querySelectorAll('[data-mxrow=\"{s}\"] .trfx .trdev')].every(d=>d.getBoundingClientRect().right<={r['r']}+1)")
    os = _one_shot(page)
    assert devs(os) == ["eq", "dly", "rev", "trim"] and page.locator(f'[data-mxrow="{os}"] .trfx canvas[data-mxtrim="{os}"]').count() == 1


EMOJI = "[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]"

def _more(page, slot):
    """Open a track's ⋯ menu (the moved controls are in it)."""
    if not page.locator(f'[data-mxrow="{slot}"].open').count():
        page.click(f'[data-trmore="{slot}"]')

def test_track_header_holds_every_control(site, page):
    _mixer(site, page)
    page.set_viewport_size({"width": 1280, "height": 800})
    for slot, word in (("drums", "Drums"), ("bass", "Bass"), ("vocals", "Vocals"), ("other", "Other")):
        row = f'[data-mxrow="{slot}"]'
        assert page.inner_text(f"{row} .trname").strip() == word
        h = _box(page, f"{row} .trh")
        for sel in (".trname", ".mxsrc", ".trbars", f'[data-v="{slot}:st"]', f'[data-v="{slot}:ct"]', "[data-mxroll]", f'[data-mxhist="{slot}:-1"]', f'[data-mxhist="{slot}:1"]', "[data-mxsolo]",
                    "[data-mxmute]", "input[data-mxdb]", "[data-trmore]"):
            b = _box(page, f"{row} .trh {sel}")
            assert b["l"] >= h["l"] - 1 and b["r"] <= h["r"] + 1 and b["r"] <= 1280 and b["r"] > b["l"], (slot, sel, b)
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert page.evaluate(f"[...document.querySelectorAll('.trk')].every(e=>!/{EMOJI}/u.test(e.textContent))")
    assert page.locator('[data-mxrow="bass"] .trmenu').is_hidden()
    _more(page, "bass")
    menu = page.locator('[data-mxrow="bass"] .trmenu')
    assert menu.locator('[data-mxfind], [data-mxalt], [data-mxlock], [data-mxdup], '
                        '[data-mxdel], [data-mxrole], [data-mxrm]').count() == 7
    page.keyboard.press("Escape")
    assert page.locator('[data-mxrow="bass"].open').count() == 0
    _more(page, "bass"); page.click('[data-mxrow="bass"] [data-mxdup]')
    page.wait_for_function("CRATE.MX.order.length===5")
    # a one-shot: the same header, its own part under it
    os = _one_shot(page)
    assert page.inner_text(f'[data-mxrow="{os}"] .trname').strip() == "One-shot"
    assert page.locator(f'[data-mxrow="{os}"] [data-mxstep]').count() == 16 and page.locator(f'[data-mxrow="{os}"] [data-mxaud]').count() == 1


PIXEL = """([slot,x,y])=>{const c=document.querySelector(`[data-mxwave="${slot}"] canvas`),k=c.width/c.clientWidth,
  d=c.getContext('2d').getImageData(Math.round(x*k),Math.round(y*k),1,1).data;return [d[0],d[1],d[2]]}"""

def test_track_shows_the_whole_song(site, page):
    _mixer(site, page)
    page.wait_for_function("['drums','bass','vocals','other'].every(s=>CRATE.TR.has(s))", timeout=20000)
    g = page.evaluate("""(()=>{const p=CRATE.MX.slots.other,s=CRATE.TR.song(p.track,'other'),c=document.querySelector('[data-mxwave="other"] canvas');
      return {w:c.clientWidth,h:c.clientHeight,dur:s.dur,a:s.bars[p.bar0],b:s.bars[p.bar0+CRATE.TR.srcBars(p.n,p.k||1)],n:s.pk.length,rate:s.rate}})()""")
    assert g["rate"] == 400 and abs(g["n"] - g["dur"] * 400) <= 1 and g["b"] > g["a"]
    xa, xb = g["a"] / g["dur"] * g["w"], g["b"] / g["dur"] * g["w"]
    col = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--KEYS').trim()")
    rgb = [int(col[i:i + 2], 16) for i in (1, 3, 5)]                                    # ("other" sounds all the way through the test song)
    assert page.evaluate(PIXEL, ["other", (xa + xb) / 2, 1]) == rgb                     # the bar joining the loop's edges
    outside = xb + 20 if xb + 20 < g["w"] else xa - 20
    assert page.evaluate(PIXEL, ["other", outside, 1]) != rgb
    assert page.evaluate(PIXEL, ["other", (xa + xb) / 2, g["h"] / 2]) == rgb            # lit inside the loop
    assert page.evaluate(PIXEL, ["other", outside, g["h"] / 2]) == [0x39, 0x40, 0x4b]   # gray outside it
    left = page.evaluate("parseFloat(document.querySelector('[data-mxwave=\"other\"] i').style.left)/100")
    assert xa / g["w"] - 0.01 <= left <= xb / g["w"] + 0.01                             # the play line is inside the loop
    assert page.inner_text('[data-mxrow="other"] .trbars') == page.evaluate("CRATE.TR.barsText(CRATE.MX.slots.other)")

def test_track_plays_without_its_picture(site, page):
    """The picture can't be had: the track still shows its loop and plays."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout
    page.evaluate("(()=>{const a=CRATE.api;CRATE.api=(p,b)=>p==='api/stems/peaks'?Promise.reject(new Error('no picture')):a(p,b)})()")
    page.click("#tabM"); page.wait_for_selector("#mxall"); page.click("#mxall")
    page.wait_for_function("CRATE.MX.on&&['drums','bass','vocals','other'].every(s=>CRATE.MX.slots[s]&&CRATE.MX.slots[s].buf)", timeout=90000)
    assert page.evaluate("CRATE.TR.has('drums')") is False
    page.wait_for_function("(()=>{const b=document.querySelector('[data-mxwave=\"drums\"]');return b.querySelector('canvas').width>50&&getComputedStyle(b.querySelector('i')).display==='block'})()")


def _edge(page, slot):
    """Where a stem track's loop is on the page: its two edges and the row's middle height, and px per bar."""
    return page.evaluate("""slot=>{const p=CRATE.MX.slots[slot],s=CRATE.TR.song(p.track,CRATE.MX.roles[slot]),r=document.querySelector(`[data-mxwave="${slot}"]`).getBoundingClientRect(),
      [v0,v1]=p._v,X=t=>r.left+(t-v0)/(v1-v0)*r.width,e=p.bar0+CRATE.TR.srcBars(p.n,p.k||1);
      return {xa:X(s.bars[p.bar0]),xb:X(s.bars[e]),y:r.top+r.height/2,bar:X(s.bars[1])-X(s.bars[0]),left:r.left,bar0:p.bar0,n:p.n,nb:s.bars.length-1}}""", slot)

def _drag(page, x0, x1, y):
    page.mouse.move(x0, y); page.mouse.down()
    for k in range(1, 6):
        page.mouse.move(x0 + (x1 - x0) * k / 5, y)
    page.mouse.up()

def test_loop_drags_and_snaps(site, page):
    _mixer(site, page)
    page.wait_for_function("['drums','bass','vocals','other'].every(s=>CRATE.TR.has(s))", timeout=20000)
    page.evaluate("CRATE.TR.setLoop('drums',4,4)")
    page.wait_for_function("CRATE.MX.slots.drums.bar0===4&&CRATE.MX.slots.drums.n===4&&CRATE.MX.slots.drums.buf&&!CRATE.MX.slots.drums._loading")
    _calls(page)
    e = _edge(page, "drums")
    page.mouse.move(e["xb"], e["y"]); page.mouse.down(); page.mouse.move(e["xb"] + e["bar"], e["y"]); page.mouse.move(e["xb"] + 2.2 * e["bar"], e["y"])
    assert page.evaluate("__calls.filter(c=>c[0]==='api/stems/render').length") == 0 and "6 bars" in page.inner_text('[data-mxwave="drums"] .trtip')
    page.mouse.up()
    page.wait_for_function("CRATE.MX.slots.drums.n===6&&CRATE.MX.slots.drums.bar0===4&&!CRATE.MX.slots.drums._loading")
    assert abs(page.evaluate("CRATE.MX.slots.drums.buf.duration") - 6 * 2.4) < 0.01          # six bars at 100 bpm
    e = _edge(page, "drums"); _drag(page, e["xa"], e["xa"] + 2 * e["bar"], e["y"])              # the start: the end stays
    page.wait_for_function("CRATE.MX.slots.drums.bar0===6&&CRATE.MX.slots.drums.n===4")
    e = _edge(page, "drums"); _drag(page, e["xa"] + 1.5 * e["bar"], e["xa"] - 1.5 * e["bar"], e["y"])   # the whole loop, three bars back
    page.wait_for_function("CRATE.MX.slots.drums.bar0===3&&CRATE.MX.slots.drums.n===4")
    e = _edge(page, "drums"); _drag(page, e["xb"], e["xb"] + 40 * e["bar"], e["y"])             # past the song's end: it stops there
    page.wait_for_function("CRATE.MX.slots.drums.bar0===3&&CRATE.MX.slots.drums.n===13")
    assert page.evaluate("__calls.filter(c=>c[0]==='api/stems/render').every(c=>c[1].bar0+c[1].n<=16)")
    e = _edge(page, "drums"); page.mouse.click(e["left"] + 0.4 * e["bar"], e["y"])              # the gray: the loop goes there
    page.wait_for_function("CRATE.MX.slots.drums.bar0===0&&CRATE.MX.slots.drums.n===13")
    page.evaluate("CRATE.TR.setLoop('bass',2,2)"); page.wait_for_function("CRATE.MX.slots.bass.bar0===2&&!CRATE.MX.slots.bass._loading")
    page.focus('[data-mxwave="bass"]'); page.keyboard.press("ArrowRight"); page.keyboard.press("Shift+ArrowRight")
    page.wait_for_function("CRATE.MX.slots.bass.bar0===3&&CRATE.MX.slots.bass.n===3")
    assert page.locator("[data-mxpos]").count() == 0 and page.locator('select[data-mxlen="drums"]').count() == 0
    # Keep the first render's reply until the next edit is already playing.
    page.evaluate("""() => {
      const api = CRATE.api;
      CRATE.api = (path, b) => {
        const reply = api(path, b);
        if (path === 'api/stems/render' && b.stem === 'other' && b.bar0 === 1 && b.n === 2) {
          return reply.then(r => new Promise(resolve => { window.releaseOldLoop = () => resolve(r); }));
        }
        return reply;
      };
      window.oldLoop = CRATE.TR.setLoop('other', 1, 2);
    }""")
    page.wait_for_function("typeof releaseOldLoop==='function'")
    page.wait_for_selector('[data-mxwave="other"].busy')
    page.evaluate("CRATE.TR.setLoop('other',5,4)")
    page.wait_for_function("CRATE.MX.slots.other.bar0===5&&CRATE.MX.slots.other.n===4&&!CRATE.MX.slots.other._loading")
    page.evaluate("() => { releaseOldLoop(); return oldLoop; }")
    assert page.locator('[data-mxwave="other"].busy').count() == 0
    assert abs(page.evaluate("CRATE.MX.slots.other.buf.duration") - 4 * 2.4) < 0.01


def test_a_half_time_loop_snaps_to_every_second_bar(site, page):
    _mixer(site, page, bpm=50)                                    # the songs are at 92 to 110: two of their bars to one
    page.wait_for_function("CRATE.TR.has('drums')&&CRATE.MX.slots.drums.k===2", timeout=20000)
    page.evaluate("CRATE.TR.setLoop('drums',2,2)"); page.wait_for_function("CRATE.MX.slots.drums.bar0===2&&!CRATE.MX.slots.drums._loading")
    e = _edge(page, "drums"); _drag(page, e["xb"], e["xb"] + 0.8 * e["bar"], e["y"])
    page.wait_for_timeout(300); assert page.evaluate("CRATE.MX.slots.drums.n") == 2          # one of the song's bars: not a step
    e = _edge(page, "drums"); _drag(page, e["xb"], e["xb"] + 2 * e["bar"], e["y"])
    page.wait_for_function("CRATE.MX.slots.drums.n===3")


def test_tracks_fit_the_window(site, page):
    _mixer(site, page)
    page.select_option("#mxaddrole", "other"); page.click("#mxadd")
    page.wait_for_function("CRATE.MX.order.length===5&&CRATE.MX.order.every(id=>CRATE.MX.slots[id]&&CRATE.MX.slots[id].buf)", timeout=60000)
    page.click("#sncap"); page.wait_for_function("CRATE.MX.snaps.length===1")
    for w, h in ((1512, 857), (1280, 800)):
        page.set_viewport_size({"width": w, "height": h}); page.wait_for_timeout(200)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('.mx,.mx *')].every(e=>e.getBoundingClientRect().right<=innerWidth+1)"), w
        assert page.evaluate("[...document.querySelectorAll('.trwave')].map(e=>Math.round(e.getBoundingClientRect().height))") == [58] * 5, w
        tk = page.evaluate("[...document.querySelectorAll('.trk')].map(e=>Math.round(e.getBoundingClientRect().height))")
        assert all(x <= 122 for x in tk), (w, tk)                     # no taller than a slot is on main
    page.set_viewport_size({"width": 1512, "height": 857}); page.wait_for_timeout(200)
    last = f'[data-mxrow="{page.evaluate("CRATE.MX.order[4]")}"] .trfx'
    for sel in (".mxtop", "#snbar", last):                         # the top bar, the strip and all five tracks, without scrolling
        b = _box(page, sel); assert b["t"] >= 0 and b["b"] <= 858, (sel, b)

def test_zoom_and_the_view_switch(site, page):
    _mixer(site, page)
    page.wait_for_function("['drums','bass','vocals','other'].every(s=>CRATE.TR.has(s))", timeout=20000)
    bar = page.evaluate("(()=>{const p=CRATE.MX.slots.drums,g=CRATE.TR.song(p.track,'drums');return g.bars[1]-g.bars[0]})()")
    r = page.evaluate("(()=>{const b=document.querySelector('[data-mxwave=\"drums\"]').getBoundingClientRect();return [b.left,b.top,b.width,b.height]})()")
    x, y = r[0] + r[2] * 0.25, r[1] + r[3] / 2
    t0 = page.evaluate("(()=>{const v=CRATE.MX.slots.drums._v;return v[0]+0.25*(v[1]-v[0])})()")
    page.evaluate("([x,y])=>document.querySelector('[data-mxwave=\"drums\"] canvas').dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,ctrlKey:true,deltaY:-120,clientX:x,clientY:y}))", [x, y])
    v = page.evaluate("CRATE.MX.slots.drums._v")
    assert v[1] - v[0] < 16 * bar * 0.5 and abs(v[0] + 0.25 * (v[1] - v[0]) - t0) < 0.2          # tighter, and the same moment under the pointer
    for _ in range(20):
        page.evaluate("([x,y])=>document.querySelector('[data-mxwave=\"drums\"] canvas').dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,ctrlKey:true,deltaY:-300,clientX:x,clientY:y}))", [x, y])
    v = page.evaluate("CRATE.MX.slots.drums._v"); assert abs((v[1] - v[0]) - 2 * bar) < 0.01    # never tighter than two bars
    page.click('[data-trview="loop"]'); page.wait_for_timeout(400)
    assert page.evaluate("""['drums','bass','vocals','other'].every(s=>{const p=CRATE.MX.slots[s],g=CRATE.TR.song(p.track,s),e=p.bar0+CRATE.TR.srcBars(p.n,p.k||1),
      w=CRATE.TR.loopView(g.bars[p.bar0],g.bars[e],g.bars[1]-g.bars[0],g.dur);return Math.abs(p._v[0]-w[0])<0.01&&Math.abs(p._v[1]-w[1])<0.01})""")
    page.click('[data-trview="song"]'); page.wait_for_timeout(400)
    assert page.evaluate("CRATE.MX.slots.bass._v[0]===0&&Math.abs(CRATE.MX.slots.bass._v[1]-CRATE.TR.song(CRATE.MX.slots.bass.track,'bass').dur)<0.01")
    page.click("#tabS"); page.click("#tabM"); page.wait_for_selector(".trfx")                 # away and back: still there, nothing stuck
    assert page.locator(".trfx").count() == 4


HARM = r"""async () => {
  const BL = window.BLEND, SR = 44100, N = 2 * SR, out = {};
  const sub = c => { const b = c.createBuffer(1, N, SR), d = b.getChannelData(0); for (let i = 0; i < N; i++) d[i] = 0.3 * Math.sin(2 * Math.PI * 55 * i / SR); return b; };
  const rms = d => { let s = 0; for (let i = SR / 2; i < N; i++) s += d[i] * d[i]; return Math.sqrt(s / (N - SR / 2)); };
  const probe = new OfflineAudioContext(1, N, SR), hc = await BL.harmMeasure(sub(probe));
  const run = async (p, withComp) => { const c = new OfflineAudioContext(1, N, SR), ch = BL.mkChain(c, c.destination, BL.duckBus(c)), s = c.createBufferSource();
    const m = BL.mixOf(p, 'bass', { on: true, fx: true, bar: 2.4, DT: { '1/8': 1 / 8 }, hc: withComp ? hc : null, duck: { on: false } });
    BL.applyChain(ch, m, 0); s.buffer = sub(c); s.connect(ch.in); s.start(0); return rms((await c.startRendering()).getChannelData(0)); };
  const base = await run({ db: 0, harm: 0 }, true);
  out.level = [];
  for (const a of [0.25, 0.5, 1]) out.level.push(20 * Math.log10((await run({ db: 0, harm: a }, true)) / base));
  out.raw = 20 * Math.log10((await run({ db: 0, harm: 1 }, false)) / base);        // the switch as it was: louder
  out.old = 20 * Math.log10((await run({ db: 0, harm: true, hup: true }, true)) / (await run({ db: 0, harm: 1 }, false)));
  out.amt = [BL.harmAmt({ harm: true }), BL.harmAmt({ harm: false }), BL.harmAmt({ harm: null }), BL.harmAmt({ harm: 0.4 })];
  return out; }"""

def test_harmonics_amount_keeps_the_level(page):
    r = page.evaluate(HARM)
    assert all(abs(x) < 0.3 for x in r["level"]), r          # the level stays where it was at 0 (the spec allows a decibel)
    assert r["raw"] > 0.8 and abs(r["old"]) < 0.05, r        # the old switch was louder; a part from before plays as it did
    assert r["amt"] == [1, 0, 0, 0.4]

@pytest.mark.parametrize("bass_harm", [True, None])
def test_state_saved_before_tracks_still_opens(site, page, bass_harm):
    _mixer(site, page)
    page.select_option("#mxkey", "C")
    _roll(page, "bass", 901)
    assert page.evaluate("CRATE.MX.slots.bass.sub") >= 0.85
    page.evaluate("""bassHarm=>{CRATE.mxPlay(false);const s=JSON.parse(localStorage.getItem('dcStems'));delete s.v;
      for(const id of Object.keys(s.slots)){const p=s.slots[id];delete p.ct;delete p.fb;p.harm=id==='bass'?bassHarm:id==='drums'?false:null;p.db=-2}
      s.snaps=[{order:s.order,roles:s.roles,slots:JSON.parse(JSON.stringify(s.slots)),duck:{}}];localStorage.setItem('dcStems',JSON.stringify(s))}""", bass_harm)
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX&&CRATE.MX.slots.bass", timeout=30000)
    if bass_harm:
        assert page.evaluate("CRATE.MX.snaps[0].slots.bass.hup===true&&!CRATE.MX.slots.drums.hup")
    else:
        assert page.evaluate("CRATE.MX.snaps[0].slots.bass.harm") is None
    page.click("#mxplay")
    page.wait_for_function("CRATE.MX.slots.bass._hc&&!CRATE.MX.slots.bass.hup", timeout=60000)
    want = page.evaluate("-2-20*Math.log10(BLEND.harmComp({harm:1},CRATE.MX.slots.bass._hc))")
    assert page.evaluate("CRATE.MX.slots.bass.db") == pytest.approx(min(6, want), abs=0.0001)
    assert page.evaluate("CRATE.MX.slots.bass.harm") == 1 and page.evaluate("CRATE.MX.slots.drums.db") == -2
    c = page.evaluate("(()=>{const c=CRATE.MX.slots.vocals._c;return [c.lo.frequency.value,c.mid.frequency.value,c.hi.frequency.value,+c.fb.gain.value.toFixed(2)]})()")
    assert c == [200, 1000, 5000, 0.35] and page.evaluate("(CRATE.MX.slots.vocals.ct||0)") == 0
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).v") == 2
    page.evaluate("CRATE.TR.set('bass','harm',50)")
    page.wait_for_function("Math.abs(CRATE.MX.slots.bass._c.hg.gain.value-0.175)<0.01")
    assert page.locator("[data-mxharm]").count() == 0 and page.locator('[data-mxrow="bass"] .trfx [data-v="bass:harm"]').count() == 1


def test_duplicating_a_track_while_its_loop_renders(site, page):
    _mixer(site, page)
    page.wait_for_function("CRATE.TR.has('other')")
    page.evaluate("""() => {
      const api = CRATE.api;
      let release;
      const held = new Promise(resolve => { release = resolve; });
      window.releaseDuplicateRender = release;
      CRATE.api = (path, part) => {
        const reply = api(path, part);
        return path === 'api/stems/render' && part.stem === 'other' && part.bar0 === 1 && part.n === 2
          ? reply.then(async r => { await held; return r; })
          : reply;
      };
      window.pendingDuplicateRender = CRATE.TR.setLoop('other', 1, 2);
    }""")
    page.wait_for_selector('[data-mxwave="other"].busy')
    _more(page, "other")
    page.click('[data-mxdup="other"]')
    copy = page.evaluate("""() => {
      const order = CRATE.MX.order;
      return order[order.indexOf('other') + 1];
    }""")
    assert page.evaluate("id=>CRATE.MX.slots[id].n", copy) == 2
    page.evaluate("() => { releaseDuplicateRender(); return pendingDuplicateRender; }")
    assert page.evaluate("id=>CRATE.MX.slots[id].buf.duration", copy) == pytest.approx(4.8, abs=0.01)


def test_pitch_after_snapshot_recall_keeps_the_other_parts_pitch(site, page):
    _mixer(site, page)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===1")
    original = page.evaluate("CRATE.MX.slots.drums.bar0")
    alternate = (original + 1) % 12
    page.evaluate("bar=>CRATE.TR.setLoop('drums',bar,4)", alternate)
    page.evaluate("CRATE.TR.set('drums','ct',7)")
    page.click('[data-sn="0"]')
    page.wait_for_function("bar=>CRATE.MX.slots.drums.bar0===bar&&!CRATE.MX.slots.drums._loading", arg=original)
    page.evaluate("CRATE.TR.set('drums','ct',-20)")
    assert page.evaluate("bar=>CRATE.MX.hist.drums.find(p=>p.bar0===bar).ct", alternate) == 7
