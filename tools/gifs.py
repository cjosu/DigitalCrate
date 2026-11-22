"""Record the README's GIFs from the running app (digitalcrate serve on :8765), with ffmpeg for the conversion.

    uv run --no-project --with playwright==1.55.0 python tools/gifs.py [out_dir] [only ...]

Each clip is scripted with Playwright, recorded as video, trimmed to the action, cropped to the part of the screen
that matters and turned into a palette-optimised GIF. Private names (reference-only artists and DIGITALCRATE_SCRUB)
are replaced live on every frame, and a dot shows where the mouse is.
"""
import json
import re
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from digitalcrate import config as C  # noqa: E402

URL = "http://localhost:8765/"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].isidentifier() else Path(__file__).resolve().parent.parent / "docs" / "img"
ONLY = [a for a in sys.argv[1:] if a.isidentifier()]
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1440, 900
from digitalcrate.policy import REFERENCE_ARTISTS  # noqa: E402  the built-in reference list too (Burial, Gas…)
PRIVATE = [n for n in [*REFERENCE_ARTISTS, *C._cfg.get("reference_artists", []), *C._cfg.get("reference_exact", []),
                       *os.environ.get("DIGITALCRATE_SCRUB", "").split(",")] if n.strip()]

INIT = """
(()=>{const names=__NAMES__;
 // live scrubbing: private names never reach a frame
 if(names.length){const re=new RegExp('\\\\b('+names.map(n=>n.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')).join('|')+')\\\\b','gi');
  const fix=root=>{const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode()))if(re.test(n.nodeValue)){re.lastIndex=0;n.nodeValue=n.nodeValue.replace(re,'(private)')}};
  new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(x=>x.nodeType===3?(re.test(x.nodeValue)&&(x.nodeValue=x.nodeValue.replace(re,'(private)'))):x.nodeType===1&&fix(x)))).observe(document,{subtree:true,childList:true,characterData:true});
  document.addEventListener('DOMContentLoaded',()=>fix(document.body))}
 // a visible cursor (headless recordings have none)
 document.addEventListener('DOMContentLoaded',()=>{const d=document.createElement('div');d.id='fakecur';
  d.style.cssText='position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(255,255,255,.85);border:2px solid #000;z-index:99999;pointer-events:none;transition:transform .08s';
  document.body.appendChild(d);document.addEventListener('mousemove',e=>{d.style.left=e.clientX+'px';d.style.top=e.clientY+'px'},true);
  document.addEventListener('mousedown',()=>d.style.transform='scale(.7)',true);document.addEventListener('mouseup',()=>d.style.transform='',true)});
})();
""".replace("__NAMES__", json.dumps(PRIVATE))


WRITES = re.compile(r"/api/(event|fav|trash/|sketch/(save|delete)|edit/save|pair/save|recat|bounce|quit|setup/)")


class Clip:
    def __init__(self, b, name):
        self.name, self.dir = name, tempfile.mkdtemp()
        self.ctx = b.new_context(viewport={"width": W, "height": H}, record_video_dir=self.dir,
                                 record_video_size={"width": W, "height": H})
        self.ctx.add_init_script(INIT)
        # recording must not change your library: listens, stars, ✕, deletes, saved sketches and edits are dropped
        self.ctx.route(WRITES, lambda r: r.fulfill(status=200, content_type="application/json", body="{}")
                       if r.request.method == "POST" else r.continue_())
        self.t0 = time.time()
        self.page = self.ctx.new_page()
        self.start = None

    def go(self):
        self.page.goto(URL)
        self.page.wait_for_function("typeof S!=='undefined' && document.querySelectorAll('#list .row').length>10")
        self.page.mouse.move(W / 2, H / 2)
        self.page.wait_for_timeout(600)

    def action(self):
        """Mark the moment the GIF starts (everything before is loading)."""
        self.start = time.time() - self.t0

    def click(self, sel, steps=14, dx=0, dy=0, mods=None):
        bb = self.page.locator(sel).first.bounding_box()
        x, y = bb["x"] + bb["width"] / 2 + dx, bb["y"] + bb["height"] / 2 + dy
        self.page.mouse.move(x, y, steps=steps)
        self.page.wait_for_timeout(120)
        if mods:
            for m in mods:
                self.page.keyboard.down(m)
        self.page.mouse.down(); self.page.mouse.up()
        if mods:
            for m in mods:
                self.page.keyboard.up(m)
        return x, y

    def drag(self, x0, y0, x1, y1, steps=18, alt=False):
        self.page.mouse.move(x0, y0, steps=10)
        if alt:
            self.page.keyboard.down("Alt")
        self.page.mouse.down(); self.page.mouse.move(x1, y1, steps=steps); self.page.mouse.up()
        if alt:
            self.page.keyboard.up("Alt")

    def save(self, crop=None, width=900, fps=12):
        """crop: (x, y, w, h) in page pixels, or a selector whose box (padded) is used."""
        end = time.time() - self.t0
        if isinstance(crop, str):
            bb = self.page.locator(crop).first.bounding_box()
            p = 10
            crop = (max(0, bb["x"] - p), max(0, bb["y"] - p), min(W, bb["width"] + 2 * p), min(H, bb["height"] + 2 * p))
        video = self.page.video.path()
        self.ctx.close()
        x, y, w, h = [int(v) // 2 * 2 for v in (crop or (0, 0, W, H))]
        out = OUT / f"{self.name}.gif"
        vf = (f"fps={fps},crop={w}:{h}:{x}:{y},scale={min(width, w)}:-1:flags=lanczos,split[a][b];"
              "[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{(self.start or 0):.2f}", "-t", f"{end - (self.start or 0):.2f}",
                        "-i", video, "-vf", vf, str(out)], check=True)
        print(f"saved {out.name}: {out.stat().st_size / 1e6:.1f} MB, {end - (self.start or 0):.1f} s")


def browse(b):
    c = Clip(b, "browse"); c.go(); pg = c.page
    c.action()
    c.click('#cats [data-v="Vocals"]'); pg.wait_for_timeout(900)
    c.click('#cats [data-v="Pads & Atmospheres"]'); pg.wait_for_timeout(900)
    c.click("#list .row:nth-of-type(2)", dx=-200); pg.wait_for_timeout(1400)
    pg.locator("#detail [data-gcat]").nth(3).scroll_into_view_if_needed(); pg.wait_for_timeout(300)
    c.click("#detail [data-gcat]:nth-of-type(3)"); pg.wait_for_timeout(1400)
    c.click("#tabA"); pg.wait_for_timeout(700)
    c.click("#aq"); pg.keyboard.type("brubeck", delay=90); pg.wait_for_timeout(900)
    c.click(".art .tw"); pg.wait_for_timeout(1200)
    c.click(".alb > a"); pg.wait_for_timeout(1800)
    c.save(crop=(262, 0, W - 262, H))  # without the filter sidebar, so the text stays readable


def sketch(b):
    c = Clip(b, "sketch"); c.go(); pg = c.page
    pg.wait_for_function("P_READY&&TASTE.loaded", timeout=60000)
    pg.click("#tabK"); pg.wait_for_function("D.kits[0]&&D.kits[0].yours", timeout=30000); pg.wait_for_timeout(800)
    k = pg.evaluate("D.kits.findIndex(k=>kitMembers(k).length>=5)")
    pg.locator(f"[data-kitsk='{k}']").click()
    pg.wait_for_function("SK.lanes.length&&SK.lanes.every(l=>l.state==='ok')", timeout=60000); pg.wait_for_timeout(1500)
    c.action(); pg.wait_for_timeout(2500)
    box = pg.locator("[data-skw='2']").bounding_box(); y = box["y"] + box["height"] / 2
    c.drag(box["x"] + box["width"] * 0.12, y, box["x"] + box["width"] * 0.7, y); pg.wait_for_timeout(1500)
    fb = pg.locator("[data-skv='0']").bounding_box()
    c.drag(fb["x"] + fb["width"] * 0.8, fb["y"] + fb["height"] / 2, fb["x"] + fb["width"] * 0.55, fb["y"] + fb["height"] / 2); pg.wait_for_timeout(900)
    if pg.locator("[data-skfit]").count():
        c.click("[data-skfit]"); pg.wait_for_timeout(5000)
    pg.wait_for_timeout(2500)
    c.save(crop="#sk")


def chords(b):
    c = Clip(b, "chords"); c.go(); pg = c.page
    pg.evaluate("select(BYID.get('1fe9dc'),'list')"); pg.wait_for_timeout(800)
    pg.click("#chordsopen"); pg.wait_for_selector(".chopt", timeout=60000); pg.wait_for_timeout(600)
    pg.locator("#chordbox").scroll_into_view_if_needed(); pg.wait_for_timeout(500)
    c.action()
    c.click("[data-chplay='0']"); pg.wait_for_timeout(9000)
    c.click("[data-chplay='1']"); pg.wait_for_timeout(5000)
    c.click('[data-chone="2:2"]'); pg.wait_for_timeout(1800)
    c.save(crop="#chordbox")


def pads(b):
    c = Clip(b, "pads"); c.go(); pg = c.page
    pg.evaluate("select(BYID.get('a59109'),'list')"); pg.wait_for_timeout(800)
    pg.click("#padsopen"); pg.wait_for_selector("#pads .pad", timeout=60000); pg.wait_for_timeout(500)
    pg.locator("#pads").scroll_into_view_if_needed(); pg.wait_for_timeout(400)
    c.action()
    for key in "1234qwer":
        pg.keyboard.press(key); pg.wait_for_timeout(330)
    c.click("#pdrec"); pg.wait_for_timeout(700)
    beat = 60 / 90
    for key in "1.q1.wq.1.q1.r..":  # a little rhythm; dots are rests (8th notes)
        if key != ".":
            pg.keyboard.press(key)
        pg.wait_for_timeout(int(beat / 2 * 1000))
    c.click("#pdrec"); pg.wait_for_timeout(300)
    c.click("#pdplay"); pg.wait_for_timeout(4500)
    c.save(crop="#pads")


def drums(b):
    c = Clip(b, "drums"); c.go(); pg = c.page
    pg.click("#tabA"); pg.fill("#aq", "brubeck quartet"); pg.wait_for_timeout(800)
    c.action()
    c.click(".art [data-rack]"); pg.wait_for_timeout(1500)
    for key in "1234qwerasdf":
        pg.keyboard.press(key); pg.wait_for_timeout(260)
    c.click('[data-rpage="1"]'); pg.wait_for_timeout(700)
    for key in "1qaz2wsx":
        pg.keyboard.press(key); pg.wait_for_timeout(240)
    pg.wait_for_timeout(600)
    c.save(crop="#modalBody")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    for f in (browse, sketch, chords, pads, drums):
        if not ONLY or f.__name__ in ONLY:
            f(b)
    b.close()
